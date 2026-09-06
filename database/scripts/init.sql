-- 1. Habilitar a extensão vetorial (Crucial para o RAG avançado)
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. Criação das Tabelas Mínimas Exigidas

-- Identidades da aplicação. O modo multiusuário ainda depende das barreiras de
-- autorização do backend e permanece desabilitado no preflight Web.
CREATE TABLE application_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    identity_provider VARCHAR(255) NOT NULL,
    subject VARCHAR(512) NOT NULL,
    email VARCHAR(320),
    display_name VARCHAR(255) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    last_login_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (identity_provider, subject),
    CHECK (status IN ('active', 'disabled')),
    CHECK (email IS NULL OR email = lower(email)),
    CHECK (length(btrim(identity_provider)) >= 1),
    CHECK (length(btrim(subject)) >= 1),
    CHECK (length(btrim(display_name)) >= 1)
);

-- Projetos de revisão
CREATE TABLE review_projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(255) NOT NULL,
    question TEXT NOT NULL,
    criteria_jsonb JSONB NOT NULL,
    status VARCHAR(50) DEFAULT 'draft_protocol',
    protocol_version INTEGER NOT NULL DEFAULT 1,
    archived_at TIMESTAMP WITH TIME ZONE,
    archived_reason TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CHECK (
        (archived_at IS NULL AND archived_reason IS NULL)
        OR
        (archived_at IS NOT NULL AND length(btrim(archived_reason)) >= 10)
    )
);

CREATE TABLE project_memberships (
    project_id UUID NOT NULL REFERENCES review_projects(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES application_users(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (project_id, user_id),
    CHECK (role IN ('owner', 'editor', 'viewer'))
);

CREATE UNIQUE INDEX uq_project_memberships_active_owner
    ON project_memberships(project_id)
    WHERE role = 'owner' AND is_active = TRUE;
CREATE INDEX idx_project_memberships_user
    ON project_memberships(user_id, is_active, role, project_id);
CREATE INDEX idx_application_users_email
    ON application_users(lower(email))
    WHERE email IS NOT NULL;

-- Recibos imutáveis que permanecem disponíveis após a exclusão do projeto.
CREATE TABLE project_lifecycle_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    target_project_id UUID NOT NULL,
    project_title VARCHAR(255) NOT NULL,
    action VARCHAR(20) NOT NULL,
    actor_identifier VARCHAR(200) NOT NULL,
    owner_user_id UUID REFERENCES application_users(id) ON DELETE SET NULL,
    details_jsonb JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (action IN ('archived', 'restored', 'deleted')),
    CHECK (length(btrim(project_title)) >= 1),
    CHECK (length(btrim(actor_identifier)) >= 1),
    CHECK (jsonb_typeof(details_jsonb) = 'object')
);

CREATE INDEX idx_review_projects_active
    ON review_projects(updated_at DESC, created_at DESC)
    WHERE archived_at IS NULL;
CREATE INDEX idx_project_lifecycle_events_target
    ON project_lifecycle_events(target_project_id, created_at DESC);
CREATE INDEX idx_project_lifecycle_events_owner
    ON project_lifecycle_events(owner_user_id, created_at DESC);

-- Operações demoradas executadas fora da sessão do navegador.
CREATE TABLE project_rag_settings (
    project_id UUID PRIMARY KEY REFERENCES review_projects(id) ON DELETE CASCADE,
    visual_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision > 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Operações demoradas executadas fora da sessão do navegador.
CREATE TABLE background_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES review_projects(id) ON DELETE CASCADE,
    job_type VARCHAR(50) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'queued',
    parameters_jsonb JSONB NOT NULL DEFAULT '{}'::jsonb,
    result_jsonb JSONB,
    progress_current INTEGER NOT NULL DEFAULT 0,
    progress_total INTEGER NOT NULL DEFAULT 0,
    progress_message TEXT,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    available_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    heartbeat_at TIMESTAMP WITH TIME ZONE,
    started_at TIMESTAMP WITH TIME ZONE,
    finished_at TIMESTAMP WITH TIME ZONE,
    worker_id VARCHAR(200),
    error_code VARCHAR(80),
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (job_type IN (
        'bibliographic_search', 'pdf_indexing', 'evidence_extraction',
        'final_report', 'rag_benchmark', 'visual_cataloging',
        'visual_interpretation'
    )),
    CHECK (status IN (
        'queued', 'running', 'retry_wait', 'succeeded', 'failed', 'cancelled'
    )),
    CHECK (progress_current >= 0),
    CHECK (progress_total >= 0),
    CHECK (attempt_count >= 0),
    CHECK (max_attempts BETWEEN 1 AND 10)
);

CREATE TABLE background_job_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES background_jobs(id) ON DELETE CASCADE,
    event_type VARCHAR(30) NOT NULL,
    details_jsonb JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (event_type IN (
        'queued', 'started', 'progress', 'retry_scheduled',
        'succeeded', 'failed', 'manual_retry', 'recovered_stale'
    ))
);

