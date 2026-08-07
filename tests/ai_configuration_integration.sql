\set ON_ERROR_STOP on

BEGIN;

INSERT INTO ai_provider_credentials
    (id, provider_code, label, encrypted_secret, secret_hint,
     scope_type, validation_status)
VALUES (
    '40000000-0000-0000-0000-000000000004',
    'google_gemini',
    'Credencial transacional',
    'conteudo-cifrado-de-teste',
    '••••1234',
    'installation',
    'valid'
);

INSERT INTO ai_model_settings
    (task_type, provider_code, credential_id, model_name,
     parameters_jsonb, scope_type)
VALUES
    (
        'report',
        'google_gemini',
        '40000000-0000-0000-0000-000000000004',
        'gemini-test-report',
        '{"temperature": 0.2}'::jsonb,
        'installation'
    ),
    (
        'embedding',
        'google_gemini',
        '40000000-0000-0000-0000-000000000004',
        'gemini-test-embedding',
        '{}'::jsonb,
        'installation'
    );

INSERT INTO ai_configuration_audit (action, changes_jsonb)
VALUES (
    'integration_test',
    '{"provider_code":"google_gemini","secret_hint":"••••1234"}'::jsonb
);

DO $$
DECLARE
    credenciais INTEGER;
    modelos INTEGER;
    auditorias_com_segredo INTEGER;
BEGIN
    SELECT COUNT(*) INTO credenciais
    FROM ai_provider_credentials
    WHERE scope_type = 'installation' AND owner_user_id IS NULL;

    SELECT COUNT(*) INTO modelos
    FROM ai_model_settings
    WHERE scope_type = 'installation'
      AND task_type IN ('report', 'embedding');

    SELECT COUNT(*) INTO auditorias_com_segredo
    FROM ai_configuration_audit
    WHERE changes_jsonb::text LIKE '%conteudo-cifrado-de-teste%';

    IF credenciais <> 1 OR modelos <> 2 OR auditorias_com_segredo <> 0 THEN
        RAISE EXCEPTION 'Falha no armazenamento local de configuração de IA';
    END IF;
END $$;

ROLLBACK;
