BEGIN;

ALTER TABLE background_jobs
    DROP CONSTRAINT IF EXISTS background_jobs_job_type_check;
ALTER TABLE background_jobs
    ADD CONSTRAINT background_jobs_job_type_check CHECK (job_type IN (
        'bibliographic_search', 'pdf_indexing', 'evidence_extraction',
        'final_report', 'rag_benchmark', 'visual_cataloging',
        'visual_interpretation'
    ));

ALTER TABLE ai_model_settings
    DROP CONSTRAINT IF EXISTS ai_model_settings_task_type_check;
ALTER TABLE ai_model_settings
    ADD CONSTRAINT ai_model_settings_task_type_check CHECK (task_type IN (
        'formulation', 'screening', 'rag', 'reranking', 'evaluation',
        'extraction', 'methodological_quality', 'report',
        'visual_interpretation', 'embedding'
    ));

CREATE TABLE IF NOT EXISTS visual_interpretations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES review_projects(id) ON DELETE CASCADE,
    artifact_id UUID NOT NULL REFERENCES visual_artifacts(id) ON DELETE CASCADE,
    source_file_sha256 CHAR(64) NOT NULL,
    image_sha256 CHAR(64) NOT NULL,
    prompt_version VARCHAR(80) NOT NULL,
    provider_code VARCHAR(50) NOT NULL,
    model_name VARCHAR(150) NOT NULL,
    model_metadata_jsonb JSONB NOT NULL DEFAULT '{}'::jsonb,
    interpretation_jsonb JSONB NOT NULL,
    review_status VARCHAR(20) NOT NULL DEFAULT 'pending',
    human_interpretation_jsonb JSONB,
    human_notes TEXT,
    reviewer_name VARCHAR(200),
    is_current BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reviewed_at TIMESTAMP WITH TIME ZONE,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (length(source_file_sha256) = 64),
    CHECK (length(image_sha256) = 64),
    CHECK (review_status IN ('pending', 'approved', 'corrected', 'rejected')),
    CHECK (jsonb_typeof(model_metadata_jsonb) = 'object'),
    CHECK (jsonb_typeof(interpretation_jsonb) = 'object'),
    CHECK (human_interpretation_jsonb IS NULL OR
           jsonb_typeof(human_interpretation_jsonb) = 'object'),
    CHECK (human_notes IS NULL OR length(btrim(human_notes)) >= 5)
);

CREATE TABLE IF NOT EXISTS visual_interpretation_review_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES review_projects(id) ON DELETE CASCADE,
    interpretation_id UUID NOT NULL REFERENCES visual_interpretations(id) ON DELETE CASCADE,
    action VARCHAR(20) NOT NULL,
    previous_jsonb JSONB NOT NULL,
    current_jsonb JSONB NOT NULL,
    reviewer_name VARCHAR(200) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (action IN ('approved', 'corrected', 'rejected')),
    CHECK (length(btrim(reviewer_name)) >= 2)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_visual_interpretations_current
    ON visual_interpretations(project_id, artifact_id)
    WHERE is_current = TRUE;
CREATE INDEX IF NOT EXISTS idx_visual_interpretations_project_status
    ON visual_interpretations(project_id, is_current, review_status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_visual_interpretation_events
    ON visual_interpretation_review_events(interpretation_id, created_at);

COMMENT ON TABLE visual_interpretations IS
    'Interpretações multimodais de candidatos visuais aprovados; permanecem fora do RAG até revisão humana.';
COMMENT ON COLUMN visual_interpretations.image_sha256 IS
    'Hash do recorte enviado em memória; a imagem e seu base64 não são persistidos nesta tabela.';
COMMENT ON TABLE visual_interpretation_review_events IS
    'Histórico imutável da segunda revisão humana das interpretações multimodais.';

COMMIT;
