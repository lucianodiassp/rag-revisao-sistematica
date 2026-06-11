## 🚀 Como rodar o projeto localmente

### Pré-requisitos

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) instalado.
  - Para usuários Windows, certifique-se de habilitar o WSL 2 durante a instalação.
- Git instalado.

### Passo a passo para subir o Banco de Dados

1. Clone este repositório:

```bash
git clone https://github.com/lucianodiassp/rag-revisao-sistematica.git
```

2. Entre na pasta do projeto:

```bash
cd rag-revisao-sistematica
```

3. Suba os containers do PostgreSQL e pgAdmin:

```bash
docker compose up -d
```

O banco de dados estará rodando na porta **5432** e o pgAdmin (interface gráfica) estará acessível em:

```text
http://localhost:5050
```

**Login:** admin@rag.com  
**Senha:** admin

---

## 🐍 Como executar o Sistema RAG (Backend e Frontend)

Após subir o banco de dados via Docker, é necessário preparar o ambiente Python e executar a aplicação.

### Pré-requisitos

- Python 3.10 ou superior instalado.

### Passo a passo

#### 1. Criar um ambiente virtual

```bash
python -m venv venv
```

#### 2. Ativar o ambiente virtual

**Windows (PowerShell)**

```powershell
.\venv\Scripts\Activate.ps1
```

**Linux/macOS**

```bash
source venv/bin/activate
```

#### 3. Instalar as dependências

```bash
pip install -r backend/requirements.txt
```

#### 4. Configurar as variáveis de ambiente

Crie um arquivo `.env` na raiz do projeto:

```env
GEMINI_API_KEY="sua-chave-aqui"
DB_HOST=localhost
DB_PORT=5432
DB_NAME=rag_systematic_review
DB_USER=rag_user
DB_PASSWORD=rag_password
```

#### 5. Carregar artigos e gerar embeddings

Antes de usar a interface RAG, carregue os artigos no banco e gere os vetores usados pela busca semântica.

No Windows PowerShell, mantenha o ambiente virtual ativado e execute:

```powershell
$env:PYTHONIOENCODING='utf-8'
python backend/coleta/orquestrador_coleta.py
python backend/processamento/gerador_embeddings.py
```

O primeiro script coleta artigos nas fontes configuradas e grava na tabela `deduplicated_papers`.

O segundo script lê os abstracts, divide em chunks, gera embeddings com `all-MiniLM-L6-v2` e grava na tabela `document_chunks`.

> Observação: algumas APIs públicas podem aplicar limite temporário de requisições. Se uma fonte retornar erro `429`, execute a carga novamente mais tarde.

#### 6. Executar a Interface Web (Streamlit)

Com o banco de dados em execução e as dependências instaladas:

```bash
python -m streamlit run frontend/app.py
```

A aplicação abrirá automaticamente em:

```text
http://localhost:8501
```

---

## Operação do Projeto

### Fluxo normal de uso

1. Subir o banco de dados e o pgAdmin:

```powershell
docker compose up -d
```

2. Ativar o ambiente Python:

```powershell
.\venv\Scripts\Activate.ps1
```

3. Carregar ou atualizar os artigos:

```powershell
$env:PYTHONIOENCODING='utf-8'
python backend/coleta/orquestrador_coleta.py
```

4. Gerar os embeddings para busca semântica:

```powershell
python backend/processamento/gerador_embeddings.py
```

5. Abrir a interface RAG:

```powershell
python -m streamlit run frontend/app.py
```

6. Acessar no navegador:

```text
http://localhost:8501
```

### Consultar os dados no pgAdmin

Acesse:

```text
http://localhost:5050
```

Login do pgAdmin:

```text
Email: admin@rag.com
Senha: admin
```

Ao registrar o servidor no pgAdmin:

```text
Server Name: RAG PostgreSQL
Host name/address: db
Port: 5432
Maintenance database: rag_systematic_review
Username: rag_user
Password: rag_password
```

Tabelas principais:

| Tabela | Finalidade |
|---------|------------|
| `deduplicated_papers` | Artigos coletados e deduplicados |
| `document_chunks` | Trechos dos abstracts com embeddings vetoriais |
| `agent_interactions` | Logs das interações dos agentes LLM |
| `screening_decisions` | Decisões e validações humanas de triagem |

### Verificar se a carga funcionou

Execute no pgAdmin ou via `psql`:

```sql
SELECT 'deduplicated_papers' AS tabela, COUNT(*) FROM deduplicated_papers
UNION ALL
SELECT 'document_chunks', COUNT(*) FROM document_chunks;
```

Se `deduplicated_papers` tiver registros, a coleta carregou artigos.

Se `document_chunks` tiver registros, os embeddings foram gerados e a interface RAG já tem base para responder perguntas.

### Atualização de schema em banco já existente