CREATE UNIQUE INDEX uq_background_jobs_active_type
    ON background_jobs(project_id, job_type)
    WHERE status IN ('queued', 'running', 'retry_wait');
CREATE INDEX idx_background_jobs_claim
    ON background_jobs(status, available_at, created_at);
CREATE INDEX idx_background_jobs_project
    ON background_jobs(project_id, job_type, created_at DESC);
CREATE INDEX idx_background_job_events_job
    ON background_job_events(job_id, created_at);

-- Registro verificável das migrações e sinais de vida dos serviços da aplicação.
CREATE TABLE schema_migrations (
    migration_name VARCHAR(255) PRIMARY KEY,
    checksum_sha256 CHAR(64) NOT NULL,
    applied_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_verified_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (length(checksum_sha256) = 64)
);

CREATE TABLE service_heartbeats (
    service_name VARCHAR(50) NOT NULL,
    instance_id VARCHAR(200) NOT NULL,
    app_version VARCHAR(50) NOT NULL,
    deployment_profile VARCHAR(30) NOT NULL,
    metadata_jsonb JSONB NOT NULL DEFAULT '{}'::jsonb,
    started_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (service_name, instance_id),
    CHECK (service_name IN ('app', 'worker')),
    CHECK (deployment_profile IN ('local', 'web_private'))
);

CREATE INDEX idx_service_heartbeats_latest
    ON service_heartbeats(service_name, last_seen_at DESC);

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
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (project_id, id)
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

-- Candidatos visuais detectados sem IA e decisões humanas rastreáveis.
CREATE TABLE visual_artifacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES review_projects(id) ON DELETE CASCADE,
    paper_id UUID NOT NULL REFERENCES deduplicated_papers(id) ON DELETE CASCADE,
    detection_key CHAR(64) NOT NULL,
    file_sha256 CHAR(64) NOT NULL,
    page_number INTEGER NOT NULL,
    artifact_type VARCHAR(20) NOT NULL,
    artifact_order INTEGER NOT NULL,
    caption TEXT,
    context_text TEXT,
    bbox_jsonb JSONB,
    detection_method VARCHAR(50) NOT NULL,
    detection_metadata_jsonb JSONB NOT NULL DEFAULT '{}'::jsonb,
    extracted_content_jsonb JSONB,
    review_status VARCHAR(20) NOT NULL DEFAULT 'pending',
    human_description TEXT,
    human_notes TEXT,
    reviewer_name VARCHAR(200),
    is_current BOOLEAN NOT NULL DEFAULT TRUE,
    detected_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reviewed_at TIMESTAMP WITH TIME ZONE,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (project_id, paper_id, detection_key),
    CHECK (length(detection_key) = 64),
    CHECK (length(file_sha256) = 64),
    CHECK (page_number > 0),
    CHECK (artifact_type IN ('figure', 'table')),
    CHECK (artifact_order > 0),
    CHECK (bbox_jsonb IS NULL OR (
        jsonb_typeof(bbox_jsonb) = 'array' AND jsonb_array_length(bbox_jsonb) = 4
    )),
    CHECK (detection_method IN ('embedded_image', 'table_structure', 'caption_only')),
    CHECK (review_status IN ('pending', 'approved', 'corrected', 'rejected')),
    CHECK (human_description IS NULL OR length(btrim(human_description)) >= 10),
    CHECK (human_notes IS NULL OR length(btrim(human_notes)) >= 5)
);

