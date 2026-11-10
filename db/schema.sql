-- =====================================================================
-- Company RAG Chatbot - PostgreSQL 16 + pgvector schema
-- Embedding dimension: 768 (gemini-embedding-001 supports reduced
-- output_dimensionality; 768 keeps HNSW indexing under pgvector's 2000-dim limit)
-- =====================================================================
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS citext;     -- case-insensitive emails

-- ---------- ENUMS ----------
CREATE TYPE user_role        AS ENUM ('super_admin','company_admin','employee','applicant');
CREATE TYPE account_status   AS ENUM ('active','inactive');
CREATE TYPE chatbot_state    AS ENUM ('not_started','started','paused','ended');
CREATE TYPE kb_status        AS ENUM ('empty','processing','ready','failed');
CREATE TYPE doc_status       AS ENUM ('uploaded','processing','ready','failed');
CREATE TYPE job_stage        AS ENUM ('upload','extract','clean','chunk','embed','index','done');
CREATE TYPE job_status       AS ENUM ('queued','running','succeeded','failed');
CREATE TYPE config_status    AS ENUM ('draft','active','failed','archived');
CREATE TYPE message_role     AS ENUM ('user','assistant');
CREATE TYPE question_type    AS ENUM ('rating_1_5','true_false');
CREATE TYPE report_type      AS ENUM ('incorrect_answer','missing_information','technical_issue','recommendation','other');
CREATE TYPE report_status    AS ENUM ('open','in_review','resolved');
CREATE TYPE deletion_status  AS ENUM ('pending','running','completed','failed');

-- ---------- helper: updated_at ----------
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END; $$ LANGUAGE plpgsql;

-- =====================================================================
-- 1. TENANCY & USERS
-- =====================================================================
CREATE TABLE companies (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name           VARCHAR(200) NOT NULL UNIQUE,
  access_status  account_status NOT NULL DEFAULT 'active',      -- SuperAdmin: activate / deactivate
  chatbot_state  chatbot_state  NOT NULL DEFAULT 'not_started', -- Company Admin: start / pause / end
  kb_status      kb_status      NOT NULL DEFAULT 'empty',       -- ready flag (green status)
  is_system      BOOLEAN NOT NULL DEFAULT FALSE,                 -- hidden benchmark workspace used by the model-evaluation lab
  created_by     UUID,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE users (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id     UUID REFERENCES companies(id) ON DELETE CASCADE,  -- NULL only for super_admin
  role           user_role NOT NULL,
  full_name      VARCHAR(200) NOT NULL,
  email          CITEXT NOT NULL UNIQUE,
  phone          VARCHAR(40),
  password_hash  TEXT NOT NULL,                                    -- argon2/bcrypt
  status         account_status NOT NULL DEFAULT 'active',
  last_login_at  TIMESTAMPTZ,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT user_company_rules CHECK (
    (role IN ('super_admin','applicant') AND company_id IS NULL) OR
    (role IN ('company_admin','employee') AND company_id IS NOT NULL))
);
CREATE INDEX idx_users_company ON users(company_id, role);
ALTER TABLE companies ADD CONSTRAINT fk_companies_created_by FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL;

-- =====================================================================
-- 2. GLOBAL RAG CONFIGURATION (SuperAdmin) - versioned
-- =====================================================================
CREATE TABLE api_credentials (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  provider       VARCHAR(50) NOT NULL DEFAULT 'google_ai_studio',
  label          VARCHAR(100) NOT NULL,
  encrypted_key  BYTEA NOT NULL,            -- Fernet/AES-GCM encrypted; never returned to frontend
  key_last4      CHAR(4) NOT NULL,          -- for display only
  is_active      BOOLEAN NOT NULL DEFAULT TRUE,
  created_by     UUID REFERENCES users(id) ON DELETE SET NULL,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE rag_config_versions (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  version        INTEGER GENERATED ALWAYS AS IDENTITY UNIQUE,
  status         config_status NOT NULL DEFAULT 'draft',
  -- each RAG part is separate so any one can be swapped independently
  document_cfg   JSONB NOT NULL,  -- {"allowed_types":["pdf","docx","txt","md"],"max_file_mb":20,"max_files":100}
  cleaning_cfg   JSONB NOT NULL,  -- {"strip_headers":true,"normalize_whitespace":true,"dedupe":true}
  chunking_cfg   JSONB NOT NULL,  -- {"strategy":"parent_child","parent_size":1500,"child_size":300,"overlap":50}
  embedding_cfg  JSONB NOT NULL,  -- {"provider":"google","model":"gemini-embedding-001","dimensions":768,"credential_id":"..."}
  retrieval_cfg  JSONB NOT NULL,  -- {"dense":{"enabled":true,"top_k":20},"sparse":{"enabled":true,"top_k":20},"fusion":"rrf","final_k":6,"reranker":null,"query_transform":null,"min_score":0.35}
  llm_cfg        JSONB NOT NULL,  -- {"provider":"google","model":"gemini-3.8-flash","temperature":0.2,"max_output_tokens":1024,"credential_id":"..."}
  prompt_cfg     JSONB NOT NULL,  -- {"system_prompt":"...","no_evidence_prompt":"..."}
  messages_cfg   JSONB NOT NULL,  -- {"ai_failure":"...","rate_limit":"...","processing_failure":"..."}
  chat_cfg       JSONB NOT NULL DEFAULT '{"max_exchanges":9}',
  validation_report JSONB,
  created_by     UUID REFERENCES users(id) ON DELETE SET NULL,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  activated_at   TIMESTAMPTZ
);
-- only ONE active config at a time (last working config is kept when a new one fails)
CREATE UNIQUE INDEX uq_one_active_config ON rag_config_versions ((status)) WHERE status = 'active';

-- =====================================================================
-- 3. EVALUATION (feedback) SETTINGS
-- =====================================================================
CREATE TABLE evaluation_settings (
  id             SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),    -- singleton row
  every_n_answers INTEGER NOT NULL DEFAULT 1 CHECK (every_n_answers >= 1),
  enabled        BOOLEAN NOT NULL DEFAULT TRUE,
  updated_by     UUID REFERENCES users(id) ON DELETE SET NULL,
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
INSERT INTO evaluation_settings DEFAULT VALUES;

CREATE TABLE evaluation_questions (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  text           VARCHAR(500) NOT NULL,
  type           question_type NOT NULL,
  position       INTEGER NOT NULL DEFAULT 0,
  is_active      BOOLEAN NOT NULL DEFAULT TRUE,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =====================================================================
-- 4. KNOWLEDGE BASE (tenant-scoped)
-- =====================================================================
CREATE TABLE documents (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id     UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  uploaded_by    UUID REFERENCES users(id) ON DELETE SET NULL,
  filename       VARCHAR(300) NOT NULL,
  file_type      VARCHAR(10)  NOT NULL,
  size_bytes     BIGINT NOT NULL,
  storage_path   TEXT NOT NULL,
  content_hash   CHAR(64),
  status         doc_status NOT NULL DEFAULT 'uploaded',
  error_message  TEXT,
  config_version_id UUID REFERENCES rag_config_versions(id),  -- config used to process it
  embedding_model VARCHAR(100),                               -- vectors from different models are NOT comparable
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (company_id, content_hash)
);
CREATE INDEX idx_documents_company ON documents(company_id, status);

CREATE TABLE processing_jobs (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id     UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  document_id    UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  stage          job_stage  NOT NULL DEFAULT 'upload',
  status         job_status NOT NULL DEFAULT 'queued',
  progress_pct   SMALLINT NOT NULL DEFAULT 0 CHECK (progress_pct BETWEEN 0 AND 100),
  attempts       SMALLINT NOT NULL DEFAULT 0,
  error_message  TEXT,                -- user-safe message
  error_detail   TEXT,                -- technical detail (admin/log only)
  eda_stats      JSONB,               -- EDA: char count, pages, language, empty pages, etc.
  started_at     TIMESTAMPTZ,
  finished_at    TIMESTAMPTZ,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_jobs_company ON processing_jobs(company_id, status);

-- parent chunks: large context returned to the LLM
CREATE TABLE parent_chunks (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id     UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  document_id    UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  chunk_index    INTEGER NOT NULL,
  content        TEXT NOT NULL,
  page_number    INTEGER,
  token_count    INTEGER,
  UNIQUE (document_id, chunk_index)
);
CREATE INDEX idx_parent_company ON parent_chunks(company_id, document_id);

-- child chunks: small units that are embedded + keyword indexed. parent_id is NULL for non parent-child strategies
CREATE TABLE chunks (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id     UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  document_id    UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  parent_id      UUID REFERENCES parent_chunks(id) ON DELETE CASCADE,
  chunk_index    INTEGER NOT NULL,
  content        TEXT NOT NULL,
  token_count    INTEGER,
  metadata       JSONB NOT NULL DEFAULT '{}',
  embedding      vector(768),                                      -- dense
  tsv            tsvector GENERATED ALWAYS AS (to_tsvector('simple', content) || to_tsvector('english', content)) STORED,  -- sparse, multilingual
  UNIQUE (document_id, chunk_index)
);
CREATE INDEX idx_chunks_company   ON chunks(company_id, document_id);
CREATE INDEX idx_chunks_embedding ON chunks USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);
CREATE INDEX idx_chunks_tsv       ON chunks USING gin (tsv);

-- =====================================================================
-- 5. CONVERSATIONS, MESSAGES, RETRIEVAL TRACE
-- =====================================================================
CREATE TABLE conversations (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id     UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  user_id        UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title          VARCHAR(200),
  exchange_count SMALLINT NOT NULL DEFAULT 0,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT exchange_limit CHECK (exchange_count BETWEEN 0 AND 9)   -- DB-level safety net; app reads max from config
);
CREATE INDEX idx_conv_user    ON conversations(user_id, updated_at DESC);
CREATE INDEX idx_conv_company ON conversations(company_id, created_at DESC);

CREATE TABLE messages (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id  UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  company_id       UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  user_id          UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role             message_role NOT NULL,
  exchange_no      SMALLINT NOT NULL,                 -- 1..9, same for the question and its answer
  content          TEXT NOT NULL,
  -- assistant-only fields
  has_evidence     BOOLEAN,                           -- was relevant info found?
  normalized_question TEXT,                           -- user messages: lowercased/trimmed for FAQ counting
  question_embedding vector(768),                     -- optional: group similar questions
  config_version_id UUID REFERENCES rag_config_versions(id),
  model_name       VARCHAR(100),
  prompt_tokens    INTEGER,
  completion_tokens INTEGER,
  latency_ms       INTEGER,
  error_code       VARCHAR(40),                       -- ai_failure | rate_limit | null
  language         VARCHAR(8),                        -- detected language of the question (en, rw, ...)
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (conversation_id, exchange_no, role)
);
CREATE INDEX idx_msg_conv     ON messages(conversation_id, created_at);
CREATE INDEX idx_msg_company  ON messages(company_id, role, created_at DESC);
CREATE INDEX idx_msg_faq      ON messages(company_id, normalized_question) WHERE role = 'user';

CREATE TABLE retrieval_logs (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  message_id     UUID NOT NULL REFERENCES messages(id) ON DELETE CASCADE,   -- the assistant message
  company_id     UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  chunk_id       UUID REFERENCES chunks(id) ON DELETE SET NULL,
  parent_id      UUID REFERENCES parent_chunks(id) ON DELETE SET NULL,
  rank           SMALLINT NOT NULL,
  dense_score    REAL,
  sparse_score   REAL,
  fused_score    REAL,
  used_in_prompt BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE INDEX idx_retr_msg ON retrieval_logs(message_id);

-- =====================================================================
-- 6. FEEDBACK & REPORTS
-- =====================================================================
CREATE TABLE feedback (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id     UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  user_id        UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  message_id     UUID NOT NULL REFERENCES messages(id) ON DELETE CASCADE,  -- assistant message
  question_id    UUID NOT NULL REFERENCES evaluation_questions(id) ON DELETE CASCADE,
  rating         SMALLINT CHECK (rating BETWEEN 1 AND 5),
  bool_value     BOOLEAN,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (message_id, question_id, user_id),
  CHECK ((rating IS NOT NULL) <> (bool_value IS NOT NULL))
);
CREATE INDEX idx_feedback_company ON feedback(company_id, created_at DESC);

CREATE TABLE reports (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id     UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  user_id        UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  conversation_id UUID REFERENCES conversations(id) ON DELETE SET NULL,
  message_id     UUID REFERENCES messages(id) ON DELETE SET NULL,
  type           report_type NOT NULL,
  comments       TEXT NOT NULL,
  status         report_status NOT NULL DEFAULT 'open',
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_reports_company ON reports(company_id, status, created_at DESC);

-- =====================================================================
-- 7. OPERATIONS: DELETION, AUDIT, ERRORS, USAGE
-- =====================================================================
CREATE TABLE deletion_jobs (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id     UUID NOT NULL,                       -- intentionally NO FK: must outlive the company row
  company_name   VARCHAR(200) NOT NULL,
  requested_by   UUID,
  status         deletion_status NOT NULL DEFAULT 'pending',
  steps          JSONB NOT NULL DEFAULT '{"anonymize":"pending","vectors":"pending","database":"pending","files":"pending","temp_files":"pending","logs":"pending"}',
  attempts       SMALLINT NOT NULL DEFAULT 0,
  last_error     TEXT,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at   TIMESTAMPTZ
);

CREATE TABLE audit_logs (
  id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  company_id     UUID,
  actor_id       UUID,
  action         VARCHAR(100) NOT NULL,               -- e.g. config.activate, company.deactivate (never secrets)
  target_type    VARCHAR(50),
  target_id      TEXT,
  details        JSONB,
  ip_address     INET,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_audit_company ON audit_logs(company_id, created_at DESC);

CREATE TABLE error_logs (
  id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  company_id     UUID,
  source         VARCHAR(40) NOT NULL,                -- llm | embedding | ingestion | retrieval | other
  error_code     VARCHAR(40),
  message        TEXT NOT NULL,
  detail         TEXT,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_errors_company ON error_logs(company_id, source, created_at DESC);

-- =====================================================================
-- 7b. ONBOARDING PORTAL, CMS CONTENT, LANGUAGES, EMAIL (added in v1.1)
-- =====================================================================
DO $$ BEGIN CREATE TYPE application_status AS ENUM ('pending','needs_info','approved','rejected','onboarded'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE form_field_type    AS ENUM ('text','textarea','number','select','multiselect');          EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE email_status       AS ENUM ('pending','sent','failed','skipped');                         EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- Languages the platform understands (add Swahili, French... as data, not code)
CREATE TABLE IF NOT EXISTS languages (
  code           VARCHAR(8) PRIMARY KEY,                 -- ISO 639-1: en, rw, sw, fr
  name           VARCHAR(100) NOT NULL,
  native_name    VARCHAR(100) NOT NULL,
  is_enabled     BOOLEAN NOT NULL DEFAULT TRUE,
  stopwords      TEXT[] NOT NULL DEFAULT '{}',           -- used for language detection + keyword-search noise removal
  sample_text    TEXT,                                   -- a sentence in this language (for the language self-check)
  sample_text_en TEXT,                                   -- its English equivalent
  sample_question TEXT,                                  -- a question in this language answered by sample_text_en
  position       INTEGER NOT NULL DEFAULT 0,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Marketing / landing page sections, edited by the SuperAdmin
CREATE TABLE IF NOT EXISTS site_content (
  key         VARCHAR(50) PRIMARY KEY,                   -- hero, features, how_it_works, ...
  label       VARCHAR(100) NOT NULL,
  content     JSONB NOT NULL DEFAULT '{}',               -- {title, subtitle, body, items:[{title,text,icon}]}
  position    INTEGER NOT NULL DEFAULT 0,
  is_active   BOOLEAN NOT NULL DEFAULT TRUE,
  updated_by  UUID REFERENCES users(id) ON DELETE SET NULL,
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Onboarding walkthrough pages (guidelines, privacy summary, terms) - versioned so acceptance is traceable
CREATE TABLE IF NOT EXISTS onboarding_steps (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  key                 VARCHAR(50) NOT NULL UNIQUE,
  position            INTEGER NOT NULL DEFAULT 0,
  requires_acceptance BOOLEAN NOT NULL DEFAULT FALSE,
  is_active           BOOLEAN NOT NULL DEFAULT TRUE,
  current_version_id  UUID,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS onboarding_step_versions (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  step_id        UUID NOT NULL REFERENCES onboarding_steps(id) ON DELETE CASCADE,
  version        INTEGER NOT NULL,
  title          VARCHAR(200) NOT NULL,
  body_markdown  TEXT NOT NULL,
  created_by     UUID REFERENCES users(id) ON DELETE SET NULL,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (step_id, version)
);
DO $$ BEGIN
  ALTER TABLE onboarding_steps ADD CONSTRAINT fk_step_current_version FOREIGN KEY (current_version_id) REFERENCES onboarding_step_versions(id);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- The company-request form is defined in data
CREATE TABLE IF NOT EXISTS application_form_fields (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  key         VARCHAR(60) NOT NULL UNIQUE,
  label       VARCHAR(200) NOT NULL,
  help_text   TEXT,
  type        form_field_type NOT NULL DEFAULT 'text',
  options     JSONB NOT NULL DEFAULT '[]',               -- for select / multiselect
  required    BOOLEAN NOT NULL DEFAULT FALSE,
  is_system   BOOLEAN NOT NULL DEFAULT FALSE,            -- system fields cannot be deleted (e.g. company_name)
  position    INTEGER NOT NULL DEFAULT 0,
  is_active   BOOLEAN NOT NULL DEFAULT TRUE,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS company_applications (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  applicant_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  status           application_status NOT NULL DEFAULT 'pending',
  company_name     VARCHAR(200) NOT NULL,
  answers          JSONB NOT NULL DEFAULT '{}',
  decision_comment TEXT,
  reviewed_by      UUID REFERENCES users(id) ON DELETE SET NULL,
  reviewed_at      TIMESTAMPTZ,
  company_id       UUID REFERENCES companies(id) ON DELETE SET NULL,
  resubmission_of  UUID REFERENCES company_applications(id) ON DELETE SET NULL,
  submitted_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  onboarded_at     TIMESTAMPTZ,
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_applications_status ON company_applications(status, submitted_at DESC);
CREATE INDEX IF NOT EXISTS idx_applications_applicant ON company_applications(applicant_id, submitted_at DESC);
-- one open request at a time; a new one is allowed after rejection
CREATE UNIQUE INDEX IF NOT EXISTS uq_one_open_application ON company_applications (applicant_id)
  WHERE status IN ('pending','needs_info','approved');

CREATE TABLE IF NOT EXISTS application_messages (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  application_id  UUID NOT NULL REFERENCES company_applications(id) ON DELETE CASCADE,
  sender_id       UUID REFERENCES users(id) ON DELETE SET NULL,
  sender_role     VARCHAR(20) NOT NULL,
  kind            VARCHAR(20) NOT NULL CHECK (kind IN ('submission','comment','info_request','response','approval','rejection','status')),
  body            TEXT NOT NULL,
  status_to       application_status,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_app_messages ON application_messages(application_id, created_at);

CREATE TABLE IF NOT EXISTS terms_acceptances (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id          UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  company_id       UUID REFERENCES companies(id) ON DELETE CASCADE,
  application_id   UUID REFERENCES company_applications(id) ON DELETE SET NULL,
  step_version_id  UUID NOT NULL REFERENCES onboarding_step_versions(id),
  accepted_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  ip_address       INET,
  user_agent       TEXT,
  UNIQUE (user_id, step_version_id)
);

-- Outgoing email queue (sent by the worker when SMTP is configured)
CREATE TABLE IF NOT EXISTS email_outbox (
  id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  to_email        CITEXT NOT NULL,
  subject         VARCHAR(300) NOT NULL,
  body            TEXT NOT NULL,
  status          email_status NOT NULL DEFAULT 'pending',
  attempts        SMALLINT NOT NULL DEFAULT 0,
  last_error      TEXT,
  application_id  UUID REFERENCES company_applications(id) ON DELETE SET NULL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  sent_at         TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_email_pending ON email_outbox(status, created_at);

-- Anonymised product-improvement data kept when a company ends service (no ids, no text, no company)
CREATE TABLE IF NOT EXISTS anonymised_feedback (
  id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  recorded_month   DATE NOT NULL,
  kind             VARCHAR(10) NOT NULL CHECK (kind IN ('rating','report')),
  evaluation_text  VARCHAR(500),
  rating           SMALLINT,
  bool_value       BOOLEAN,
  report_type      report_type,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =====================================================================
-- 7c. MODEL EVALUATION LAB (added in v1.2)
-- =====================================================================
CREATE TABLE IF NOT EXISTS eval_datasets (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name        VARCHAR(200) NOT NULL UNIQUE,
  description TEXT,
  company_id  UUID REFERENCES companies(id) ON DELETE SET NULL,   -- hidden system company that holds the benchmark's chunks
  is_starter  BOOLEAN NOT NULL DEFAULT FALSE,
  created_by  UUID REFERENCES users(id) ON DELETE SET NULL,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS eval_documents (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  dataset_id         UUID NOT NULL REFERENCES eval_datasets(id) ON DELETE CASCADE,
  filename           VARCHAR(300) NOT NULL,
  file_type          VARCHAR(10) NOT NULL,
  language           VARCHAR(8),
  storage_path       TEXT NOT NULL,
  size_bytes         BIGINT NOT NULL,
  document_id        UUID REFERENCES documents(id) ON DELETE SET NULL,   -- the processed copy in the system company
  ingest_fingerprint VARCHAR(64),                                         -- cleaning+chunking+embedding settings used; re-ingest when they change
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (dataset_id, filename)
);

CREATE TABLE IF NOT EXISTS eval_cases (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  dataset_id        UUID NOT NULL REFERENCES eval_datasets(id) ON DELETE CASCADE,
  position          INTEGER NOT NULL DEFAULT 0,
  question          TEXT NOT NULL,
  question_language VARCHAR(8) NOT NULL DEFAULT 'en',
  document_language VARCHAR(8),                       -- language of the document that holds the answer (cross-language analysis)
  answerable        BOOLEAN NOT NULL DEFAULT TRUE,    -- FALSE = the documents do NOT contain the answer (tests "I could not find it")
  expected_answer   TEXT,
  evidence          JSONB NOT NULL DEFAULT '[]',      -- verbatim phrases of the document that contain the answer (ground truth for retrieval)
  key_facts         JSONB NOT NULL DEFAULT '[]',      -- facts a correct answer must contain; "a|b" = alternatives
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_eval_cases_dataset ON eval_cases(dataset_id, position);

CREATE TABLE IF NOT EXISTS eval_runs (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  dataset_id      UUID NOT NULL REFERENCES eval_datasets(id) ON DELETE CASCADE,
  kind            VARCHAR(20) NOT NULL CHECK (kind IN ('retrieval','llm')),
  status          VARCHAR(20) NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','running','completed','failed')),
  params          JSONB NOT NULL DEFAULT '{}',
  config_snapshot JSONB,                              -- the exact RAG settings that were evaluated
  progress_pct    SMALLINT NOT NULL DEFAULT 0,
  message         TEXT,
  summary         JSONB,                              -- aggregated metrics
  error           TEXT,
  created_by      UUID REFERENCES users(id) ON DELETE SET NULL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  started_at      TIMESTAMPTZ,
  finished_at     TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_eval_runs_created ON eval_runs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_eval_runs_status ON eval_runs(status, created_at);

CREATE TABLE IF NOT EXISTS eval_case_results (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id     UUID NOT NULL REFERENCES eval_runs(id) ON DELETE CASCADE,
  case_id    UUID REFERENCES eval_cases(id) ON DELETE SET NULL,
  question   TEXT NOT NULL,
  metrics    JSONB NOT NULL DEFAULT '{}',
  details    JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_eval_results_run ON eval_case_results(run_id);

-- =====================================================================
-- 8. updated_at triggers
-- =====================================================================
DO $$ DECLARE t TEXT; BEGIN
  FOREACH t IN ARRAY ARRAY['companies','users','api_credentials','documents','conversations','reports','languages','onboarding_steps','application_form_fields','company_applications','eval_datasets'] LOOP
    EXECUTE format('CREATE TRIGGER trg_%I_updated BEFORE UPDATE ON %I FOR EACH ROW EXECUTE FUNCTION set_updated_at()', t, t);
  END LOOP;
END $$;

-- =====================================================================
-- 9. ROW-LEVEL SECURITY (defence in depth; backend ALSO enforces company scope)
-- The API sets per request:  SET LOCAL app.current_company_id = '<uuid>';
-- SuperAdmin requests set:   SET LOCAL app.bypass_rls = 'on';
-- =====================================================================
DO $$ DECLARE t TEXT; BEGIN
  FOREACH t IN ARRAY ARRAY['documents','processing_jobs','parent_chunks','chunks','conversations','messages',
                           'retrieval_logs','feedback','reports'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format($p$CREATE POLICY tenant_isolation ON %I USING (
        current_setting('app.bypass_rls', true) = 'on'
        OR company_id = NULLIF(current_setting('app.current_company_id', true), '')::uuid)
      WITH CHECK (
        current_setting('app.bypass_rls', true) = 'on'
        OR company_id = NULLIF(current_setting('app.current_company_id', true), '')::uuid)$p$, t);
  END LOOP;
END $$;

-- Application role (NOT the table owner, so RLS applies). Password is changed by the migration/setup script.
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'rag_app') THEN
    CREATE ROLE rag_app LOGIN PASSWORD 'change_me_app';
  END IF;
EXCEPTION WHEN insufficient_privilege THEN
  RAISE NOTICE 'Cannot create role rag_app on this server (managed database). Connect the app as the database owner: row-level security still applies because every tenant table uses FORCE ROW LEVEL SECURITY.';
END $$;
DO $$ BEGIN
  IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'rag_app') THEN
    GRANT USAGE ON SCHEMA public TO rag_app;
    GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO rag_app;
    GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO rag_app;
  END IF;
END $$;
