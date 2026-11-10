-- =====================================================================
-- Migration 002: company onboarding portal, CMS content, languages, email outbox
-- Safe to run more than once. Run as the DB owner WITHOUT --single-transaction:
--   docker compose exec -T db psql -U rag_owner -d company_rag < db/migrations/002_onboarding_multilingual.sql
-- Fresh installs get the same changes from db/schema.sql (nothing to run).
-- =====================================================================
SET app.bypass_rls = 'on';

-- ---- 1. changes to existing tables ---------------------------------
ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'applicant';

ALTER TABLE users DROP CONSTRAINT IF EXISTS company_required_for_non_superadmin;
ALTER TABLE users DROP CONSTRAINT IF EXISTS user_company_rules;
ALTER TABLE users ADD CONSTRAINT user_company_rules CHECK (
  (role IN ('super_admin','applicant') AND company_id IS NULL) OR
  (role IN ('company_admin','employee') AND company_id IS NOT NULL));

ALTER TABLE messages  ADD COLUMN IF NOT EXISTS language VARCHAR(8);
ALTER TABLE documents ADD COLUMN IF NOT EXISTS embedding_model VARCHAR(100);
UPDATE documents d SET embedding_model = COALESCE(
    (SELECT c.embedding_cfg->>'model' FROM rag_config_versions c WHERE c.id = d.config_version_id), 'gemini-embedding-001')
 WHERE d.embedding_model IS NULL AND d.status = 'ready';

ALTER TABLE deletion_jobs ALTER COLUMN steps SET DEFAULT
  '{"anonymize":"pending","vectors":"pending","database":"pending","files":"pending","temp_files":"pending","logs":"pending"}';

-- multilingual keyword index: raw tokens ('simple') + English stems, so Kinyarwanda and English both match
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_attrdef ad JOIN pg_attribute a ON a.attrelid = ad.adrelid AND a.attnum = ad.adnum
                 WHERE a.attrelid = 'chunks'::regclass AND a.attname = 'tsv' AND pg_get_expr(ad.adbin, ad.adrelid) LIKE '%simple%') THEN
    DROP INDEX IF EXISTS idx_chunks_tsv;
    ALTER TABLE chunks DROP COLUMN tsv;
    ALTER TABLE chunks ADD COLUMN tsv tsvector GENERATED ALWAYS AS (to_tsvector('simple', content) || to_tsvector('english', content)) STORED;
  END IF;
END $$;
CREATE INDEX IF NOT EXISTS idx_chunks_tsv ON chunks USING gin (tsv);

-- ---- 2. new objects (identical block is embedded in schema.sql) ----
-- BEGIN NEW OBJECTS
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
-- END NEW OBJECTS
ALTER TABLE languages ADD COLUMN IF NOT EXISTS sample_question TEXT;

DO $$ DECLARE t TEXT; BEGIN
  FOREACH t IN ARRAY ARRAY['languages','onboarding_steps','application_form_fields','company_applications'] LOOP
    EXECUTE format('DROP TRIGGER IF EXISTS trg_%I_updated ON %I', t, t);
    EXECUTE format('CREATE TRIGGER trg_%I_updated BEFORE UPDATE ON %I FOR EACH ROW EXECUTE FUNCTION set_updated_at()', t, t);
  END LOOP;
END $$;

DO $$ BEGIN
  IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'rag_app') THEN
    GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO rag_app;
    GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO rag_app;
  END IF;
END $$;
