"""Execução reproduzível do benchmark do RAG contra um Golden Set humano."""

import csv
import hashlib
import io
import json
import re
import time

from backend.app.ai_config import (
    get_embedding_config,
    get_generation_config,
    get_reranking_config,
    TASK_RAG,
)
from backend.app.database import (
    carregar_ultima_execucao_avaliacao,
    salvar_execucao_avaliacao,
)
from backend.app.golden_set import list_golden_queries
from backend.app.rag_citations import RESPOSTA_SEM_CONTEXTO
from backend.app.reranking import fundir_rankings
from backend.app.visual_rag import (
    evidence_metadata, get_visual_rag_setting, list_eligible_visual_evidence,
    ensure_visual_evidence_current,
)
from backend.app.retrieval_metrics import (
    DEFAULT_K_VALUES,
    aggregate_ranking_metrics,
    evaluate_ranking,
)


RUN_TYPE = "rag_retrieval_benchmark"
DEFAULT_RETRY_MAX_ATTEMPTS = 4
DEFAULT_RETRY_BASE_DELAY_SECONDS = 2.0
DEFAULT_RETRY_MAX_DELAY_SECONDS = 15.0
TRANSIENT_STATUS_CODES = {429, 503}
TRANSIENT_ERROR_MARKERS = (
    "UNAVAILABLE",
    "RESOURCE_EXHAUSTED",
    "HIGH DEMAND",
    "RATE LIMIT",
    "TOO MANY REQUESTS",
)
DEFAULT_CALIBRATION_WEIGHTS = tuple(round(index * 0.05, 2) for index in range(21))
MIN_CALIBRATION_QUERIES = 10


def _exception_chain(error):
    current = error
    visited = set()
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


def _error_status_code(error):
    for attribute in ("status_code", "code"):
        value = getattr(error, attribute, None)
        if callable(value):
            try:
                value = value()
            except Exception:
                value = None
        if hasattr(value, "value"):
            value = value.value
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


def is_transient_ai_error(error):
    """Identifica indisponibilidade temporária ou limite de uso do provedor."""
    for item in _exception_chain(error):
        if _error_status_code(item) in TRANSIENT_STATUS_CODES:
            return True
        message = str(item).upper()
        if re.search(r"\b(?:429|503)\b", message):
            return True
        if any(marker in message for marker in TRANSIENT_ERROR_MARKERS):
            return True
    return False


def _safe_error(error):
    message = " ".join(str(error).split()) or error.__class__.__name__
    message = re.sub(
        r"(?i)(\b(?:api[_-]?key|x-goog-api-key|authorization|key)\b\s*[:=]\s*)"
        r"[^\s,;&]+",
        r"\1[REDACTED]",
        message,
    )
    message = re.sub(
        r"(?i)\bBearer\s+[^\s,;]+",
        "Bearer [REDACTED]",
        message,
    )
    return f"{error.__class__.__name__}: {message}"[:500]


def _run_query_with_retry(
    rag_runner,
    question,
    project_id,
    *,
    max_attempts,
    base_delay_seconds,
    max_delay_seconds,
    sleep_func,
    retry_callback=None,
):
    attempts = max(1, int(max_attempts))
    base_delay = max(0.0, float(base_delay_seconds))
    max_delay = max(0.0, float(max_delay_seconds))
    retry_errors = []
    retry_delays = []

    for attempt in range(1, attempts + 1):
        try:
            response = rag_runner(question, project_id, return_details=True)
            return response, {
                "execution_status": "success_after_retry" if attempt > 1 else "success",
                "execution_attempts": attempt,
                "retry_count": attempt - 1,
                "retry_delays_seconds": retry_delays,
                "retry_errors": retry_errors,
                "execution_error": None,
            }
        except Exception as error:
            if not is_transient_ai_error(error):
                raise
            safe_error = _safe_error(error)
            retry_errors.append(safe_error)
            if attempt >= attempts:
                return None, {
                    "execution_status": "failed_transient",
                    "execution_attempts": attempt,
                    "retry_count": attempt - 1,
                    "retry_delays_seconds": retry_delays,
                    "retry_errors": retry_errors,
                    "execution_error": safe_error,
                }
            delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
            retry_delays.append(round(delay, 3))
            if retry_callback:
                retry_callback(attempt, attempts, delay, safe_error)
            sleep_func(delay)

    raise RuntimeError("Política de novas tentativas inválida.")


