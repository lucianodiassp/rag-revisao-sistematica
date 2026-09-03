import hashlib
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import pytest

from backend.app import visual_rag as vr
from backend.app.rag_citations import formatar_citacao, validar_citacoes_rag
from backend.app.retrieval_metrics import evaluate_ranking
from backend.app.rag_benchmark import _compare_visual_runs, _validate_visual_benchmark_snapshot
from backend.app.reranking import _candidato_auditavel
from backend.agentes import agente_rag as rag


PAPER = "74000000-0000-0000-0000-000000000001"
ARTIFACT = "74000000-0000-0000-0000-000000000002"
INTERPRETATION = "74000000-0000-0000-0000-000000000003"


def row():
    return {
        "id": INTERPRETATION, "artifact_id": ARTIFACT, "paper_id": PAPER,
        "page_number": 2, "artifact_type": "figure", "caption": "Rotas de transporte",
        "paper_title": "Estudo de logística", "source_file_sha256": "a" * 64,
        "review_status": "approved", "human_description": "Fluxo de otimização de rotas.",
        "artifact_updated_at": "2026-09-03", "updated_at": "2026-09-03",
        "provider_code": "google_gemini", "model_name": "example",
        "interpretation_jsonb": {"summary": "As rotas reduzem o deslocamento.",
                                 "observations": ["A rota A é menor."], "limitations": ["Escala ilegível"],
                                 "structured_data": {"valor": 999}},
    }


def evidence():
    return {"source_type": vr.SOURCE_TYPE, "paper_id": PAPER, "artifact_id": ARTIFACT,
            "interpretation_id": INTERPRETATION, "page_number": 2, "evidence_revision": "rev1",
            "setting_revision": 1, "source_file_sha256": "a" * 64,
            "text": "Interpretação revisada das rotas.", "candidate_id": "c2", "chunk_id": None,
            "original_rank": 2, "rrf_score": .01, "rerank_rank": 1}


def db_mock(monkeypatch, rows=None, one=None):
    cursor = MagicMock()
    cursor.__enter__.return_value = cursor
    cursor.fetchall.return_value = rows or []
    cursor.fetchone.return_value = one
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.cursor.return_value = cursor
    factory = Mock(return_value=connection)
    monkeypatch.setattr(vr, "get_connection", factory)
    return cursor


def test_absent_project_setting_is_off(monkeypatch):
    db_mock(monkeypatch)
    assert vr.get_visual_rag_setting("project") == {"enabled": False, "revision": 0}


def test_saving_setting_has_revision_and_audit(monkeypatch):
    cursor = db_mock(monkeypatch, one=(4,))
    assert vr.set_visual_rag_setting("project", True) == {"enabled": True, "revision": 4}
    sql = " ".join(c.args[0] for c in cursor.execute.call_args_list)
    assert "FOR UPDATE" in sql
    assert "revision + 1" in sql
    assert "visual_rag_configuration" in sql


@pytest.mark.parametrize("value", [None, "true", 1])
def test_setting_rejects_non_boolean(value):
    with pytest.raises(ValueError):
        vr.set_visual_rag_setting("project", value)


def test_corrected_summary_does_not_reuse_original_ai_data():
    item = row()
    item.update(review_status="corrected", human_interpretation_jsonb={"summary": "Correção humana: nenhum valor é legível."})
    text = vr._reviewed_text(item)
    assert "Correção humana" in text
    assert "999" not in text
    assert "A rota A" not in text


def test_approved_summary_preserves_limits_and_values():
    text = vr._reviewed_text(row())
    assert "Escala ilegível" in text and "999" in text
    assert "não é transcrição literal" in text


