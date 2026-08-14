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
    protocol_version INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Histórico imutável das alterações do protocolo de cada revisão.
CREATE TABLE review_protocol_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES review_projects(id) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    question TEXT NOT NULL,
    criteria_jsonb JSONB NOT NULL,
    change_reason TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (project_id, version)
);

-- Strings e parâmetros de busca por base
CREATE TABLE search_queries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES review_projects(id) ON DELETE CASCADE,
    source VARCHAR(100) NOT NULL,
    query_text TEXT NOT NULL,
    query_jsonb JSONB,
    executed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Registros brutos coletados nas bases abertas
CREATE TABLE retrieved_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES review_projects(id) ON DELETE CASCADE,
    search_query_id UUID REFERENCES search_queries(id) ON DELETE SET NULL,
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
    project_id UUID NOT NULL REFERENCES review_projects(id) ON DELETE CASCADE,
    canonical_doi VARCHAR(255),
    title TEXT NOT NULL,
    abstract TEXT,
    merged_sources_jsonb JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Decisões explicáveis da deduplicação, incluindo candidatos que aguardam
-- validação humana antes de serem liberados para a triagem.
CREATE TABLE deduplication_decisions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES review_projects(id) ON DELETE CASCADE,
    retrieved_record_id UUID NOT NULL REFERENCES retrieved_records(id) ON DELETE CASCADE,
    candidate_paper_id UUID REFERENCES deduplicated_papers(id) ON DELETE SET NULL,
    result_paper_id UUID REFERENCES deduplicated_papers(id) ON DELETE SET NULL,
    rule_code VARCHAR(50) NOT NULL,
    similarity_score NUMERIC(5,4) NOT NULL,
    system_action VARCHAR(50) NOT NULL,
    explanation TEXT NOT NULL,
    evidence_jsonb JSONB NOT NULL,
    incoming_record_jsonb JSONB NOT NULL,
    review_status VARCHAR(30) NOT NULL DEFAULT 'automatic',
    human_decision VARCHAR(30),
    review_justification TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reviewed_at TIMESTAMP WITH TIME ZONE,
    UNIQUE (retrieved_record_id),
    CHECK (rule_code IN ('doi_exact', 'title_exact', 'title_similar', 'no_candidate')),
    CHECK (similarity_score BETWEEN 0 AND 1),
    CHECK (system_action IN ('auto_create', 'auto_merge', 'pending_review')),
    CHECK (review_status IN ('automatic', 'pending', 'reviewed')),
    CHECK (human_decision IS NULL OR human_decision IN ('merge', 'keep_separate')),
    CHECK (review_justification IS NULL OR length(btrim(review_justification)) >= 5)
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
    project_id UUID NOT NULL REFERENCES review_projects(id) ON DELETE CASCADE,
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
    exclusion_reason_code VARCHAR(50),
    reviewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CHECK (exclusion_reason_code IS NULL OR exclusion_reason_code IN (
        'population_mismatch', 'intervention_mismatch', 'outcome_mismatch',
        'study_design_mismatch', 'publication_type', 'language', 'date_range',
        'insufficient_information', 'restricted_access', 'pdf_not_found',
        'metadata_mismatch', 'other'
    )),
    CHECK (
        (human_decision = 'Excluir' AND exclusion_reason_code IS NOT NULL)
        OR (human_decision IS DISTINCT FROM 'Excluir' AND exclusion_reason_code IS NULL)
    )
);

-- Histórico de reavaliações motivadas durante as etapas posteriores à triagem.
CREATE TABLE screening_reassessments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES review_projects(id) ON DELETE CASCADE,
    screening_decision_id UUID NOT NULL REFERENCES screening_decisions(id) ON DELETE CASCADE,
    paper_id UUID NOT NULL REFERENCES deduplicated_papers(id) ON DELETE CASCADE,
    action VARCHAR(50) NOT NULL,
    reason_code VARCHAR(50) NOT NULL,
    reason TEXT NOT NULL,
    previous_human_decision VARCHAR(50) NOT NULL,
    previous_justification TEXT,
    resulting_human_decision VARCHAR(50),
    origin VARCHAR(50) NOT NULL DEFAULT 'pdf_management',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CHECK (action IN ('return_to_screening', 'exclude')),
    CHECK (reason_code IN ('restricted_access', 'pdf_not_found', 'metadata_mismatch', 'other')),
    CHECK (origin IN ('pdf_management')),
    CHECK (length(btrim(reason)) >= 5)
);

-- Matriz de evidências estruturada
CREATE TABLE extracted_evidence (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    paper_id UUID UNIQUE REFERENCES deduplicated_papers(id) ON DELETE CASCADE,
    extraction_jsonb JSONB NOT NULL,
    schema_version VARCHAR(50) NOT NULL DEFAULT 'traceable-v1',
    human_review_status VARCHAR(50) DEFAULT 'pending',
    human_review_jsonb JSONB,
    review_notes TEXT,
    extracted_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    reviewed_at TIMESTAMP WITH TIME ZONE
);

