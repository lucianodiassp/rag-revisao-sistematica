BEGIN;

ALTER TABLE extracted_evidence
    ADD COLUMN IF NOT EXISTS schema_version VARCHAR(50) NOT NULL DEFAULT 'legacy-v0',
    ADD COLUMN IF NOT EXISTS human_review_jsonb JSONB,
    ADD COLUMN IF NOT EXISTS review_notes TEXT,
    ADD COLUMN IF NOT EXISTS extracted_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMP WITH TIME ZONE;

CREATE UNIQUE INDEX IF NOT EXISTS uq_extracted_evidence_paper
    ON extracted_evidence(paper_id);

CREATE TABLE IF NOT EXISTS evidence_field_sources (
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

-- Garante a mesma regra caso a tabela tenha sido criada por uma versão anterior
-- desta migração durante o desenvolvimento.
ALTER TABLE evidence_field_sources
    DROP CONSTRAINT IF EXISTS evidence_field_sources_chunk_id_fkey;
ALTER TABLE evidence_field_sources
    ADD CONSTRAINT evidence_field_sources_chunk_id_fkey
    FOREIGN KEY (chunk_id) REFERENCES paper_chunks(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS idx_evidence_sources_extraction
    ON evidence_field_sources(extraction_id);
CREATE INDEX IF NOT EXISTS idx_evidence_sources_chunk
    ON evidence_field_sources(chunk_id);

COMMIT;