CREATE TABLE visual_artifact_review_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES review_projects(id) ON DELETE CASCADE,
    artifact_id UUID NOT NULL REFERENCES visual_artifacts(id) ON DELETE CASCADE,
    action VARCHAR(20) NOT NULL,
    previous_jsonb JSONB NOT NULL,
    current_jsonb JSONB NOT NULL,
    reviewer_name VARCHAR(200) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (action IN ('approved', 'corrected', 'rejected')),
    CHECK (length(btrim(reviewer_name)) >= 2)
);

CREATE TABLE visual_interpretations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES review_projects(id) ON DELETE CASCADE,
    artifact_id UUID NOT NULL REFERENCES visual_artifacts(id) ON DELETE CASCADE,
    source_file_sha256 CHAR(64) NOT NULL,
    image_sha256 CHAR(64) NOT NULL,
    prompt_version VARCHAR(80) NOT NULL,
    provider_code VARCHAR(50) NOT NULL,
    model_name VARCHAR(150) NOT NULL,
    model_metadata_jsonb JSONB NOT NULL DEFAULT '{}'::jsonb,
    interpretation_jsonb JSONB NOT NULL,
    review_status VARCHAR(20) NOT NULL DEFAULT 'pending',
    human_interpretation_jsonb JSONB,
    human_notes TEXT,
    reviewer_name VARCHAR(200),
    is_current BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reviewed_at TIMESTAMP WITH TIME ZONE,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (length(source_file_sha256) = 64),
    CHECK (length(image_sha256) = 64),
    CHECK (review_status IN ('pending', 'approved', 'corrected', 'rejected')),
    CHECK (jsonb_typeof(model_metadata_jsonb) = 'object'),
    CHECK (jsonb_typeof(interpretation_jsonb) = 'object'),
    CHECK (human_interpretation_jsonb IS NULL OR jsonb_typeof(human_interpretation_jsonb) = 'object'),
    CHECK (human_notes IS NULL OR length(btrim(human_notes)) >= 5)
);

CREATE TABLE visual_interpretation_review_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES review_projects(id) ON DELETE CASCADE,
    interpretation_id UUID NOT NULL REFERENCES visual_interpretations(id) ON DELETE CASCADE,
    action VARCHAR(20) NOT NULL,
    previous_jsonb JSONB NOT NULL,
    current_jsonb JSONB NOT NULL,
    reviewer_name VARCHAR(200) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (action IN ('approved', 'corrected', 'rejected')),
    CHECK (length(btrim(reviewer_name)) >= 2)
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

-- Instrumentos versionados e avaliações humanas de qualidade metodológica.
-- O instrumento genérico é configurável por projeto e não representa, por si só,
-- conformidade com ferramentas oficiais como RoB 2 ou ROBINS-I.
CREATE TABLE methodological_assessment_instruments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES review_projects(id) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    name VARCHAR(200) NOT NULL,
    description TEXT NOT NULL,
    schema_version VARCHAR(50) NOT NULL DEFAULT 'generic-methodological-v1',
    domains_jsonb JSONB NOT NULL,
    change_reason TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (project_id, version),
    UNIQUE (project_id, id),
    CHECK (length(btrim(name)) >= 5),
    CHECK (length(btrim(description)) >= 10),
    CHECK (length(btrim(change_reason)) >= 5),
    CHECK (jsonb_typeof(domains_jsonb) = 'array')
);

CREATE UNIQUE INDEX uq_methodological_instrument_active
    ON methodological_assessment_instruments(project_id)
    WHERE is_active = TRUE;

