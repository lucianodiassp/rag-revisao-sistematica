BEGIN;

ALTER TABLE application_users
    ADD COLUMN IF NOT EXISTS is_operator BOOLEAN NOT NULL DEFAULT FALSE;

-- A instalação privada atual possui uma única identidade ativa. Preservar para
-- ela as operações globais já disponíveis antes da introdução deste papel.
WITH sole_user AS (
    SELECT (ARRAY_AGG(id ORDER BY id))[1] AS id
    FROM application_users
    WHERE status = 'active'
    HAVING COUNT(*) = 1
)
UPDATE application_users AS application_user
SET is_operator = TRUE,
    updated_at = CURRENT_TIMESTAMP
FROM sole_user
WHERE application_user.id = sole_user.id
  AND application_user.is_operator = FALSE;

CREATE INDEX IF NOT EXISTS idx_application_users_operator
    ON application_users(status, is_operator)
    WHERE is_operator = TRUE;

COMMENT ON COLUMN application_users.is_operator IS
    'Autoriza operações globais da instalação; não substitui papéis por projeto.';

COMMIT;
