# 🚀 RAG Systematic Review: Plataforma de Apoio à Decisão

Este projeto é um Sistema de Apoio à Decisão (SAD) baseado em Inteligência Artificial (LLMs) e Busca Vetorial (RAG) para acelerar e auditar o processo de Revisões Sistemáticas da Literatura Académica.

## 🛠️ Arquitetura Atual

* **Motor LLM Central:** Google Gemini (`gemini-2.5-flash`)
* **Motor Vetorial (Embeddings):** Google Gemini (`gemini-embedding-001`) com redução Matryoshka para 768 dimensões.
* **Base de Dados:** PostgreSQL 16 estendido com `pgvector` (Busca Híbrida: BM25 + Vetorial com RRF).
* **Interface:** Streamlit (Multi-page).

---

## ⚙️ Como rodar o projeto localmente

### Pré-requisitos

* **Docker Desktop** instalado (habilitar WSL 2 no Windows).
* **Git** instalado.
* **Python 3.10+** instalado.

### 1. Subir a Infraestrutura (Banco de Dados Vetorial)

Clone o repositório, entre na pasta e inicie os containers:

```bash
git clone https://github.com/lucianodiassp/rag-revisao-sistematica.git
cd rag-revisao-sistematica
docker compose up -d
```

* **PostgreSQL (com pgvector):** Porta `5432`
* **pgAdmin (Interface Visual):** http://localhost:5050

**Credenciais padrão do pgAdmin:**

* Usuário: `admin@rag.com`
* Senha: `admin`

### 2. Preparar o Ambiente Python

Crie e ative o ambiente virtual.

#### Windows (PowerShell)

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

#### Linux/macOS

```bash
python3 -m venv venv
source venv/bin/activate
```

Instale as dependências:

```bash
pip install -r backend/requirements.txt
```

Crie um arquivo `.env` na raiz do projeto:

```env
GEMINI_API_KEY="sua-chave-api-do-google-aqui"

DB_HOST=localhost
DB_PORT=5432
DB_NAME=rag_systematic_review
DB_USER=rag_user
DB_PASSWORD=rag_password
```

---

## 🔄 Fluxo de Operação: Human-in-the-Loop

Diferente de sistemas totalmente automatizados, esta plataforma exige validação humana em etapas críticas. Siga a ordem abaixo para operar o ciclo completo.

### Passo 1: Coleta de Artigos

Busque os artigos nas bases de dados (PubMed, OpenAlex e Semantic Scholar) utilizando sua estratégia de busca baseada em PICO.

```powershell
$env:PYTHONIOENCODING='utf-8'
python backend/coleta/orquestrador_coleta.py
```

---

### Passo 2: Triagem Manual (Streamlit)

Abra a interface web para que a IA sugira as aprovações, mas **o veredito final seja humano**.

```bash
python -m streamlit run frontend/app.py
```

> Acesse o menu **"1. Triagem"** em http://localhost:8501 e classifique os artigos como **"Incluir"** ou **"Excluir"**.

---

### Passo 3: Indexação Vetorial

Gere os embeddings (coordenadas matemáticas) apenas para os artigos aprovados na etapa anterior.

```bash
python backend/processamento/gerador_embeddings.py
```

---

### Passo 4: Auditoria do Sistema RAG (LLM-as-a-Judge)

Execute o agente avaliador. Ele realizará consultas automáticas ao motor de busca e atribuirá métricas de:

* Fidelidade (Faithfulness)
* Relevância (Relevance)

O objetivo é detectar possíveis alucinações e validar a qualidade das respostas.

```bash
python backend/agentes/agente_avaliador.py
```

---

### Passo 5: Geração da Síntese e Relatório Final

Com os embeddings armazenados e a auditoria concluída, retorne à interface web:

http://localhost:8501

Acesse o menu **"3. Relatório Final"** e gere o documento consolidado da revisão sistemática.

---

## 🗄️ Tabelas Principais do PostgreSQL

A base de dados combina modelagem relacional tradicional com campos JSONB e vetores para busca semântica.

| Tabela                | Finalidade                                                          |
| --------------------- | ------------------------------------------------------------------- |
| `deduplicated_papers` | Artigos coletados e deduplicados (título e resumo).                 |
| `screening_decisions` | Registra a decisão humana e a justificativa gerada pela IA.         |
| `paper_chunks`        | Fragmentos lógicos dos artigos aprovados.                           |
| `embeddings_metadata` | Armazena os vetores de 768 dimensões gerados pelo Google Gemini.    |
| `agent_interactions`  | Log auditável de todas as operações realizadas pelos agentes de IA. |

---

## 🔍 Verificar se a Carga Vetorial Funcionou

Acesse o pgAdmin, abra a **Query Tool** e execute:

```sql
SELECT
    'Artigos Aprovados' AS etapa,
    COUNT(*) AS quantidade
FROM screening_decisions
WHERE human_decision = 'Incluir'

UNION ALL

SELECT
    'Chunks Vetorizados',
    COUNT(*)
FROM embeddings_metadata;
```

> Se a linha **"Chunks Vetorizados"** retornar registros, o mecanismo de busca semântica está operacional e pronto para responder perguntas fundamentadas na literatura indexada.

---

## 🛑 Parar os Serviços Docker

Para desligar os containers sem perder os dados:

```bash
docker compose down
```

Para remover também os volumes e reiniciar a base do zero:

```bash
docker compose down -v
```

> ⚠️ Atenção: o comando acima apagará permanentemente todos os dados armazenados no PostgreSQL.


## 🧪 Validação e Testes com Utilizadores

Se você é um testador ou avaliador da plataforma, preparamos um roteiro passo a passo com cenários práticos para guiar a sua experiência e capturar o seu feedback de forma estruturada.

👉 **[Clique aqui para acessar o Roteiro de Testes Funcionais (UAT)](docs/roteiro_testes.md)**