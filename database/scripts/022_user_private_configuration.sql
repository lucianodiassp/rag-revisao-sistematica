BEGIN;

-- Uma instalação já atualizada normalmente possui uma única identidade ativa.
-- Nesse caso, converte o escopo legado sem tocar no conteúdo cifrado das chaves.
WITH sole_user AS (
    SELECT (ARRAY_AGG(id ORDER BY id))[1] AS id
    FROM application_users
    WHERE status = 'active'
    HAVING COUNT(*) = 1
)
UPDATE ai_provider_credentials AS legacy
SET scope_type = 'user', owner_user_id = sole_user.id,
    updated_at = CURRENT_TIMESTAMP
FROM sole_user
WHERE legacy.scope_type = 'installation'
  AND legacy.scope_id IS NULL
  AND legacy.owner_user_id IS NULL
  AND NOT EXISTS (
      SELECT 1 FROM ai_provider_credentials AS personal
      WHERE personal.provider_code = legacy.provider_code
        AND personal.scope_type = 'user'
        AND personal.scope_id IS NULL
        AND personal.owner_user_id = sole_user.id
        AND personal.is_active = legacy.is_active
  );

WITH sole_user AS (
    SELECT (ARRAY_AGG(id ORDER BY id))[1] AS id
    FROM application_users
    WHERE status = 'active'
    HAVING COUNT(*) = 1
)
UPDATE ai_model_settings AS legacy
SET scope_type = 'user', owner_user_id = sole_user.id,
    updated_at = CURRENT_TIMESTAMP
FROM sole_user
WHERE legacy.scope_type = 'installation'
  AND legacy.scope_id IS NULL
  AND legacy.owner_user_id IS NULL
  AND NOT EXISTS (
      SELECT 1 FROM ai_model_settings AS personal
      WHERE personal.task_type = legacy.task_type
        AND personal.scope_type = 'user'
        AND personal.scope_id IS NULL
        AND personal.owner_user_id = sole_user.id
        AND personal.is_active = legacy.is_active
  );

WITH sole_user AS (
    SELECT (ARRAY_AGG(id ORDER BY id))[1] AS id
    FROM application_users
    WHERE status = 'active'
    HAVING COUNT(*) = 1
)
UPDATE bibliographic_source_settings AS legacy
SET scope_type = 'user', owner_user_id = sole_user.id,
    updated_at = CURRENT_TIMESTAMP
FROM sole_user
WHERE legacy.scope_type = 'installation'
  AND legacy.scope_id IS NULL
  AND legacy.owner_user_id IS NULL
  AND NOT EXISTS (
      SELECT 1 FROM bibliographic_source_settings AS personal
      WHERE personal.source_code = legacy.source_code
        AND personal.scope_type = 'user'
        AND personal.scope_id IS NULL
        AND personal.owner_user_id = sole_user.id
  );

WITH sole_user AS (
    SELECT (ARRAY_AGG(id ORDER BY id))[1] AS id
    FROM application_users
    WHERE status = 'active'
    HAVING COUNT(*) = 1
)
UPDATE bibliographic_source_credentials AS legacy
SET scope_type = 'user', owner_user_id = sole_user.id,
    updated_at = CURRENT_TIMESTAMP
FROM sole_user
WHERE legacy.scope_type = 'installation'
  AND legacy.scope_id IS NULL
  AND legacy.owner_user_id IS NULL
  AND NOT EXISTS (
      SELECT 1 FROM bibliographic_source_credentials AS personal
      WHERE personal.source_code = legacy.source_code
        AND personal.scope_type = 'user'
        AND personal.scope_id IS NULL
        AND personal.owner_user_id = sole_user.id
        AND personal.is_active = legacy.is_active
  );

WITH sole_user AS (
    SELECT (ARRAY_AGG(id ORDER BY id))[1] AS id
    FROM application_users
    WHERE status = 'active'
    HAVING COUNT(*) = 1
)
UPDATE ai_configuration_audit AS audit
SET scope_type = 'user', owner_user_id = sole_user.id
FROM sole_user
WHERE audit.scope_type = 'installation'
  AND audit.scope_id IS NULL
  AND audit.owner_user_id IS NULL;

WITH sole_user AS (
    SELECT (ARRAY_AGG(id ORDER BY id))[1] AS id
    FROM application_users
    WHERE status = 'active'
    HAVING COUNT(*) = 1
)
UPDATE bibliographic_configuration_audit AS audit
SET scope_type = 'user', owner_user_id = sole_user.id
FROM sole_user
WHERE audit.scope_type = 'installation'
  AND audit.scope_id IS NULL
  AND audit.owner_user_id IS NULL;

ALTER TABLE ai_provider_credentials
    DROP CONSTRAINT IF EXISTS ai_provider_credentials_owner_user_id_fkey;
ALTER TABLE ai_provider_credentials
    ADD CONSTRAINT ai_provider_credentials_owner_user_id_fkey
    FOREIGN KEY (owner_user_id) REFERENCES application_users(id) ON DELETE CASCADE;
ALTER TABLE ai_model_settings
    DROP CONSTRAINT IF EXISTS ai_model_settings_owner_user_id_fkey;
ALTER TABLE ai_model_settings
    ADD CONSTRAINT ai_model_settings_owner_user_id_fkey
    FOREIGN KEY (owner_user_id) REFERENCES application_users(id) ON DELETE CASCADE;
