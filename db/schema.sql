CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE tracks (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source text NOT NULL,                -- fma | jamendo | artist | upload | musicbrainz
  source_id text NOT NULL,
  mbid text,
  recording_group_id uuid,             -- alternate versions/duplicates share a group
  title text NOT NULL,
  artist text NOT NULL,
  album text,
  duration_s real,
  artwork_url text,
  source_url text,
  license text,
  license_url text,
  attribution text,
  owner_session text,                  -- set only for uploads
  created_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz,
  UNIQUE (source, source_id)
);

CREATE TABLE audio_assets (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  track_id uuid NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
  visibility text NOT NULL CHECK (visibility IN ('catalog','private')),
  owner_session text,
  storage_key text NOT NULL,
  sha256 text NOT NULL,
  bytes bigint NOT NULL,
  duration_s real NOT NULL,
  codec text,
  peaks jsonb,
  analysis_allowed boolean NOT NULL DEFAULT false,
  playback_allowed boolean NOT NULL DEFAULT false,
  storage_allowed boolean NOT NULL DEFAULT false,
  status text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','processing','ready','failed')),
  error text,
  original_filename text,
  created_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz
);
CREATE INDEX ON audio_assets (track_id);
CREATE INDEX ON audio_assets (expires_at) WHERE expires_at IS NOT NULL;

CREATE TABLE feature_versions (
  id serial PRIMARY KEY,
  preprocess_version text NOT NULL,
  model_name text NOT NULL,
  model_revision text NOT NULL,
  embed_dim int NOT NULL,
  config jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (preprocess_version, model_name, model_revision)
);

CREATE TABLE segments (
  id bigserial PRIMARY KEY,
  asset_id uuid NOT NULL REFERENCES audio_assets(id) ON DELETE CASCADE,
  track_id uuid NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
  scale_s int NOT NULL,
  start_s real NOT NULL,
  end_s real NOT NULL,
  embedding vector(512) NOT NULL,
  chroma_mean vector(12) NOT NULL,
  chroma_seq jsonb NOT NULL,           -- list of 12-d frames at ~2 Hz
  chroma_conf real,
  tempo real,
  tempo_conf real,
  onset_density real,
  timbre jsonb NOT NULL,               -- fixed-range descriptors in [0,1]
  preprocess_version text NOT NULL,
  model_version text NOT NULL,
  UNIQUE (asset_id, scale_s, start_s, preprocess_version, model_version)
);
CREATE INDEX ON segments (track_id);
-- Exact search while the catalog is small. Add HNSW only once benchmarks justify it:
--   CREATE INDEX ON segments USING hnsw (embedding vector_cosine_ops);
-- and then measure approximate-retrieval recall against exact search.

CREATE TABLE analysis_jobs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  kind text NOT NULL CHECK (kind IN ('index_asset','query')),
  asset_id uuid NOT NULL REFERENCES audio_assets(id) ON DELETE CASCADE,
  owner_session text,
  start_s real,
  end_s real,
  cache_key text,
  status text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','processing','ready','failed','cancelled')),
  error text,
  celery_task_id text,
  created_at timestamptz NOT NULL DEFAULT now(),
  started_at timestamptz,
  finished_at timestamptz
);

CREATE TABLE query_features (
  cache_key text PRIMARY KEY,          -- sha256 + start + end + preprocess + model
  asset_id uuid NOT NULL REFERENCES audio_assets(id) ON DELETE CASCADE,
  owner_session text,
  start_s real NOT NULL,
  end_s real NOT NULL,
  windows jsonb NOT NULL,
  preprocess_version text NOT NULL,
  model_version text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE searches (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_session text NOT NULL,
  query_asset_id uuid REFERENCES audio_assets(id) ON DELETE SET NULL,
  start_s real, end_s real, whole_song boolean NOT NULL DEFAULT false,
  mode text NOT NULL,
  weights jsonb NOT NULL,
  analysis_versions jsonb NOT NULL,
  latency_ms int,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE results (
  id bigserial PRIMARY KEY,
  search_id uuid NOT NULL REFERENCES searches(id) ON DELETE CASCADE,
  owner_session text NOT NULL,
  track_id uuid NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
  start_s real, end_s real,
  rank int NOT NULL,
  score real NOT NULL,
  components jsonb NOT NULL,
  confidence text NOT NULL,
  explanations jsonb NOT NULL
);

CREATE TABLE feedback (
  id bigserial PRIMARY KEY,
  result_id bigint NOT NULL REFERENCES results(id) ON DELETE CASCADE,
  owner_session text NOT NULL,
  label text NOT NULL CHECK (label IN ('good','poor')),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (result_id, owner_session)
);

CREATE TABLE saved_items (
  id bigserial PRIMARY KEY,
  owner_session text NOT NULL,
  track_id uuid NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
  start_s real, end_s real,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- ---------- Row Level Security ----------
-- The API connects as resonant_app (not the table owner) and sets app.session_id per transaction.
-- Worker, ingestion and migrations use the owner role and bypass RLS.
GRANT USAGE ON SCHEMA public TO resonant_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO resonant_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO resonant_app;

CREATE FUNCTION app_sid() RETURNS text LANGUAGE sql STABLE AS
  $$ SELECT NULLIF(current_setting('app.session_id', true), '') $$;

ALTER TABLE tracks ENABLE ROW LEVEL SECURITY;
CREATE POLICY tracks_read ON tracks FOR SELECT TO resonant_app
  USING (owner_session IS NULL OR owner_session = app_sid());
CREATE POLICY tracks_write ON tracks FOR ALL TO resonant_app
  USING (owner_session = app_sid()) WITH CHECK (owner_session = app_sid());

ALTER TABLE audio_assets ENABLE ROW LEVEL SECURITY;
CREATE POLICY assets_read ON audio_assets FOR SELECT TO resonant_app
  USING (visibility = 'catalog' OR owner_session = app_sid());
CREATE POLICY assets_write ON audio_assets FOR ALL TO resonant_app
  USING (visibility = 'private' AND owner_session = app_sid())
  WITH CHECK (visibility = 'private' AND owner_session = app_sid());

ALTER TABLE segments ENABLE ROW LEVEL SECURITY;
CREATE POLICY segments_read ON segments FOR SELECT TO resonant_app
  USING (EXISTS (SELECT 1 FROM audio_assets a WHERE a.id = asset_id
                 AND (a.visibility = 'catalog' OR a.owner_session = app_sid())));

ALTER TABLE feature_versions ENABLE ROW LEVEL SECURITY;
CREATE POLICY fv_read ON feature_versions FOR SELECT TO resonant_app USING (true);

DO $$ DECLARE t text; BEGIN
  FOREACH t IN ARRAY ARRAY['analysis_jobs','query_features','searches','results','feedback','saved_items'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('CREATE POLICY %I ON %I FOR ALL TO resonant_app USING (owner_session = app_sid()) WITH CHECK (owner_session = app_sid())', t || '_own', t);
  END LOOP;
END $$;
