"""Limitações revisáveis e confiança humana na síntese da revisão."""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal
import json
import uuid

from psycopg2.extras import Json

from backend.app.protocol_service import protocol_fingerprint


CATEGORIES = {
    "search_coverage": "Cobertura da busca",
    "selection": "Seleção dos estudos",
    "document_access": "Acesso e integridade documental",
    "methodological_quality": "Qualidade metodológica",
    "evidence_traceability": "Rastreabilidade das evidências",
    "computational_reliability": "Confiabilidade computacional",
    "other": "Outra limitação",
}
IMPACTS = ("low", "moderate", "high")
STATUSES = ("pending", "confirmed", "dismissed", "mitigated", "resolved")
CONFIDENCE_LEVELS = ("high", "moderate", "low", "very_low")
CONFIDENCE_DOMAINS = (
    {
        "code": "search_coverage",
        "label": "Cobertura da busca",
        "description": "Abrangência das fontes, calibração, PRESS e recuperação de estudos conhecidos.",
    },
    {
        "code": "selection",
        "label": "Consistência da seleção",
        "description": "Conclusão da deduplicação e das decisões humanas de triagem.",
    },
    {
        "code": "document_access",
        "label": "Acesso e integridade documental",
        "description": "Disponibilidade dos textos integrais e possíveis efeitos de OCR.",
    },
    {
        "code": "methodological_quality",
        "label": "Robustez metodológica dos estudos",
        "description": "Cobertura e resultados das avaliações metodológicas humanas.",
    },
    {
        "code": "evidence_traceability",
        "label": "Rastreabilidade das evidências",
        "description": "Extrações revisadas e fontes literais validadas para a síntese.",
    },
    {
        "code": "computational_reliability",
        "label": "Confiabilidade computacional",
        "description": "Cobertura do Golden Set, benchmark e falhas observadas no RAG.",
    },
)


def _factory(connection_factory=None):
    if connection_factory is not None:
        return connection_factory
    from backend.app.database import get_connection

    return get_connection


def _row(cursor, value):
    if value is None:
        return None
    return dict(zip((item[0] for item in cursor.description), value))


def _rows(cursor):
    columns = [item[0] for item in cursor.description]
    return [dict(zip(columns, value)) for value in cursor.fetchall()]


def _json_safe(value):
    """Normaliza tipos retornados pelo PostgreSQL antes de gravá-los em JSONB."""
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, Decimal):
        return float(value)
    return value


