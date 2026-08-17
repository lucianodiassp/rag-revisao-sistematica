import io
import json
import zipfile

import pytest

from backend.app.reproducibility_import import (
    ReproducibilityImportError,
    import_reproducibility_package,
    validate_reproducibility_package,
)
from backend.app.reproducibility_package import build_reproducibility_package


PROJECT_ID = "81000000-0000-4000-8000-000000000001"
PROTOCOL_ID = "81000000-0000-4000-8000-000000000002"
SEARCH_ID = "81000000-0000-4000-8000-000000000003"
RECORD_ID = "81000000-0000-4000-8000-000000000004"
PAPER_ID = "81000000-0000-4000-8000-000000000005"
SCREENING_ID = "81000000-0000-4000-8000-000000000006"
EXTRACTION_ID = "81000000-0000-4000-8000-000000000007"
CHUNK_ID = "81000000-0000-4000-8000-000000000008"


def _dataset():
    source = {
        "id": "81000000-0000-4000-8000-000000000009",
        "extraction_id": EXTRACTION_ID,
        "paper_id": PAPER_ID,
        "field_name": "objective",
        "evidence_order": 0,
        "chunk_id": CHUNK_ID,
        "page_number": 2,
        "quote": "Trecho literal preservado para auditoria.",
        "quote_validated": True,
    }
    return {
        "project": {
            "id": PROJECT_ID,
            "title": "Projeto portável",
            "question": "Quais resultados foram encontrados?",
            "criteria_jsonb": {"pico": {}, "_demo": {"seed_id": "demo-antiga"}},
            "status": "search_ready",
            "protocol_version": 1,
        },
        "protocol_versions": [
            {
                "id": PROTOCOL_ID,
                "project_id": PROJECT_ID,
                "version": 1,
                "question": "Quais resultados foram encontrados?",
                "criteria_jsonb": {"pico": {}},
                "change_reason": "Criação do protocolo",
            }
        ],
        "searches": [
            {
                "id": SEARCH_ID,
                "project_id": PROJECT_ID,
                "source": "OpenAlex",
                "query_text": "systematic review",
                "query_jsonb": {},
            }
        ],
        "retrieved_records": [
            {
                "id": RECORD_ID,
                "project_id": PROJECT_ID,
                "search_query_id": SEARCH_ID,
                "source": "OpenAlex",
                "external_id": "W123",
                "doi": "10.1000/portable",
                "metadata_jsonb": {"title": "Artigo portável"},
                "raw_jsonb": {},
            }
        ],
        "papers": [
            {
                "id": PAPER_ID,
                "project_id": PROJECT_ID,
                "canonical_doi": "10.1000/portable",
                "title": "Artigo portável",
                "abstract": "Resumo do artigo.",
                "merged_sources_jsonb": {"sources": ["OpenAlex"]},
            }
        ],
        "deduplication": [],
        "screening": [
            {
                "id": SCREENING_ID,
                "paper_id": PAPER_ID,
                "paper_title": "Artigo portável",
                "suggested_decision": "Incluir",
                "human_decision": "Incluir",
                "rationale_jsonb": {"confidence": 0.9},
                "justification": "Atende aos critérios definidos.",
            }
        ],
        "reassessments": [],
        "extractions": [
            {
                "id": EXTRACTION_ID,
                "paper_id": PAPER_ID,
                "paper_title": "Artigo portável",
                "extraction_jsonb": {
                    "objective": {
                        "value": "Avaliar portabilidade",
                        "evidence": [{"chunk_id": CHUNK_ID, "page_number": 2}],
                    }
                },
                "schema_version": "traceable-v1",
                "human_review_status": "approved",
                "validated_sources": [source],
            }
        ],
        "evidence_sources": [source],
        "methodological_instruments": [],
        "methodological_assessments": [],
        "methodological_sources": [],
        "document_index": [
            {
                "paper_id": PAPER_ID,
                "paper_title": "Artigo portável",
                "full_text_chunks": 5,
                "embedding_records": 5,
                "embedding_models": ["embedding-model"],
                "embedding_dimensions": [768],
            }
        ],
        "interactions": [],
        "evaluations": [],
        "golden_queries": [],
        "golden_versions": [],
        "prisma_snapshots": [],
    }


