BEGIN;

CREATE TABLE IF NOT EXISTS screening_reassessments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES review_projects(id) ON DELETE CASCADE,
    screening_decision_id UUID NOT NULL REFERENCES screening_decisions(id) ON DELETE CASCADE,
    paper_id UUID NOT NULL REFERENCES deduplicated_papers(id) ON DELETE CASCADE,
    action VARCHAR(50) NOT NULL,
    reason_code VARCHAR(50) NOT NULL,
    reason TEXT NOT NULL,
    previous_human_decision VARCHAR(50) NOT NULL,
    previous_justification TEXT,
    resulting_human_decision VARCHAR(50),
    origin VARCHAR(50) NOT NULL DEFAULT 'pdf_management',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CHECK (action IN ('return_to_screening', 'exclude')),
    CHECK (reason_code IN ('restricted_access', 'pdf_not_found', 'metadata_mismatch', 'other')),
    CHECK (origin IN ('pdf_management')),
    CHECK (length(btrim(reason)) >= 5)
);

CREATE INDEX IF NOT EXISTS idx_screening_reassessments_project
    ON screening_reassessments(project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_screening_reassessments_paper
    ON screening_reassessments(paper_id, created_at DESC);

COMMIT;
