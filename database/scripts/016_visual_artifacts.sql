BEGIN;

ALTER TABLE background_jobs
    DROP CONSTRAINT IF EXISTS background_jobs_job_type_check;
ALTER TABLE background_jobs
    ADD CONSTRAINT background_jobs_job_type_check CHECK (job_type IN (
        'bibliographic_search', 'pdf_indexing', 'evidence_extraction',
        'final_report', 'rag_benchmark', 'visual_cataloging'
    ));

CREATE TABLE IF NOT EXISTS visual_artifacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES review_projects(id) ON DELETE CASCADE,
    paper_id UUID NOT NULL REFERENCES deduplicated_papers(id) ON DELETE CASCADE,
    detection_key CHAR(64) NOT NULL,
    file_sha256 CHAR(64) NOT NULL,
    page_number INTEGER NOT NULL,
    artifact_type VARCHAR(20) NOT NULL,
    artifact_order INTEGER NOT NULL,
    caption TEXT,
    context_text TEXT,
    bbox_jsonb JSONB,
    detection_method VARCHAR(50) NOT NULL,
    detection_metadata_jsonb JSONB NOT NULL DEFAULT '{}'::jsonb,
    extracted_content_jsonb JSONB,
    review_status VARCHAR(20) NOT NULL DEFAULT 'pending',
    human_description TEXT,
    human_notes TEXT,
    reviewer_name VARCHAR(200),
    is_current BOOLEAN NOT NULL DEFAULT TRUE,
    detected_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reviewed_at TIMESTAMP WITH TIME ZONE,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (project_id, paper_id, detection_key),
    CHECK (length(detection_key) = 64),
    CHECK (length(file_sha256) = 64),
    CHECK (page_number > 0),
    CHECK (artifact_type IN ('figure', 'table')),
    CHECK (artifact_order > 0),
    CHECK (bbox_jsonb IS NULL OR (
        jsonb_typeof(bbox_jsonb) = 'array' AND jsonb_array_length(bbox_jsonb) = 4
    )),
    CHECK (detection_method IN (
        'embedded_image', 'table_structure', 'caption_only'
    )),
    CHECK (review_status IN ('pending', 'approved', 'corrected', 'rejected')),
    CHECK (human_description IS NULL OR length(btrim(human_description)) >= 10),
    CHECK (human_notes IS NULL OR length(btrim(human_notes)) >= 5)
);

CREATE TABLE IF NOT EXISTS visual_artifact_review_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES review_projects(id) ON DELETE CASCADE,
    artifact_id UUID NOT NULL REFERENCES visual_artifacts(id) ON DELETE CASCADE,
    action VARCHAR(20) NOT NULL,
    previous_jsonb JSONB NOT NULL,
    current_jsonb JSONB NOT NULL,
    reviewer_name VARCHAR(200) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (action IN ('approved', 'corrected', 'rejected')),
    CHECK (length(btrim(reviewer_name)) >= 2)
);

CREATE INDEX IF NOT EXISTS idx_visual_artifacts_project_status
    ON visual_artifacts(project_id, is_current, review_status, page_number);
CREATE INDEX IF NOT EXISTS idx_visual_artifacts_paper
    ON visual_artifacts(paper_id, page_number, artifact_order);
CREATE INDEX IF NOT EXISTS idx_visual_artifact_events_artifact
    ON visual_artifact_review_events(artifact_id, created_at);

COMMENT ON TABLE visual_artifacts IS
    'Candidatos visuais detectados em PDFs; não representam interpretação semântica por IA.';
COMMENT ON COLUMN visual_artifacts.detection_metadata_jsonb IS
    'Metadados técnicos do detector, incluindo semantic_interpretation=false nesta etapa.';
COMMENT ON TABLE visual_artifact_review_events IS
    'Histórico imutável das decisões humanas sobre candidatos do catálogo visual.';

COMMIT;
