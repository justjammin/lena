-- Migration 001: initial schema
-- Run once against the lena database.  Idempotent (IF NOT EXISTS everywhere).

-- ---------------------------------------------------------------------------
-- Extensions
-- ---------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ---------------------------------------------------------------------------
-- mem0 pgvector table
-- Schema expected by mem0ai's pgvector store.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS mem0_memories (
    id          uuid        PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id     text        NOT NULL,
    session_id  text,
    memory      text        NOT NULL,
    embedding   vector(768),
    metadata    jsonb       NOT NULL DEFAULT '{}',
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_mem0_user
    ON mem0_memories (user_id);

CREATE INDEX IF NOT EXISTS idx_mem0_embedding
    ON mem0_memories USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- ---------------------------------------------------------------------------
-- Team moat table  (Phase 3 — structure created now, data populated later)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS lena_team_memory (
    id          uuid        PRIMARY KEY DEFAULT uuid_generate_v4(),
    team_id     text        NOT NULL,
    project     text,
    domain      text,
    type        text        NOT NULL,
    content     text        NOT NULL,
    embedding   vector(768),
    metadata    jsonb       NOT NULL DEFAULT '{}',
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_team_mem_team
    ON lena_team_memory (team_id, type, domain);

-- For production queries: SET ivfflat.probes = 10; before SELECT for better recall
-- Default probes=1 is fast but misses ~30% of true nearest neighbors at lists=100
CREATE INDEX IF NOT EXISTS idx_team_mem_embedding
    ON lena_team_memory USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