O arquivo `database/scripts/init.sql` só é executado automaticamente quando o volume do PostgreSQL é criado pela primeira vez.

Se o volume Docker já existir, alterações posteriores no `init.sql` não são reaplicadas automaticamente.

Para aplicar a atualização necessária na tabela `screening_decisions` sem apagar dados:

```powershell
docker exec rag_postgres_db psql -U rag_user -d rag_systematic_review -c "ALTER TABLE screening_decisions ADD COLUMN IF NOT EXISTS justification TEXT; ALTER TABLE screening_decisions ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;"
```

Para recriar o banco do zero e reaplicar todo o `init.sql`:

```powershell
docker compose down -v
docker compose up -d
```

> Atenção: `docker compose down -v` apaga o volume do PostgreSQL e remove os dados carregados.

### Parar os serviços

Para parar os containers sem apagar os dados:

```powershell
docker compose down
```

Para parar a interface Streamlit, pressione `Ctrl+C` no terminal em que ela estiver rodando.

---

## 🗄️ Arquitetura da Base de Dados e Rastreabilidade (Requisito 6.3)

A persistência de dados do sistema foi desenhada para garantir o cumprimento rigoroso dos requisitos de auditoria, reprodutibilidade e do conceito de **Humano no Ciclo (Human-in-the-Loop)**.

Utilizamos o **PostgreSQL 16** estendido com o módulo vetorial **pgvector**, executado de forma isolada e segura em ambiente Docker.

### 📊 Modelo de Dados e Esquema de Armazenamento

O banco de dados utiliza uma abordagem híbrida: colunas relacionais clássicas (com integridade referencial estrita e chaves geradas via UUID) combinadas com campos **JSONB** estruturados.

Essa escolha permite indexar árvores complexas de metadados retornadas pelas APIs de coleta (OpenAlex/PubMed) e logs de agentes LLM sem perder flexibilidade.

Abaixo está a estrutura da tabela crítica de triagem e tomada de decisão:

| Coluna | Tipo | Restrições | Descrição |
|---------|---------|---------|---------|
| `id` | UUID | PRIMARY KEY | Identificador único universal da decisão |
| `paper_id` | UUID | FOREIGN KEY | Associa ao artigo (`ON DELETE CASCADE`) |
| `suggested_decision` | VARCHAR(50) | - | Recomendação inicial gerada pelo Agente IA |
| `human_decision` | VARCHAR(50) | - | Decisão final validada pelo revisor humano |
| `rationale_jsonb` | JSONB | - | Justificativa estruturada gerada pelo LLM |
| `justification` | TEXT | - | Justificativa ou observações do revisor humano |
| `reviewed_at` | TIMESTAMP | DEFAULT NOW() | Data e hora da conciliação humana |

---

## 🔍 Scripts de Auditoria e Governação SQL

Para cumprir o escopo de auditoria do pipeline RAG, o repositório disponibiliza consultas avançadas prontas para execução via pgAdmin.

### 1. Ciclo de Vida do Artigo (End-to-End Traceability)

Cruza os metadados brutos do artigo, a análise de confiança da IA e o veredito final do especialista humano.

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
ORDER BY sd.reviewed_at DESC;
```

### 2. Detecção de Conflitos (IA vs Humano)

Filtra decisões em que o revisor humano divergiu da recomendação da IA.

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
WHERE ai.output_jsonb->>'suggested_decision' <> sd.human_decision::text;
```

### 3. Extração de Evidências Aninhadas (JSONB Unnesting)

Lista cada evidência utilizada pelo agente LLM para justificar sua decisão.

```sql
SELECT 
    ai.id AS log_id,
    ai.input_jsonb->>'title' AS titulo_artigo,
    evidencia->>'field' AS campo_analisado,
    evidencia->>'snippet' AS trecho_extraido_pela_ia
FROM agent_interactions ai,
LATERAL jsonb_array_elements(ai.output_jsonb->'evidence') AS evidencia
WHERE ai.agent_name = 'screening_agent'
  AND ai.output_jsonb->'evidence' IS NOT NULL;
```

### 4. Volumetria e Performance por Modelo

Métricas consolidadas por provedor e modelo utilizado.

```sql
SELECT 
    ai.model_jsonb->>'provider' AS provedor,
    ai.model_jsonb->>'model_name' AS modelo_utilizado,
    COUNT(*) AS total_interacoes,
    ROUND(
        AVG(
            CAST(ai.output_jsonb->>'confidence' AS NUMERIC)
        ),
        4
    ) AS media_confianca_ia
FROM agent_interactions ai
WHERE ai.model_jsonb IS NOT NULL
GROUP BY
    ai.model_jsonb->>'provider',
    ai.model_jsonb->>'model_name'
ORDER BY total_interacoes DESC;
```