-- Liga cada campo extraído ao trecho literal e à página de origem.
CREATE TABLE evidence_field_sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    extraction_id UUID NOT NULL REFERENCES extracted_evidence(id) ON DELETE CASCADE,
    field_name VARCHAR(50) NOT NULL,
    evidence_order INTEGER NOT NULL DEFAULT 0,
    chunk_id UUID NOT NULL REFERENCES paper_chunks(id) ON DELETE CASCADE,
    page_number INTEGER,
    quote TEXT NOT NULL,
    quote_validated BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Métricas e experimentos (Avaliação Quantitativa)
CREATE TABLE evaluation_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES review_projects(id) ON DELETE CASCADE,
    run_type VARCHAR(100) NOT NULL,
    metrics_jsonb JSONB NOT NULL,
    params_jsonb JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Retratos imutáveis e versionados do fluxo de seleção e síntese.
CREATE TABLE prisma_flow_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES review_projects(id) ON DELETE CASCADE,
    snapshot_version INTEGER NOT NULL,
    protocol_version INTEGER NOT NULL,
    metrics_jsonb JSONB NOT NULL,
    source_counts_jsonb JSONB NOT NULL,
    exclusion_reasons_jsonb JSONB NOT NULL,
    interpretation_jsonb JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (project_id, snapshot_version)
);

-- Credenciais cifradas e configurações de IA da instalação local. Os campos de
-- escopo e proprietário permitem evolução futura sem misturar segredos de usuários.
CREATE TABLE ai_provider_credentials (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    provider_code VARCHAR(50) NOT NULL,
    label VARCHAR(100) NOT NULL,
    encrypted_secret TEXT NOT NULL,
    secret_hint VARCHAR(20) NOT NULL,
    scope_type VARCHAR(30) NOT NULL DEFAULT 'installation',
    scope_id UUID,
    owner_user_id UUID,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    validation_status VARCHAR(30) NOT NULL DEFAULT 'untested',
    last_validated_at TIMESTAMP WITH TIME ZONE,
    validation_error TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CHECK (scope_type IN ('installation', 'user', 'team')),
    CHECK (validation_status IN ('untested', 'valid', 'invalid'))
);

CREATE UNIQUE INDEX uq_ai_credentials_active_scope
    ON ai_provider_credentials (
        provider_code,
        scope_type,
        COALESCE(scope_id, '00000000-0000-0000-0000-000000000000'::uuid),
        COALESCE(owner_user_id, '00000000-0000-0000-0000-000000000000'::uuid)
    ) WHERE is_active = TRUE;

CREATE TABLE ai_model_settings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_type VARCHAR(50) NOT NULL,
    provider_code VARCHAR(50) NOT NULL,
    credential_id UUID REFERENCES ai_provider_credentials(id) ON DELETE SET NULL,
    model_name VARCHAR(150) NOT NULL,
    parameters_jsonb JSONB NOT NULL DEFAULT '{}'::jsonb,
    embedding_dimensions INTEGER,
    scope_type VARCHAR(30) NOT NULL DEFAULT 'installation',
    scope_id UUID,
    owner_user_id UUID,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CHECK (task_type IN (
        'formulation', 'screening', 'rag', 'reranking', 'evaluation',
        'extraction', 'report', 'embedding'
    )),
    CHECK (scope_type IN ('installation', 'user', 'team')),
    CHECK (embedding_dimensions IS NULL OR embedding_dimensions > 0)
);

CREATE UNIQUE INDEX uq_ai_model_settings_active_scope
    ON ai_model_settings (
        task_type,
        scope_type,
        COALESCE(scope_id, '00000000-0000-0000-0000-000000000000'::uuid),
        COALESCE(owner_user_id, '00000000-0000-0000-0000-000000000000'::uuid)
    ) WHERE is_active = TRUE;

CREATE TABLE ai_configuration_audit (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    action VARCHAR(100) NOT NULL,
    scope_type VARCHAR(30) NOT NULL DEFAULT 'installation',
    scope_id UUID,
    owner_user_id UUID,
    changes_jsonb JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CHECK (scope_type IN ('installation', 'user', 'team'))
);