def collect_limitation_facts(project_id, connection_factory=None):
    """Coleta fatos objetivos; nenhuma classificação humana é inferida aqui."""
    factory = _factory(connection_factory)
    with factory() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT protocol_version, criteria_jsonb FROM review_projects WHERE id = %s",
            (str(project_id),),
        )
        project = cursor.fetchone()
        if not project:
            raise ValueError("Projeto não encontrado.")
        protocol_version, protocol = int(project[0]), project[1] or {}

        cursor.execute(
            """
            SELECT protocol_version, status, summary_jsonb, created_at
            FROM search_calibration_runs
            WHERE project_id = %s
            ORDER BY created_at DESC, id DESC LIMIT 1
            """,
            (str(project_id),),
        )
        calibration = _row(cursor, cursor.fetchone())

        cursor.execute(
            """
            SELECT protocol_version, checklist_jsonb, overall_decision, reviewed_at
            FROM press_search_reviews
            WHERE project_id = %s AND protocol_version = %s
            LIMIT 1
            """,
            (str(project_id), protocol_version),
        )
        press_review = _row(cursor, cursor.fetchone())

        cursor.execute(
            """
            SELECT COUNT(*) FILTER (WHERE review_status = 'pending') AS pending
            FROM deduplication_decisions WHERE project_id = %s
            """,
            (str(project_id),),
        )
        dedup_pending = int(cursor.fetchone()[0] or 0)

        cursor.execute(
            """
            SELECT
                COUNT(DISTINCT p.id) AS papers,
                COUNT(DISTINCT p.id) FILTER (
                    WHERE s.id IS NULL OR s.human_decision IS NULL OR s.human_decision = 'Talvez'
                ) AS screening_pending,
                COUNT(DISTINCT p.id) FILTER (WHERE s.human_decision = 'Incluir') AS included,
                COUNT(DISTINCT p.id) FILTER (
                    WHERE s.human_decision = 'Incluir' AND EXISTS (
                        SELECT 1 FROM paper_chunks pc
                        WHERE pc.paper_id = p.id AND pc.chunk_type LIKE 'full_text_part_%%'
                    )
                ) AS indexed,
                COUNT(DISTINCT p.id) FILTER (
                    WHERE s.human_decision = 'Incluir' AND EXISTS (
                        SELECT 1 FROM paper_chunks pc
                        WHERE pc.paper_id = p.id AND pc.chunk_type LIKE 'full_text_part_%%'
                          AND pc.metadata_jsonb->>'text_extraction_method' = 'ocr'
                    )
                ) AS used_ocr,
                COUNT(DISTINCT p.id) FILTER (
                    WHERE s.human_decision = 'Incluir' AND EXISTS (
                        SELECT 1 FROM extracted_evidence e
                        WHERE e.paper_id = p.id
                          AND e.human_review_status IN ('approved', 'corrected')
                          AND e.human_review_jsonb IS NOT NULL
                          AND EXISTS (
                              SELECT 1 FROM evidence_field_sources efs
                              WHERE efs.extraction_id = e.id AND efs.quote_validated = TRUE
                          )
                    )
                ) AS synthesis_ready
            FROM deduplicated_papers p
            LEFT JOIN screening_decisions s ON s.paper_id = p.id
            WHERE p.project_id = %s
            """,
            (str(project_id),),
        )
        row = cursor.fetchone()
        workflow = {
            "papers": int(row[0] or 0),
            "screening_pending": int(row[1] or 0),
            "included": int(row[2] or 0),
            "indexed": int(row[3] or 0),
            "used_ocr": int(row[4] or 0),
            "synthesis_ready": int(row[5] or 0),
        }

        cursor.execute(
            """
            WITH active AS (
                SELECT id FROM methodological_assessment_instruments
                WHERE project_id = %s AND is_active = TRUE LIMIT 1
            ), included AS (
                SELECT DISTINCT p.id
                FROM deduplicated_papers p
                JOIN screening_decisions s ON s.paper_id = p.id
                WHERE p.project_id = %s AND s.human_decision = 'Incluir'
            )
            SELECT
                (SELECT COUNT(*) FROM included),
                COUNT(*) FILTER (WHERE a.review_status = 'reviewed'),
                COUNT(*) FILTER (WHERE a.review_status = 'reviewed' AND a.overall_rating = 'high'),
                COUNT(*) FILTER (WHERE a.review_status = 'reviewed' AND a.overall_rating = 'uncertain')
            FROM methodological_assessments a
            JOIN active i ON i.id = a.instrument_id
            JOIN included p ON p.id = a.paper_id
            """,
            (str(project_id), str(project_id)),
        )
        quality = cursor.fetchone()
        methodological = {
            "included": int(quality[0] or 0),
            "reviewed": int(quality[1] or 0),
            "high_risk": int(quality[2] or 0),
            "uncertain": int(quality[3] or 0),
        }

        cursor.execute(
            """
            SELECT metrics_jsonb, created_at
            FROM evaluation_runs
            WHERE project_id = %s AND run_type = 'rag_retrieval_benchmark'
            ORDER BY created_at DESC, id DESC LIMIT 1
            """,
            (str(project_id),),
        )
        benchmark = _row(cursor, cursor.fetchone())

        cursor.execute(
            """
            SELECT p.id AS paper_id, p.title, e.human_review_jsonb->'limitations' AS limitations
            FROM extracted_evidence e
            JOIN deduplicated_papers p ON p.id = e.paper_id
            WHERE p.project_id = %s
              AND e.human_review_status IN ('approved', 'corrected')
              AND jsonb_typeof(e.human_review_jsonb->'limitations') = 'array'
              AND jsonb_array_length(e.human_review_jsonb->'limitations') > 0
            ORDER BY p.title
            """,
            (str(project_id),),
        )
        study_limitations = _rows(cursor)

    return {
        "project_id": str(project_id),
        "protocol_version": protocol_version,
        "protocol": protocol,
        "calibration": calibration,
        "press_review": press_review,
        "dedup_pending": dedup_pending,
        "workflow": workflow,
        "methodological": methodological,
        "benchmark": benchmark,
        "study_limitations": study_limitations,
    }


