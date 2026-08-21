"""Calibração rastreável da estratégia de busca com artigos sentinela."""

from __future__ import annotations

import csv
from difflib import SequenceMatcher
import io
import json
from datetime import date, datetime

from psycopg2 import IntegrityError
from psycopg2.extras import Json

from backend.app.bibliographic_config import (
    SOURCE_LABELS,
    SOURCE_OPENALEX,
    SOURCE_PUBMED,
    SOURCE_SEMANTIC_SCHOLAR,
    get_bibliographic_settings,
)
from backend.app.project_utils import normalizar_doi, normalizar_titulo
from backend.app.protocol_service import normalize_protocol, protocol_fingerprint


TITLE_SIMILARITY_THRESHOLD = 0.93
SOURCE_ORDER = (SOURCE_OPENALEX, SOURCE_PUBMED, SOURCE_SEMANTIC_SCHOLAR)
PRESS_RESPONSES = ("yes", "no", "uncertain", "not_applicable")
PRESS_DOMAINS = (
    {
        "code": "research_question_translation",
        "label": "Tradução da pergunta de pesquisa",
        "question": "A estratégia representa adequadamente a pergunta e os componentes PICO/PICOS aplicáveis?",
    },
    {
        "code": "boolean_proximity",
        "label": "Operadores booleanos e de proximidade",
        "question": "AND, OR, NOT, parênteses e operadores de proximidade foram usados de forma coerente?",
    },
    {
        "code": "subject_headings",
        "label": "Vocabulário controlado",
        "question": "Descritores ou cabeçalhos de assunto relevantes foram considerados quando a fonte os oferece?",
    },
    {
        "code": "text_words",
        "label": "Termos em texto livre",
        "question": "Sinônimos, siglas, variantes de grafia e termos em texto livre relevantes estão contemplados?",
    },
    {
        "code": "spelling_syntax",
        "label": "Grafia e sintaxe",
        "question": "A estratégia está livre de erros de grafia, sintaxe, aspas e agrupamento?",
    },
    {
        "code": "limits_filters",
        "label": "Limites e filtros",
        "question": "Limites de data, idioma, publicação e desenho são justificados e não restringem indevidamente a recuperação?",
    },
)


def _connection_factory(connection_factory=None):
    if connection_factory is not None:
        return connection_factory
    from backend.app.database import get_connection

    return get_connection


def _row(cursor, value):
    if value is None:
        return None
    return dict(zip((column[0] for column in cursor.description), value))


def _rows(cursor):
    columns = [column[0] for column in cursor.description]
    return [dict(zip(columns, value)) for value in cursor.fetchall()]


def _clean_title(value):
    return " ".join(str(value or "").split()).strip()


def _title_similarity(first, second):
    first = normalizar_titulo(first)
    second = normalizar_titulo(second)
    if not first or not second:
        return 0.0
    sequence = SequenceMatcher(None, first, second).ratio()
    first_tokens, second_tokens = set(first.split()), set(second.split())
    token_score = (
        len(first_tokens & second_tokens) / len(first_tokens | second_tokens)
        if first_tokens and second_tokens
        else 0.0
    )
    return round((0.70 * sequence) + (0.30 * token_score), 4)


def list_sentinels(project_id, active_only=False, connection_factory=None):
    factory = _connection_factory(connection_factory)
    with factory() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT id, project_id, title, canonical_doi, notes, is_active,
                   created_at, updated_at
            FROM search_calibration_sentinels
            WHERE project_id = %s AND (%s = FALSE OR is_active = TRUE)
            ORDER BY is_active DESC, title, id
            """,
            (str(project_id), bool(active_only)),
        )
        return _rows(cursor)


def save_sentinel(project_id, title, doi=None, notes=None, sentinel_id=None, connection_factory=None):
    title = _clean_title(title)
    doi = normalizar_doi(doi)
    notes = str(notes or "").strip() or None
    if len(title) < 5:
        raise ValueError("Informe um título com pelo menos 5 caracteres.")
    factory = _connection_factory(connection_factory)
    try:
        with factory() as connection, connection.cursor() as cursor:
            if sentinel_id:
                cursor.execute(
                    """
                    UPDATE search_calibration_sentinels
                    SET title = %s, canonical_doi = %s, notes = %s,
                        is_active = TRUE, updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s AND project_id = %s
                    RETURNING id
                    """,
                    (title, doi, notes, str(sentinel_id), str(project_id)),
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO search_calibration_sentinels
                        (project_id, title, canonical_doi, notes)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id
                    """,
                    (str(project_id), title, doi, notes),
                )
            row = cursor.fetchone()
            if not row:
                raise ValueError("Artigo sentinela não encontrado neste projeto.")
            return str(row[0])
    except IntegrityError as error:
        raise ValueError("Já existe um artigo sentinela com este DOI no projeto.") from error


