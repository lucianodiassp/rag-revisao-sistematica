BEGIN;

ALTER TABLE screening_decisions
    ADD COLUMN IF NOT EXISTS exclusion_reason_code VARCHAR(50);

UPDATE screening_decisions
SET exclusion_reason_code = 'other'
WHERE human_decision = 'Excluir'
  AND exclusion_reason_code IS NULL;

UPDATE screening_decisions
SET exclusion_reason_code = NULL
WHERE human_decision IS DISTINCT FROM 'Excluir';

ALTER TABLE screening_decisions
    DROP CONSTRAINT IF EXISTS screening_decisions_exclusion_reason_code_check,
    DROP CONSTRAINT IF EXISTS screening_decisions_exclusion_reason_consistency_check;

ALTER TABLE screening_decisions
    ADD CONSTRAINT screening_decisions_exclusion_reason_code_check
    CHECK (exclusion_reason_code IS NULL OR exclusion_reason_code IN (
        'population_mismatch', 'intervention_mismatch', 'outcome_mismatch',
        'study_design_mismatch', 'publication_type', 'language', 'date_range',
        'insufficient_information', 'restricted_access', 'pdf_not_found',
        'metadata_mismatch', 'other'
    )),
    ADD CONSTRAINT screening_decisions_exclusion_reason_consistency_check
    CHECK (
        (human_decision = 'Excluir' AND exclusion_reason_code IS NOT NULL)
        OR (human_decision IS DISTINCT FROM 'Excluir' AND exclusion_reason_code IS NULL)
    );

CREATE TABLE IF NOT EXISTS prisma_flow_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES review_projects(id) ON DELETE CASCADE,
    snapshot_version INTEGER NOT NULL,
    protocol_version INTEGER NOT NULL,
    metrics_jsonb JSONB NOT NULL,
    source_counts_jsonb JSONB NOT NULL,
    exclusion_reasons_jsonb JSONB NOT NULL,
    interpretation_jsonb JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (project_id, snapshot_version)
);

CREATE INDEX IF NOT EXISTS idx_prisma_snapshots_project
    ON prisma_flow_snapshots(project_id, snapshot_version DESC);

COMMIT;
