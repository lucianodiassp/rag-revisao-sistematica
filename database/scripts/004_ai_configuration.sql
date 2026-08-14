BEGIN;

CREATE TABLE IF NOT EXISTS ai_provider_credentials (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    provider_code VARCHAR(50) NOT NULL,
    label VARCHAR(100) NOT NULL,
    encrypted_secret TEXT NOT NULL,
    secret_hint VARCHAR(20) NOT NULL,
    scope_type VARCHAR(30) NOT NULL DEFAULT 'installation',
    scope_id UUID,
    owner_user_id UUID,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    validation_status VARCHAR(30) NOT NULL DEFAULT 'untested',
    last_validated_at TIMESTAMP WITH TIME ZONE,
    validation_error TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CHECK (scope_type IN ('installation', 'user', 'team')),
    CHECK (validation_status IN ('untested', 'valid', 'invalid'))
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_credentials_active_scope
    ON ai_provider_credentials (
        provider_code,
        scope_type,
        COALESCE(scope_id, '00000000-0000-0000-0000-000000000000'::uuid),
        COALESCE(owner_user_id, '00000000-0000-0000-0000-000000000000'::uuid)
    )
    WHERE is_active = TRUE;

CREATE TABLE IF NOT EXISTS ai_model_settings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_type VARCHAR(50) NOT NULL,
    provider_code VARCHAR(50) NOT NULL,
    credential_id UUID REFERENCES ai_provider_credentials(id) ON DELETE SET NULL,
    model_name VARCHAR(150) NOT NULL,
    parameters_jsonb JSONB NOT NULL DEFAULT '{}'::jsonb,
    embedding_dimensions INTEGER,
    scope_type VARCHAR(30) NOT NULL DEFAULT 'installation',
    scope_id UUID,
    owner_user_id UUID,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CHECK (task_type IN (
        'formulation', 'screening', 'rag', 'reranking', 'evaluation',
        'extraction', 'report', 'embedding'
    )),
    CHECK (scope_type IN ('installation', 'user', 'team')),
    CHECK (embedding_dimensions IS NULL OR embedding_dimensions > 0)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_model_settings_active_scope
    ON ai_model_settings (
        task_type,
        scope_type,
        COALESCE(scope_id, '00000000-0000-0000-0000-000000000000'::uuid),
        COALESCE(owner_user_id, '00000000-0000-0000-0000-000000000000'::uuid)
    )
    WHERE is_active = TRUE;

CREATE TABLE IF NOT EXISTS ai_configuration_audit (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    action VARCHAR(100) NOT NULL,
    scope_type VARCHAR(30) NOT NULL DEFAULT 'installation',
    scope_id UUID,
    owner_user_id UUID,
    changes_jsonb JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CHECK (scope_type IN ('installation', 'user', 'team'))
);

CREATE INDEX IF NOT EXISTS idx_ai_credentials_scope
    ON ai_provider_credentials(scope_type, scope_id, owner_user_id);
CREATE INDEX IF NOT EXISTS idx_ai_model_settings_scope
    ON ai_model_settings(scope_type, scope_id, owner_user_id);
CREATE INDEX IF NOT EXISTS idx_ai_configuration_audit_created
    ON ai_configuration_audit(created_at DESC);

COMMIT;
