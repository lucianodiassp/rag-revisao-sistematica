# 🧠 RAG Acadêmico: Automação de Revisões Sistemáticas da Literatura

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-pgvector-blue)
![Streamlit](https://img.shields.io/badge/Streamlit-UI-FF4B4B)
![Gemini AI](https://img.shields.io/badge/AI-Google_Gemini-orange)

## 🎯 Sobre o Projeto

Este projeto é um **Sistema de Apoio à Decisão (SAD)** de código aberto, baseado na arquitetura **RAG (Retrieval-Augmented Generation)**, desenvolvido para automatizar e conferir rigor científico ao processo de **Revisão Sistemática da Literatura (RSL)**.

---

## 🏗️ Raio-X da Arquitetura

- **Frontend:** Streamlit, com páginas de configuração, gestão de PDFs, auditoria e geração do relatório final.
- **Backend:** Python, com arquitetura modularizada por agentes inteligentes.
- **Banco de Dados:** PostgreSQL com a extensão `pgvector`, utilizada para buscas por similaridade semântica.
- **Inteligência Artificial:** Google Gemini, utilizando o modelo `gemini-2.5-flash` como LLM e os modelos `text-embedding-004` ou `gemini-embedding-001` para vetorização em 768 dimensões.

---

## 🚀 Principais Funcionalidades

### 1. Orquestrador de Coleta Tripla

- Integração simultânea com três importantes bases de dados científicas: **PubMed**, **OpenAlex** e **Semantic Scholar**.
- **Degradação elegante (*graceful degradation*):** o sistema detecta a presença de chaves de API no arquivo `.env` para utilizar limites de requisição ampliados. Quando as chaves não estão disponíveis, utiliza automaticamente as rotas públicas com limites reduzidos.
- Sanitização das consultas para evitar falhas de interpretação em APIs que não oferecem suporte completo a expressões booleanas.

### 2. Ingestão e Engenharia Vetorial de PDFs

- Desduplicação dos artigos no banco de dados por meio do DOI (*Digital Object Identifier*).
- Extração integral de texto utilizando a biblioteca `PyMuPDF`, incluindo suporte a artigos estruturados em múltiplas colunas.
- Segmentação de texto (*chunking*) com janela deslizante e sobreposição (*overlap*), reduzindo a perda de contexto entre parágrafos, fórmulas e sequências de raciocínio.
- Armazenamento dos vetores diretamente no PostgreSQL utilizando o tipo `vector(768)`.

### 3. Motor de Busca Híbrida com RRF

- Implementação do algoritmo **Reciprocal Rank Fusion (RRF)** diretamente no PostgreSQL.
- Combinação de:
  - **Busca lexical**, utilizando pesquisa textual para localizar palavras-chave, siglas e expressões exatas.
  - **Busca semântica**, utilizando `pgvector` para identificar conteúdos conceitualmente relacionados.
- Prompt de sistema orientado à redução de alucinações: o modelo deve evitar respostas quando não houver evidências suficientes nos fragmentos recuperados dos PDFs armazenados.

### 4. Agentes de Síntese e Auditoria

- **Agente Avaliador (*LLM-as-a-Judge*):** analisa as respostas produzidas pelo sistema RAG e avalia o rigor científico utilizando as perguntas registradas no protocolo versionado do projeto ativo.
- **Agente Relator:** coleta métricas do fluxo de trabalho, informações do processo PRISMA e dados tabulados em JSON para elaborar a seção de **Resultados e Discussão** em linguagem acadêmica.
- O agente relator utiliza temperatura `0.2`, buscando maior consistência e rigor factual nas respostas.

---

## ⚙️ Como Executar o Projeto Localmente

### Pré-requisitos

Antes de iniciar, verifique se os seguintes componentes estão instalados:

- **Docker Desktop**, com o WSL 2 habilitado em ambientes Windows.
- **Git**.
- **Python 3.10 ou superior**.

---

### 1. Clonar o Repositório

Execute os comandos abaixo:

```bash
git clone https://github.com/lucianodiassp/rag-revisao-sistematica.git
cd rag-revisao-sistematica
```

---

### 2. Subir a Infraestrutura

Inicie os containers do PostgreSQL e do pgAdmin:

```bash
docker compose up -d
```

Serviços disponibilizados:

- **PostgreSQL com pgvector:** porta `5432`.
- **pgAdmin:** [http://localhost:5050](http://localhost:5050).

#### Atualizar um banco criado por uma versão anterior

Em instalações que já possuem o volume `postgres_data`, aplique as migrações uma vez:

```bash
docker compose up -d --force-recreate db
docker compose exec -T db psql -U rag_user -d rag_systematic_review -f /docker-entrypoint-initdb.d/z98_project_isolation.sql
docker compose exec -T db psql -U rag_user -d rag_systematic_review -f /docker-entrypoint-initdb.d/z99_traceable_evidence.sql
```

A migração preserva os dados existentes, associa registros antigos a um projeto
legado quando necessário e passa a exigir isolamento por projeto. Em bancos novos,
ela é aplicada automaticamente na primeira inicialização.

#### Credenciais padrão do pgAdmin

- **Usuário:** `admin@rag.com`
- **Senha:** `admin`

> ⚠️ As credenciais padrão devem ser alteradas antes da implantação do sistema em um ambiente de produção.

---

### 3. Preparar o Ambiente Python

Crie e ative um ambiente virtual.

#### Windows — PowerShell

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

#### Linux ou macOS

```bash
python3 -m venv venv
source venv/bin/activate
```

Instale as dependências do projeto:

```bash
pip install -r requirements.txt
```

---

### 4. Configurar as Variáveis de Ambiente

Crie um arquivo chamado `.env` na raiz do projeto:

```env
GEMINI_API_KEY="sua-chave-api-do-google-aqui"

DB_HOST=localhost
DB_PORT=5432
DB_NAME=rag_systematic_review
DB_USER=rag_user
DB_PASSWORD=rag_password
```

> ⚠️ Não publique o arquivo `.env` nem suas chaves de API em repositórios públicos. Verifique se o arquivo está incluído no `.gitignore`.

---

## 🔄 Fluxo de Operação: *Human-in-the-Loop*

Diferentemente de sistemas totalmente automatizados, esta plataforma exige validação humana em etapas críticas. As etapas abaixo representam o fluxo completo de operação.

### Projeto ativo e rastreabilidade

Antes de operar o pipeline, crie ou selecione um projeto na página
**Configuração Pesquisa**. A seleção é compartilhada entre as páginas da sessão e
limita coleta, triagem, PDFs, RAG, auditoria e relatório ao corpus desse projeto.
Cada alteração da pergunta, dos critérios ou da estratégia de busca gera uma nova
versão auditável do protocolo no PostgreSQL.

Ao executar módulos diretamente pelo terminal, defina `PROJECT_ID` quando houver
mais de um projeto cadastrado:

```powershell
$env:PROJECT_ID = "uuid-do-projeto"
```

### Passo 1: Coleta de Artigos

Realize a busca de artigos nas bases **PubMed**, **OpenAlex** e **Semantic Scholar**, utilizando uma estratégia de busca estruturada, como PICO.

No Windows PowerShell, execute:

```powershell
$env:PYTHONIOENCODING = "utf-8"
python backend/coleta/orquestrador_coleta.py
```

Em ambientes Linux ou macOS, execute:

```bash
PYTHONIOENCODING=utf-8 python backend/coleta/orquestrador_coleta.py
```

---

### Passo 2: Triagem Manual no Streamlit

Inicie a interface web:

```bash
python -m streamlit run frontend/app.py
```

Acesse:

[http://localhost:8501](http://localhost:8501)

No menu lateral, selecione a opção **1. Triagem**.

A inteligência artificial poderá sugerir a inclusão ou exclusão dos artigos, mas o veredito final deverá ser realizado por um avaliador humano.

Os artigos devem ser classificados como:

- **Incluir**
- **Excluir**

---

### Passo 3: Indexação Vetorial e páginas de origem

Após a triagem, envie os documentos na página **Gestão de PDFs** e execute o botão
de processamento e vetorização. A mesma operação pode ser iniciada pelo terminal:

```bash
python backend/processamento/leitor_pdf.py
```

Os vetores gerados serão armazenados no PostgreSQL utilizando a extensão `pgvector`.
Cada chunk do PDF também registra a página de origem. Índices criados por versões
anteriores são reconstruídos automaticamente na próxima execução da indexação.

---

### Passo 4: Extração e revisão da Matriz de Evidências

Na página **2. Matriz de Evidências**, execute a extração dos PDFs. Para cada campo,
o sistema exige uma citação literal vinculada a um chunk e à página correspondente.
Citações que não existem no trecho indicado são descartadas automaticamente.

Confira as fontes apresentadas, corrija os valores quando necessário e registre a
decisão humana. A saída original da IA e a versão revisada são preservadas. Somente
evidências com status **Aprovada** ou **Corrigida e aprovada** alimentam o relatório.

---

### Passo 5: Auditoria do Sistema RAG

Execute o agente avaliador:

```bash
python backend/agentes/agente_avaliador.py
```

O agente realizará consultas automáticas ao mecanismo de busca e atribuirá métricas como:

- **Fidelidade (*Faithfulness*)**
- **Relevância (*Relevance*)**

O objetivo dessa etapa é detectar possíveis alucinações e avaliar a qualidade das respostas geradas pelo sistema.

---

### Passo 6: Geração da Síntese e do Relatório Final

Após a geração dos embeddings e a conclusão da auditoria, acesse novamente a interface:

[http://localhost:8501](http://localhost:8501)

No menu lateral, selecione a opção **3. Relatório Final** para gerar o documento consolidado da revisão sistemática.

---

## 🛑 Como Parar os Serviços Docker

Para desligar os containers sem remover os dados armazenados:

```bash
docker compose down
```

Para desligar os containers e remover também os volumes:

```bash
docker compose down -v
```

> ⚠️ **Atenção:** o comando `docker compose down -v` removerá permanentemente os dados armazenados nos volumes do PostgreSQL.

---

## 🧪 Validação e Testes com Usuários

Para testadores e avaliadores da plataforma, foi preparado um roteiro com cenários práticos para orientar a utilização do sistema e registrar o feedback de forma estruturada.

👉 **[Acesse o Roteiro de Testes Funcionais — UAT](docs/roteiro_testes.md)**

---

## 📄 Licença

Este projeto é disponibilizado como software de código aberto. Consulte o arquivo `LICENSE` para conhecer as condições de utilização, modificação e distribuição.

