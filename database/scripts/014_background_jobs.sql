BEGIN;

CREATE TABLE IF NOT EXISTS background_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES review_projects(id) ON DELETE CASCADE,
    job_type VARCHAR(50) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'queued',
    parameters_jsonb JSONB NOT NULL DEFAULT '{}'::jsonb,
    result_jsonb JSONB,
    progress_current INTEGER NOT NULL DEFAULT 0,
    progress_total INTEGER NOT NULL DEFAULT 0,
    progress_message TEXT,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    available_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    heartbeat_at TIMESTAMP WITH TIME ZONE,
    started_at TIMESTAMP WITH TIME ZONE,
    finished_at TIMESTAMP WITH TIME ZONE,
    worker_id VARCHAR(200),
    error_code VARCHAR(80),
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (job_type IN (
        'bibliographic_search', 'pdf_indexing', 'evidence_extraction',
        'final_report', 'rag_benchmark', 'visual_cataloging',
        'visual_interpretation'
    )),
    CHECK (status IN (
        'queued', 'running', 'retry_wait', 'succeeded', 'failed', 'cancelled'
    )),
    CHECK (progress_current >= 0),
    CHECK (progress_total >= 0),
    CHECK (attempt_count >= 0),
    CHECK (max_attempts BETWEEN 1 AND 10)
);

CREATE TABLE IF NOT EXISTS background_job_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES background_jobs(id) ON DELETE CASCADE,
    event_type VARCHAR(30) NOT NULL,
    details_jsonb JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (event_type IN (
        'queued', 'started', 'progress', 'retry_scheduled',
        'succeeded', 'failed', 'manual_retry', 'recovered_stale'
    ))
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_background_jobs_active_type
    ON background_jobs(project_id, job_type)
    WHERE status IN ('queued', 'running', 'retry_wait');

CREATE INDEX IF NOT EXISTS idx_background_jobs_claim
    ON background_jobs(status, available_at, created_at);
CREATE INDEX IF NOT EXISTS idx_background_jobs_project
    ON background_jobs(project_id, job_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_background_job_events_job
    ON background_job_events(job_id, created_at);

COMMIT;
