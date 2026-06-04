-- 1. Habilitar a extensão vetorial (Crucial para o RAG avançado)
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. Criação das Tabelas Mínimas Exigidas

-- Projetos de revisão
CREATE TABLE review_projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(255) NOT NULL,
    question TEXT NOT NULL,
    criteria_jsonb JSONB NOT NULL,
    status VARCHAR(50) DEFAULT 'draft_protocol',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Strings e parâmetros de busca por base
CREATE TABLE search_queries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES review_projects(id) ON DELETE CASCADE,
    source VARCHAR(100) NOT NULL,
    query_text TEXT NOT NULL,
    query_jsonb JSONB,
    executed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Registros brutos coletados nas bases abertas
CREATE TABLE retrieved_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES review_projects(id) ON DELETE CASCADE,
    source VARCHAR(100) NOT NULL,
    external_id VARCHAR(255),
    doi VARCHAR(255),
    metadata_jsonb JSONB NOT NULL,
    raw_jsonb JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Registros consolidados após deduplicação
CREATE TABLE deduplicated_papers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES review_projects(id) ON DELETE CASCADE,
    canonical_doi VARCHAR(255),
    title TEXT NOT NULL,
    abstract TEXT,
    merged_sources_jsonb JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Chunks indexáveis para o pipeline RAG
CREATE TABLE paper_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    paper_id UUID REFERENCES deduplicated_papers(id) ON DELETE CASCADE,
    chunk_type VARCHAR(50) NOT NULL,
    chunk_text TEXT NOT NULL,
    metadata_jsonb JSONB
);

-- Metadados dos embeddings (onde usaremos o pgvector)
CREATE TABLE embeddings_metadata (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chunk_id UUID REFERENCES paper_chunks(id) ON DELETE CASCADE,
    model_name VARCHAR(100) NOT NULL,
    dimensions INTEGER NOT NULL,
    embedding VECTOR(768), -- Assumindo um modelo de embedding padrão de 768 dimensões (ex: nomic-embed-text ou similares)
    embedding_params_jsonb JSONB
);

-- Log obrigatório de todos os agentes (O coração da Rastreabilidade)
CREATE TABLE agent_interactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES review_projects(id) ON DELETE CASCADE,
    agent_name VARCHAR(100) NOT NULL,
    input_jsonb JSONB NOT NULL,
    output_jsonb JSONB NOT NULL,
    model_jsonb JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Sugestões dos agentes e validações humanas (Triagem)
CREATE TABLE screening_decisions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    paper_id UUID REFERENCES deduplicated_papers(id) ON DELETE CASCADE,
    suggested_decision VARCHAR(50),
    human_decision VARCHAR(50),
    rationale_jsonb JSONB,
	justification TEXT,
    reviewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Matriz de evidências estruturada
CREATE TABLE extracted_evidence (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    paper_id UUID REFERENCES deduplicated_papers(id) ON DELETE CASCADE,
    extraction_jsonb JSONB NOT NULL,
    human_review_status VARCHAR(50) DEFAULT 'pending'
);

-- Métricas e experimentos (Avaliação Quantitativa)
CREATE TABLE evaluation_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES review_projects(id) ON DELETE CASCADE,
    run_type VARCHAR(100) NOT NULL,
    metrics_jsonb JSONB NOT NULL,
    params_jsonb JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);