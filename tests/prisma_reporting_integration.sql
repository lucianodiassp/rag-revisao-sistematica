BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'screening_decisions'
          AND column_name = 'exclusion_reason_code'
    ) THEN
        RAISE EXCEPTION 'Coluna de motivo estruturado não encontrada';
    END IF;

    IF to_regclass('public.prisma_flow_snapshots') IS NULL THEN
        RAISE EXCEPTION 'Tabela de snapshots PRISMA não encontrada';
    END IF;
END $$;

INSERT INTO review_projects
    (id, title, question, criteria_jsonb, protocol_version)
VALUES
    ('99000000-0000-0000-0000-000000000001', 'Teste PRISMA',
     'Pergunta de teste?', '{}'::jsonb, 2);

INSERT INTO deduplicated_papers
    (id, project_id, title, merged_sources_jsonb)
VALUES
    ('99000000-0000-0000-0000-000000000002',
     '99000000-0000-0000-0000-000000000001',
     'Artigo fora da população', '{}'::jsonb);

INSERT INTO screening_decisions
    (id, paper_id, suggested_decision, human_decision, justification,
     exclusion_reason_code, reviewed_at)
VALUES
    ('99000000-0000-0000-0000-000000000003',
     '99000000-0000-0000-0000-000000000002',
     'Incluir', 'Excluir', 'População incompatível com o protocolo.',
     'population_mismatch', CURRENT_TIMESTAMP);

INSERT INTO prisma_flow_snapshots
    (project_id, snapshot_version, protocol_version, metrics_jsonb,
     source_counts_jsonb, exclusion_reasons_jsonb, interpretation_jsonb)
VALUES
    ('99000000-0000-0000-0000-000000000001', 1, 2,
     '{"records_identified": 1}'::jsonb,
     '{"bibtex": 1}'::jsonb,
     '{"screening": {"population_mismatch": 1}, "full_text": {}}'::jsonb,
     '{"statements": ["Fluxo de teste"], "warnings": []}'::jsonb);

DO $$
DECLARE
    reason_count INTEGER;
BEGIN
    SELECT (exclusion_reasons_jsonb #>> '{screening,population_mismatch}')::INTEGER
    INTO reason_count
    FROM prisma_flow_snapshots
    WHERE project_id = '99000000-0000-0000-0000-000000000001';

    IF reason_count <> 1 THEN
        RAISE EXCEPTION 'Motivo de exclusão não foi preservado no snapshot';
    END IF;
END $$;

ROLLBACK;