-- Configuração e credenciais cifradas das fontes bibliográficas.
CREATE TABLE bibliographic_source_settings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_code VARCHAR(50) NOT NULL,
    is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    contact_email VARCHAR(255),
    tool_name VARCHAR(100) NOT NULL DEFAULT 'rag-revisao-sistematica',
    request_timeout_seconds INTEGER NOT NULL DEFAULT 30,
    max_retries INTEGER NOT NULL DEFAULT 3,
    scope_type VARCHAR(30) NOT NULL DEFAULT 'installation',
    scope_id UUID,
    owner_user_id UUID,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CHECK (source_code IN ('openalex', 'semantic_scholar', 'pubmed')),
    CHECK (scope_type IN ('installation', 'user', 'team')),
    CHECK (request_timeout_seconds BETWEEN 1 AND 120),
    CHECK (max_retries BETWEEN 1 AND 10)
);

CREATE UNIQUE INDEX uq_bibliographic_settings_scope
    ON bibliographic_source_settings (
        source_code,
        scope_type,
        COALESCE(scope_id, '00000000-0000-0000-0000-000000000000'::uuid),
        COALESCE(owner_user_id, '00000000-0000-0000-0000-000000000000'::uuid)
    );

CREATE TABLE bibliographic_source_credentials (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_code VARCHAR(50) NOT NULL,
    label VARCHAR(100) NOT NULL,
    encrypted_secret TEXT NOT NULL,
    secret_hint VARCHAR(20) NOT NULL,
    scope_type VARCHAR(30) NOT NULL DEFAULT 'installation',
    scope_id UUID,
    owner_user_id UUID,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    validation_status VARCHAR(30) NOT NULL DEFAULT 'untested',
    last_validated_at TIMESTAMP WITH TIME ZONE,
    validation_error TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CHECK (source_code IN ('openalex', 'semantic_scholar', 'pubmed')),
    CHECK (scope_type IN ('installation', 'user', 'team')),
    CHECK (validation_status IN ('untested', 'valid', 'invalid'))
);

CREATE UNIQUE INDEX uq_bibliographic_credentials_active_scope
    ON bibliographic_source_credentials (
        source_code,
        scope_type,
        COALESCE(scope_id, '00000000-0000-0000-0000-000000000000'::uuid),
        COALESCE(owner_user_id, '00000000-0000-0000-0000-000000000000'::uuid)
    ) WHERE is_active = TRUE;

CREATE TABLE bibliographic_configuration_audit (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    action VARCHAR(100) NOT NULL,
    source_code VARCHAR(50),
    scope_type VARCHAR(30) NOT NULL DEFAULT 'installation',
    scope_id UUID,
    owner_user_id UUID,
    changes_jsonb JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CHECK (source_code IS NULL OR source_code IN ('openalex', 'semantic_scholar', 'pubmed')),
    CHECK (scope_type IN ('installation', 'user', 'team'))
);

CREATE INDEX idx_search_queries_project ON search_queries(project_id);
CREATE INDEX idx_retrieved_records_project ON retrieved_records(project_id);
CREATE INDEX idx_deduplicated_papers_project ON deduplicated_papers(project_id);
CREATE INDEX idx_deduplication_decisions_project ON deduplication_decisions(project_id, created_at DESC);
CREATE INDEX idx_deduplication_decisions_pending ON deduplication_decisions(project_id, review_status, created_at DESC);
CREATE INDEX idx_deduplicated_papers_project_doi ON deduplicated_papers(project_id, canonical_doi);
CREATE INDEX idx_agent_interactions_project ON agent_interactions(project_id);
CREATE INDEX idx_screening_reassessments_project ON screening_reassessments(project_id, created_at DESC);
CREATE INDEX idx_screening_reassessments_paper ON screening_reassessments(paper_id, created_at DESC);
CREATE INDEX idx_evaluation_runs_project ON evaluation_runs(project_id);
CREATE INDEX idx_prisma_snapshots_project ON prisma_flow_snapshots(project_id, snapshot_version DESC);
CREATE INDEX idx_paper_chunks_paper ON paper_chunks(paper_id);
CREATE INDEX idx_embeddings_chunk ON embeddings_metadata(chunk_id);
CREATE INDEX idx_evidence_sources_extraction ON evidence_field_sources(extraction_id);
CREATE INDEX idx_evidence_sources_chunk ON evidence_field_sources(chunk_id);
CREATE INDEX idx_ai_credentials_scope ON ai_provider_credentials(scope_type, scope_id, owner_user_id);
CREATE INDEX idx_ai_model_settings_scope ON ai_model_settings(scope_type, scope_id, owner_user_id);
CREATE INDEX idx_ai_configuration_audit_created ON ai_configuration_audit(created_at DESC);
CREATE INDEX idx_bibliographic_settings_scope ON bibliographic_source_settings(scope_type, scope_id, owner_user_id);
CREATE INDEX idx_bibliographic_credentials_scope ON bibliographic_source_credentials(scope_type, scope_id, owner_user_id);
CREATE INDEX idx_bibliographic_audit_created ON bibliographic_configuration_audit(created_at DESC);
