"""Métricas determinísticas de recuperação contra julgamentos humanos."""

import math


DEFAULT_K_VALUES = (1, 3, 5, 10)


def _judgment_key(judgment):
    page = judgment.get("page_number")
    return (str(judgment["paper_id"]), int(page) if page is not None else None,
            str(judgment.get("artifact_id") or ""))


def _match_ranking(ranking, judgments):
    remaining = {_judgment_key(item): int(item.get("relevance_grade", 1)) for item in judgments}
    matched = []
    for result in ranking:
        paper_id = str(result.get("paper_id"))
        page = result.get("page_number")
        page = int(page) if page is not None else None
        candidates = [
            (key, grade)
            for key, grade in remaining.items()
            if key[0] == paper_id and (key[1] is None or key[1] == page)
            and key[2] == (str(result.get("artifact_id") or "")
                           if result.get("source_type") == "visual_interpretation" else "")
        ]
        if not candidates:
            matched.append({"relevant": False, "grade": 0, "judgment_key": None})
            continue
        key, grade = sorted(candidates, key=lambda item: (-item[1], item[0][1] or 0))[0]
        remaining.pop(key)
        matched.append({"relevant": True, "grade": grade, "judgment_key": key})
    return matched


def evaluate_ranking(ranking, judgments, k_values=DEFAULT_K_VALUES):
    """Calcula Precision, Recall, Hit Rate, MRR e nDCG em diferentes cortes."""
    ranking = list(ranking or [])
    judgments = list(judgments or [])
    if not judgments:
        raise ValueError("Ao menos um julgamento relevante é necessário.")
    matched = _match_ranking(ranking, judgments)
    total_relevant = len({_judgment_key(item) for item in judgments})
    ideal_grades = sorted(
        [int(item.get("relevance_grade", 1)) for item in judgments], reverse=True
    )
    metrics = {
        "judged_relevant": total_relevant,
        "retrieved_count": len(ranking),
        "reciprocal_rank": 0.0,
    }
    for rank, item in enumerate(matched, 1):
        if item["relevant"]:
            metrics["reciprocal_rank"] = round(1.0 / rank, 6)
            break

    for raw_k in k_values:
        k = int(raw_k)
        if k <= 0:
            raise ValueError("Os valores de k devem ser maiores que zero.")
        top = matched[:k]
        relevant_count = sum(1 for item in top if item["relevant"])
        dcg = sum(
            (2 ** item["grade"] - 1) / math.log2(rank + 1)
            for rank, item in enumerate(top, 1)
            if item["grade"] > 0
        )
        idcg = sum(
            (2 ** grade - 1) / math.log2(rank + 1)
            for rank, grade in enumerate(ideal_grades[:k], 1)
        )
        metrics.update(
            {
                f"precision_at_{k}": round(relevant_count / k, 6),
                f"recall_at_{k}": round(relevant_count / total_relevant, 6),
                f"hit_rate_at_{k}": 1.0 if relevant_count else 0.0,
                f"ndcg_at_{k}": round(dcg / idcg, 6) if idcg else 0.0,
            }
        )
    return metrics


def aggregate_ranking_metrics(per_query_metrics):
    items = [item for item in per_query_metrics if item]
    if not items:
        return {}
    numeric_keys = sorted(
        {
            key
            for item in items
            for key, value in item.items()
            if isinstance(value, (int, float))
            and key not in {"judged_relevant", "retrieved_count"}
        }
    )
    return {
        key: round(sum(float(item.get(key, 0.0)) for item in items) / len(items), 6)
        for key in numeric_keys
    }