def _compact_ranking(ranking):
    return [
        {
            "rank": index,
            "chunk_id": str(item.get("chunk_id") or ""),
            **evidence_metadata(item),
            "paper_id": str(item.get("paper_id") or ""),
            "paper_title": item.get("paper_title"),
            "page_number": item.get("page_number"),
            "rrf_score": item.get("rrf_score"),
            "original_rank": item.get("original_rank"),
            "model_rank": item.get("model_rank"),
            "rerank_rank": item.get("rerank_rank"),
            "rerank_score": item.get("rerank_score"),
            "fusion_score": item.get("fusion_score"),
        }
        for index, item in enumerate(ranking or [], 1)
    ]


def _golden_hash(snapshot):
    canonical = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _compare_visual_runs(mixed_results, queries, baseline_results, k_values):
    """Compara texto e texto+visual na mesma pergunta, sem misturar denominadores."""
    by_id = {str(item["id"]): item for item in queries}
    baseline_metrics, mixed_metrics, rows = [], [], []
    cohorts = {"textual_regression": ([], []), "visual_retrieval": ([], [])}
    for mixed in mixed_results:
        query = by_id[str(mixed["query_id"])]
        if query["expected_refusal"] or mixed.get("execution_status", "").startswith("failed"):
            continue
        baseline = baseline_results.get(query["id"], {})
        response = baseline.get("response")
        if not response:
            continue
        trace = response.get("reranking") or {}
        ranking = trace.get("reranked_ranking") or trace.get("final_ranking") or []
        before = evaluate_ranking(ranking, query["relevances"], k_values)
        after = mixed.get("reranked_metrics")
        if not after:
            continue
        baseline_metrics.append(before)
        mixed_metrics.append(after)
        for name, visual in (("textual_regression", False), ("visual_retrieval", True)):
            judgments = [j for j in query["relevances"] if bool(j.get("artifact_id")) == visual]
            if judgments:
                cohorts[name][0].append(evaluate_ranking(ranking, judgments, k_values))
                cohorts[name][1].append(evaluate_ranking(mixed.get("reranked_ranking") or [], judgments, k_values))
        rows.append({"query_id": query["id"], "question": query["question"],
                     "text_only": before, "text_plus_visual": after,
                     "text_only_ranking": _compact_ranking(ranking),
                     "text_plus_visual_ranking": mixed.get("reranked_ranking") or []})
    before = aggregate_ranking_metrics(baseline_metrics)
    after = aggregate_ranking_metrics(mixed_metrics)
    keys = sorted(set(before) | set(after))
    return {"status": "comparable" if rows else "unavailable", "query_count": len(rows),
            "excluded_answerable_query_count": sum(not q["expected_refusal"] for q in queries) - len(rows),
            "text_only": before, "text_plus_visual": after,
            "delta": {key: round(after.get(key, 0) - before.get(key, 0), 6) for key in keys},
            "results": rows,
            "cohorts": {name: {"query_count": len(pair[0]),
                                "text_only": aggregate_ranking_metrics(pair[0]),
                                "text_plus_visual": aggregate_ranking_metrics(pair[1])}
                        for name, pair in cohorts.items()}}


def _validate_visual_benchmark_snapshot(project_id, snapshot, setting):
    if get_visual_rag_setting(project_id) != setting:
        raise ValueError("A configuração visual mudou durante o benchmark. Execute novamente.")
    current = list_eligible_visual_evidence(project_id)
    def signature(items):
        return sorted((i["interpretation_id"], i["evidence_revision"], i["source_file_sha256"]) for i in items)
    if signature(current) != signature(snapshot):
        raise ValueError("O catálogo visual mudou durante o benchmark. Execute novamente com o catálogo estável.")


def validate_golden_set(snapshot):
    queries = snapshot.get("queries") or []
    errors = []
    if not queries:
        errors.append("Cadastre ao menos uma pergunta no Golden Set.")
    for item in queries:
        if not item.get("expected_refusal") and not item.get("relevances"):
            errors.append(
                f"A pergunta '{item.get('question')}' não possui fonte relevante."
            )
        if item.get("expected_refusal") and item.get("relevances"):
            errors.append(
                f"A pergunta de recusa '{item.get('question')}' possui fontes incompatíveis."
            )
    return errors


def _mean(values):
    values = [float(value) for value in values if value is not None]
    return round(sum(values) / len(values), 6) if values else None