def set_sentinel_active(project_id, sentinel_id, is_active, connection_factory=None):
    factory = _connection_factory(connection_factory)
    with factory() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE search_calibration_sentinels
            SET is_active = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s AND project_id = %s
            RETURNING id
            """,
            (bool(is_active), str(sentinel_id), str(project_id)),
        )
        if not cursor.fetchone():
            raise ValueError("Artigo sentinela não encontrado neste projeto.")


def _default_collectors():
    from backend.coleta.coleta_openalex import recolher_artigos_openalex
    from backend.coleta.coleta_pubmed import recolher_artigos_pubmed
    from backend.coleta.coleta_semantic import recolher_artigos_semantic

    return {
        SOURCE_OPENALEX: recolher_artigos_openalex,
        SOURCE_PUBMED: recolher_artigos_pubmed,
        SOURCE_SEMANTIC_SCHOLAR: recolher_artigos_semantic,
    }


def _match_sentinel(sentinel, results):
    sentinel_doi = normalizar_doi(sentinel.get("canonical_doi"))
    candidates = []
    for rank, article in enumerate(results, start=1):
        sources = article.get("fontes_dict") or {}
        result_doi = normalizar_doi((sources.get("external_ids") or {}).get("doi"))
        result_title = _clean_title(article.get("titulo"))
        similarity = _title_similarity(sentinel.get("title"), result_title)
        if sentinel_doi and result_doi and sentinel_doi == result_doi:
            method, score = "doi_exact", 1.0
        elif sentinel_doi and result_doi and sentinel_doi != result_doi:
            # Um DOI divergente prevalece sobre a semelhança textual para evitar
            # marcar como recuperadas publicações distintas com títulos iguais.
            continue
        elif normalizar_titulo(sentinel.get("title")) == normalizar_titulo(result_title):
            method, score = "title_exact", 1.0
        elif similarity >= TITLE_SIMILARITY_THRESHOLD:
            method, score = "title_similar", similarity
        else:
            continue
        candidates.append(
            {
                "rank": rank,
                "method": method,
                "similarity": score,
                "matched_title": result_title,
                "matched_doi": result_doi,
            }
        )
    if not candidates:
        return None
    return min(candidates, key=lambda item: (0 if item["method"] == "doi_exact" else 1, item["rank"]))


def _safe_result(article, rank):
    sources = article.get("fontes_dict") or {}
    return {
        "rank": rank,
        "title": _clean_title(article.get("titulo")),
        "doi": normalizar_doi((sources.get("external_ids") or {}).get("doi")),
        "external_ids": sources.get("external_ids") or {},
    }


def run_calibration(project_id, max_results_per_source=100, collectors=None, connection_factory=None):
    """Executa uma busca piloto isolada e persiste seu retrato imutável."""
    try:
        limit = int(max_results_per_source)
    except (TypeError, ValueError) as exc:
        raise ValueError("O limite por fonte deve ser numérico.") from exc
    if not 10 <= limit <= 100:
        raise ValueError("O limite por fonte deve estar entre 10 e 100.")

    factory = _connection_factory(connection_factory)
    with factory() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT protocol_version, criteria_jsonb
            FROM review_projects WHERE id = %s
            """,
            (str(project_id),),
        )
        project = cursor.fetchone()
        if not project:
            raise ValueError("Projeto não encontrado.")
        protocol_version, protocol = int(project[0]), normalize_protocol(project[1])

    if not protocol.get("search_string"):
        raise ValueError("Confirme uma versão do protocolo com string de busca antes da calibração.")
    sentinels = list_sentinels(project_id, active_only=True, connection_factory=factory)
    if not sentinels:
        raise ValueError("Cadastre ao menos um artigo sentinela ativo.")

    configurations = get_bibliographic_settings()
    collectors = collectors or _default_collectors()
    queries, source_results, errors, matches = {}, {}, {}, []
    enabled_sources = [code for code in SOURCE_ORDER if configurations[code].enabled]
    if not enabled_sources:
        raise ValueError("Ative ao menos uma fonte bibliográfica para executar o piloto.")

    for source_code in enabled_sources:
        query = protocol["source_search_strings"].get(source_code) or protocol["search_string"]
        queries[source_code] = query
        try:
            articles = collectors[source_code](
                query, max_resultados=limit, raise_on_error=True
            ) or []
        except Exception as error:  # a falha fica registrada e as outras fontes continuam
            articles = []
            errors[source_code] = f"{error.__class__.__name__}: {str(error)}"[:500]
        source_results[source_code] = [
            _safe_result(article, rank) for rank, article in enumerate(articles, start=1)
        ]
        for sentinel in sentinels:
            match = _match_sentinel(sentinel, articles)
            if match:
                matches.append({**match, "source_code": source_code, "sentinel": sentinel})

    recovered_ids = {str(item["sentinel"]["id"]) for item in matches}
    source_summary = {}
    for source_code in enabled_sources:
        source_matches = [item for item in matches if item["source_code"] == source_code]
        recovered = len({str(item["sentinel"]["id"]) for item in source_matches})
        source_summary[source_code] = {
            "label": SOURCE_LABELS[source_code],
            "query": queries[source_code],
            "results_scanned": len(source_results[source_code]),
            "sentinels_recovered": recovered,
            "known_item_sensitivity": round(recovered / len(sentinels), 4),
            "error": errors.get(source_code),
        }
    missed = [
        {"id": str(item["id"]), "title": item["title"], "doi": item.get("canonical_doi")}
        for item in sentinels
        if str(item["id"]) not in recovered_ids
    ]
    status = "failed" if len(errors) == len(enabled_sources) else ("partial" if errors else "completed")
    summary = {
        "active_sentinels": len(sentinels),
        "recovered_unique": len(recovered_ids),
        "known_item_sensitivity": round(len(recovered_ids) / len(sentinels), 4),
        "sources": source_summary,
        "missed_sentinels": missed,
        "interpretation": (
            "Mede apenas a recuperação dos artigos sentinela cadastrados; não estima a sensibilidade completa da revisão."
        ),
    }
    snapshot = [
        {"id": str(item["id"]), "title": item["title"], "doi": item.get("canonical_doi")}
        for item in sentinels
    ]

    with factory() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO search_calibration_runs
                (project_id, protocol_version, protocol_fingerprint,
                 max_results_per_source, status, queries_jsonb,
                 sentinel_snapshot_jsonb, source_results_jsonb, summary_jsonb)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                str(project_id), protocol_version, protocol_fingerprint(protocol), limit,
                status, Json(queries), Json(snapshot), Json(source_results), Json(summary),
            ),
        )
        run_id = str(cursor.fetchone()[0])
        for match in matches:
            evidence = {
                "sentinel_title": match["sentinel"]["title"],
                "sentinel_doi": match["sentinel"].get("canonical_doi"),
                "threshold": TITLE_SIMILARITY_THRESHOLD,
            }
            cursor.execute(
                """
                INSERT INTO search_calibration_matches
                    (run_id, sentinel_id, source_code, result_rank, match_method,
                     similarity_score, matched_title, matched_doi, evidence_jsonb)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    run_id, str(match["sentinel"]["id"]), match["source_code"],
                    match["rank"], match["method"], match["similarity"],
                    match["matched_title"], match["matched_doi"], Json(evidence),
                ),
            )
    return {"id": run_id, "status": status, "protocol_version": protocol_version, "summary_jsonb": summary}


def list_calibration_runs(project_id, connection_factory=None):
    factory = _connection_factory(connection_factory)
    with factory() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT id, project_id, protocol_version, protocol_fingerprint,
                   max_results_per_source, status, queries_jsonb,
                   sentinel_snapshot_jsonb, source_results_jsonb, summary_jsonb, created_at
            FROM search_calibration_runs
            WHERE project_id = %s ORDER BY created_at DESC, id DESC
            """,
            (str(project_id),),
        )
        runs = _rows(cursor)
        if not runs:
            return []
        run_ids = [str(item["id"]) for item in runs]
        cursor.execute(
            """
            SELECT id, run_id, sentinel_id, source_code, result_rank, match_method,
                   similarity_score, matched_title, matched_doi, evidence_jsonb, created_at
            FROM search_calibration_matches
            WHERE run_id = ANY(%s::uuid[])
            ORDER BY run_id, source_code, result_rank
            """,
            (run_ids,),
        )
        matches = _rows(cursor)
    by_run = {}
    for match in matches:
        match["similarity_score"] = float(match["similarity_score"])
        by_run.setdefault(str(match["run_id"]), []).append(match)
    for run in runs:
        run["matches"] = by_run.get(str(run["id"]), [])
    return runs


