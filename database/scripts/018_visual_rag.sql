BEGIN;

CREATE TABLE IF NOT EXISTS project_rag_settings (
    project_id UUID PRIMARY KEY REFERENCES review_projects(id) ON DELETE CASCADE,
    visual_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision > 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE project_rag_settings IS
    'Opt-in por projeto para interpretações visuais revisadas no Assistente; ausência de registro significa desativado.';

ALTER TABLE rag_golden_relevances ADD COLUMN IF NOT EXISTS artifact_id UUID
    REFERENCES visual_artifacts(id) ON DELETE CASCADE;
-- Mantém o nome: a migração 010 reaplicada não recria a antiga restrição.
DROP INDEX IF EXISTS uq_rag_golden_relevance_target;
CREATE UNIQUE INDEX uq_rag_golden_relevance_target ON rag_golden_relevances (
    golden_query_id, paper_id, COALESCE(page_number, 0),
    COALESCE(artifact_id, '00000000-0000-0000-0000-000000000000'::uuid)
);

COMMIT;