def _model_ranking_from_trace(trace, reranked):
    model_ranking = trace.get("model_ranking") or []
    if model_ranking:
        return model_ranking
    if trace.get("status") != "success":
        return []
    # Compatibilidade com traces produzidos antes da fusão configurável.
    reconstructed = []
    for index, item in enumerate(reranked or [], 1):
        candidate = dict(item)
        candidate["model_rank"] = int(
            candidate.get("model_rank") or candidate.get("rerank_rank") or index
        )
        reconstructed.append(candidate)
    reconstructed.sort(key=lambda item: item["model_rank"])
    return reconstructed


def calibrate_reranking_weights(
    results,
    golden_queries,
    *,
    k_values=DEFAULT_K_VALUES,
    weights=DEFAULT_CALIBRATION_WEIGHTS,
    configured_weight=0.0,
):
    """Avalia pesos sem novas chamadas de IA usando as duas ordens já registradas."""
    golden_by_id = {str(item["id"]): item for item in golden_queries or []}
    eligible = []
    answerable_total = 0
    for result in results or []:
        if result.get("expected_refusal") or result.get("rrf_metrics") is None:
            continue
        answerable_total += 1
        if not result.get("model_ranking"):
            continue
        golden = golden_by_id.get(str(result.get("query_id")))
        if golden and golden.get("relevances"):
            eligible.append((result, golden))

    candidates = []
    if eligible:
        for weight in weights:
            weight = round(min(1.0, max(0.0, float(weight))), 2)
            metrics = []
            for result, golden in eligible:
                fused = fundir_rankings(result["model_ranking"], weight)
                metrics.append(evaluate_ranking(fused, golden["relevances"], k_values))
            aggregate = aggregate_ranking_metrics(metrics)
            candidates.append({"rrf_weight": weight, **aggregate})

    recommendation = None
    if candidates and eligible:
        recommendation = max(
            candidates,
            key=lambda item: (
                item.get("recall_at_5") or 0.0,
                item.get("ndcg_at_5") or 0.0,
                item.get("reciprocal_rank") or 0.0,
                -item["rrf_weight"],
            ),
        )["rrf_weight"]

    sample_size = len(eligible)
    return {
        "status": (
            "unavailable"
            if not sample_size
            else "sufficient"
            if sample_size >= MIN_CALIBRATION_QUERIES
            else "exploratory"
        ),
        "answerable_query_count": sample_size,
        "total_answerable_query_count": answerable_total,
        "excluded_answerable_query_count": max(0, answerable_total - sample_size),
        "coverage_rate": (
            round(sample_size / answerable_total, 6) if answerable_total else None
        ),
        "coverage_status": (
            "complete" if sample_size == answerable_total else "partial"
        ),
        "minimum_recommended_queries": MIN_CALIBRATION_QUERIES,
        "configured_rrf_weight": round(float(configured_weight or 0.0), 2),
        "recommended_rrf_weight": recommendation,
        "selection_objective": ["recall_at_5", "ndcg_at_5", "reciprocal_rank"],
        "candidate_weights": candidates,
    }


