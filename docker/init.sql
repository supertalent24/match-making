-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================================================
-- RAW DATA TABLES
-- ============================================================================

-- Raw candidate data as ingested (before any processing)
CREATE TABLE IF NOT EXISTS raw_candidates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source VARCHAR(50) NOT NULL,  -- 'cv', 'github', 'form'
    raw_data JSONB NOT NULL,
    ingested_at TIMESTAMPTZ DEFAULT NOW()
);

-- Raw job descriptions as ingested
CREATE TABLE IF NOT EXISTS raw_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID,
    raw_description TEXT NOT NULL,
    ingested_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- NORMALIZED DATA TABLES
-- ============================================================================

-- LLM-normalized candidate profiles
CREATE TABLE IF NOT EXISTS normalized_candidates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id UUID NOT NULL REFERENCES raw_candidates(id) ON DELETE CASCADE,
    normalized_json JSONB NOT NULL,
    prompt_version VARCHAR(50) NOT NULL,
    model_version VARCHAR(50) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- LLM-normalized job requirements
CREATE TABLE IF NOT EXISTS normalized_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES raw_jobs(id) ON DELETE CASCADE,
    normalized_json JSONB NOT NULL,
    prompt_version VARCHAR(50) NOT NULL,
    model_version VARCHAR(50) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- VECTOR TABLES (pgvector)
-- ============================================================================

-- Candidate embeddings for semantic search
CREATE TABLE IF NOT EXISTS candidate_vectors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id UUID NOT NULL REFERENCES raw_candidates(id) ON DELETE CASCADE,
    vector_type VARCHAR(50) NOT NULL,  -- 'position', 'experience', 'domain_context', 'personality'
    vector vector(1536) NOT NULL,
    model_version VARCHAR(50) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Job embeddings for semantic matching
CREATE TABLE IF NOT EXISTS job_vectors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES raw_jobs(id) ON DELETE CASCADE,
    vector_type VARCHAR(50) NOT NULL,  -- 'role_description', 'domain_context', 'culture'
    vector vector(1536) NOT NULL,
    model_version VARCHAR(50) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- MATCHING RESULTS
-- ============================================================================

-- Computed matches between jobs and candidates
CREATE TABLE IF NOT EXISTS matches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES raw_jobs(id) ON DELETE CASCADE,
    candidate_id UUID NOT NULL REFERENCES raw_candidates(id) ON DELETE CASCADE,
    match_score FLOAT NOT NULL,
    keyword_score FLOAT,
    vector_score FLOAT,
    breakdown_json JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(job_id, candidate_id)
);

-- ============================================================================
-- INDEXES
-- ============================================================================

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_raw_candidates_source ON raw_candidates(source);
CREATE INDEX IF NOT EXISTS idx_raw_candidates_ingested ON raw_candidates(ingested_at);

CREATE INDEX IF NOT EXISTS idx_normalized_candidates_candidate ON normalized_candidates(candidate_id);
CREATE INDEX IF NOT EXISTS idx_normalized_candidates_version ON normalized_candidates(prompt_version);

CREATE INDEX IF NOT EXISTS idx_normalized_jobs_job ON normalized_jobs(job_id);

-- Vector indexes using HNSW for fast similarity search
CREATE INDEX IF NOT EXISTS idx_candidate_vectors_hnsw ON candidate_vectors 
    USING hnsw (vector vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_candidate_vectors_type ON candidate_vectors(vector_type);

CREATE INDEX IF NOT EXISTS idx_job_vectors_hnsw ON job_vectors 
    USING hnsw (vector vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_job_vectors_type ON job_vectors(vector_type);

-- Match indexes
CREATE INDEX IF NOT EXISTS idx_matches_job ON matches(job_id);
CREATE INDEX IF NOT EXISTS idx_matches_candidate ON matches(candidate_id);
CREATE INDEX IF NOT EXISTS idx_matches_score ON matches(match_score DESC);

-- ============================================================================
-- LLM COST TRACKING
-- ============================================================================

-- Track LLM API costs per asset, run, and operation
CREATE TABLE IF NOT EXISTS llm_costs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id VARCHAR(100) NOT NULL,
    asset_key VARCHAR(100) NOT NULL,
    partition_key VARCHAR(100),
    operation VARCHAR(50) NOT NULL,  -- 'normalize_cv', 'normalize_job', 'score', 'embed'
    model VARCHAR(100) NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    total_tokens INTEGER GENERATED ALWAYS AS (input_tokens + output_tokens) STORED,
    cost_usd DECIMAL(10, 6) NOT NULL,
    code_version VARCHAR(50),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for cost analysis
CREATE INDEX IF NOT EXISTS idx_llm_costs_asset ON llm_costs(asset_key);
CREATE INDEX IF NOT EXISTS idx_llm_costs_operation ON llm_costs(operation);
CREATE INDEX IF NOT EXISTS idx_llm_costs_created ON llm_costs(created_at);
CREATE INDEX IF NOT EXISTS idx_llm_costs_code_version ON llm_costs(code_version);
CREATE INDEX IF NOT EXISTS idx_llm_costs_run ON llm_costs(run_id);

-- View for cost aggregation by asset and code version
CREATE OR REPLACE VIEW llm_cost_summary AS
SELECT 
    asset_key,
    operation,
    code_version,
    COUNT(*) as call_count,
    AVG(cost_usd) as avg_cost_per_call,
    SUM(cost_usd) as total_cost,
    AVG(input_tokens) as avg_input_tokens,
    AVG(output_tokens) as avg_output_tokens
FROM llm_costs
GROUP BY asset_key, operation, code_version;

-- View for daily cost trends
CREATE OR REPLACE VIEW llm_daily_costs AS
SELECT 
    DATE(created_at) as date,
    asset_key,
    SUM(cost_usd) as daily_cost,
    COUNT(*) as call_count,
    SUM(total_tokens) as total_tokens
FROM llm_costs
GROUP BY DATE(created_at), asset_key;

-- ============================================================================
-- DAGSTER STORAGE (for run history, schedules, etc.)
-- ============================================================================

-- Dagster will create its own tables, but we ensure the schema exists
-- The dagster-postgres package handles table creation automatically
