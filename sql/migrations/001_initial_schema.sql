-- ================================================================
-- Schema Inicial: Tabelas para ETL Incremental e Model Registry
-- ================================================================

-- Watermarks (controle de processamento incremental)
CREATE TABLE IF NOT EXISTS processing_watermarks (
  source TEXT PRIMARY KEY,
  last_ts TIMESTAMP NOT NULL,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Raw tables (append-only)
CREATE TABLE IF NOT EXISTS pipelines_raw (
  id BIGINT PRIMARY KEY,
  project_id BIGINT NOT NULL,
  status TEXT,
  ref TEXT,
  sha TEXT,
  web_url TEXT,
  created_at TIMESTAMP,
  updated_at TIMESTAMP,
  finished_at TIMESTAMP,
  source_data JSONB,
  ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS jobs_raw (
  id BIGINT PRIMARY KEY,
  pipeline_id BIGINT NOT NULL,
  project_id BIGINT NOT NULL,
  name TEXT,
  stage TEXT,
  status TEXT,
  duration NUMERIC,
  queued_duration NUMERIC,
  failure_reason TEXT,
  retry_count INT DEFAULT 0,
  web_url TEXT,
  created_at TIMESTAMP,
  started_at TIMESTAMP,
  finished_at TIMESTAMP,
  source_data JSONB,
  ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (pipeline_id) REFERENCES pipelines_raw(id) ON DELETE CASCADE
);

-- Agregados diários (materializados)
CREATE TABLE IF NOT EXISTS metrics_daily (
  project_id BIGINT,
  job_name TEXT,
  day DATE,
  builds INT DEFAULT 0,
  fails INT DEFAULT 0,
  p95_duration NUMERIC,
  p99_duration NUMERIC,
  avg_duration NUMERIC,
  total_duration NUMERIC,
  max_retries INT DEFAULT 0,
  error_types JSONB,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (project_id, job_name, day)
);

-- Feature Store (offline - histórico)
CREATE TABLE IF NOT EXISTS features_offline (
  entity_key TEXT NOT NULL,
  feature_version INT NOT NULL,
  payload JSONB NOT NULL,
  event_time TIMESTAMP NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (entity_key, feature_version)
);

-- Feature Store (online - cache atual)
CREATE TABLE IF NOT EXISTS features_online (
  entity_key TEXT PRIMARY KEY,
  feature_version INT NOT NULL,
  payload JSONB NOT NULL,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Predições (por run_id e model_version)
CREATE TABLE IF NOT EXISTS predictions (
  run_id TEXT NOT NULL,
  model_version INT NOT NULL,
  feature_version INT NOT NULL,
  prediction JSONB NOT NULL,
  score NUMERIC,
  label TEXT,
  metadata JSONB,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (run_id, model_version)
);

-- Backfill (predições históricas)
CREATE TABLE IF NOT EXISTS predictions_backfill (
  run_id TEXT NOT NULL,
  model_version INT NOT NULL,
  feature_version INT NOT NULL,
  prediction JSONB NOT NULL,
  score NUMERIC,
  label TEXT,
  metadata JSONB,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (run_id, model_version)
);

-- Model Registry (controle de versões)
CREATE TABLE IF NOT EXISTS model_registry (
  model_version INT PRIMARY KEY,
  feature_version INT NOT NULL,
  model_type TEXT NOT NULL,
  model_path TEXT NOT NULL,
  transformer_path TEXT,
  feature_schema_path TEXT NOT NULL,
  training_window_start DATE,
  training_window_end DATE,
  metrics JSONB,
  is_current BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  trained_by TEXT
);

-- Config KV (para MODEL_CURRENT, etc)
CREATE TABLE IF NOT EXISTS kv_config (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Índices para performance
CREATE INDEX IF NOT EXISTS idx_pipelines_raw_project_updated ON pipelines_raw(project_id, updated_at);
CREATE INDEX IF NOT EXISTS idx_jobs_raw_pipeline ON jobs_raw(pipeline_id);
CREATE INDEX IF NOT EXISTS idx_jobs_raw_project_created ON jobs_raw(project_id, created_at);
CREATE INDEX IF NOT EXISTS idx_metrics_daily_project_day ON metrics_daily(project_id, day);
CREATE INDEX IF NOT EXISTS idx_features_offline_entity_time ON features_offline(entity_key, event_time);
CREATE INDEX IF NOT EXISTS idx_predictions_run_created ON predictions(run_id, created_at);
CREATE INDEX IF NOT EXISTS idx_predictions_model_version ON predictions(model_version, created_at);

-- Inicializa MODEL_CURRENT
INSERT INTO kv_config (key, value) VALUES ('MODEL_CURRENT', '1')
ON CONFLICT (key) DO NOTHING;

-- Inicializa FEATURE_VERSION_CURRENT
INSERT INTO kv_config (key, value) VALUES ('FEATURE_VERSION_CURRENT', '1')
ON CONFLICT (key) DO NOTHING;

