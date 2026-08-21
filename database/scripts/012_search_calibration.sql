BEGIN;

CREATE TABLE IF NOT EXISTS search_calibration_sentinels (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES review_projects(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    canonical_doi VARCHAR(255),
    notes TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CHECK (length(btrim(title)) >= 5)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_search_calibration_sentinel_doi
    ON search_calibration_sentinels(project_id, canonical_doi)
    WHERE canonical_doi IS NOT NULL;

CREATE TABLE IF NOT EXISTS search_calibration_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES review_projects(id) ON DELETE CASCADE,
    protocol_version INTEGER NOT NULL,
    protocol_fingerprint VARCHAR(64) NOT NULL,
    max_results_per_source INTEGER NOT NULL,
    status VARCHAR(20) NOT NULL,
    queries_jsonb JSONB NOT NULL,
    sentinel_snapshot_jsonb JSONB NOT NULL,
    source_results_jsonb JSONB NOT NULL,
    summary_jsonb JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CHECK (max_results_per_source BETWEEN 10 AND 100),
    CHECK (status IN ('completed', 'partial', 'failed')),
    CHECK (length(protocol_fingerprint) = 64)
);

ALTER TABLE search_calibration_runs
    DROP CONSTRAINT IF EXISTS search_calibration_runs_max_results_per_source_check;
ALTER TABLE search_calibration_runs
    ADD CONSTRAINT search_calibration_runs_max_results_per_source_check
    CHECK (max_results_per_source BETWEEN 10 AND 100);

CREATE TABLE IF NOT EXISTS search_calibration_matches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES search_calibration_runs(id) ON DELETE CASCADE,
    sentinel_id UUID REFERENCES search_calibration_sentinels(id) ON DELETE SET NULL,
    source_code VARCHAR(50) NOT NULL,
    result_rank INTEGER NOT NULL,
    match_method VARCHAR(30) NOT NULL,
    similarity_score NUMERIC(5,4) NOT NULL,
    matched_title TEXT NOT NULL,
    matched_doi VARCHAR(255),
    evidence_jsonb JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (run_id, sentinel_id, source_code),
    CHECK (source_code IN ('openalex', 'semantic_scholar', 'pubmed')),
    CHECK (result_rank > 0),
    CHECK (match_method IN ('doi_exact', 'title_exact', 'title_similar')),
    CHECK (similarity_score BETWEEN 0 AND 1)
);

CREATE TABLE IF NOT EXISTS press_search_reviews (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES review_projects(id) ON DELETE CASCADE,
    protocol_version INTEGER NOT NULL,
    protocol_fingerprint VARCHAR(64) NOT NULL,
    checklist_jsonb JSONB NOT NULL,
    overall_decision VARCHAR(30) NOT NULL,
    reviewer_name VARCHAR(150),
    review_notes TEXT,
    reviewed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (project_id, protocol_version),
    CHECK (overall_decision IN ('approved', 'changes_requested')),
    CHECK (length(protocol_fingerprint) = 64)
);

CREATE INDEX IF NOT EXISTS idx_search_calibration_sentinels_project
    ON search_calibration_sentinels(project_id, is_active, created_at);
CREATE INDEX IF NOT EXISTS idx_search_calibration_runs_project
    ON search_calibration_runs(project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_search_calibration_matches_run
    ON search_calibration_matches(run_id, source_code, result_rank);
CREATE INDEX IF NOT EXISTS idx_press_search_reviews_project
    ON press_search_reviews(project_id, protocol_version DESC);

COMMIT;
