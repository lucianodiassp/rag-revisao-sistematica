\set ON_ERROR_STOP on

BEGIN;

INSERT INTO review_projects
    (id, title, question, criteria_jsonb, status, protocol_version)
VALUES
    ('71000000-0000-0000-0000-000000000001',
     'Teste de reavaliação',
     'Pergunta de teste',
     '{}'::jsonb,
     'screening',
     1);

INSERT INTO deduplicated_papers
    (id, project_id, title, abstract, merged_sources_jsonb)
VALUES
    ('71000000-0000-0000-0000-000000000002',
     '71000000-0000-0000-0000-000000000001',
     'Artigo de acesso restrito',
     'Resumo de teste',
     '{"sources":["OpenAlex"]}'::jsonb);

INSERT INTO screening_decisions
    (id, paper_id, suggested_decision, human_decision, rationale_jsonb, justification)
VALUES
    ('71000000-0000-0000-0000-000000000003',
     '71000000-0000-0000-0000-000000000002',
     'Incluir',
     'Incluir',
     '{"justification":"Atende aos critérios"}'::jsonb,
     'Inclusão inicial');

UPDATE screening_decisions
SET human_decision = NULL, justification = NULL, reviewed_at = NULL
WHERE id = '71000000-0000-0000-0000-000000000003';

INSERT INTO screening_reassessments
    (project_id, screening_decision_id, paper_id, action, reason_code, reason,
     previous_human_decision, previous_justification, resulting_human_decision)
VALUES
    ('71000000-0000-0000-0000-000000000001',
     '71000000-0000-0000-0000-000000000003',
     '71000000-0000-0000-0000-000000000002',
     'return_to_screening',
     'restricted_access',
     'Acesso apenas mediante pagamento.',
     'Incluir',
     'Inclusão inicial',
     NULL);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM screening_decisions
        WHERE id = '71000000-0000-0000-0000-000000000003'
          AND human_decision IS NULL
    ) THEN
        RAISE EXCEPTION 'O artigo não retornou à triagem';
    END IF;
END $$;

UPDATE screening_decisions
SET human_decision = 'Incluir', justification = 'Reincluído', reviewed_at = CURRENT_TIMESTAMP
WHERE id = '71000000-0000-0000-0000-000000000003';

UPDATE screening_decisions
SET human_decision = 'Excluir',
    justification = 'PDF não obtido legalmente.',
    reviewed_at = CURRENT_TIMESTAMP
WHERE id = '71000000-0000-0000-0000-000000000003';

INSERT INTO screening_reassessments
    (project_id, screening_decision_id, paper_id, action, reason_code, reason,
     previous_human_decision, previous_justification, resulting_human_decision)
VALUES
    ('71000000-0000-0000-0000-000000000001',
     '71000000-0000-0000-0000-000000000003',
     '71000000-0000-0000-0000-000000000002',
     'exclude',
     'pdf_not_found',
     'PDF não obtido legalmente.',
     'Incluir',
     'Reincluído',
     'Excluir');

DO $$
BEGIN
    IF (SELECT human_decision FROM screening_decisions
        WHERE id = '71000000-0000-0000-0000-000000000003') <> 'Excluir' THEN
        RAISE EXCEPTION 'O artigo não foi excluído';
    END IF;
    IF (SELECT count(*) FROM screening_reassessments
        WHERE paper_id = '71000000-0000-0000-0000-000000000002') <> 2 THEN
        RAISE EXCEPTION 'O histórico de reavaliações está incompleto';
    END IF;
END $$;

ROLLBACK;
