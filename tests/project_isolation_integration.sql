\set ON_ERROR_STOP on

BEGIN;

INSERT INTO review_projects (id, title, question, criteria_jsonb)
VALUES
    ('10000000-0000-0000-0000-000000000001', 'Teste A', 'Pergunta A', '{}'::jsonb),
    ('20000000-0000-0000-0000-000000000002', 'Teste B', 'Pergunta B', '{}'::jsonb);

INSERT INTO deduplicated_papers
    (id, project_id, canonical_doi, title, abstract, merged_sources_jsonb)
VALUES
    (
        '11000000-0000-0000-0000-000000000001',
        '10000000-0000-0000-0000-000000000001',
        '10.0000/shared',
        'Mesmo artigo lógico',
        'Conteúdo exclusivo do projeto A',
        '{"sources": ["Teste A"]}'::jsonb
    ),
    (
        '22000000-0000-0000-0000-000000000002',
        '20000000-0000-0000-0000-000000000002',
        '10.0000/shared',
        'Mesmo artigo lógico',
        'Conteúdo exclusivo do projeto B',
        '{"sources": ["Teste B"]}'::jsonb
    );

INSERT INTO paper_chunks (paper_id, chunk_type, chunk_text)
VALUES
    ('11000000-0000-0000-0000-000000000001', 'abstract', 'chunk do projeto A'),
    ('22000000-0000-0000-0000-000000000002', 'abstract', 'chunk do projeto B');

DO $$
DECLARE
    artigos_a INTEGER;
    artigos_b INTEGER;
    chunks_a INTEGER;
    chunks_b INTEGER;
BEGIN
    SELECT COUNT(*) INTO artigos_a
    FROM deduplicated_papers
    WHERE project_id = '10000000-0000-0000-0000-000000000001';

    SELECT COUNT(*) INTO artigos_b
    FROM deduplicated_papers
    WHERE project_id = '20000000-0000-0000-0000-000000000002';

    SELECT COUNT(*) INTO chunks_a
    FROM paper_chunks pc
    JOIN deduplicated_papers p ON p.id = pc.paper_id
    WHERE p.project_id = '10000000-0000-0000-0000-000000000001'
      AND pc.chunk_text = 'chunk do projeto A';

    SELECT COUNT(*) INTO chunks_b
    FROM paper_chunks pc
    JOIN deduplicated_papers p ON p.id = pc.paper_id
    WHERE p.project_id = '20000000-0000-0000-0000-000000000002'
      AND pc.chunk_text = 'chunk do projeto B';

    IF artigos_a <> 1 OR artigos_b <> 1 OR chunks_a <> 1 OR chunks_b <> 1 THEN
        RAISE EXCEPTION 'Falha no isolamento por projeto';
    END IF;
END $$;

ROLLBACK;

SELECT
    (SELECT COUNT(*) FROM search_queries WHERE project_id IS NULL) AS buscas_sem_projeto,
    (SELECT COUNT(*) FROM retrieved_records WHERE project_id IS NULL) AS registros_sem_projeto,
    (SELECT COUNT(*) FROM deduplicated_papers WHERE project_id IS NULL) AS artigos_sem_projeto,
    (SELECT COUNT(*) FROM agent_interactions WHERE project_id IS NULL) AS logs_sem_projeto,
    (SELECT COUNT(*) FROM evaluation_runs WHERE project_id IS NULL) AS avaliacoes_sem_projeto;