def _package():
    return build_reproducibility_package(
        _dataset(), generated_at="2026-08-17T18:00:00+00:00"
    )["data"]


def _rewrite_package(data, changes=None, extra_files=None):
    changes = changes or {}
    extra_files = extra_files or {}
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data), "r") as source, zipfile.ZipFile(
        output, "w", compression=zipfile.ZIP_DEFLATED
    ) as target:
        for name in source.namelist():
            target.writestr(name, changes.get(name, source.read(name)))
        for name, content in extra_files.items():
            target.writestr(name, content)
    return output.getvalue()


class RecordingCursor:
    def __init__(self, fail_at=None):
        self.calls = []
        self.fail_at = fail_at

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def execute(self, query, params=()):
        self.calls.append((query, params))
        if self.fail_at and len(self.calls) == self.fail_at:
            raise RuntimeError("falha simulada")


class RecordingConnection:
    def __init__(self, fail_at=None):
        self.recording_cursor = RecordingCursor(fail_at=fail_at)
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def cursor(self):
        return self.recording_cursor

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


def test_validation_confirms_integrity_and_reports_operational_limits():
    preview = validate_reproducibility_package(_package())

    assert preview["manifest"]["project"]["title"] == "Projeto portável"
    assert preview["manifest"]["counts"]["unique_papers"] == 1
    assert preview["dataset"]["evidence_sources"][0]["chunk_id"] == CHUNK_ID
    assert any("PDFs" in warning for warning in preview["warnings"])


def test_validation_rejects_tampered_content():
    tampered = _rewrite_package(
        _package(),
        changes={"01_projeto/projeto.json": b'{"id":"alterado"}'},
    )

    with pytest.raises(ReproducibilityImportError, match="manifesto|integridade"):
        validate_reproducibility_package(tampered)


def test_validation_rejects_unsafe_archive_path():
    unsafe = _rewrite_package(_package(), extra_files={"../fora.txt": b"nao extrair"})

    with pytest.raises(ReproducibilityImportError, match="inseguro"):
        validate_reproducibility_package(unsafe)


def test_import_remaps_ids_preserves_audit_quotes_and_commits_once():
    connection = RecordingConnection()

    result = import_reproducibility_package(
        _package(),
        title="Projeto reconstruído",
        connection_factory=lambda: connection,
    )

    statements = "\n".join(query for query, _ in connection.recording_cursor.calls)
    project_call = next(
        call
        for call in connection.recording_cursor.calls
        if "INSERT INTO review_projects" in call[0]
    )
    imported_criteria = project_call[1][3].adapted
    assert result["source_project_id"] == PROJECT_ID
    assert result["project_id"] != PROJECT_ID
    assert result["title"] == "Projeto reconstruído"
    assert "INSERT INTO review_projects" in statements
    assert "INSERT INTO paper_chunks" in statements
    assert "imported_evidence_quote" in statements
    assert "INSERT INTO evidence_field_sources" in statements
    assert "_demo" not in imported_criteria
    assert imported_criteria["_import"]["source_project_id"] == PROJECT_ID
    assert imported_criteria["_import"]["package_sha256"] == result["sha256"]
    assert connection.commits == 1
    assert connection.rollbacks == 0
    assert connection.closed is True


def test_import_rolls_back_everything_on_database_failure():
    connection = RecordingConnection(fail_at=4)

    with pytest.raises(ReproducibilityImportError, match="nenhuma alteração"):
        import_reproducibility_package(
            _package(),
            connection_factory=lambda: connection,
        )

    assert connection.commits == 0
    assert connection.rollbacks == 1
    assert connection.closed is True
