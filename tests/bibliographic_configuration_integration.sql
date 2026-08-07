\set ON_ERROR_STOP on

BEGIN;

INSERT INTO bibliographic_source_settings
    (source_code, is_enabled, contact_email, tool_name,
     request_timeout_seconds, max_retries)
VALUES
    ('openalex', TRUE, 'teste@instituicao.br', 'rag-teste', 20, 2),
    ('semantic_scholar', FALSE, NULL, 'rag-teste', 30, 3),
    ('pubmed', TRUE, 'teste@instituicao.br', 'rag-teste', 40, 4);

INSERT INTO bibliographic_source_credentials
    (id, source_code, label, encrypted_secret, secret_hint, validation_status)
VALUES (
    '50000000-0000-0000-0000-000000000005',
    'openalex',
    'Credencial transacional',
    'conteudo-cifrado-de-teste',
    '••••1234',
    'valid'
);

INSERT INTO bibliographic_configuration_audit
    (action, source_code, changes_jsonb)
VALUES (
    'integration_test',
    'openalex',
    '{"secret_hint":"••••1234","is_enabled":true}'::jsonb
);

DO $$
DECLARE
    configuracoes INTEGER;
    credenciais INTEGER;
    auditorias_com_segredo INTEGER;
BEGIN
    SELECT COUNT(*) INTO configuracoes
    FROM bibliographic_source_settings
    WHERE scope_type = 'installation';

    SELECT COUNT(*) INTO credenciais
    FROM bibliographic_source_credentials
    WHERE scope_type = 'installation' AND is_active = TRUE;

    SELECT COUNT(*) INTO auditorias_com_segredo
    FROM bibliographic_configuration_audit
    WHERE changes_jsonb::text LIKE '%conteudo-cifrado-de-teste%';

    IF configuracoes <> 3 OR credenciais <> 1 OR auditorias_com_segredo <> 0 THEN
        RAISE EXCEPTION 'Falha na configuração central das fontes bibliográficas';
    END IF;
END $$;

ROLLBACK;
