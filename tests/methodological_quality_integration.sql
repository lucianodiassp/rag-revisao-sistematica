\set ON_ERROR_STOP on

BEGIN;

INSERT INTO review_projects (id, title, question, criteria_jsonb)
VALUES
    ('99000000-0000-0000-0000-000000000001', 'Qualidade A', 'Pergunta A?', '{}'::jsonb),
    ('99000000-0000-0000-0000-000000000002', 'Qualidade B', 'Pergunta B?', '{}'::jsonb);

INSERT INTO deduplicated_papers (id, project_id, title, merged_sources_jsonb)
VALUES (
    '99000000-0000-0000-0000-000000000003',
    '99000000-0000-0000-0000-000000000001',
    'Artigo metodológico',
    '{}'::jsonb
);

INSERT INTO paper_chunks (id, paper_id, chunk_type, chunk_text, metadata_jsonb)
VALUES (
    '99000000-0000-0000-0000-000000000004',
    '99000000-0000-0000-0000-000000000003',
    'full_text_part_1',
    'The study design and sampling procedure were fully described.',
    '{"source_type":"pdf","page_start":5}'::jsonb
);

INSERT INTO methodological_assessment_instruments
    (id, project_id, version, name, description, domains_jsonb, change_reason)
VALUES (
    '99000000-0000-0000-0000-000000000005',
    '99000000-0000-0000-0000-000000000001',
    1,
    'Checklist de integração',
    'Instrumento metodológico usado somente pelo teste.',
    '[{"code":"study_design","label":"Desenho","question":"O desenho foi descrito adequadamente?","critical":true}]'::jsonb,
    'Criação para o teste de integração'
);

INSERT INTO methodological_assessments
    (id, project_id, paper_id, instrument_id, human_assessment_jsonb,
     overall_rating, review_status, review_notes, reviewed_at)
VALUES (
    '99000000-0000-0000-0000-000000000006',
    '99000000-0000-0000-0000-000000000001',
    '99000000-0000-0000-0000-000000000003',
    '99000000-0000-0000-0000-000000000005',
    '{"domains":[{"domain_code":"study_design","response":"yes","justification":"Descrição conferida pelo revisor."}]}'::jsonb,
    'low',
    'reviewed',
    'Avaliação humana de integração.',
    CURRENT_TIMESTAMP
);

INSERT INTO methodological_assessment_sources
    (assessment_id, domain_code, chunk_id, page_number, quote,
     quote_validated, human_validated)
VALUES (
    '99000000-0000-0000-0000-000000000006',
    'study_design',
    '99000000-0000-0000-0000-000000000004',
    5,
    'The study design and sampling procedure were fully described.',
    TRUE,
    TRUE
);

DO $$
BEGIN
    BEGIN
        INSERT INTO methodological_assessments
            (id, project_id, paper_id, instrument_id, review_status)
        VALUES (
            '99000000-0000-0000-0000-000000000007',
            '99000000-0000-0000-0000-000000000002',
            '99000000-0000-0000-0000-000000000003',
            '99000000-0000-0000-0000-000000000005',
            'pending'
        );
        RAISE EXCEPTION 'Banco aceitou mistura de projeto, artigo e instrumento';
    EXCEPTION
        WHEN foreign_key_violation THEN NULL;
    END;
END $$;

DO $$
BEGIN
    IF (SELECT COUNT(*) FROM methodological_assessments
        WHERE project_id = '99000000-0000-0000-0000-000000000001') <> 1 THEN
        RAISE EXCEPTION 'Avaliação metodológica não foi preservada no projeto correto';
    END IF;
    IF (SELECT COUNT(*) FROM methodological_assessments
        WHERE project_id = '99000000-0000-0000-0000-000000000002') <> 0 THEN
        RAISE EXCEPTION 'Isolamento metodológico entre projetos falhou';
    END IF;
    IF NOT EXISTS (
        SELECT 1
        FROM methodological_assessment_sources s
        JOIN paper_chunks pc ON pc.id = s.chunk_id
        WHERE s.assessment_id = '99000000-0000-0000-0000-000000000006'
          AND s.page_number = (pc.metadata_jsonb->>'page_start')::integer
          AND pc.chunk_text LIKE '%' || s.quote || '%'
          AND s.human_validated = TRUE
    ) THEN
        RAISE EXCEPTION 'Fonte metodológica literal e humana não foi preservada';
    END IF;
END $$;

ROLLBACK;
