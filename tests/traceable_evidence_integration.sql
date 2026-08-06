\set ON_ERROR_STOP on

BEGIN;

INSERT INTO review_projects (id, title, question, criteria_jsonb)
VALUES (
    '30000000-0000-0000-0000-000000000003',
    'Teste de evidência rastreável',
    'A rastreabilidade está preservada?',
    '{}'::jsonb
);

INSERT INTO deduplicated_papers
    (id, project_id, title, abstract, merged_sources_jsonb)
VALUES (
    '33000000-0000-0000-0000-000000000003',
    '30000000-0000-0000-0000-000000000003',
    'Artigo rastreável',
    'Resumo de teste',
    '{}'::jsonb
);

INSERT INTO paper_chunks
    (id, paper_id, chunk_type, chunk_text, metadata_jsonb)
VALUES (
    '33300000-0000-0000-0000-000000000003',
    '33000000-0000-0000-0000-000000000003',
    'full_text_part_1',
    'The method achieved 94.2 percent accuracy.',
    '{"source_type":"pdf","page_start":7,"page_end":7}'::jsonb
);

INSERT INTO extracted_evidence
    (id, paper_id, extraction_jsonb, schema_version, human_review_status)
VALUES (
    '33330000-0000-0000-0000-000000000003',
    '33000000-0000-0000-0000-000000000003',
    '{"schema_version":"traceable-v1","main_results":{"value":"Accuracy de 94,2%","confidence":0.9,"evidence":[{"chunk_id":"33300000-0000-0000-0000-000000000003","page":7,"quote":"achieved 94.2 percent accuracy"}]}}'::jsonb,
    'traceable-v1',
    'pending'
);

INSERT INTO evidence_field_sources
    (extraction_id, field_name, chunk_id, page_number, quote)
VALUES (
    '33330000-0000-0000-0000-000000000003',
    'main_results',
    '33300000-0000-0000-0000-000000000003',
    7,
    'achieved 94.2 percent accuracy'
);

DO $$
DECLARE
    fontes_validas INTEGER;
    pendentes_no_relatorio INTEGER;
BEGIN
    SELECT COUNT(*) INTO fontes_validas
    FROM evidence_field_sources efs
    JOIN extracted_evidence e ON e.id = efs.extraction_id
    JOIN paper_chunks pc ON pc.id = efs.chunk_id
    JOIN deduplicated_papers p ON p.id = e.paper_id
    WHERE p.project_id = '30000000-0000-0000-0000-000000000003'
      AND efs.page_number = (pc.metadata_jsonb->>'page_start')::INTEGER
      AND pc.chunk_text ILIKE '%' || efs.quote || '%';

    SELECT COUNT(*) INTO pendentes_no_relatorio
    FROM extracted_evidence e
    JOIN deduplicated_papers p ON p.id = e.paper_id
    WHERE p.project_id = '30000000-0000-0000-0000-000000000003'
      AND e.human_review_status IN ('approved', 'corrected');

    IF fontes_validas <> 1 OR pendentes_no_relatorio <> 0 THEN
        RAISE EXCEPTION 'Falha na fonte rastreável ou no bloqueio de pendentes';
    END IF;
END $$;

UPDATE extracted_evidence
SET human_review_status = 'approved',
    human_review_jsonb = '{"main_results":"Accuracy de 94,2%"}'::jsonb,
    reviewed_at = CURRENT_TIMESTAMP
WHERE id = '33330000-0000-0000-0000-000000000003';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM extracted_evidence e
        JOIN deduplicated_papers p ON p.id = e.paper_id
        WHERE p.project_id = '30000000-0000-0000-0000-000000000003'
          AND e.human_review_status IN ('approved', 'corrected')
          AND e.human_review_jsonb IS NOT NULL
    ) THEN
        RAISE EXCEPTION 'Evidência aprovada não ficou disponível para relatório';
    END IF;
END $$;

ROLLBACK;