CREATE TABLE methodological_assessments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES review_projects(id) ON DELETE CASCADE,
    paper_id UUID NOT NULL REFERENCES deduplicated_papers(id) ON DELETE CASCADE,
    instrument_id UUID NOT NULL REFERENCES methodological_assessment_instruments(id),
    ai_suggestion_jsonb JSONB,
    human_assessment_jsonb JSONB,
    overall_rating VARCHAR(30),
    review_status VARCHAR(30) NOT NULL DEFAULT 'pending',
    review_notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    reviewed_at TIMESTAMP WITH TIME ZONE,
    UNIQUE (project_id, paper_id, instrument_id),
    FOREIGN KEY (project_id, paper_id)
        REFERENCES deduplicated_papers(project_id, id) ON DELETE CASCADE,
    FOREIGN KEY (project_id, instrument_id)
        REFERENCES methodological_assessment_instruments(project_id, id) ON DELETE CASCADE,
    CHECK (review_status IN ('pending', 'reviewed')),
    CHECK (overall_rating IS NULL OR overall_rating IN ('low', 'moderate', 'high', 'uncertain')),
    CHECK (review_notes IS NULL OR length(btrim(review_notes)) >= 5)
);

CREATE TABLE methodological_assessment_sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    assessment_id UUID NOT NULL REFERENCES methodological_assessments(id) ON DELETE CASCADE,
    domain_code VARCHAR(80) NOT NULL,
    evidence_order INTEGER NOT NULL DEFAULT 0,
    chunk_id UUID NOT NULL REFERENCES paper_chunks(id) ON DELETE CASCADE,
    page_number INTEGER,
    quote TEXT NOT NULL,
    quote_validated BOOLEAN NOT NULL DEFAULT TRUE,
    human_validated BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (assessment_id, domain_code, evidence_order),
    CHECK (page_number IS NULL OR page_number > 0),
    CHECK (length(btrim(quote)) >= 5)
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

-- Perguntas e julgamentos humanos usados como gabarito do benchmark do RAG.
CREATE TABLE rag_golden_queries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES review_projects(id) ON DELETE CASCADE,
    question TEXT NOT NULL,
    expected_refusal BOOLEAN NOT NULL DEFAULT FALSE,
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (project_id, question),
    CHECK (length(btrim(question)) >= 5)
);

CREATE TABLE rag_golden_relevances (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    golden_query_id UUID NOT NULL REFERENCES rag_golden_queries(id) ON DELETE CASCADE,
    paper_id UUID NOT NULL REFERENCES deduplicated_papers(id) ON DELETE CASCADE,
    page_number INTEGER,
    artifact_id UUID REFERENCES visual_artifacts(id) ON DELETE CASCADE,
    relevance_grade INTEGER NOT NULL DEFAULT 2,
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CHECK (page_number IS NULL OR page_number > 0),
    CHECK (relevance_grade BETWEEN 1 AND 3)
);

CREATE UNIQUE INDEX uq_rag_golden_relevance_target
    ON rag_golden_relevances (
        golden_query_id,
        paper_id,
        COALESCE(page_number, 0),
        COALESCE(artifact_id, '00000000-0000-0000-0000-000000000000'::uuid)
    );

-- Cada edição do gabarito produz um retrato imutável, usado posteriormente
-- para reproduzir e interpretar execuções do benchmark.
CREATE TABLE rag_golden_set_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES review_projects(id) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    set_jsonb JSONB NOT NULL,
    change_reason TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (project_id, version)
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
        'extraction', 'methodological_quality', 'report',
        'visual_interpretation', 'embedding'
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

-- Calibração da estratégia com artigos conhecidos, sem inserir os resultados
-- piloto no corpus definitivo do projeto.
CREATE TABLE search_calibration_sentinels (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES review_projects(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    canonical_doi VARCHAR(255),
    notes TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CHECK (length(btrim(title)) >= 5)
);

CREATE UNIQUE INDEX uq_search_calibration_sentinel_doi
    ON search_calibration_sentinels(project_id, canonical_doi)
    WHERE canonical_doi IS NOT NULL;

CREATE TABLE search_calibration_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES review_projects(id) ON DELETE CASCADE,
    protocol_version INTEGER NOT NULL,
    protocol_fingerprint VARCHAR(64) NOT NULL,
    max_results_per_source INTEGER NOT NULL,
    status VARCHAR(20) NOT NULL,
    queries_jsonb JSONB NOT NULL,
    sentinel_snapshot_jsonb JSONB NOT NULL,
    source_results_jsonb JSONB NOT NULL,
    summary_jsonb JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CHECK (max_results_per_source BETWEEN 10 AND 100),
    CHECK (status IN ('completed', 'partial', 'failed')),
    CHECK (length(protocol_fingerprint) = 64)
);