def save_press_review(project_id, protocol_version, checklist, overall_decision, reviewer_name=None, review_notes=None, connection_factory=None):
    if overall_decision not in {"approved", "changes_requested"}:
        raise ValueError("Informe a decisão geral da revisão PRESS.")
    normalized = []
    submitted = {item.get("code"): item for item in checklist or []}
    for domain in PRESS_DOMAINS:
        item = submitted.get(domain["code"], {})
        response = item.get("response")
        if response not in PRESS_RESPONSES:
            raise ValueError(f"Revise o domínio: {domain['label']}.")
        normalized.append(
            {
                **domain,
                "response": response,
                "comment": str(item.get("comment") or "").strip(),
            }
        )
    factory = _connection_factory(connection_factory)
    with factory() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT criteria_jsonb FROM review_protocol_versions
            WHERE project_id = %s AND version = %s
            """,
            (str(project_id), int(protocol_version)),
        )
        row = cursor.fetchone()
        if not row:
            raise ValueError("Versão do protocolo não encontrada.")
        fingerprint = protocol_fingerprint(row[0])
        cursor.execute(
            """
            INSERT INTO press_search_reviews
                (project_id, protocol_version, protocol_fingerprint, checklist_jsonb,
                 overall_decision, reviewer_name, review_notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (project_id, protocol_version) DO UPDATE SET
                protocol_fingerprint = EXCLUDED.protocol_fingerprint,
                checklist_jsonb = EXCLUDED.checklist_jsonb,
                overall_decision = EXCLUDED.overall_decision,
                reviewer_name = EXCLUDED.reviewer_name,
                review_notes = EXCLUDED.review_notes,
                reviewed_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            RETURNING id
            """,
            (
                str(project_id), int(protocol_version), fingerprint, Json(normalized),
                overall_decision, str(reviewer_name or "").strip() or None,
                str(review_notes or "").strip() or None,
            ),
        )
        return str(cursor.fetchone()[0])


def list_press_reviews(project_id, connection_factory=None):
    factory = _connection_factory(connection_factory)
    with factory() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT id, project_id, protocol_version, protocol_fingerprint,
                   checklist_jsonb, overall_decision, reviewer_name, review_notes,
                   reviewed_at, updated_at
            FROM press_search_reviews
            WHERE project_id = %s ORDER BY protocol_version DESC
            """,
            (str(project_id),),
        )
        return _rows(cursor)


def calibration_export_json(run):
    return json.dumps(run, ensure_ascii=False, indent=2, default=_json_default).encode("utf-8")


def calibration_matches_csv(run):
    output = io.StringIO(newline="")
    columns = ["source", "sentinel_id", "rank", "match_method", "similarity", "matched_title", "matched_doi"]
    writer = csv.DictWriter(output, fieldnames=columns, delimiter=";")
    writer.writeheader()
    for item in run.get("matches") or []:
        writer.writerow(
            {
                "source": item.get("source_code"),
                "sentinel_id": item.get("sentinel_id"),
                "rank": item.get("result_rank"),
                "match_method": item.get("match_method"),
                "similarity": item.get("similarity_score"),
                "matched_title": item.get("matched_title"),
                "matched_doi": item.get("matched_doi") or "",
            }
        )
    return ("\ufeff" + output.getvalue()).encode("utf-8")


def _json_default(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)
