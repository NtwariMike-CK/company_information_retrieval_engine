-- =====================================================================
-- Migration 003: model evaluation lab (benchmark datasets, runs, per-case results)
-- Safe to run more than once. Run as the DB owner WITHOUT --single-transaction:
--   docker compose exec -T db psql -U rag_owner -d company_rag < db/migrations/003_model_evaluation.sql
-- Fresh installs get the same changes from db/schema.sql (nothing to run).
-- =====================================================================
SET app.bypass_rls = 'on';

-- system companies hold benchmark documents/chunks; they are hidden from every company list
ALTER TABLE companies ADD COLUMN IF NOT EXISTS is_system BOOLEAN NOT NULL DEFAULT FALSE;

-- BEGIN NEW OBJECTS 003
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
-- END NEW OBJECTS 003

DO $$ BEGIN
  DROP TRIGGER IF EXISTS trg_eval_datasets_updated ON eval_datasets;
  CREATE TRIGGER trg_eval_datasets_updated BEFORE UPDATE ON eval_datasets FOR EACH ROW EXECUTE FUNCTION set_updated_at();
END $$;

DO $$ BEGIN
  IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'rag_app') THEN
    GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO rag_app;
    GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO rag_app;
  END IF;
END $$;