CREATE TABLE search_calibration_matches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES search_calibration_runs(id) ON DELETE CASCADE,
    sentinel_id UUID REFERENCES search_calibration_sentinels(id) ON DELETE SET NULL,
    source_code VARCHAR(50) NOT NULL,
    result_rank INTEGER NOT NULL,
    match_method VARCHAR(30) NOT NULL,
    similarity_score NUMERIC(5,4) NOT NULL,
    matched_title TEXT NOT NULL,
    matched_doi VARCHAR(255),
    evidence_jsonb JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (run_id, sentinel_id, source_code),
    CHECK (source_code IN ('openalex', 'semantic_scholar', 'pubmed')),
    CHECK (result_rank > 0),
    CHECK (match_method IN ('doi_exact', 'title_exact', 'title_similar')),
    CHECK (similarity_score BETWEEN 0 AND 1)
);

CREATE TABLE press_search_reviews (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES review_projects(id) ON DELETE CASCADE,
    protocol_version INTEGER NOT NULL,
    protocol_fingerprint VARCHAR(64) NOT NULL,
    checklist_jsonb JSONB NOT NULL,
    overall_decision VARCHAR(30) NOT NULL,
    reviewer_name VARCHAR(150),
    review_notes TEXT,
    reviewed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (project_id, protocol_version),
    CHECK (overall_decision IN ('approved', 'changes_requested')),
    CHECK (length(protocol_fingerprint) = 64)
);

-- Limitações metodológicas revisáveis e snapshots humanos de confiança na síntese.
CREATE TABLE review_limitations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES review_projects(id) ON DELETE CASCADE,
    detected_protocol_version INTEGER NOT NULL,
    source_kind VARCHAR(30) NOT NULL,
    signal_code VARCHAR(200) NOT NULL,
    category VARCHAR(40) NOT NULL,
    scope_type VARCHAR(30) NOT NULL DEFAULT 'project',
    scope_id UUID,
    title VARCHAR(300) NOT NULL,
    description TEXT NOT NULL,
    evidence_jsonb JSONB NOT NULL DEFAULT '{}'::jsonb,
    status VARCHAR(30) NOT NULL DEFAULT 'pending',
    impact VARCHAR(20) NOT NULL DEFAULT 'moderate',
    mitigation TEXT,
    human_notes TEXT,
    is_current BOOLEAN NOT NULL DEFAULT TRUE,
    first_detected_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_detected_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    reviewed_at TIMESTAMP WITH TIME ZONE,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (project_id, signal_code),
    CHECK (source_kind IN ('automatic', 'study_reported', 'manual')),
    CHECK (category IN (
        'search_coverage', 'selection', 'document_access',
        'methodological_quality', 'evidence_traceability',
        'computational_reliability', 'other'
    )),
    CHECK (scope_type IN ('project', 'paper', 'source', 'process')),
    CHECK (status IN ('pending', 'confirmed', 'dismissed', 'mitigated', 'resolved')),
    CHECK (impact IN ('low', 'moderate', 'high')),
    CHECK (length(btrim(title)) >= 5),
    CHECK (length(btrim(description)) >= 10)
);

CREATE TABLE review_limitation_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES review_projects(id) ON DELETE CASCADE,
    limitation_id UUID NOT NULL REFERENCES review_limitations(id) ON DELETE CASCADE,
    action VARCHAR(40) NOT NULL,
    previous_jsonb JSONB,
    current_jsonb JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CHECK (action IN ('created', 'detected', 'reviewed', 'reactivated', 'deactivated'))
);