ALTER TABLE ai_configuration_audit
    DROP CONSTRAINT IF EXISTS ai_configuration_audit_owner_user_id_fkey;
ALTER TABLE ai_configuration_audit
    ADD CONSTRAINT ai_configuration_audit_owner_user_id_fkey
    FOREIGN KEY (owner_user_id) REFERENCES application_users(id) ON DELETE CASCADE;

ALTER TABLE bibliographic_source_settings
    DROP CONSTRAINT IF EXISTS bibliographic_source_settings_owner_user_id_fkey;
ALTER TABLE bibliographic_source_settings
    ADD CONSTRAINT bibliographic_source_settings_owner_user_id_fkey
    FOREIGN KEY (owner_user_id) REFERENCES application_users(id) ON DELETE CASCADE;
ALTER TABLE bibliographic_source_credentials
    DROP CONSTRAINT IF EXISTS bibliographic_source_credentials_owner_user_id_fkey;
ALTER TABLE bibliographic_source_credentials
    ADD CONSTRAINT bibliographic_source_credentials_owner_user_id_fkey
    FOREIGN KEY (owner_user_id) REFERENCES application_users(id) ON DELETE CASCADE;
ALTER TABLE bibliographic_configuration_audit
    DROP CONSTRAINT IF EXISTS bibliographic_configuration_audit_owner_user_id_fkey;
ALTER TABLE bibliographic_configuration_audit
    ADD CONSTRAINT bibliographic_configuration_audit_owner_user_id_fkey
    FOREIGN KEY (owner_user_id) REFERENCES application_users(id) ON DELETE CASCADE;

ALTER TABLE ai_provider_credentials
    DROP CONSTRAINT IF EXISTS ai_provider_credentials_private_scope_check;
ALTER TABLE ai_provider_credentials
    ADD CONSTRAINT ai_provider_credentials_private_scope_check CHECK (
        (scope_type = 'installation' AND scope_id IS NULL AND owner_user_id IS NULL)
        OR (scope_type = 'user' AND scope_id IS NULL AND owner_user_id IS NOT NULL)
        OR (scope_type = 'team' AND scope_id IS NOT NULL)
    );
ALTER TABLE ai_model_settings
    DROP CONSTRAINT IF EXISTS ai_model_settings_private_scope_check;
ALTER TABLE ai_model_settings
    ADD CONSTRAINT ai_model_settings_private_scope_check CHECK (
        (scope_type = 'installation' AND scope_id IS NULL AND owner_user_id IS NULL)
        OR (scope_type = 'user' AND scope_id IS NULL AND owner_user_id IS NOT NULL)
        OR (scope_type = 'team' AND scope_id IS NOT NULL)
    );
ALTER TABLE ai_configuration_audit
    DROP CONSTRAINT IF EXISTS ai_configuration_audit_private_scope_check;
ALTER TABLE ai_configuration_audit
    ADD CONSTRAINT ai_configuration_audit_private_scope_check CHECK (
        (scope_type = 'installation' AND scope_id IS NULL AND owner_user_id IS NULL)
        OR (scope_type = 'user' AND scope_id IS NULL AND owner_user_id IS NOT NULL)
        OR (scope_type = 'team' AND scope_id IS NOT NULL)
    );

ALTER TABLE bibliographic_source_settings
    DROP CONSTRAINT IF EXISTS bibliographic_source_settings_private_scope_check;
ALTER TABLE bibliographic_source_settings
    ADD CONSTRAINT bibliographic_source_settings_private_scope_check CHECK (
        (scope_type = 'installation' AND scope_id IS NULL AND owner_user_id IS NULL)
        OR (scope_type = 'user' AND scope_id IS NULL AND owner_user_id IS NOT NULL)
        OR (scope_type = 'team' AND scope_id IS NOT NULL)
    );
ALTER TABLE bibliographic_source_credentials
    DROP CONSTRAINT IF EXISTS bibliographic_source_credentials_private_scope_check;
ALTER TABLE bibliographic_source_credentials
    ADD CONSTRAINT bibliographic_source_credentials_private_scope_check CHECK (
        (scope_type = 'installation' AND scope_id IS NULL AND owner_user_id IS NULL)
        OR (scope_type = 'user' AND scope_id IS NULL AND owner_user_id IS NOT NULL)
        OR (scope_type = 'team' AND scope_id IS NOT NULL)
    );
ALTER TABLE bibliographic_configuration_audit
    DROP CONSTRAINT IF EXISTS bibliographic_configuration_audit_private_scope_check;
ALTER TABLE bibliographic_configuration_audit
    ADD CONSTRAINT bibliographic_configuration_audit_private_scope_check CHECK (
        (scope_type = 'installation' AND scope_id IS NULL AND owner_user_id IS NULL)
        OR (scope_type = 'user' AND scope_id IS NULL AND owner_user_id IS NOT NULL)
        OR (scope_type = 'team' AND scope_id IS NOT NULL)
    );

COMMENT ON COLUMN ai_provider_credentials.owner_user_id IS
    'Proprietário exclusivo da credencial quando scope_type=user.';
COMMENT ON COLUMN bibliographic_source_credentials.owner_user_id IS
    'Proprietário exclusivo da credencial quando scope_type=user.';

COMMIT;