def derive_limitation_signals(facts):
    """Transforma fatos em alertas explicáveis, sem validá-los como limitações."""
    version = int(facts["protocol_version"])
    signals = []

    def add(code, category, title, description, evidence, impact="moderate", source="automatic", scope="project", scope_id=None):
        signals.append(
            {
                "signal_code": code,
                "category": category,
                "title": title,
                "description": description,
                "evidence_jsonb": deepcopy(evidence),
                "impact": impact,
                "source_kind": source,
                "scope_type": scope,
                "scope_id": str(scope_id) if scope_id else None,
                "detected_protocol_version": version,
            }
        )

    calibration = facts.get("calibration")
    if not calibration or int(calibration.get("protocol_version") or 0) != version:
        add(
            "search_calibration_current_missing", "search_coverage",
            "Estratégia atual sem busca piloto",
            "A versão atual do protocolo ainda não possui uma calibração registrada com artigos sentinela.",
            {"protocol_version": version, "latest_calibration": calibration},
        )
    else:
        summary = calibration.get("summary_jsonb") or {}
        sensitivity = float(summary.get("known_item_sensitivity") or 0)
        if sensitivity < 1:
            add(
                "search_sentinel_gaps", "search_coverage",
                "Artigos sentinela não recuperados",
                "A busca piloto da versão atual não recuperou todos os estudos relevantes conhecidos cadastrados.",
                {
                    "known_item_sensitivity": sensitivity,
                    "active_sentinels": summary.get("active_sentinels"),
                    "recovered_unique": summary.get("recovered_unique"),
                    "missed_sentinels": summary.get("missed_sentinels") or [],
                },
                impact="high" if sensitivity < 0.8 else "moderate",
            )
        if calibration.get("status") != "completed":
            add(
                "search_calibration_partial", "search_coverage",
                "Busca piloto incompleta",
                "Uma ou mais fontes habilitadas não concluíram a última busca piloto.",
                {"status": calibration.get("status"), "sources": summary.get("sources") or {}},
            )

    press = facts.get("press_review")
    if not press:
        add(
            "press_review_current_missing", "search_coverage",
            "Revisão PRESS não registrada",
            "A estratégia da versão atual ainda não possui uma revisão humana PRESS registrada.",
            {"protocol_version": version},
        )
    else:
        unresolved = [
            item for item in (press.get("checklist_jsonb") or [])
            if item.get("response") in {"no", "uncertain"}
        ]
        if press.get("overall_decision") != "approved" or unresolved:
            add(
                "press_review_unresolved", "search_coverage",
                "Pendências na revisão PRESS",
                "A revisão humana da estratégia solicitou alterações ou manteve domínios não resolvidos.",
                {"overall_decision": press.get("overall_decision"), "unresolved_domains": unresolved},
                impact="high" if press.get("overall_decision") == "changes_requested" else "moderate",
            )

    if int(facts.get("dedup_pending") or 0):
        add(
            "deduplication_pending", "selection", "Deduplicações aguardando decisão",
            "Existem candidatos a duplicata ainda não revisados, o que pode alterar o conjunto de artigos únicos.",
            {"pending_decisions": int(facts["dedup_pending"])},
        )
    workflow = facts.get("workflow") or {}
    if int(workflow.get("screening_pending") or 0):
        add(
            "screening_incomplete", "selection", "Triagem humana incompleta",
            "Há artigos sem decisão humana final ou marcados como Talvez.",
            {"pending_articles": int(workflow["screening_pending"]), "papers": workflow.get("papers")},
        )
    included = int(workflow.get("included") or 0)
    indexed = int(workflow.get("indexed") or 0)
    if included > indexed:
        add(
            "included_full_text_missing", "document_access", "Textos integrais ausentes",
            "Parte dos artigos incluídos ainda não possui texto integral indexado para conferência e síntese.",
            {"included": included, "indexed": indexed, "missing": included - indexed},
            impact="high",
        )
    if int(workflow.get("used_ocr") or 0):
        add(
            "ocr_text_quality", "document_access", "Texto obtido com OCR",
            "Um ou mais documentos utilizaram reconhecimento óptico; os trechos empregados como evidência exigem conferência visual.",
            {"documents_with_ocr": int(workflow["used_ocr"]), "indexed": indexed},
            impact="low",
        )
    ready = int(workflow.get("synthesis_ready") or 0)
    if included > ready:
        add(
            "evidence_review_incomplete", "evidence_traceability", "Evidências ainda não prontas para síntese",
            "Parte dos estudos incluídos não possui extração aprovada ou corrigida com fonte literal validada.",
            {"included": included, "synthesis_ready": ready, "pending": included - ready},
            impact="high" if ready == 0 and included else "moderate",
        )

    quality = facts.get("methodological") or {}
    quality_included = int(quality.get("included") or 0)
    quality_reviewed = int(quality.get("reviewed") or 0)
    if quality_included > quality_reviewed:
        add(
            "methodological_quality_incomplete", "methodological_quality",
            "Avaliação metodológica incompleta",
            "Nem todos os artigos incluídos foram avaliados por uma pessoa com o instrumento metodológico ativo.",
            {"included": quality_included, "reviewed": quality_reviewed, "missing": quality_included - quality_reviewed},
            impact="high" if quality_reviewed == 0 and quality_included else "moderate",
        )
    if int(quality.get("high_risk") or 0) or int(quality.get("uncertain") or 0):
        add(
            "methodological_quality_concerns", "methodological_quality",
            "Riscos metodológicos nos estudos",
            "A revisão humana identificou estudos com alto risco ou classificação metodológica incerta.",
            {"high_risk": int(quality.get("high_risk") or 0), "uncertain": int(quality.get("uncertain") or 0)},
            impact="high" if int(quality.get("high_risk") or 0) else "moderate",
        )

    benchmark = facts.get("benchmark")
    if not benchmark:
        add(
            "rag_benchmark_missing", "computational_reliability", "RAG sem benchmark quantitativo",
            "Não há uma execução quantitativa do RAG registrada para este projeto.",
            {"run_type": "rag_retrieval_benchmark"},
            impact="low",
        )
    else:
        summary = ((benchmark.get("metrics_jsonb") or {}).get("summary") or {})
        comparison = summary.get("comparison_cohort") or {}
        comparable = int(comparison.get("query_count") or 0)
        failed = int(summary.get("failed_query_count") or 0)
        partial = (summary.get("reranking_calibration") or {}).get("coverage_status") == "partial"
        if comparable < 10 or failed or partial:
            add(
                "rag_benchmark_limited", "computational_reliability", "Cobertura limitada do benchmark RAG",
                "O benchmark possui amostra comparável pequena, falhas ou cobertura parcial do reranking.",
                {"comparable_queries": comparable, "failed_queries": failed, "reranking_coverage_partial": partial},
                impact="moderate" if failed or comparable < 5 else "low",
            )

    for item in facts.get("study_limitations") or []:
        limitations = [str(value).strip() for value in (item.get("limitations") or []) if str(value).strip()]
        if not limitations:
            continue
        add(
            f"study_reported:{item['paper_id']}", "methodological_quality",
            f"Limitações relatadas: {item['title']}",
            "O próprio estudo relata limitações que devem ser consideradas na interpretação agregada.",
            {"paper_id": str(item["paper_id"]), "paper_title": item["title"], "reported_limitations": limitations},
            impact="moderate", source="study_reported", scope="paper", scope_id=item["paper_id"],
        )
    return signals


