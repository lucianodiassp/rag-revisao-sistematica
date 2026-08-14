BEGIN;

ALTER TABLE ai_model_settings
    DROP CONSTRAINT IF EXISTS ai_model_settings_task_type_check;

ALTER TABLE ai_model_settings
    ADD CONSTRAINT ai_model_settings_task_type_check
    CHECK (task_type IN (
        'formulation', 'screening', 'rag', 'reranking', 'evaluation',
        'extraction', 'report', 'embedding'
    ));

COMMIT;
