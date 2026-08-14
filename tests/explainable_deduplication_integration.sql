\set ON_ERROR_STOP on

BEGIN;

INSERT INTO review_projects
    (id, title, question, criteria_jsonb, status, protocol_version)
VALUES
    ('72000000-0000-0000-0000-000000000001',
     'Teste de deduplicação', 'Pergunta de teste', '{}'::jsonb, 'search_ready', 1);

INSERT INTO search_queries (id, project_id, source, query_text, query_jsonb)
VALUES
    ('72000000-0000-0000-0000-000000000002',
     '72000000-0000-0000-0000-000000000001', 'BibTeX', 'teste.bib', '{}'::jsonb);

INSERT INTO retrieved_records
    (id, project_id, search_query_id, source, doi, metadata_jsonb, raw_jsonb)
VALUES
    ('72000000-0000-0000-0000-000000000003',
     '72000000-0000-0000-0000-000000000001',
     '72000000-0000-0000-0000-000000000002',
     'BibTeX', '10.1000/teste', '{}'::jsonb, '{}'::jsonb);

INSERT INTO deduplicated_papers
    (id, project_id, canonical_doi, title, abstract, merged_sources_jsonb)
VALUES
    ('72000000-0000-0000-0000-000000000004',
     '72000000-0000-0000-0000-000000000001',
     '10.1000/existente', 'Título semelhante', 'Resumo',
     '{"sources":["OpenAlex"]}'::jsonb);

INSERT INTO deduplication_decisions
    (id, project_id, retrieved_record_id, candidate_paper_id, rule_code,
     similarity_score, system_action, explanation, evidence_jsonb,
     incoming_record_jsonb, review_status)
VALUES
    ('72000000-0000-0000-0000-000000000005',
     '72000000-0000-0000-0000-000000000001',
     '72000000-0000-0000-0000-000000000003',
     '72000000-0000-0000-0000-000000000004',
     'title_similar', 0.8750, 'pending_review',
     'Similaridade acima do limite.',
     '{"title_similarity":0.90,"author_overlap":0.70,"year_match":true}'::jsonb,
     '{"title":"Título recebido","proposed_paper_id":"72000000-0000-0000-0000-000000000006","fontes_dict":{"sources":["BibTeX"]}}'::jsonb,
     'pending');

UPDATE deduplication_decisions
SET result_paper_id = candidate_paper_id,
    review_status = 'reviewed',
    human_decision = 'merge',
    review_justification = 'Mesmo título, autores e ano.',
    reviewed_at = CURRENT_TIMESTAMP
WHERE id = '72000000-0000-0000-0000-000000000005';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM deduplication_decisions
        WHERE id = '72000000-0000-0000-0000-000000000005'
          AND review_status = 'reviewed'
          AND human_decision = 'merge'
          AND similarity_score = 0.8750
          AND evidence_jsonb->>'title_similarity' = '0.90'
    ) THEN
        RAISE EXCEPTION 'A decisão explicável não foi preservada';
    END IF;
END $$;

ROLLBACK;