def test_query_restricts_project_two_reviews_current_pdf_and_inclusion(monkeypatch):
    cursor = db_mock(monkeypatch, [row()])
    monkeypatch.setattr(vr, "_pdf_hash", lambda _: "a" * 64)
    result = vr.list_eligible_visual_evidence("project", setting={"revision": 3})
    sql, parameters = cursor.execute.call_args.args
    assert parameters == ("project", vr.MAX_ELIGIBLE_ROWS + 1)
    for fragment in ("i.project_id = %s", "i.is_current AND a.is_current",
                     "i.review_status IN", "a.review_status IN", "s.human_decision = 'Incluir'",
                     "i.source_file_sha256 = a.file_sha256", "p.project_id = a.project_id"):
        assert fragment in sql
    assert result[0]["chunk_id"] is None
    assert result[0]["setting_revision"] == 3
    assert len(result[0]["evidence_revision"]) == 64


@pytest.mark.parametrize("actual_hash", [None, "b" * 64])
def test_changed_or_missing_pdf_not_retrieved(monkeypatch, actual_hash):
    db_mock(monkeypatch, [row()])
    monkeypatch.setattr(vr, "_pdf_hash", lambda _: actual_hash)
    assert vr.list_eligible_visual_evidence("project") == []


def test_hash_pdf_bytes_and_detect_replacement(tmp_path, monkeypatch):
    import fitz
    monkeypatch.setattr(vr, "pdf_directory", lambda: tmp_path)
    path = tmp_path / f"{PAPER}.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.save(path)
    doc.close()
    before = vr._pdf_hash(PAPER)
    assert before == hashlib.sha256(path.read_bytes()).hexdigest()
    doc = fitz.open(path)
    doc[0].insert_text((50, 50), "Outra versao")
    doc.saveIncr()
    doc.close()
    assert vr._pdf_hash(PAPER) != before


def test_disabled_search_never_reads_catalog(monkeypatch):
    lookup = Mock(side_effect=AssertionError("should not access catalog"))
    monkeypatch.setattr(vr, "list_eligible_visual_evidence", lookup)
    assert vr.retrieve_visual_evidence("rotas", "p", {"enabled": False}) == []
    lookup.assert_not_called()


def test_search_requires_substantive_overlap(monkeypatch):
    item = evidence() | {"search_text": "Otimização de rotas"}
    monkeypatch.setattr(vr, "list_eligible_visual_evidence", lambda *a, **k: [item])
    assert vr.retrieve_visual_evidence("Rotas?", "p", {"enabled": True}) == [item]
    assert vr.retrieve_visual_evidence("Tratamento de diabetes", "p", {"enabled": True}) == []


def test_text_order_unchanged_without_visual_and_unique_ids_with_visual():
    textual = [{"candidate_id": "c1", "rrf_score": .03}, {"candidate_id": "c2", "rrf_score": .02}]
    assert vr.combine_candidates(textual, []) is textual
    result = vr.combine_candidates(textual, [evidence()])
    assert [i["candidate_id"] for i in result] == ["c1", "c2", "c3"]
    assert result[1]["artifact_id"] == ARTIFACT
    assert textual[1]["candidate_id"] == "c2"


@pytest.mark.parametrize("setting,current", [
    ({"enabled": False, "revision": 1}, []),
    ({"enabled": True, "revision": 2}, [evidence()]),
    ({"enabled": True, "revision": 1}, []),
    ({"enabled": True, "revision": 1}, [evidence() | {"evidence_revision": "changed"}]),
])
def test_revocation_or_stale_evidence_fails_closed(monkeypatch, setting, current):
    monkeypatch.setattr(vr, "get_visual_rag_setting", lambda _: setting)
    monkeypatch.setattr(vr, "list_eligible_visual_evidence", lambda *a, **k: current)
    with pytest.raises(ValueError):
        vr.ensure_visual_evidence_current("project", [evidence()])


def test_text_only_validation_does_not_query_database(monkeypatch):
    monkeypatch.setattr(vr, "get_visual_rag_setting", Mock(side_effect=AssertionError))
    vr.ensure_visual_evidence_current("project", [{"paper_id": PAPER, "page_number": 2}])