def synchronize_limitations(project_id, connection_factory=None):
    factory = _factory(connection_factory)
    facts = collect_limitation_facts(project_id, connection_factory=factory)
    signals = derive_limitation_signals(facts)
    with factory() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT id, signal_code, status, is_current, category, title, description,
                   evidence_jsonb, impact, mitigation, human_notes
            FROM review_limitations
            WHERE project_id = %s AND source_kind IN ('automatic', 'study_reported')
            FOR UPDATE
            """,
            (str(project_id),),
        )
        existing = {row[1]: row for row in cursor.fetchall()}
        current_codes = {item["signal_code"] for item in signals}
        for signal_code, previous in existing.items():
            if signal_code in current_codes or not previous[3]:
                continue
            new_status = "resolved" if previous[2] == "pending" else previous[2]
            cursor.execute(
                """
                UPDATE review_limitations
                SET is_current = FALSE, status = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (new_status, str(previous[0])),
            )
            cursor.execute(
                """
                INSERT INTO review_limitation_events
                    (project_id, limitation_id, action, previous_jsonb, current_jsonb)
                VALUES (%s, %s, 'deactivated', %s, %s)
                """,
                (
                    str(project_id), str(previous[0]),
                    Json({"status": previous[2], "is_current": previous[3]}),
                    Json({"status": new_status, "is_current": False}),
                ),
            )
        for signal in signals:
            previous = existing.get(signal["signal_code"])
            if previous:
                limitation_id = str(previous[0])
                reactivated = previous[2] == "resolved" or not previous[3]
                cursor.execute(
                    """
                    UPDATE review_limitations SET
                        detected_protocol_version = %s, source_kind = %s, category = %s,
                        scope_type = %s, scope_id = %s, title = %s, description = %s,
                        evidence_jsonb = %s, impact = CASE WHEN status = 'pending' OR status = 'resolved' THEN %s ELSE impact END,
                        status = CASE WHEN status = 'resolved' THEN 'pending' ELSE status END,
                        is_current = TRUE, last_detected_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                    """,
                    (
                        signal["detected_protocol_version"], signal["source_kind"], signal["category"],
                        signal["scope_type"], signal["scope_id"], signal["title"], signal["description"],
                        Json(_json_safe(signal["evidence_jsonb"])), signal["impact"], limitation_id,
                    ),
                )
                if reactivated:
                    cursor.execute(
                        """
                        INSERT INTO review_limitation_events
                            (project_id, limitation_id, action, previous_jsonb, current_jsonb)
                        VALUES (%s, %s, 'reactivated', %s, %s)
                        """,
                        (
                            str(project_id), limitation_id,
                            Json({"status": previous[2], "is_current": previous[3]}),
                            Json(_json_safe(signal)),
                        ),
                    )
            else:
                cursor.execute(
                    """
                    INSERT INTO review_limitations
                        (project_id, detected_protocol_version, source_kind, signal_code,
                         category, scope_type, scope_id, title, description,
                         evidence_jsonb, impact)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        str(project_id), signal["detected_protocol_version"], signal["source_kind"],
                        signal["signal_code"], signal["category"], signal["scope_type"],
                        signal["scope_id"], signal["title"], signal["description"],
                        Json(_json_safe(signal["evidence_jsonb"])), signal["impact"],
                    ),
                )
                limitation_id = str(cursor.fetchone()[0])
                cursor.execute(
                    """
                    INSERT INTO review_limitation_events
                        (project_id, limitation_id, action, current_jsonb)
                    VALUES (%s, %s, 'created', %s)
                    """,
                    (str(project_id), limitation_id, Json(_json_safe(signal))),
                )
    return {"facts": facts, "signals_detected": len(signals)}


def list_limitations(project_id, include_historical=True, connection_factory=None):
    factory = _factory(connection_factory)
    with factory() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT id, project_id, detected_protocol_version, source_kind, signal_code,
                   category, scope_type, scope_id, title, description, evidence_jsonb,
                   status, impact, mitigation, human_notes, is_current,
                   first_detected_at, last_detected_at, reviewed_at, updated_at
            FROM review_limitations
            WHERE project_id = %s AND (%s = TRUE OR is_current = TRUE)
            ORDER BY is_current DESC,
                     CASE status WHEN 'pending' THEN 0 WHEN 'confirmed' THEN 1 WHEN 'mitigated' THEN 2 ELSE 3 END,
                     CASE impact WHEN 'high' THEN 0 WHEN 'moderate' THEN 1 ELSE 2 END,
                     category, title
            """,
            (str(project_id), bool(include_historical)),
        )
        return _rows(cursor)