def _interpret_summary(summary):
    statements = []
    warnings = []
    comparison = summary.get("comparison_cohort") or {}
    comparison_count = int(comparison.get("query_count") or 0)
    if comparison_count:
        rrf = comparison.get("rrf") or {}
        reranked = comparison.get("reranked") or {}
    elif "comparison_cohort" in summary:
        rrf = {}
        reranked = {}
        warnings.append(
            "Nenhuma pergunta possuía os três rankings; a comparação entre pipelines "
            "foi omitida para evitar denominadores incompatíveis."
        )
    else:
        rrf = summary.get("rrf") or {}
        reranked = summary.get("reranked") or {}
    for key, label in (
        ("recall_at_5", "Recall@5"),
        ("ndcg_at_5", "nDCG@5"),
        ("reciprocal_rank", "MRR"),
    ):
        before = rrf.get(key)
        after = reranked.get(key)
        if before is None or after is None:
            continue
        delta = round(after - before, 4)
        direction = "melhorou" if delta > 0 else "piorou" if delta < 0 else "permaneceu igual"
        statements.append(
            f"{label} {direction} após a fusão configurada na amostra comparável "
            f"({before:.3f} → {after:.3f})."
        )
    excluded = int(comparison.get("excluded_answerable_query_count") or 0)
    if excluded:
        warnings.append(
            f"A comparação entre pipelines excluiu {excluded} pergunta(s) sem ranking "
            "da IA, garantindo o mesmo denominador para RRF, IA e fusão."
        )
    calibration = summary.get("reranking_calibration") or {}
    recommended_weight = calibration.get("recommended_rrf_weight")
    if recommended_weight is not None:
        statements.append(
            f"O peso RRF explorado com melhor resultado foi {recommended_weight:.2f}."
        )
    if calibration.get("status") == "exploratory":
        warnings.append(
            "A recomendação de peso ainda é exploratória: amplie o Golden Set antes "
            "de adotá-la como configuração estável."
        )
    if calibration.get("coverage_status") == "partial":
        warnings.append(
            "A recomendação de peso foi calculada somente na amostra comparável; "
            "não a adote como estável enquanto houver fallbacks do reranking."
        )
    refusal = summary.get("correct_refusal_rate")
    if refusal is not None:
        statements.append(f"A taxa correta de recusa foi {refusal * 100:.1f}%.")
    false_refusal = summary.get("false_refusal_rate")
    if false_refusal:
        warnings.append(
            f"O sistema recusou incorretamente {false_refusal * 100:.1f}% das perguntas respondíveis."
        )
    if summary.get("reranking_fallback_count"):
        warnings.append(
            f"{summary['reranking_fallback_count']} pergunta(s) usaram fallback RRF; "
            "o motivo foi preservado nos resultados por pergunta."
        )
    reranking_recovered = int(summary.get("reranking_recovered_after_retry_count") or 0)
    if reranking_recovered:
        statements.append(
            f"{reranking_recovered} reranking(s) foram recuperados por nova tentativa controlada."
        )
    refusal_recovered = int(summary.get("refusal_recovered_count") or 0)
    if refusal_recovered:
        statements.append(
            f"{refusal_recovered} recusa(s) iniciais foram corrigidas após reavaliação das evidências."
        )
    retried = int(summary.get("retried_query_count") or 0)
    if retried:
        statements.append(
            f"{retried} pergunta(s) exigiram novas tentativas por indisponibilidade temporária."
        )
    failed = int(summary.get("failed_query_count") or 0)
    if failed:
        warnings.append(
            f"{failed} pergunta(s) não foram concluídas após esgotar as novas tentativas; "
            "as demais foram preservadas."
        )
    citation = summary.get("citation_compliance_rate")
    if citation is not None:
        statements.append(
            f"{citation * 100:.1f}% das respostas cumpriram integralmente o formato de citação rastreável."
        )
    return {"statements": statements, "warnings": warnings}


