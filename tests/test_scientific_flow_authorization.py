"""Contratos de autorização das operações científicas vinculadas a projetos."""

from unittest.mock import Mock, patch

import pytest

from backend.app import (
    deduplication,
    methodological_quality,
    rag_benchmark,
    screening_service,
    search_calibration,
    synthesis_confidence,
    visual_catalog,
    visual_interpretation,
    visual_rag,
)


PROJECT_ID = "project-authorization-contract"
PAPER_ID = "paper-authorization-contract"
RESOURCE_ID = "resource-authorization-contract"


def _assert_gate(module, expected_role, operation):
    with patch.object(
        module,
        "enforce_project_access",
        side_effect=PermissionError("blocked by authorization contract"),
    ) as access_gate:
        with pytest.raises(PermissionError, match="authorization contract"):
            operation()

    assert access_gate.call_count == 1
    assert access_gate.call_args.args[:2] == (PROJECT_ID, expected_role)


@pytest.mark.parametrize(
    ("module", "operation"),
    [
        (
            screening_service,
            lambda: screening_service.get_screening_summary(
                PROJECT_ID, connection_factory=Mock()
            ),
        ),
        (
            deduplication,
            lambda: deduplication.listar_resumo_deduplicacao(
                PROJECT_ID, connection_factory=Mock()
            ),
        ),
        (
            search_calibration,
            lambda: search_calibration.list_calibration_runs(
                PROJECT_ID, connection_factory=Mock()
            ),
        ),
        (
            synthesis_confidence,
            lambda: synthesis_confidence.list_limitations(
                PROJECT_ID, connection_factory=Mock()
            ),
        ),
        (
            methodological_quality,
            lambda: methodological_quality.list_instrument_versions(PROJECT_ID),
        ),
        (
            visual_catalog,
            lambda: visual_catalog.list_visual_artifacts(PROJECT_ID),
        ),
        (
            visual_interpretation,
            lambda: visual_interpretation.get_current_visual_interpretation(
                PROJECT_ID, RESOURCE_ID
            ),
        ),
        (
            visual_rag,
            lambda: visual_rag.get_visual_rag_setting(PROJECT_ID),
        ),
        (
            rag_benchmark,
            lambda: rag_benchmark.get_latest_rag_benchmark(PROJECT_ID),
        ),
    ],
)
def test_scientific_reads_require_viewer_role(module, operation):
    _assert_gate(module, "viewer", operation)


@pytest.mark.parametrize(
    ("module", "operation"),
    [
        (
            screening_service,
            lambda: screening_service.save_human_screening_decision(
                PROJECT_ID,
                PAPER_ID,
                screening_service.DECISION_INCLUDE,
                connection_factory=Mock(),
            ),
        ),
        (
            deduplication,
            lambda: deduplication.revisar_decisao_deduplicacao(
                PROJECT_ID,
                RESOURCE_ID,
                deduplication.HUMAN_KEEP_SEPARATE,
                "Decisão humana justificada.",
                connection_factory=Mock(),
            ),
        ),
        (
            search_calibration,
            lambda: search_calibration.save_sentinel(
                PROJECT_ID,
                "Estudo sentinela para autorização",
                connection_factory=Mock(),
            ),
        ),
        (
            synthesis_confidence,
            lambda: synthesis_confidence.review_limitation(
                PROJECT_ID,
                RESOURCE_ID,
                "confirmed",
                "moderate",
                connection_factory=Mock(),
            ),
        ),
        (
            methodological_quality,
            lambda: methodological_quality.create_instrument_version(
                PROJECT_ID, "Instrumento", "Descrição suficiente", [], "Nova versão"
            ),
        ),
        (
            visual_catalog,
            lambda: visual_catalog.review_visual_artifact(
                PROJECT_ID, RESOURCE_ID, "approved", "Pessoa revisora"
            ),
        ),
        (
            visual_interpretation,
            lambda: visual_interpretation.review_visual_interpretation(
                PROJECT_ID, RESOURCE_ID, "approved", "Pessoa revisora"
            ),
        ),
        (
            visual_rag,
            lambda: visual_rag.set_visual_rag_setting(PROJECT_ID, True),
        ),
        (
            rag_benchmark,
            lambda: rag_benchmark.run_rag_benchmark(PROJECT_ID),
        ),
    ],
)
def test_scientific_mutations_require_editor_role(module, operation):
    _assert_gate(module, "editor", operation)