def create_manual_limitation(project_id, category, title, description, impact, mitigation=None, human_notes=None, connection_factory=None):
    if category not in CATEGORIES:
        raise ValueError("Categoria de limitação inválida.")
    if impact not in IMPACTS:
        raise ValueError("Impacto inválido.")
    title = " ".join(str(title or "").split()).strip()
    description = " ".join(str(description or "").split()).strip()
    if len(title) < 5 or len(description) < 10:
        raise ValueError("Informe um título e uma descrição suficientemente detalhados.")
    factory = _factory(connection_factory)
    signal_code = f"manual:{uuid.uuid4()}"
    with factory() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT protocol_version FROM review_projects WHERE id = %s", (str(project_id),))
        row = cursor.fetchone()
        if not row:
            raise ValueError("Projeto não encontrado.")
        cursor.execute(
            """
            INSERT INTO review_limitations
                (project_id, detected_protocol_version, source_kind, signal_code,
                 category, title, description, evidence_jsonb, status, impact,
                 mitigation, human_notes, reviewed_at)
            VALUES (%s, %s, 'manual', %s, %s, %s, %s, '{}'::jsonb,
                    'confirmed', %s, %s, %s, CURRENT_TIMESTAMP)
            RETURNING id
            """,
            (
                str(project_id), int(row[0]), signal_code, category, title, description,
                impact, str(mitigation or "").strip() or None,
                str(human_notes or "").strip() or None,
            ),
        )
        limitation_id = str(cursor.fetchone()[0])
        cursor.execute(
            """
            INSERT INTO review_limitation_events
                (project_id, limitation_id, action, current_jsonb)
            VALUES (%s, %s, 'created', %s)
            """,
            (str(project_id), limitation_id, Json({"source_kind": "manual", "status": "confirmed", "impact": impact})),
        )
        return limitation_id


