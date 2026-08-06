-- ============================================================================
-- Execute com: psql -v project_id='<UUID_DO_PROJETO>' -f auditoria.sql
-- SCRIPTS DE AUDITORIA E RASTREABILIDADE (REQUISITO REVISÃO SISTEMÁTICA)
-- Objetivo: Demonstrar a transparência do pipeline, logs dos agentes e 
--           reconciliação de decisões (Humano no Ciclo).
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. RASTREABILIDADE PONTA A PONTA (LIFECYCLE AUDIT)
-- Mostra toda a história de um artigo: metadados, o que o agente decidiu 
-- e o que o humano validou no final.
-- ----------------------------------------------------------------------------
SELECT 
    p.id AS artigo_id,
    p.title AS titulo_artigo,
    p.merged_sources_jsonb->'sources' AS fontes_origem,
    ai.agent_name AS agente_responsavel,
    ai.output_jsonb->>'suggested_decision' AS recomendacao_ia,
    CAST(ai.output_jsonb->>'confidence' AS NUMERIC) AS confianca_ia,
    sd.human_decision AS decisao_final_humana,
    sd.reviewed_at AS data_validacao
FROM deduplicated_papers p
LEFT JOIN agent_interactions ai 
    ON ai.project_id = p.project_id
   AND ai.input_jsonb->>'paper_id' = p.id::text
LEFT JOIN screening_decisions sd 
    ON sd.paper_id = p.id
WHERE p.project_id = :'project_id'::uuid
ORDER BY sd.reviewed_at DESC;


-- ----------------------------------------------------------------------------
-- 2. AUDITORIA DE CONFLITOS (DIVERGÊNCIA IA VS HUMANO)
-- Identifica casos onde a IA errou ou onde o critério humano foi divergente.
-- Crucial para recalibrar os prompts dos agentes de triagem.
-- ----------------------------------------------------------------------------
SELECT 
    p.id AS artigo_id,
    p.title AS titulo_artigo,
    ai.output_jsonb->>'suggested_decision' AS sugerido_pela_ia,
    ai.output_jsonb->'criteria_matched' AS criterios_ia,
    sd.human_decision AS decidido_pelo_humano,
    sd.justification AS justificativa_humana
FROM screening_decisions sd
JOIN deduplicated_papers p ON p.id = sd.paper_id
JOIN agent_interactions ai ON ai.input_jsonb->>'paper_id' = p.id::text
WHERE p.project_id = :'project_id'::uuid
  AND ai.project_id = p.project_id
  AND ai.output_jsonb->>'suggested_decision' <> sd.human_decision::text;


-- ----------------------------------------------------------------------------
-- 3. EXTRAÇÃO DE EVIDÊNCIAS DE DENTRO DE ARRAYS NESTED (JSONB DEEP AUDIT)
-- O agente salva um array de objetos na chave 'evidence'. Esta query quebra
-- o array em linhas individuais (JSONB Unnesting) para auditar os snippets.
-- ----------------------------------------------------------------------------
SELECT 
    ai.id AS log_id,
    ai.created_at AS data_analise,
    ai.input_jsonb->>'title' AS titulo_artigo,
    evidencia->>'field' AS campo_analisado,
    evidencia->>'snippet' AS trecho_extraido_pela_ia
FROM agent_interactions ai,
LATERAL jsonb_array_elements(ai.output_jsonb->'evidence') AS evidencia
WHERE ai.agent_name = 'screening_agent'
  AND ai.project_id = :'project_id'::uuid
  AND ai.output_jsonb->'evidence' IS NOT NULL;


-- ----------------------------------------------------------------------------
-- 4. PERFORMANCE E VOLUMETRIA POR MODELO/PROVEDOR
-- Analisa a média de confiança e o volume de decisões com base no modelo
-- de linguagem utilizado (útil para avaliar Ollama vs APIs pagas).
-- ----------------------------------------------------------------------------
SELECT 
    ai.model_jsonb->>'provider' AS provedor,
    ai.model_jsonb->>'model_name' AS modelo_utilizado,
    COUNT(*) AS total_interacoes,
    ROUND(AVG(CAST(ai.output_jsonb->>'confidence' AS NUMERIC)), 4) AS media_confianca_ia
FROM agent_interactions ai
WHERE ai.model_jsonb IS NOT NULL
  AND ai.project_id = :'project_id'::uuid
GROUP BY ai.model_jsonb->>'provider', ai.model_jsonb->>'model_name'
ORDER BY total_interacoes DESC;
