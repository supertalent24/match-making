-- Enable pgvector extension (required before Alembic migrations can create vector columns)
-- This runs on first database initialization only
CREATE EXTENSION IF NOT EXISTS vector;
