-- Phase 3 index additions for lena_team_memory
-- ivfflat probes: SET ivfflat.probes = 10 at query time for recall/accuracy tradeoff
-- maintenance_work_mem: SET maintenance_work_mem = '256MB' before CREATE INDEX for faster build
-- HNSW migration (003_hnsw.sql): use when table > 100k rows for better recall at scale

-- ---------------------------------------------------------------------------
-- Recency-bounded recall: team_id + type filter + ORDER BY created_at DESC
-- Supports: WHERE team_id = $1 AND type = $2 ORDER BY created_at DESC
-- ---------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_team_mem_type_recency
    ON lena_team_memory (team_id, type, created_at DESC);

-- ---------------------------------------------------------------------------
-- Content-hash dedup check: metadata->>'hash' = $1 AND team_id = $2
-- Supports: WHERE team_id = $1 AND metadata->>'hash' = $2 LIMIT 1
-- ---------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_team_mem_content_hash
    ON lena_team_memory ((metadata->>'hash'), team_id);

-- ---------------------------------------------------------------------------
-- Atomic dedup guarantee: unique index on (team_id, hash) prevents duplicate
-- rows even under concurrent upsert calls (SELECT+INSERT is not atomic).
-- Note: Postgres UNIQUE *constraints* reject expression columns — must use a
-- UNIQUE *index*. ON CONFLICT in upsert uses the column-list inference form.
-- idx_team_mem_content_hash above is made redundant by this index; keeping it
-- for backward-compat until a later migration drops it.
-- ---------------------------------------------------------------------------
CREATE UNIQUE INDEX IF NOT EXISTS uq_team_content_hash
    ON lena_team_memory (team_id, (metadata->>'hash'));

-- ---------------------------------------------------------------------------
-- GIN on full metadata for future jsonb_path_ops queries
-- ---------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_team_mem_metadata_gin
    ON lena_team_memory USING GIN (metadata jsonb_path_ops);

-- ---------------------------------------------------------------------------
-- ivfflat note: lists=100 is appropriate for tables under 100k rows
-- HNSW alternative for when table exceeds 100k rows (see 003_hnsw_migration.sql):
-- CREATE INDEX idx_team_mem_hnsw ON lena_team_memory
--   USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);
-- DROP INDEX IF EXISTS idx_team_mem_embedding;
-- ---------------------------------------------------------------------------
