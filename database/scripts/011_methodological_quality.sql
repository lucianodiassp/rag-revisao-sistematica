BEGIN;

ALTER TABLE ai_model_settings
    DROP CONSTRAINT IF EXISTS ai_model_settings_task_type_check;
ALTER TABLE ai_model_settings
    ADD CONSTRAINT ai_model_settings_task_type_check CHECK (task_type IN (
        'formulation', 'screening', 'rag', 'reranking', 'evaluation',
        'extraction', 'methodological_quality', 'report',
        'visual_interpretation', 'embedding'
    ));

CREATE TABLE IF NOT EXISTS methodological_assessment_instruments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES review_projects(id) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    name VARCHAR(200) NOT NULL,
    description TEXT NOT NULL,
    schema_version VARCHAR(50) NOT NULL DEFAULT 'generic-methodological-v1',
    domains_jsonb JSONB NOT NULL,
    change_reason TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (project_id, version),
    CHECK (length(btrim(name)) >= 5),
    CHECK (length(btrim(description)) >= 10),
    CHECK (length(btrim(change_reason)) >= 5),
    CHECK (jsonb_typeof(domains_jsonb) = 'array')
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_deduplicated_papers_project_identity
    ON deduplicated_papers(project_id, id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_methodological_instrument_project_identity
    ON methodological_assessment_instruments(project_id, id);

CREATE UNIQUE INDEX IF NOT EXISTS uq_methodological_instrument_active
    ON methodological_assessment_instruments(project_id)
    WHERE is_active = TRUE;

CREATE TABLE IF NOT EXISTS methodological_assessments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES review_projects(id) ON DELETE CASCADE,
    paper_id UUID NOT NULL REFERENCES deduplicated_papers(id) ON DELETE CASCADE,
    instrument_id UUID NOT NULL REFERENCES methodological_assessment_instruments(id),
    ai_suggestion_jsonb JSONB,
    human_assessment_jsonb JSONB,
    overall_rating VARCHAR(30),
    review_status VARCHAR(30) NOT NULL DEFAULT 'pending',
    review_notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    reviewed_at TIMESTAMP WITH TIME ZONE,
    UNIQUE (project_id, paper_id, instrument_id),
    CHECK (review_status IN ('pending', 'reviewed')),
    CHECK (overall_rating IS NULL OR overall_rating IN (
        'low', 'moderate', 'high', 'uncertain'
    )),
    CHECK (review_notes IS NULL OR length(btrim(review_notes)) >= 5)
);

CREATE TABLE IF NOT EXISTS methodological_assessment_sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    assessment_id UUID NOT NULL REFERENCES methodological_assessments(id) ON DELETE CASCADE,
    domain_code VARCHAR(80) NOT NULL,
    evidence_order INTEGER NOT NULL DEFAULT 0,
    chunk_id UUID NOT NULL REFERENCES paper_chunks(id) ON DELETE CASCADE,
    page_number INTEGER,
    quote TEXT NOT NULL,
    quote_validated BOOLEAN NOT NULL DEFAULT TRUE,
    human_validated BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (assessment_id, domain_code, evidence_order),
    CHECK (page_number IS NULL OR page_number > 0),
    CHECK (length(btrim(quote)) >= 5)
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'methodological_assessments_project_paper_fkey'
    ) THEN
        ALTER TABLE methodological_assessments
            ADD CONSTRAINT methodological_assessments_project_paper_fkey
            FOREIGN KEY (project_id, paper_id)
            REFERENCES deduplicated_papers(project_id, id) ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'methodological_assessments_project_instrument_fkey'
    ) THEN
        ALTER TABLE methodological_assessments
            ADD CONSTRAINT methodological_assessments_project_instrument_fkey
            FOREIGN KEY (project_id, instrument_id)
            REFERENCES methodological_assessment_instruments(project_id, id) ON DELETE CASCADE;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_methodological_instruments_project
    ON methodological_assessment_instruments(project_id, version DESC);
CREATE INDEX IF NOT EXISTS idx_methodological_assessments_project
    ON methodological_assessments(project_id, review_status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_methodological_assessments_paper
    ON methodological_assessments(paper_id);
CREATE INDEX IF NOT EXISTS idx_methodological_sources_assessment
    ON methodological_assessment_sources(assessment_id, domain_code);

COMMIT;
