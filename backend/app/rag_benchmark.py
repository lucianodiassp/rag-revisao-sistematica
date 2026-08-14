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
            "paper_id": str(item.get("paper_id") or ""),
            "page_number": item.get("page_number"),
            "rrf_score": item.get("rrf_score"),
            "original_rank": item.get("original_rank"),
            "rerank_rank": item.get("rerank_rank"),
            "rerank_score": item.get("rerank_score"),
        }
        for index, item in enumerate(ranking or [], 1)
    ]


def _golden_hash(snapshot):
    canonical = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


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


def _interpret_summary(summary):
    statements = []
    warnings = []
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
            f"{label} {direction} após o reranking ({before:.3f} → {after:.3f})."
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
            "Parte das perguntas usou fallback RRF porque o reranking não foi concluído."
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
):
    """Executa RAG uma vez por pergunta e avalia RRF, reranking, recusa e citações."""
    project_id = str(project_id)
    golden = list_golden_queries(project_id)
    errors = validate_golden_set(golden)
    if errors:
        raise ValueError(" ".join(errors))
    if rag_runner is None:
        from backend.agentes.agente_rag import responder_com_rag

        rag_runner = responder_com_rag

    results = []
    rrf_metrics = []
    reranked_metrics = []
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
    queries = golden["queries"]

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
                    "rrf_ranking": [],
                    "reranked_ranking": [],
                    "rrf_metrics": None,
                    "reranked_metrics": None,
                    "citation_metrics": None,
                    **execution,
                }
            )
            continue

        successful_count += 1
        trace = response.get("reranking") or {}
        initial = trace.get("initial_ranking") or []
        reranked = trace.get("reranked_ranking") or trace.get("final_ranking") or []
        refused = RESPOSTA_SEM_CONTEXTO.lower() in str(response.get("answer") or "").lower()
        if trace.get("status") == "fallback_rrf":
            fallback_count += 1

        item = {
            "query_id": query["id"],
            "question": query["question"],
            "expected_refusal": bool(query["expected_refusal"]),
            "response_refused": refused,
            "answer": response.get("answer"),
            "reranking_status": trace.get("status"),
            "rrf_ranking": _compact_ranking(initial),
            "reranked_ranking": _compact_ranking(reranked),
            "rrf_metrics": None,
            "reranked_metrics": None,
            **execution,
        }
        if query["expected_refusal"]:
            expected_refusals.append(1.0 if refused else 0.0)
        else:
            item["rrf_metrics"] = evaluate_ranking(initial, query["relevances"], k_values)
            item["reranked_metrics"] = evaluate_ranking(
                reranked, query["relevances"], k_values
            )
            rrf_metrics.append(item["rrf_metrics"])
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

    citation_denominator = citation_valid + citation_invalid
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
        "reranked": aggregate_ranking_metrics(reranked_metrics),
        "correct_refusal_rate": _mean(expected_refusals),
        "false_refusal_rate": _mean(answerable_refusals),
        "citation_validity": (
            round(citation_valid / citation_denominator, 6)
            if citation_denominator
            else None
        ),
        "citation_compliance_rate": _mean(citation_compliance),
        "reranking_fallback_count": fallback_count,
    }
    summary["interpretation"] = _interpret_summary(summary)
    golden_snapshot = json.loads(json.dumps(golden, ensure_ascii=False, default=str))
    params = {
        "golden_set_version": int(golden["version"]),
        "golden_set_hash": _golden_hash(golden_snapshot),
        "golden_set_snapshot": golden_snapshot,
        "k_values": [int(k) for k in k_values],
        "retrieval_pipeline": "hybrid_vector_fts_rrf_plus_optional_reranking",
        "embedding": get_embedding_config().metadata(),
        "rag_model": get_generation_config(TASK_RAG).metadata(),
        "reranking": get_reranking_config().metadata(),
        "retry_policy": {
            "transient_status_codes": sorted(TRANSIENT_STATUS_CODES),
            "max_attempts_per_query": max(1, int(retry_max_attempts)),
            "base_delay_seconds": max(0.0, float(retry_base_delay_seconds)),
            "max_delay_seconds": max(0.0, float(retry_max_delay_seconds)),
            "backoff": "exponential",
        },
    }
    metrics = {"summary": summary, "results": results}
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
            "status_execucao",
            "tentativas",
            "novas_tentativas",
            "erro_execucao",
        ]
    )
    for item in (run.get("metrics") or {}).get("results", []):
        for pipeline, key in (("RRF", "rrf_metrics"), ("Reranking", "reranked_metrics")):
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
                    item.get("execution_status"),
                    item.get("execution_attempts"),
                    item.get("retry_count"),
                    item.get("execution_error"),
                ]
            )
    return "\ufeff" + output.getvalue()
