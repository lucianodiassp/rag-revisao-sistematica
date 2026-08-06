BEGIN;

ALTER TABLE review_projects
    ADD COLUMN IF NOT EXISTS protocol_version INTEGER NOT NULL DEFAULT 1,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP;

CREATE TABLE IF NOT EXISTS review_protocol_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES review_projects(id) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    question TEXT NOT NULL,
    criteria_jsonb JSONB NOT NULL,
    change_reason TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (project_id, version)
);

ALTER TABLE retrieved_records
    ADD COLUMN IF NOT EXISTS search_query_id UUID REFERENCES search_queries(id) ON DELETE SET NULL;

DO $$
DECLARE
    legacy_project_id UUID;
BEGIN
    SELECT id INTO legacy_project_id
    FROM review_projects
    ORDER BY created_at
    LIMIT 1;

    IF legacy_project_id IS NULL AND (
        EXISTS (SELECT 1 FROM search_queries WHERE project_id IS NULL)
        OR EXISTS (SELECT 1 FROM retrieved_records WHERE project_id IS NULL)
        OR EXISTS (SELECT 1 FROM deduplicated_papers WHERE project_id IS NULL)
        OR EXISTS (SELECT 1 FROM agent_interactions WHERE project_id IS NULL)
        OR EXISTS (SELECT 1 FROM evaluation_runs WHERE project_id IS NULL)
    ) THEN
        INSERT INTO review_projects (title, question, criteria_jsonb, status)
        VALUES (
            'Projeto legado',
            'Configuração migrada da versão anterior',
            '{"pico": {}, "inclusion_criteria": [], "exclusion_criteria": [], "search_string": "", "audit_questions": []}'::jsonb,
            'draft_protocol'
        )
        RETURNING id INTO legacy_project_id;
    END IF;

    IF legacy_project_id IS NOT NULL THEN
        UPDATE search_queries SET project_id = legacy_project_id WHERE project_id IS NULL;
        UPDATE retrieved_records SET project_id = legacy_project_id WHERE project_id IS NULL;
        UPDATE deduplicated_papers SET project_id = legacy_project_id WHERE project_id IS NULL;
        UPDATE agent_interactions SET project_id = legacy_project_id WHERE project_id IS NULL;
        UPDATE evaluation_runs SET project_id = legacy_project_id WHERE project_id IS NULL;

        INSERT INTO review_protocol_versions
            (project_id, version, question, criteria_jsonb, change_reason)
        SELECT rp.id, rp.protocol_version, rp.question, rp.criteria_jsonb, 'Snapshot criado pela migração'
        FROM review_projects rp
        ON CONFLICT (project_id, version) DO NOTHING;
    END IF;
END $$;

ALTER TABLE search_queries ALTER COLUMN project_id SET NOT NULL;
ALTER TABLE retrieved_records ALTER COLUMN project_id SET NOT NULL;
ALTER TABLE deduplicated_papers ALTER COLUMN project_id SET NOT NULL;
ALTER TABLE agent_interactions ALTER COLUMN project_id SET NOT NULL;
ALTER TABLE evaluation_runs ALTER COLUMN project_id SET NOT NULL;

CREATE INDEX IF NOT EXISTS idx_search_queries_project ON search_queries(project_id);
CREATE INDEX IF NOT EXISTS idx_retrieved_records_project ON retrieved_records(project_id);
CREATE INDEX IF NOT EXISTS idx_deduplicated_papers_project ON deduplicated_papers(project_id);
CREATE INDEX IF NOT EXISTS idx_agent_interactions_project ON agent_interactions(project_id);
CREATE INDEX IF NOT EXISTS idx_evaluation_runs_project ON evaluation_runs(project_id);
CREATE INDEX IF NOT EXISTS idx_paper_chunks_paper ON paper_chunks(paper_id);
CREATE INDEX IF NOT EXISTS idx_embeddings_chunk ON embeddings_metadata(chunk_id);

COMMIT;
