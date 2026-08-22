import json
import uuid
from datetime import datetime, timezone

from backend.app.synthesis_confidence import (
    CONFIDENCE_DOMAINS,
    confidence_snapshot_json,
    derive_limitation_signals,
    suggest_confidence,
)


def _complete_facts():
    return {
        "protocol_version": 2,
        "calibration": {
            "protocol_version": 2,
            "status": "completed",
            "summary_jsonb": {
                "known_item_sensitivity": 1,
                "active_sentinels": 3,
                "recovered_unique": 3,
            },
        },
        "press_review": {
            "overall_decision": "approved",
            "checklist_jsonb": [{"response": "yes"}],
        },
        "dedup_pending": 0,
        "workflow": {
            "papers": 1,
            "screening_pending": 0,
            "included": 1,
            "indexed": 1,
            "used_ocr": 0,
            "synthesis_ready": 1,
        },
        "methodological": {
            "included": 1,
            "reviewed": 1,
            "high_risk": 0,
            "uncertain": 0,
        },
        "benchmark": {
            "metrics_jsonb": {
                "summary": {
                    "comparison_cohort": {"query_count": 12},
                    "failed_query_count": 0,
                    "reranking_calibration": {"coverage_status": "complete"},
                }
            }
        },
        "study_limitations": [],
    }


def test_complete_project_has_no_automatic_limitation_signals():
    assert derive_limitation_signals(_complete_facts()) == []


def test_incomplete_workflow_produces_explainable_scoped_signals():
    facts = _complete_facts()
    facts.update({"calibration": None, "press_review": None, "dedup_pending": 2})
    facts["workflow"].update(
        {"screening_pending": 4, "included": 3, "indexed": 1, "synthesis_ready": 0}
    )
    facts["methodological"].update({"included": 3, "reviewed": 0})
    facts["benchmark"] = None

    signals = derive_limitation_signals(facts)
    by_code = {item["signal_code"]: item for item in signals}

    assert by_code["search_calibration_current_missing"]["category"] == "search_coverage"
    assert by_code["press_review_current_missing"]["source_kind"] == "automatic"
    assert by_code["deduplication_pending"]["evidence_jsonb"]["pending_decisions"] == 2
    assert by_code["included_full_text_missing"]["impact"] == "high"
    assert by_code["evidence_review_incomplete"]["evidence_jsonb"]["pending"] == 3
    assert by_code["methodological_quality_incomplete"]["impact"] == "high"
    assert by_code["rag_benchmark_missing"]["impact"] == "low"


def test_study_reported_limitations_are_distinguished_from_review_process():
    facts = _complete_facts()
    paper_id = uuid.uuid4()
    facts["study_limitations"] = [
        {
            "paper_id": paper_id,
            "title": "Estudo A",
            "limitations": ["Amostra pequena", "Curto acompanhamento"],
        }
    ]

    signal = derive_limitation_signals(facts)[0]

    assert signal["source_kind"] == "study_reported"
    assert signal["scope_type"] == "paper"
    assert signal["scope_id"] == str(paper_id)
    assert signal["evidence_jsonb"]["reported_limitations"] == [
        "Amostra pequena", "Curto acompanhamento"
    ]


def test_confidence_suggestion_is_deterministic_but_explicitly_non_binding():
    limitations = [
        {
            "id": "high-confirmed",
            "category": "document_access",
            "impact": "high",
            "status": "confirmed",
            "is_current": True,
        },
        {
            "id": "high-mitigated",
            "category": "search_coverage",
            "impact": "high",
            "status": "mitigated",
            "is_current": True,
        },
        {
            "id": "ignored",
            "category": "selection",
            "impact": "high",
            "status": "dismissed",
            "is_current": True,
        },
    ]

    result = suggest_confidence(limitations)
    domains = {item["code"]: item for item in result["domains"]}

    assert result["overall_level"] == "low"
    assert domains["document_access"]["suggested_level"] == "low"
    assert domains["search_coverage"]["suggested_level"] == "moderate"
    assert len(domains) == len(CONFIDENCE_DOMAINS)
    assert "não vinculante" in result["notice"]


def test_snapshot_export_handles_postgresql_types_and_preserves_utf8():
    payload = {
        "id": uuid.uuid4(),
        "created_at": datetime(2026, 8, 21, 12, 0, tzinfo=timezone.utc),
        "rationale": "Confiança moderada após revisão das limitações.",
    }

    exported = confidence_snapshot_json(payload)
    decoded = json.loads(exported)

    assert decoded["id"] == str(payload["id"])
    assert decoded["created_at"] == "2026-08-21T12:00:00+00:00"
    assert "limitações" in exported.decode("utf-8")
