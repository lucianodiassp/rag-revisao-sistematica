BEGIN;

ALTER TABLE review_projects
    ADD COLUMN IF NOT EXISTS archived_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE review_projects
    ADD COLUMN IF NOT EXISTS archived_reason TEXT;

ALTER TABLE review_projects
    DROP CONSTRAINT IF EXISTS review_projects_archived_reason_check;
ALTER TABLE review_projects
    ADD CONSTRAINT review_projects_archived_reason_check CHECK (
        (archived_at IS NULL AND archived_reason IS NULL)
        OR
        (archived_at IS NOT NULL AND length(btrim(archived_reason)) >= 10)
    );

CREATE TABLE IF NOT EXISTS project_lifecycle_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    target_project_id UUID NOT NULL,
    project_title VARCHAR(255) NOT NULL,
    action VARCHAR(20) NOT NULL,
    actor_identifier VARCHAR(200) NOT NULL,
    details_jsonb JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (action IN ('archived', 'restored', 'deleted')),
    CHECK (length(btrim(project_title)) >= 1),
    CHECK (length(btrim(actor_identifier)) >= 1),
    CHECK (jsonb_typeof(details_jsonb) = 'object')
);

CREATE INDEX IF NOT EXISTS idx_review_projects_active
    ON review_projects(updated_at DESC, created_at DESC)
    WHERE archived_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_project_lifecycle_events_target
    ON project_lifecycle_events(target_project_id, created_at DESC);

COMMENT ON COLUMN review_projects.archived_at IS
    'Arquivamento reversível; projetos arquivados não aparecem no seletor operacional.';
COMMENT ON TABLE project_lifecycle_events IS
    'Recibos imutáveis de arquivamento, restauração e exclusão; não possui FK para sobreviver à exclusão do projeto.';

COMMIT;
