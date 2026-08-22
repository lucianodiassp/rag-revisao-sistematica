import hashlib
import io
import json
import zipfile

import pytest

from backend.app.reproducibility_package import (
    PACKAGE_FORMAT,
    PACKAGE_VERSION,
    ReproducibilityPackageError,
    build_reproducibility_package,
)
from backend.app.version import APP_VERSION


PROJECT_ID = "11111111-1111-1111-1111-111111111111"
PAPER_ID = "22222222-2222-2222-2222-222222222222"


def _dataset():
    return {
        "project": {
            "id": PROJECT_ID,
            "title": "Revisão com acentuação",
            "question": "Quais métodos foram utilizados?",
            "criteria_jsonb": {
                "pico": {"population": "Estudos científicos"},
                "api_key": "segredo-que-nao-pode-sair",
            },
            "status": "search_ready",
            "protocol_version": 2,
            "created_at": "2026-08-01T10:00:00+00:00",
            "updated_at": "2026-08-02T10:00:00+00:00",
        },
        "protocol_versions": [
            {
                "version": 1,
                "question": "Pergunta inicial",
                "criteria_jsonb": {},
                "change_reason": "Criação",
            }
        ],
        "searches": [
            {
                "id": "search-1",
                "source": "OpenAlex",
                "query_text": "machine learning",
                "query_jsonb": {
                    "source_configuration": {
                        "authenticated": True,
                        "contact_email": "pesquisador@example.org",
                    }
                },
            }
        ],
        "retrieved_records": [
            {
                "id": "record-1",
                "source": "OpenAlex",
                "doi": "10.1000/teste",
                "metadata_jsonb": {"title": "Título científico"},
                "raw_jsonb": {
                    "token": "token-secreto",
                    "openalex_api_key": "outra-chave-secreta",
                },
            }
        ],
        "papers": [
            {
                "id": PAPER_ID,
                "title": "=HYPERLINK(\"https://example.org\")",
                "canonical_doi": "10.1000/teste",
                "abstract": "Resumo público.",
                "merged_sources_jsonb": {"sources": ["OpenAlex"]},
            }
        ],
        "deduplication": [],
        "screening": [
            {
                "paper_id": PAPER_ID,
                "paper_title": "Título científico",
                "suggested_decision": "Incluir",
                "human_decision": "Incluir",
                "justification": "Atende aos critérios.",
            }
        ],
        "reassessments": [],
        "extractions": [
            {
                "id": "extraction-1",
                "paper_id": PAPER_ID,
                "paper_title": "Título científico",
                "extraction_jsonb": {
                    "objective": {"value": "Avaliar o método", "evidence": []},
                    "method": {"value": "Experimento", "evidence": []},
                    "dataset": {"value": "Amostra A", "evidence": []},
                    "metrics": {"value": ["Precisão"], "evidence": []},
                    "main_results": {"value": "Resultado principal", "evidence": []},
                    "limitations": {"value": ["Amostra pequena"], "evidence": []},
                },
                "human_review_status": "approved",
                "human_review_jsonb": {
                    "objective": "Avaliar o método",
                    "method": "Experimento",
                    "dataset": "Amostra A",
                    "metrics": ["Precisão"],
                    "main_results": "Resultado principal",
                    "limitations": ["Amostra pequena"],
                },
                "schema_version": "traceable-v1",
                "validated_sources": [
                    {
                        "chunk_id": "chunk-1",
                        "page_number": 3,
                        "quote": "Trecho literal validado.",
                    }
                ],
            }
        ],
        "evidence_sources": [
            {
                "extraction_id": "extraction-1",
                "paper_id": PAPER_ID,
                "chunk_id": "chunk-1",
                "page_number": 3,
                "quote": "Trecho literal validado.",
                "quote_validated": True,
            }
        ],
        "methodological_instruments": [
            {
                "id": "instrument-1",
                "version": 1,
                "name": "Checklist genérico",
                "domains_jsonb": [{"code": "study_design", "label": "Desenho"}],
                "is_active": True,
            }
        ],
        "methodological_assessments": [
            {
                "id": "assessment-1",
                "paper_id": PAPER_ID,
                "paper_title": "Título científico",
                "instrument_id": "instrument-1",
                "instrument_version": 1,
                "human_assessment_jsonb": {
                    "domains": [
                        {
                            "domain_code": "study_design",
                            "response": "yes",
                            "justification": "Desenho claramente descrito.",
                        }
                    ]
                },
                "overall_rating": "low",
                "review_status": "reviewed",
            }
        ],
        "methodological_sources": [
            {
                "assessment_id": "assessment-1",
                "paper_id": PAPER_ID,
                "domain_code": "study_design",
                "page_number": 3,
                "quote": "Trecho metodológico literal.",
                "human_validated": True,
            }
        ],
        "document_index": [
            {
                "paper_id": PAPER_ID,
                "paper_title": "Título científico",
                "full_text_chunks": 4,
                "embedding_records": 4,
                "embedding_models": ["embedding-model"],
                "embedding_dimensions": [768],
            }
        ],
        "interactions": [
            {
                "id": "interaction-1",
                "agent_name": "report_agent",
                "input_jsonb": {"paper_ids": [PAPER_ID]},
                "output_jsonb": {
                    "report_markdown": "# Síntese final\n\nResultado com evidência."
                },
                "model_jsonb": {
                    "provider": "google_gemini",
                    "model_name": "gemini-test",
                    "task": "report",
                    "password": "nao-exportar",
                },
                "created_at": "2026-08-03T10:00:00+00:00",
            }
        ],
        "evaluations": [],
        "golden_queries": [],
        "golden_versions": [],
        "prisma_snapshots": [],
        "review_limitations": [
            {
                "id": "limitation-1",
                "source_kind": "manual",
                "signal_code": "manual:1",
                "category": "other",
                "title": "Limitação confirmada",
                "description": "Limitação registrada pelo pesquisador.",
                "status": "confirmed",
                "impact": "moderate",
                "is_current": True,
            }
        ],
        "review_limitation_events": [],
        "synthesis_confidence_snapshots": [
            {
                "id": "confidence-1",
                "snapshot_version": 1,
                "protocol_version": 2,
                "overall_level": "moderate",
                "domain_ratings_jsonb": [],
                "limitation_snapshot_jsonb": [],
                "rationale": "Classificação humana registrada para a síntese.",
            }
        ],
    }