def review_limitation(project_id, limitation_id, status, impact, mitigation=None, human_notes=None, connection_factory=None):
    if status not in {"confirmed", "dismissed", "mitigated", "resolved"}:
        raise ValueError("Decisão humana inválida.")
    if impact not in IMPACTS:
        raise ValueError("Impacto inválido.")
    mitigation = str(mitigation or "").strip() or None
    human_notes = str(human_notes or "").strip() or None
    if status == "mitigated" and (not mitigation or len(mitigation) < 5):
        raise ValueError("Descreva a medida de mitigação adotada.")
    if status in {"dismissed", "resolved"} and (not human_notes or len(human_notes) < 5):
        raise ValueError("Justifique a decisão humana em pelo menos 5 caracteres.")
    factory = _factory(connection_factory)
    with factory() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT id, status, impact, mitigation, human_notes, is_current
            FROM review_limitations
            WHERE id = %s AND project_id = %s FOR UPDATE
            """,
            (str(limitation_id), str(project_id)),
        )
        row = cursor.fetchone()
        if not row:
            raise ValueError("Limitação não encontrada neste projeto.")
        previous = {
            "status": row[1], "impact": row[2], "mitigation": row[3],
            "human_notes": row[4], "is_current": row[5],
        }
        current = {
            "status": status, "impact": impact, "mitigation": mitigation,
            "human_notes": human_notes, "is_current": row[5],
        }
        cursor.execute(
            """
            UPDATE review_limitations
            SET status = %s, impact = %s, mitigation = %s, human_notes = %s,
                reviewed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (status, impact, mitigation, human_notes, str(limitation_id)),
        )
        cursor.execute(
            """
            INSERT INTO review_limitation_events
                (project_id, limitation_id, action, previous_jsonb, current_jsonb)
            VALUES (%s, %s, 'reviewed', %s, %s)
            """,
            (str(project_id), str(limitation_id), Json(previous), Json(current)),
        )