def run_rag_benchmark(
    project_id,
    *,
    rag_runner=None,
    progress_callback=None,
    k_values=DEFAULT_K_VALUES,
    retry_max_attempts=DEFAULT_RETRY_MAX_ATTEMPTS,
    retry_base_delay_seconds=DEFAULT_RETRY_BASE_DELAY_SECONDS,
    retry_max_delay_seconds=DEFAULT_RETRY_MAX_DELAY_SECONDS,
    sleep_func=time.sleep,
    compare_visual=False,
):
    """Executa RAG uma vez por pergunta e avalia RRF, reranking, recusa e citações."""
    project_id = str(project_id)
    golden = list_golden_queries(project_id)
    errors = validate_golden_set(golden)
    if errors:
        raise ValueError(" ".join(errors))
    visual_snapshot = []
    visual_judgments = [item for query in golden["queries"] for item in query["relevances"] if item.get("artifact_id")]
    if compare_visual or visual_judgments:
        visual_snapshot = list_eligible_visual_evidence(project_id)
        eligible_ids = {item["artifact_id"] for item in visual_snapshot}
        if any(item["artifact_id"] not in eligible_ids for item in visual_judgments):
            raise ValueError("O Golden Set contém fonte visual desatualizada ou indisponível. Revise os julgamentos antes de executar.")
    visual_setting = None
    if compare_visual:
        visual_setting = get_visual_rag_setting(project_id)
        if not visual_setting["enabled"]:
            raise ValueError("Ative o uso visual no Assistente deste projeto antes da comparação.")
        for item in visual_snapshot:
            item["setting_revision"] = visual_setting["revision"]
    if rag_runner is None:
        from backend.agentes.agente_rag import responder_com_rag

        rag_runner = responder_com_rag

    results = []
    rrf_metrics = []
    model_reranked_metrics = []
    reranked_metrics = []
    comparable_rrf_metrics = []
    comparable_model_metrics = []
    comparable_reranked_metrics = []
    answerable_refusals = []
    expected_refusals = []
    citation_valid = 0
    citation_invalid = 0
    citation_compliance = []
    fallback_count = 0
    failed_count = 0
    successful_count = 0
    retried_count = 0
    total_retry_count = 0
    reranking_retried_count = 0
    reranking_total_retry_count = 0
    reranking_recovered_count = 0
    refusal_reconsidered_count = 0
    refusal_recovered_count = 0
    queries = golden["queries"]
    baseline_results = {}

    for index, query in enumerate(queries, 1):
        if progress_callback:
            progress_callback(index - 1, len(queries), query["question"])

        def report_retry(attempt, max_attempts, delay, _error):
            if progress_callback:
                progress_callback(
                    index - 1,
                    len(queries),
                    f"{query['question']} · nova tentativa {attempt + 1}/{max_attempts} "
                    f"em {delay:g}s",
                )

        if compare_visual:
            _validate_visual_benchmark_snapshot(project_id, visual_snapshot, visual_setting)
            baseline, baseline_execution = _run_query_with_retry(
                lambda *args, **kwargs: rag_runner(*args, **kwargs, visual_mode=False),
                query["question"], project_id, max_attempts=retry_max_attempts,
                base_delay_seconds=retry_base_delay_seconds, max_delay_seconds=retry_max_delay_seconds,
                sleep_func=sleep_func, retry_callback=report_retry,
            )
            baseline_results[query["id"]] = {"response": baseline, "execution": baseline_execution}
        response, execution = _run_query_with_retry(
            rag_runner,
            query["question"],
            project_id,
            max_attempts=retry_max_attempts,
            base_delay_seconds=retry_base_delay_seconds,
            max_delay_seconds=retry_max_delay_seconds,
            sleep_func=sleep_func,
            retry_callback=report_retry,
        )
        total_retry_count += execution["retry_count"]
        if execution["retry_count"]:
            retried_count += 1
        if response is None:
            failed_count += 1
            results.append(
                {
                    "query_id": query["id"],
                    "question": query["question"],
                    "expected_refusal": bool(query["expected_refusal"]),
                    "response_refused": None,
                    "answer": None,
                    "reranking_status": "not_completed",
                    "reranking_error": None,
                    "reranking_errors": [],
                    "reranking_attempts": 0,
                    "reranking_retry_count": 0,
                    "reranking_recovered_after_retry": False,
                    "comparison_eligible": False,
                    "generation": {},
                    "rrf_ranking": [],
                    "model_ranking": [],
                    "reranked_ranking": [],
                    "rrf_metrics": None,
                    "model_reranked_metrics": None,
                    "reranked_metrics": None,
                    "citation_metrics": None,
                    **execution,
                }
            )
            continue

        successful_count += 1
        trace = response.get("reranking") or {}
        generation_trace = response.get("generation") or {}
        initial = trace.get("initial_ranking") or []
        reranked = trace.get("reranked_ranking") or trace.get("final_ranking") or []
        model_ranking = _model_ranking_from_trace(trace, reranked)
        refused = RESPOSTA_SEM_CONTEXTO.lower() in str(response.get("answer") or "").lower()
        if trace.get("status") == "fallback_rrf":
            fallback_count += 1
        reranking_retry_count = int(trace.get("retry_count") or 0)
        reranking_total_retry_count += reranking_retry_count
        if reranking_retry_count:
            reranking_retried_count += 1
        if trace.get("recovered_after_retry"):
            reranking_recovered_count += 1
        if generation_trace.get("refusal_reconsidered"):
            refusal_reconsidered_count += 1
        if generation_trace.get("refusal_recovered"):
            refusal_recovered_count += 1

        item = {
            "query_id": query["id"],
            "question": query["question"],
            "expected_refusal": bool(query["expected_refusal"]),
            "response_refused": refused,
            "answer": response.get("answer"),
            "reranking_status": trace.get("status"),
            "reranking_error": trace.get("error"),
            "reranking_errors": trace.get("errors") or [],
            "reranking_attempts": int(trace.get("attempts") or 0),
            "reranking_retry_count": reranking_retry_count,
            "reranking_recovered_after_retry": bool(
                trace.get("recovered_after_retry")
            ),
            "comparison_eligible": False,
            "generation": generation_trace,
            "visual_retrieval": trace.get("visual_retrieval") or {"enabled": False},
            "rrf_ranking": _compact_ranking(initial),
            "model_ranking": _compact_ranking(model_ranking),
            "reranked_ranking": _compact_ranking(reranked),
            "rrf_metrics": None,
            "model_reranked_metrics": None,
            "reranked_metrics": None,
            **execution,
        }
        if query["expected_refusal"]:
            expected_refusals.append(1.0 if refused else 0.0)
        else:
            item["rrf_metrics"] = evaluate_ranking(initial, query["relevances"], k_values)
            if model_ranking:
                item["model_reranked_metrics"] = evaluate_ranking(
                    model_ranking, query["relevances"], k_values
                )
            item["reranked_metrics"] = evaluate_ranking(
                reranked, query["relevances"], k_values
            )
            rrf_metrics.append(item["rrf_metrics"])
            if item["model_reranked_metrics"] is not None:
                model_reranked_metrics.append(item["model_reranked_metrics"])
                comparable_rrf_metrics.append(item["rrf_metrics"])
                comparable_model_metrics.append(item["model_reranked_metrics"])
                comparable_reranked_metrics.append(item["reranked_metrics"])
                item["comparison_eligible"] = True
            reranked_metrics.append(item["reranked_metrics"])
            answerable_refusals.append(1.0 if refused else 0.0)

            citation = response.get("citation_validation") or {}
            valid_count = len(citation.get("valid_citations") or [])
            invalid_count = len(citation.get("invalid_citations_removed") or [])
            appended_count = len(citation.get("source_citations_appended") or [])
            citation_valid += valid_count
            citation_invalid += invalid_count
            compliant = (
                not refused
                and valid_count > 0
                and invalid_count == 0
                and appended_count == 0
            )
            citation_compliance.append(1.0 if compliant else 0.0)
            item["citation_metrics"] = {
                "valid_citations": valid_count,
                "invalid_citations_removed": invalid_count,
                "sources_appended_due_to_missing_citations": appended_count,
                "format_compliant": compliant,
            }
        results.append(item)

    visual_comparison = None
    if compare_visual:
        _validate_visual_benchmark_snapshot(project_id, visual_snapshot, visual_setting)
        visual_comparison = _compare_visual_runs(results, queries, baseline_results, k_values)

    citation_denominator = citation_valid + citation_invalid
    reranking_config = get_reranking_config()
    calibration = calibrate_reranking_weights(
        results,
        queries,
        k_values=k_values,
        configured_weight=getattr(reranking_config, "rrf_weight", 0.0),
    )
    evaluated_answerable_count = len(rrf_metrics)
    comparable_count = len(comparable_rrf_metrics)
    comparison_cohort = {
        "query_count": comparable_count,
        "total_answerable_query_count": evaluated_answerable_count,
        "excluded_answerable_query_count": max(
            0, evaluated_answerable_count - comparable_count
        ),
        "coverage_rate": (
            round(comparable_count / evaluated_answerable_count, 6)
            if evaluated_answerable_count
            else None
        ),
        "rrf": aggregate_ranking_metrics(comparable_rrf_metrics),
        "model_reranked": aggregate_ranking_metrics(comparable_model_metrics),
        "reranked": aggregate_ranking_metrics(comparable_reranked_metrics),
    }
    summary = {
        "query_count": len(queries),
        "answerable_query_count": sum(
            1 for query in queries if not query["expected_refusal"]
        ),
        "refusal_query_count": sum(
            1 for query in queries if query["expected_refusal"]
        ),
        "evaluated_answerable_query_count": len(rrf_metrics),
        "evaluated_refusal_query_count": len(expected_refusals),
        "successful_query_count": successful_count,
        "failed_query_count": failed_count,
        "retried_query_count": retried_count,
        "total_retry_count": total_retry_count,
        "rrf": aggregate_ranking_metrics(rrf_metrics),
        "model_reranked": aggregate_ranking_metrics(model_reranked_metrics),
        "reranked": aggregate_ranking_metrics(reranked_metrics),
        "comparison_cohort": comparison_cohort,
        "reranking_calibration": calibration,
        "correct_refusal_rate": _mean(expected_refusals),
        "false_refusal_rate": _mean(answerable_refusals),
        "citation_validity": (
            round(citation_valid / citation_denominator, 6)
            if citation_denominator
            else None
        ),
        "citation_compliance_rate": _mean(citation_compliance),
        "reranking_fallback_count": fallback_count,
        "reranking_retried_query_count": reranking_retried_count,
        "reranking_total_retry_count": reranking_total_retry_count,
        "reranking_recovered_after_retry_count": reranking_recovered_count,
        "refusal_reconsidered_count": refusal_reconsidered_count,
        "refusal_recovered_count": refusal_recovered_count,
        "visual_comparison": visual_comparison,
    }
    summary["interpretation"] = _interpret_summary(summary)
    golden_snapshot = json.loads(json.dumps(golden, ensure_ascii=False, default=str))
    params = {
        "golden_set_version": int(golden["version"]),
        "golden_set_hash": _golden_hash(golden_snapshot),
        "golden_set_snapshot": golden_snapshot,
        "k_values": [int(k) for k in k_values],
        "retrieval_pipeline": "hybrid_vector_fts_rrf_plus_optional_reranking",
        "compare_visual": bool(compare_visual),
        "visual_setting": visual_setting,
        "visual_evidence_snapshot": [evidence_metadata(item) | {"paper_id": item["paper_id"], "page_number": item["page_number"]} for item in visual_snapshot],
        "embedding": get_embedding_config().metadata(),
        "rag_model": get_generation_config(TASK_RAG).metadata(),
        "reranking": reranking_config.metadata(),
        "retry_policy": {
            "transient_status_codes": sorted(TRANSIENT_STATUS_CODES),
            "max_attempts_per_query": max(1, int(retry_max_attempts)),
            "base_delay_seconds": max(0.0, float(retry_base_delay_seconds)),
            "max_delay_seconds": max(0.0, float(retry_max_delay_seconds)),
            "backoff": "exponential",
        },
    }
    metrics = {"summary": summary, "results": results}
    if compare_visual:
        metrics["text_only_runs"] = baseline_results
    run_id = salvar_execucao_avaliacao(project_id, RUN_TYPE, metrics, params)
    if progress_callback:
        progress_callback(len(queries), len(queries), "Benchmark concluído")
    return {
        "id": str(run_id),
        "project_id": project_id,
        "metrics": metrics,
        "params": params,
    }


