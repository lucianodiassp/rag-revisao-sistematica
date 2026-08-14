BEGIN;

DO $$
BEGIN
    IF to_regclass('public.rag_golden_queries') IS NULL
       OR to_regclass('public.rag_golden_relevances') IS NULL
       OR to_regclass('public.rag_golden_set_versions') IS NULL THEN
        RAISE EXCEPTION 'Tabelas do benchmark RAG não encontradas';
    END IF;
END $$;

INSERT INTO review_projects
    (id, title, question, criteria_jsonb, protocol_version)
VALUES
    ('98000000-0000-0000-0000-000000000001', 'Benchmark RAG',
     'Pergunta do projeto?', '{}'::jsonb, 1);

INSERT INTO deduplicated_papers
    (id, project_id, title, merged_sources_jsonb)
VALUES
    ('98000000-0000-0000-0000-000000000002',
     '98000000-0000-0000-0000-000000000001',
     'Artigo relevante', '{}'::jsonb);

INSERT INTO rag_golden_queries
    (id, project_id, question, expected_refusal)
VALUES
    ('98000000-0000-0000-0000-000000000003',
     '98000000-0000-0000-0000-000000000001',
     'Qual método foi utilizado?', FALSE),
    ('98000000-0000-0000-0000-000000000004',
     '98000000-0000-0000-0000-000000000001',
     'Qual é a capital de Marte?', TRUE);

INSERT INTO rag_golden_relevances
    (golden_query_id, paper_id, page_number, relevance_grade)
VALUES
    ('98000000-0000-0000-0000-000000000003',
     '98000000-0000-0000-0000-000000000002', 7, 3);

INSERT INTO rag_golden_set_versions
    (project_id, version, set_jsonb, change_reason)
VALUES
    ('98000000-0000-0000-0000-000000000001', 1,
     '{"version":1,"queries":[{"question":"Qual método foi utilizado?"}]}'::jsonb,
     'Teste de integração');

INSERT INTO evaluation_runs
    (project_id, run_type, metrics_jsonb, params_jsonb)
VALUES
    ('98000000-0000-0000-0000-000000000001',
     'rag_retrieval_benchmark',
     '{"summary":{"rrf":{"recall_at_5":0.5},"reranked":{"recall_at_5":1.0}}}'::jsonb,
     '{"golden_set_version":1,"golden_set_hash":"hash-de-teste"}'::jsonb);

DO $$
BEGIN
    IF (SELECT COUNT(*) FROM rag_golden_queries
        WHERE project_id = '98000000-0000-0000-0000-000000000001') <> 2 THEN
        RAISE EXCEPTION 'Perguntas do Golden Set não foram preservadas';
    END IF;
    IF (SELECT metrics_jsonb #>> '{summary,reranked,recall_at_5}'
        FROM evaluation_runs
        WHERE project_id = '98000000-0000-0000-0000-000000000001'
          AND run_type = 'rag_retrieval_benchmark') <> '1.0' THEN
        RAISE EXCEPTION 'Métrica do benchmark não foi preservada em JSONB';
    END IF;
END $$;

ROLLBACK;