def _confidence_from_impacts(impacts):
    impacts = list(impacts)
    high = impacts.count("high")
    moderate = impacts.count("moderate")
    low = impacts.count("low")
    if high >= 2:
        return "very_low"
    if high == 1:
        return "low"
    if moderate:
        return "moderate"
    if low:
        return "moderate"
    return "high"


def suggest_confidence(limitations):
    active = [
        item for item in limitations
        if item.get("is_current") and item.get("status") in {"confirmed", "mitigated"}
    ]
    effective = []
    for item in active:
        impact = item["impact"]
        if item["status"] == "mitigated":
            impact = {"high": "moderate", "moderate": "low", "low": None}[impact]
        if impact:
            effective.append({**item, "effective_impact": impact})
    domains = []
    for domain in CONFIDENCE_DOMAINS:
        related = [item for item in effective if item["category"] == domain["code"]]
        domains.append(
            {
                **domain,
                "suggested_level": _confidence_from_impacts(
                    item["effective_impact"] for item in related
                ),
                "limitation_ids": [str(item["id"]) for item in related],
            }
        )
    return {
        "overall_level": _confidence_from_impacts(item["effective_impact"] for item in effective),
        "domains": domains,
        "basis_count": len(active),
        "notice": "Sugestão determinística e não vinculante; a classificação válida é sempre humana.",
    }


def save_confidence_snapshot(project_id, domain_ratings, overall_level, rationale, reviewer_name=None, connection_factory=None):
    if overall_level not in CONFIDENCE_LEVELS:
        raise ValueError("Nível geral de confiança inválido.")
    rationale = " ".join(str(rationale or "").split()).strip()
    if len(rationale) < 20:
        raise ValueError("Justifique a confiança da síntese com pelo menos 20 caracteres.")
    submitted = {item.get("code"): item for item in domain_ratings or []}
    normalized_domains = []
    for domain in CONFIDENCE_DOMAINS:
        item = submitted.get(domain["code"], {})
        level = item.get("level")
        if level not in CONFIDENCE_LEVELS:
            raise ValueError(f"Revise a dimensão: {domain['label']}.")
        normalized_domains.append(
            {**domain, "level": level, "rationale": " ".join(str(item.get("rationale") or "").split()).strip()}
        )
    factory = _factory(connection_factory)
    with factory() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT protocol_version, criteria_jsonb FROM review_projects WHERE id = %s FOR UPDATE",
            (str(project_id),),
        )
        project = cursor.fetchone()
        if not project:
            raise ValueError("Projeto não encontrado.")
        cursor.execute(
            """
            SELECT COUNT(*) FROM review_limitations
            WHERE project_id = %s AND is_current = TRUE AND status = 'pending'
            """,
            (str(project_id),),
        )
        pending = int(cursor.fetchone()[0] or 0)
        if pending:
            raise ValueError(
                f"Revise os {pending} alerta(s) pendente(s) antes de registrar a confiança."
            )
        cursor.execute(
            """
            SELECT id, signal_code, source_kind, category, scope_type, scope_id,
                   title, description, evidence_jsonb, status, impact,
                   mitigation, human_notes, is_current, reviewed_at
            FROM review_limitations
            WHERE project_id = %s AND is_current = TRUE
              AND status IN ('confirmed', 'mitigated')
            ORDER BY category, title
            """,
            (str(project_id),),
        )
        limitations = _rows(cursor)
        cursor.execute(
            """
            SELECT COALESCE(MAX(snapshot_version), 0) + 1
            FROM synthesis_confidence_snapshots WHERE project_id = %s
            """,
            (str(project_id),),
        )
        version = int(cursor.fetchone()[0])
        cursor.execute(
            """
            INSERT INTO synthesis_confidence_snapshots
                (project_id, snapshot_version, protocol_version, protocol_fingerprint,
                 overall_level, domain_ratings_jsonb, limitation_snapshot_jsonb,
                 rationale, reviewer_name)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, created_at
            """,
            (
                str(project_id), version, int(project[0]), protocol_fingerprint(project[1] or {}),
                overall_level, Json(_json_safe(normalized_domains)),
                Json(_json_safe(limitations)), rationale,
                " ".join(str(reviewer_name or "").split()).strip() or None,
            ),
        )
        created = cursor.fetchone()
    return {
        "id": str(created[0]), "snapshot_version": version,
        "protocol_version": int(project[0]), "overall_level": overall_level,
        "created_at": created[1],
    }


