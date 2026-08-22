BEGIN;

CREATE TABLE IF NOT EXISTS review_limitations (
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

CREATE TABLE IF NOT EXISTS review_limitation_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES review_projects(id) ON DELETE CASCADE,
    limitation_id UUID NOT NULL REFERENCES review_limitations(id) ON DELETE CASCADE,
    action VARCHAR(40) NOT NULL,
    previous_jsonb JSONB,
    current_jsonb JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CHECK (action IN ('created', 'detected', 'reviewed', 'reactivated', 'deactivated'))
);

-- Mantém a migração idempotente também em instalações que executaram uma versão
-- anterior deste arquivo durante o desenvolvimento.
ALTER TABLE review_limitation_events
    DROP CONSTRAINT IF EXISTS review_limitation_events_action_check;
ALTER TABLE review_limitation_events
    ADD CONSTRAINT review_limitation_events_action_check
    CHECK (action IN ('created', 'detected', 'reviewed', 'reactivated', 'deactivated'));

CREATE TABLE IF NOT EXISTS synthesis_confidence_snapshots (
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

CREATE INDEX IF NOT EXISTS idx_review_limitations_project
    ON review_limitations(project_id, is_current, status, category, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_review_limitations_scope
    ON review_limitations(project_id, scope_type, scope_id);
CREATE INDEX IF NOT EXISTS idx_review_limitation_events_project
    ON review_limitation_events(project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_synthesis_confidence_project
    ON synthesis_confidence_snapshots(project_id, snapshot_version DESC);

COMMIT;
