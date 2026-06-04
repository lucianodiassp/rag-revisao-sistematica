## 🚀 Como rodar o projeto localmente

**Pré-requisitos:**
* [Docker Desktop](https://www.docker.com/products/docker-desktop/) instalado (Para usuários de Windows, certifique-se de habilitar o WSL 2 durante a instalação).
* Git instalado.

**Passo a passo para subir o Banco de Dados:**
1. Clone este repositório: `git clone https://github.com/lucianodiassp/rag-revisao-sistematica.git`
2. Entre na pasta do projeto: `cd rag-revisao-sistematica`
3. Suba os containers do PostgreSQL e pgAdmin: `docker compose up -d`

O banco de dados estará rodando na porta 5432 e o pgAdmin (interface gráfica) estará acessível no seu navegador em `http://localhost:5050` (Login: admin@rag.com | Senha: admin).



## 🗄️ Arquitetura da Base de Dados e Rastreabilidade (Requisito 6.3)

A persistência de dados do sistema foi desenhada para garantir o cumprimento rigoroso dos requisitos de auditoria, reprodutibilidade e o conceito de **Humano no Ciclo (Human-in-the-Loop)**. Utilizamos o **PostgreSQL 16** estendido com o módulo vetorial **pgvector**, rodando de forma isolada e segura em ambiente Docker.

### 📊 Modelo de Dados e Esquema de Armazenamento

O banco de dados utiliza uma abordagem híbrida: colunas relacionais clássicas (com integridade referencial estrita e chaves geradas via UUID) combinadas com campos **JSONB** estruturados. Esta escolha permite indexar árvores complexas de metadados retornadas pelas APIs de coleta (OpenAlex/PubMed) e logs de agentes LLM sem perder a flexibilidade.

Abaixo está a estrutura da tabela crítica de triagem e tomada de decisão:

| Coluna | Tipo | Restrições | Descrição |
| :--- | :--- | :--- | :--- |
| `id` | UUID | PRIMARY KEY | Identificador único universal da decisão. |
| `paper_id` | UUID | FOREIGN KEY | Associa ao artigo (`ON DELETE CASCADE`). |
| `suggested_decision` | VARCHAR(50) | - | Recomendação inicial gerada pelo Agente IA. |
| `human_decision` | VARCHAR(50) | - | Decisão final validada pelo revisor humano. |
| `rationale_jsonb` | JSONB | - | Justificativa estruturada gerada pelo LLM. |
| `justification` | TEXT | - | Justificativa ou observações do revisor humano. |
| `reviewed_at` | TIMESTAMP | DEFAULT NOW() | Data e hora exata da conciliação humana. |

---

### 🔍 Scripts de Auditoria e Governação SQL

Para cumprir o escopo de auditoria do pipeline de RAG, o repositório disponibiliza consultas avançadas prontas para execução via pgAdmin. Estas queries manipulam dados semiestruturados diretamente na base de dados:

#### 1. Ciclo de Vida do Artigo (End-to-End Traceability)
Cruza os metadados brutos do artigo, a análise de confiança da Inteligência Artificial e o veredito final do especialista humano.
```sql
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
LEFT JOIN agent_interactions ai ON ai.input_jsonb->>'paper_id' = p.id::text
LEFT JOIN screening_decisions sd ON sd.paper_id = p.id
ORDER BY sd.reviewed_at DESC;```

#### 2. Detecção de Conflitos (IA vs Humano)
Filtra ativamente todas as decisões onde o revisor humano divergiu da recomendação do modelo de linguagem. Essencial para auditoria de viés e recalibração de prompts.
```sql
SELECT 
    p.id AS artigo_id,
    p.title AS titulo_artigo,
    ai.output_jsonb->>'suggested_decision' AS sugerido_pela_ia,
    sd.human_decision AS decidido_pelo_humano,
    sd.justification AS justificativa_humana
FROM screening_decisions sd
JOIN deduplicated_papers p ON p.id = sd.paper_id
JOIN agent_interactions ai ON ai.input_jsonb->>'paper_id' = p.id::text
WHERE ai.output_jsonb->>'suggested_decision' <> sd.human_decision::text;```

#### 3. Extração de Evidências Aninhadas (JSONB Unnesting)
Abre matrizes internas (arrays) de objetos JSON para listar individualmente cada trecho de texto (snippet) que o agente LLM utilizou como base para aceitar ou rejeitar um artigo.
```sql
SELECT 
    ai.id AS log_id,
    ai.input_jsonb->>'title' AS titulo_artigo,
    evidencia->>'field' AS campo_analisado,
    evidencia->>'snippet' AS trecho_extraido_pela_ia
FROM agent_interactions ai,
LATERAL jsonb_array_elements(ai.output_jsonb->'evidence') AS evidencia
WHERE ai.agent_name = 'screening_agent'
  AND ai.output_jsonb->'evidence' IS NOT NULL;```

#### 4. Volumetria e Performance por Modelo
Métricas consolidadas de volumetria e média de confiança gerada por provedor (ex: OpenAI, Anthropic, Ollama), permitindo avaliar a estabilidade de cada modelo no pipeline.

```sql
SELECT 
    ai.model_jsonb->>'provider' AS provedor,
    ai.model_jsonb->>'model_name' AS modelo_utilizado,
    COUNT(*) AS total_interacoes,
    ROUND(AVG(CAST(ai.output_jsonb->>'confidence' AS NUMERIC)), 4) AS media_confianca_ia
FROM agent_interactions ai
WHERE ai.model_jsonb IS NOT NULL
GROUP BY ai.model_jsonb->>'provider', ai.model_jsonb->>'model_name'
ORDER BY total_interacoes DESC;```

---