def list_confidence_snapshots(project_id, connection_factory=None):
    factory = _factory(connection_factory)
    with factory() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT id, project_id, snapshot_version, protocol_version,
                   protocol_fingerprint, overall_level, domain_ratings_jsonb,
                   limitation_snapshot_jsonb, rationale, reviewer_name, created_at
            FROM synthesis_confidence_snapshots
            WHERE project_id = %s ORDER BY snapshot_version DESC
            """,
            (str(project_id),),
        )
        return _rows(cursor)


def confidence_summary(project_id, connection_factory=None):
    factory = _factory(connection_factory)
    limitations = list_limitations(project_id, include_historical=False, connection_factory=factory)
    snapshots = list_confidence_snapshots(project_id, connection_factory=factory)
    with factory() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT protocol_version FROM review_projects WHERE id = %s", (str(project_id),))
        row = cursor.fetchone()
        if not row:
            raise ValueError("Projeto não encontrado.")
        protocol_version = int(row[0])
    latest = snapshots[0] if snapshots else None
    comparison_fields = (
        "id", "signal_code", "source_kind", "category", "scope_type", "scope_id",
        "title", "description", "evidence_jsonb", "status", "impact", "mitigation",
        "human_notes",
    )

    def limitation_state(items):
        return sorted(
            [
                _json_safe({field: item.get(field) for field in comparison_fields})
                for item in items if item.get("status") in {"confirmed", "mitigated"}
            ],
            key=lambda item: str(item.get("id")),
        )

    current_state = limitation_state(limitations)
    snapshot_state = limitation_state(
        (latest or {}).get("limitation_snapshot_jsonb", [])
    )
    pending = sum(1 for item in limitations if item["status"] == "pending")
    is_stale = bool(
        latest and (
            int(latest["protocol_version"]) != protocol_version
            or current_state != snapshot_state
        )
    )
    warnings = []
    if not latest:
        warnings.append("A confiança da síntese ainda não foi classificada por uma pessoa.")
    if pending:
        warnings.append(f"Há {pending} alerta(s) de limitação aguardando revisão humana.")
    if is_stale:
        warnings.append("O snapshot de confiança não representa mais o protocolo ou as limitações atuais.")
    return {
        "protocol_version": protocol_version,
        "latest_snapshot": latest,
        "current_limitations": limitations,
        "pending_count": pending,
        "is_stale": is_stale,
        "warnings": warnings,
    }


def confidence_snapshot_json(snapshot):
    return json.dumps(snapshot, ensure_ascii=False, indent=2, default=_json_default).encode("utf-8")


def _json_default(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)