CREATE TABLE synthesis_confidence_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES review_projects(id) ON DELETE CASCADE,
    snapshot_version INTEGER NOT NULL,
    protocol_version INTEGER NOT NULL,
    protocol_fingerprint VARCHAR(64) NOT NULL,
    overall_level VARCHAR(20) NOT NULL,
    domain_ratings_jsonb JSONB NOT NULL,
    limitation_snapshot_jsonb JSONB NOT NULL,
    rationale TEXT NOT NULL,
    reviewer_name VARCHAR(150),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (project_id, snapshot_version),
    CHECK (overall_level IN ('high', 'moderate', 'low', 'very_low')),
    CHECK (length(protocol_fingerprint) = 64),
    CHECK (length(btrim(rationale)) >= 20),
    CHECK (jsonb_typeof(domain_ratings_jsonb) = 'array'),
    CHECK (jsonb_typeof(limitation_snapshot_jsonb) = 'array')
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
CREATE INDEX idx_rag_golden_queries_project ON rag_golden_queries(project_id, created_at);
CREATE INDEX idx_rag_golden_relevances_query ON rag_golden_relevances(golden_query_id);
CREATE INDEX idx_rag_golden_versions_project ON rag_golden_set_versions(project_id, version DESC);
CREATE INDEX idx_prisma_snapshots_project ON prisma_flow_snapshots(project_id, snapshot_version DESC);
CREATE INDEX idx_paper_chunks_paper ON paper_chunks(paper_id);
CREATE INDEX idx_embeddings_chunk ON embeddings_metadata(chunk_id);
CREATE INDEX idx_visual_artifacts_project_status ON visual_artifacts(project_id, is_current, review_status, page_number);
CREATE INDEX idx_visual_artifacts_paper ON visual_artifacts(paper_id, page_number, artifact_order);
CREATE INDEX idx_visual_artifact_events_artifact ON visual_artifact_review_events(artifact_id, created_at);
CREATE UNIQUE INDEX uq_visual_interpretations_current ON visual_interpretations(project_id, artifact_id) WHERE is_current = TRUE;
CREATE INDEX idx_visual_interpretations_project_status ON visual_interpretations(project_id, is_current, review_status, created_at DESC);
CREATE INDEX idx_visual_interpretation_events ON visual_interpretation_review_events(interpretation_id, created_at);
CREATE INDEX idx_evidence_sources_extraction ON evidence_field_sources(extraction_id);
CREATE INDEX idx_evidence_sources_chunk ON evidence_field_sources(chunk_id);
CREATE INDEX idx_methodological_instruments_project ON methodological_assessment_instruments(project_id, version DESC);
CREATE INDEX idx_methodological_assessments_project ON methodological_assessments(project_id, review_status, updated_at DESC);
CREATE INDEX idx_methodological_assessments_paper ON methodological_assessments(paper_id);
CREATE INDEX idx_methodological_sources_assessment ON methodological_assessment_sources(assessment_id, domain_code);
CREATE INDEX idx_ai_credentials_scope ON ai_provider_credentials(scope_type, scope_id, owner_user_id);
CREATE INDEX idx_ai_model_settings_scope ON ai_model_settings(scope_type, scope_id, owner_user_id);
CREATE INDEX idx_ai_configuration_audit_created ON ai_configuration_audit(created_at DESC);
CREATE INDEX idx_bibliographic_settings_scope ON bibliographic_source_settings(scope_type, scope_id, owner_user_id);
CREATE INDEX idx_bibliographic_credentials_scope ON bibliographic_source_credentials(scope_type, scope_id, owner_user_id);
CREATE INDEX idx_bibliographic_audit_created ON bibliographic_configuration_audit(created_at DESC);
CREATE INDEX idx_search_calibration_sentinels_project ON search_calibration_sentinels(project_id, is_active, created_at);
CREATE INDEX idx_search_calibration_runs_project ON search_calibration_runs(project_id, created_at DESC);
CREATE INDEX idx_search_calibration_matches_run ON search_calibration_matches(run_id, source_code, result_rank);
CREATE INDEX idx_press_search_reviews_project ON press_search_reviews(project_id, protocol_version DESC);
CREATE INDEX idx_review_limitations_project ON review_limitations(project_id, is_current, status, category, updated_at DESC);
CREATE INDEX idx_review_limitations_scope ON review_limitations(project_id, scope_type, scope_id);
CREATE INDEX idx_review_limitation_events_project ON review_limitation_events(project_id, created_at DESC);
CREATE INDEX idx_synthesis_confidence_project ON synthesis_confidence_snapshots(project_id, snapshot_version DESC);
