BEGIN;

CREATE TABLE IF NOT EXISTS bibliographic_source_settings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_code VARCHAR(50) NOT NULL,
    is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    contact_email VARCHAR(255),
    tool_name VARCHAR(100) NOT NULL DEFAULT 'rag-revisao-sistematica',
    request_timeout_seconds INTEGER NOT NULL DEFAULT 30,
    max_retries INTEGER NOT NULL DEFAULT 3,
    scope_type VARCHAR(30) NOT NULL DEFAULT 'installation',
    scope_id UUID,
    owner_user_id UUID,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CHECK (source_code IN ('openalex', 'semantic_scholar', 'pubmed')),
    CHECK (scope_type IN ('installation', 'user', 'team')),
    CHECK (request_timeout_seconds BETWEEN 1 AND 120),
    CHECK (max_retries BETWEEN 1 AND 10)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_bibliographic_settings_scope
    ON bibliographic_source_settings (
        source_code,
        scope_type,
        COALESCE(scope_id, '00000000-0000-0000-0000-000000000000'::uuid),
        COALESCE(owner_user_id, '00000000-0000-0000-0000-000000000000'::uuid)
    );

CREATE TABLE IF NOT EXISTS bibliographic_source_credentials (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_code VARCHAR(50) NOT NULL,
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
    CHECK (source_code IN ('openalex', 'semantic_scholar', 'pubmed')),
    CHECK (scope_type IN ('installation', 'user', 'team')),
    CHECK (validation_status IN ('untested', 'valid', 'invalid'))
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_bibliographic_credentials_active_scope
    ON bibliographic_source_credentials (
        source_code,
        scope_type,
        COALESCE(scope_id, '00000000-0000-0000-0000-000000000000'::uuid),
        COALESCE(owner_user_id, '00000000-0000-0000-0000-000000000000'::uuid)
    )
    WHERE is_active = TRUE;

CREATE TABLE IF NOT EXISTS bibliographic_configuration_audit (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    action VARCHAR(100) NOT NULL,
    source_code VARCHAR(50),
    scope_type VARCHAR(30) NOT NULL DEFAULT 'installation',
    scope_id UUID,
    owner_user_id UUID,
    changes_jsonb JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CHECK (source_code IS NULL OR source_code IN ('openalex', 'semantic_scholar', 'pubmed')),
    CHECK (scope_type IN ('installation', 'user', 'team'))
);

CREATE INDEX IF NOT EXISTS idx_bibliographic_settings_scope
    ON bibliographic_source_settings(scope_type, scope_id, owner_user_id);
CREATE INDEX IF NOT EXISTS idx_bibliographic_credentials_scope
    ON bibliographic_source_credentials(scope_type, scope_id, owner_user_id);
CREATE INDEX IF NOT EXISTS idx_bibliographic_audit_created
    ON bibliographic_configuration_audit(created_at DESC);

COMMIT;
