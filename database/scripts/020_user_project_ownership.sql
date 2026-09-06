BEGIN;

CREATE TABLE IF NOT EXISTS application_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    identity_provider VARCHAR(255) NOT NULL,
    subject VARCHAR(512) NOT NULL,
    email VARCHAR(320),
    display_name VARCHAR(255) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    last_login_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (identity_provider, subject),
    CHECK (status IN ('active', 'disabled')),
    CHECK (email IS NULL OR email = lower(email)),
    CHECK (length(btrim(identity_provider)) >= 1),
    CHECK (length(btrim(subject)) >= 1),
    CHECK (length(btrim(display_name)) >= 1)
);

CREATE TABLE IF NOT EXISTS project_memberships (
    project_id UUID NOT NULL REFERENCES review_projects(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES application_users(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (project_id, user_id),
    CHECK (role IN ('owner', 'editor', 'viewer'))
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_project_memberships_active_owner
    ON project_memberships(project_id)
    WHERE role = 'owner' AND is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_project_memberships_user
    ON project_memberships(user_id, is_active, role, project_id);
CREATE INDEX IF NOT EXISTS idx_application_users_email
    ON application_users(lower(email))
    WHERE email IS NOT NULL;

ALTER TABLE project_lifecycle_events
    ADD COLUMN IF NOT EXISTS owner_user_id UUID;
ALTER TABLE project_lifecycle_events
    DROP CONSTRAINT IF EXISTS project_lifecycle_events_owner_user_id_fkey;
ALTER TABLE project_lifecycle_events
    ADD CONSTRAINT project_lifecycle_events_owner_user_id_fkey
    FOREIGN KEY (owner_user_id) REFERENCES application_users(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_project_lifecycle_events_owner
    ON project_lifecycle_events(owner_user_id, created_at DESC);

COMMENT ON TABLE application_users IS
    'Identidades persistentes derivadas do sujeito estável do provedor OIDC ou do perfil local.';
COMMENT ON TABLE project_memberships IS
    'Associação de acesso preparada para propriedade e compartilhamento futuro de projetos.';
COMMENT ON COLUMN project_lifecycle_events.owner_user_id IS
    'Proprietário do recibo; permite preservar o histórico após a exclusão do projeto.';

COMMIT;