def test_visual_citation_requires_exact_artifact_and_plain_text_cannot_replace_it():
    citation = formatar_citacao(PAPER, 2, ARTIFACT)
    answer, audit = validar_citacoes_rag(f"Interpretação {citation}", [evidence()])
    assert citation in answer and audit["valid_citations"] == [citation]
    _, audit = validar_citacoes_rag(f"Texto [{PAPER}, p. 2]", [evidence()])
    assert not audit["valid_citations"]
    assert audit["invalid_citations_removed"]
    _, audit = validar_citacoes_rag(f"Visual [{PAPER}, p. 2, visual {INTERPRETATION}]", [evidence()])
    assert not audit["valid_citations"]


def test_metrics_disambiguate_text_and_two_visuals_on_same_page():
    visual = evidence()
    text = {"paper_id": PAPER, "page_number": 2}
    judgments = [text, text | {"artifact_id": ARTIFACT}, text | {"artifact_id": INTERPRETATION}]
    metrics = evaluate_ranking([text, visual, deepcopy(visual)], judgments, (3,))
    assert metrics["judged_relevant"] == 3
    assert metrics["recall_at_3"] == pytest.approx(2 / 3, abs=1e-6)
    assert evaluate_ranking([text], [judgments[1]], (1,))["recall_at_1"] == 0


def test_reranker_trace_preserves_visual_identity_without_fake_chunk():
    trace = _candidato_auditavel(evidence(), incluir_texto=True)
    assert trace["chunk_id"] is None
    for key in ("artifact_id", "interpretation_id", "source_file_sha256", "evidence_revision"):
        assert trace[key] == evidence()[key]


def test_generation_revalidates_before_delivery(monkeypatch):
    monkeypatch.setattr(rag, "buscar_contexto_reranqueado", lambda *a, **k: ([evidence()], {"status": "success"}))
    guard = Mock(side_effect=[None, ValueError("PDF mudou")])
    monkeypatch.setattr(rag, "ensure_visual_evidence_current", guard)
    generator = Mock(return_value=SimpleNamespace(text="Resposta com dados"))
    monkeypatch.setattr(rag, "generate_content", generator)
    with pytest.raises(ValueError, match="PDF mudou"):
        rag.responder_com_rag("Rotas?", "project", True)
    assert guard.call_count == 2
    prompt = generator.call_args.kwargs["system_instruction"]
    assert formatar_citacao(PAPER, 2, ARTIFACT) in prompt
    assert "não texto literal" in prompt


def test_compare_uses_paired_full_rankings_and_separate_text_cohort():
    text = {"paper_id": PAPER, "page_number": 2}
    judgments = [text, text | {"artifact_id": ARTIFACT}]
    queries = [{"id": "q", "question": "Rotas?", "expected_refusal": False, "relevances": judgments}]
    mixed_ranking = [evidence(), text]
    mixed = [{"query_id": "q", "reranked_ranking": mixed_ranking,
              "reranked_metrics": evaluate_ranking(mixed_ranking, judgments), "execution_status": "success"}]
    baseline = {"q": {"response": {"reranking": {"reranked_ranking": [text], "final_ranking": []}}}}
    result = _compare_visual_runs(mixed, queries, baseline, (1, 3, 5, 10))
    assert result["text_only"]["recall_at_5"] == .5
    assert result["text_plus_visual"]["recall_at_5"] == 1
    assert result["cohorts"]["textual_regression"]["text_only"]["reciprocal_rank"] == 1
    assert result["cohorts"]["textual_regression"]["text_plus_visual"]["reciprocal_rank"] == .5


def test_benchmark_snapshot_detects_new_approval(monkeypatch):
    setting = {"enabled": True, "revision": 1}
    monkeypatch.setattr("backend.app.rag_benchmark.get_visual_rag_setting", lambda _: setting)
    monkeypatch.setattr("backend.app.rag_benchmark.list_eligible_visual_evidence", lambda _: [evidence()])
    with pytest.raises(ValueError, match="catálogo visual mudou"):
        _validate_visual_benchmark_snapshot("project", [], setting)