def test_package_contains_readable_artifacts_and_manifest_hashes():
    result = build_reproducibility_package(
        _dataset(), generated_at="2026-08-16T15:30:00+00:00"
    )

    with zipfile.ZipFile(io.BytesIO(result["data"]), "r") as archive:
        names = set(archive.namelist())
        assert "README.md" in names
        assert "manifest.json" in names
        assert "05_evidencias/matriz_evidencias.csv" in names
        assert "06_avaliacao/avaliacoes_metodologicas.json" in names
        assert "06_avaliacao/fontes_metodologicas.csv" in names
        assert "06_avaliacao/limitacoes_sintese.json" in names
        assert "06_avaliacao/confianca_sintese.json" in names
        assert "08_relatorio/relatorio_final.md" in names
        assert not any(name.lower().endswith(".pdf") for name in names)

        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["format"] == PACKAGE_FORMAT
        assert manifest["version"] == PACKAGE_VERSION
        assert manifest["application"]["version"] == APP_VERSION
        assert manifest["application"]["deployment_profile"] == "local"
        assert manifest["counts"]["unique_papers"] == 1
        assert manifest["counts"]["indexed_papers"] == 1
        assert manifest["counts"]["reviewed_methodological_assessments"] == 1
        assert manifest["counts"]["review_limitations"] == 1
        assert manifest["counts"]["synthesis_confidence_snapshots"] == 1
        assert manifest["scope"]["secrets_excluded"] is True
        for entry in manifest["integrity"]["files"]:
            content = archive.read(entry["path"])
            assert len(content) == entry["size"]
            assert hashlib.sha256(content).hexdigest() == entry["sha256"]


def test_package_redacts_secrets_and_preserves_utf8_csv():
    result = build_reproducibility_package(
        _dataset(), generated_at="2026-08-16T15:30:00+00:00"
    )

    with zipfile.ZipFile(io.BytesIO(result["data"]), "r") as archive:
        exported_content = b"\n".join(archive.read(name) for name in archive.namelist())
        assert b"segredo-que-nao-pode-sair" not in exported_content
        assert b"token-secreto" not in exported_content
        assert b"outra-chave-secreta" not in exported_content
        assert b"nao-exportar" not in exported_content
        assert b"pesquisador@example.org" not in exported_content
        matrix = archive.read("05_evidencias/matriz_evidencias.csv")
        assert matrix.startswith(b"\xef\xbb\xbf")
        assert "Título científico" in matrix.decode("utf-8-sig")
        papers_csv = archive.read("03_selecao/artigos_unicos.csv").decode("utf-8-sig")
        assert "'=HYPERLINK" in papers_csv
        project = json.loads(archive.read("01_projeto/projeto.json"))
        assert project["criteria_jsonb"]["api_key"] == "[REMOVIDO DO PACOTE]"


def test_package_filename_is_portable_and_checksum_matches():
    result = build_reproducibility_package(
        _dataset(), generated_at="2026-08-16T15:30:00+00:00"
    )

    assert result["filename"].startswith("pacote-reprodutibilidade-revisao-com-acentuacao-")
    assert result["filename"].endswith(".zip")
    assert result["sha256"] == hashlib.sha256(result["data"]).hexdigest()


def test_package_rejects_incomplete_project_snapshot():
    with pytest.raises(ReproducibilityPackageError, match="incompleto"):
        build_reproducibility_package({"project": {}})
