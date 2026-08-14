BEGIN;

CREATE TABLE IF NOT EXISTS deduplication_decisions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES review_projects(id) ON DELETE CASCADE,
    retrieved_record_id UUID NOT NULL REFERENCES retrieved_records(id) ON DELETE CASCADE,
    candidate_paper_id UUID REFERENCES deduplicated_papers(id) ON DELETE SET NULL,
    result_paper_id UUID REFERENCES deduplicated_papers(id) ON DELETE SET NULL,
    rule_code VARCHAR(50) NOT NULL,
    similarity_score NUMERIC(5,4) NOT NULL,
    system_action VARCHAR(50) NOT NULL,
    explanation TEXT NOT NULL,
    evidence_jsonb JSONB NOT NULL,
    incoming_record_jsonb JSONB NOT NULL,
    review_status VARCHAR(30) NOT NULL DEFAULT 'automatic',
    human_decision VARCHAR(30),
    review_justification TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reviewed_at TIMESTAMP WITH TIME ZONE,
    UNIQUE (retrieved_record_id),
    CHECK (rule_code IN ('doi_exact', 'title_exact', 'title_similar', 'no_candidate')),
    CHECK (similarity_score BETWEEN 0 AND 1),
    CHECK (system_action IN ('auto_create', 'auto_merge', 'pending_review')),
    CHECK (review_status IN ('automatic', 'pending', 'reviewed')),
    CHECK (human_decision IS NULL OR human_decision IN ('merge', 'keep_separate')),
    CHECK (review_justification IS NULL OR length(btrim(review_justification)) >= 5)
);

CREATE INDEX IF NOT EXISTS idx_deduplication_decisions_project
    ON deduplication_decisions(project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_deduplication_decisions_pending
    ON deduplication_decisions(project_id, review_status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_deduplicated_papers_project_doi
    ON deduplicated_papers(project_id, canonical_doi);

COMMIT;
