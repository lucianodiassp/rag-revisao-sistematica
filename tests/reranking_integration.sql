\set ON_ERROR_STOP on

BEGIN;

INSERT INTO review_projects
    (id, title, question, criteria_jsonb, status, protocol_version)
VALUES
    ('73000000-0000-0000-0000-000000000001',
     'Teste de reranking', 'Pergunta de teste', '{}'::jsonb, 'screening', 1);

INSERT INTO ai_model_settings
    (id, task_type, provider_code, model_name, parameters_jsonb,
     scope_type, scope_id, is_active)
VALUES
    ('73000000-0000-0000-0000-000000000002',
     'reranking', 'google_gemini', 'gemini-test',
     '{"temperature":0.0,"enabled":true,"candidate_limit":12,"final_limit":4}'::jsonb,
     'team', '73000000-0000-0000-0000-000000000001', TRUE);

INSERT INTO agent_interactions
    (id, project_id, agent_name, input_jsonb, output_jsonb, model_jsonb)
VALUES
    ('73000000-0000-0000-0000-000000000003',
     '73000000-0000-0000-0000-000000000001',
     'reranking_agent',
     '{"question":"Pergunta","candidates":[{"candidate_id":"c1","original_rank":1,"rrf_score":0.03,"page_number":7}]}'::jsonb,
     '{"status":"success","selected":[{"candidate_id":"c1","rerank_rank":1,"rerank_score":95,"page_number":7}]}'::jsonb,
     '{"provider":"google_gemini","model_name":"gemini-test","candidate_limit":12,"final_limit":4}'::jsonb);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM ai_model_settings
        WHERE id = '73000000-0000-0000-0000-000000000002'
          AND task_type = 'reranking'
          AND parameters_jsonb->>'enabled' = 'true'
    ) THEN
        RAISE EXCEPTION 'A configuração do reranking não foi persistida';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM agent_interactions
        WHERE id = '73000000-0000-0000-0000-000000000003'
          AND agent_name = 'reranking_agent'
          AND output_jsonb->>'status' = 'success'
          AND output_jsonb->'selected'->0->>'rerank_score' = '95'
          AND output_jsonb->'selected'->0->>'page_number' = '7'
    ) THEN
        RAISE EXCEPTION 'A trilha JSONB do reranking não foi preservada';
    END IF;
END $$;

ROLLBACK;