def get_latest_rag_benchmark(project_id):
    return carregar_ultima_execucao_avaliacao(project_id, RUN_TYPE)


def benchmark_to_json(run):
    return json.dumps(run, ensure_ascii=False, indent=2, default=str)


def benchmark_to_csv(run):
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter=";")
    writer.writerow(
        [
            "pergunta",
            "esperava_recusa",
            "recusou",
            "pipeline",
            "precision_at_5",
            "recall_at_5",
            "hit_rate_at_5",
            "mrr",
            "ndcg_at_5",
            "status_reranking",
            "amostra_comparavel",
            "tentativas_reranking",
            "novas_tentativas_reranking",
            "erro_reranking",
            "peso_rrf_configurado",
            "recusa_reavaliada",
            "recusa_recuperada",
            "status_execucao",
            "tentativas",
            "novas_tentativas",
            "erro_execucao",
        ]
    )
    for item in (run.get("metrics") or {}).get("results", []):
        configured_weight = (
            ((run.get("params") or {}).get("reranking") or {}).get("rrf_weight")
        )
        for pipeline, key in (
            ("RRF", "rrf_metrics"),
            ("Reranking IA", "model_reranked_metrics"),
            ("Fusão configurada", "reranked_metrics"),
        ):
            metrics = item.get(key) or {}
            writer.writerow(
                [
                    item.get("question"),
                    item.get("expected_refusal"),
                    item.get("response_refused"),
                    pipeline,
                    metrics.get("precision_at_5"),
                    metrics.get("recall_at_5"),
                    metrics.get("hit_rate_at_5"),
                    metrics.get("reciprocal_rank"),
                    metrics.get("ndcg_at_5"),
                    item.get("reranking_status"),
                    item.get("comparison_eligible"),
                    item.get("reranking_attempts"),
                    item.get("reranking_retry_count"),
                    item.get("reranking_error"),
                    configured_weight,
                    (item.get("generation") or {}).get("refusal_reconsidered"),
                    (item.get("generation") or {}).get("refusal_recovered"),
                    item.get("execution_status"),
                    item.get("execution_attempts"),
                    item.get("retry_count"),
                    item.get("execution_error"),
                ]
            )
    return "\ufeff" + output.getvalue()
