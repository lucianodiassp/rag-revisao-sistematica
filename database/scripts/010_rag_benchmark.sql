BEGIN;

CREATE TABLE IF NOT EXISTS rag_golden_queries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES review_projects(id) ON DELETE CASCADE,
    question TEXT NOT NULL,
    expected_refusal BOOLEAN NOT NULL DEFAULT FALSE,
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (project_id, question),
    CHECK (length(btrim(question)) >= 5)
);

CREATE TABLE IF NOT EXISTS rag_golden_relevances (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    golden_query_id UUID NOT NULL REFERENCES rag_golden_queries(id) ON DELETE CASCADE,
    paper_id UUID NOT NULL REFERENCES deduplicated_papers(id) ON DELETE CASCADE,
    page_number INTEGER,
    relevance_grade INTEGER NOT NULL DEFAULT 2,
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CHECK (page_number IS NULL OR page_number > 0),
    CHECK (relevance_grade BETWEEN 1 AND 3)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_rag_golden_relevance_target
    ON rag_golden_relevances (
        golden_query_id,
        paper_id,
        COALESCE(page_number, 0)
    );

CREATE TABLE IF NOT EXISTS rag_golden_set_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES review_projects(id) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    set_jsonb JSONB NOT NULL,
    change_reason TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (project_id, version)
);

CREATE INDEX IF NOT EXISTS idx_rag_golden_queries_project
    ON rag_golden_queries(project_id, created_at);
CREATE INDEX IF NOT EXISTS idx_rag_golden_relevances_query
    ON rag_golden_relevances(golden_query_id);
CREATE INDEX IF NOT EXISTS idx_rag_golden_versions_project
    ON rag_golden_set_versions(project_id, version DESC);

COMMIT;
