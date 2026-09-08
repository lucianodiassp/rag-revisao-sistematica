BEGIN;

CREATE TABLE IF NOT EXISTS project_invitations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES review_projects(id) ON DELETE CASCADE,
    email VARCHAR(320) NOT NULL,
    role VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    invited_by_user_id UUID REFERENCES application_users(id) ON DELETE SET NULL,
    accepted_by_user_id UUID REFERENCES application_users(id) ON DELETE SET NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    accepted_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (email = lower(email)),
    CHECK (length(btrim(email)) >= 3),
    CHECK (role IN ('editor', 'viewer')),
    CHECK (status IN ('pending', 'accepted', 'revoked', 'expired')),
    CHECK (
        (status = 'accepted' AND accepted_by_user_id IS NOT NULL AND accepted_at IS NOT NULL)
        OR status <> 'accepted'
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_project_invitations_pending_email
    ON project_invitations(project_id, lower(email))
    WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_project_invitations_email_status
    ON project_invitations(lower(email), status, expires_at);
CREATE INDEX IF NOT EXISTS idx_project_invitations_project
    ON project_invitations(project_id, created_at DESC);

-- Auditoria separada do conteúdo científico. O identificador do projeto não tem
-- FK para que o recibo continue disponível depois de uma exclusão permanente.
CREATE TABLE IF NOT EXISTS project_access_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    target_project_id UUID,
    project_title VARCHAR(255),
    action VARCHAR(40) NOT NULL,
    actor_user_id UUID REFERENCES application_users(id) ON DELETE SET NULL,
    target_user_id UUID REFERENCES application_users(id) ON DELETE SET NULL,
    target_email VARCHAR(320),
    previous_role VARCHAR(20),
    new_role VARCHAR(20),
    details_jsonb JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (action IN (
        'invited', 'invitation_accepted', 'invitation_revoked',
        'role_changed', 'membership_revoked', 'ownership_transferred',
        'user_enabled', 'user_disabled'
    )),
    CHECK (target_email IS NULL OR target_email = lower(target_email)),
    CHECK (previous_role IS NULL OR previous_role IN ('owner', 'editor', 'viewer')),
    CHECK (new_role IS NULL OR new_role IN ('owner', 'editor', 'viewer')),
    CHECK (jsonb_typeof(details_jsonb) = 'object')
);

CREATE INDEX IF NOT EXISTS idx_project_access_events_project
    ON project_access_events(target_project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_project_access_events_target_user
    ON project_access_events(target_user_id, created_at DESC);

COMMENT ON TABLE project_invitations IS
    'Pré-autorização por e-mail verificado; não armazena token ou senha.';
COMMENT ON TABLE project_access_events IS
    'Recibos de administração de acesso e titularidade, sem conteúdo científico.';

COMMIT;
