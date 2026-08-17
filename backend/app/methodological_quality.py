"""Avaliação metodológica genérica, versionada e rastreável por projeto.

O módulo oferece um checklist configurável e apoio opcional de IA. Ele não implementa
nem reivindica equivalência a instrumentos oficiais específicos de desenho de estudo.
"""

import json
import re
import time
import uuid

from google.genai.errors import APIError
from psycopg2.extras import Json

from backend.app.ai_config import TASK_METHOD_QUALITY, get_generation_config
from backend.app.ai_service import generate_content
from backend.app.database import get_connection, log_interacao_agente
from backend.app.evidence_utils import normalizar_trecho


INSTRUMENT_SCHEMA_VERSION = "generic-methodological-v1"
MAX_CONTEXT_CHARACTERS = 100_000
RESPONSES = ("yes", "no", "uncertain", "not_applicable")
RATINGS = ("low", "moderate", "high", "uncertain")

DEFAULT_INSTRUMENT_NAME = "Checklist metodológico genérico"
DEFAULT_INSTRUMENT_DESCRIPTION = (
    "Checklist exploratório para documentar transparência, qualidade e possíveis "
    "fontes de viés. Deve ser adaptado ao desenho dos estudos e revisado por humano."
)
DEFAULT_DOMAINS = (
    {
        "code": "population_selection",
        "label": "Seleção da população ou amostra",
        "question": "A população ou amostra foi definida e selecionada de forma adequada ao objetivo?",
        "critical": False,
    },
    {
        "code": "study_design",
        "label": "Desenho do estudo",
        "question": "O desenho do estudo é apropriado e está descrito com clareza?",
        "critical": True,
    },
    {
        "code": "data_quality",
        "label": "Qualidade dos dados",
        "question": "A origem, preparação e qualidade dos dados estão adequadamente documentadas?",
        "critical": True,
    },
    {
        "code": "method_transparency",
        "label": "Transparência do método",
        "question": "O método possui detalhes suficientes para compreender como os resultados foram obtidos?",
        "critical": False,
    },
    {
        "code": "outcome_metrics",
        "label": "Desfechos e métricas",
        "question": "Os desfechos ou métricas são pertinentes e definidos de forma verificável?",
        "critical": False,
    },
    {
        "code": "confounding",
        "label": "Vieses e fatores de confusão",
        "question": "Possíveis vieses ou fatores de confusão foram considerados e tratados?",
        "critical": False,
    },
    {
        "code": "reproducibility",
        "label": "Reprodutibilidade",
        "question": "Há informação suficiente sobre dados, código, parâmetros ou procedimentos para apoiar a reprodução?",
        "critical": False,
    },
    {
        "code": "conflicts_funding",
        "label": "Financiamento e conflitos de interesse",
        "question": "Financiamento e potenciais conflitos de interesse foram declarados?",
        "critical": False,
    },
)


def _row_as_dict(cursor, row):
    if not row:
        return None
    return dict(zip((item[0] for item in cursor.description), row))


def validate_domains(domains):
    if not isinstance(domains, (list, tuple)) or not domains:
        raise ValueError("O instrumento precisa possuir ao menos um domínio.")
    normalized = []
    codes = set()
    for item in domains:
        code = re.sub(r"[^a-z0-9_]+", "_", str(item.get("code") or "").strip().lower()).strip("_")
        label = str(item.get("label") or "").strip()
        question = str(item.get("question") or "").strip()
        if len(code) < 3 or code in codes:
            raise ValueError("Cada domínio deve possuir um código único com ao menos 3 caracteres.")
        if len(label) < 3 or len(question) < 10:
            raise ValueError("Todos os domínios precisam de nome e pergunta descritiva.")
        codes.add(code)
        normalized.append(
            {"code": code, "label": label, "question": question, "critical": bool(item.get("critical"))}
        )
    return normalized


def calculate_overall_rating(domain_results, domains):
    by_code = {item["domain_code"]: item for item in domain_results}
    negatives = 0
    uncertainties = 0
    critical_negative = False
    for domain in domains:
        response = (by_code.get(domain["code"]) or {}).get("response", "uncertain")
        if response == "no":
            negatives += 1
            critical_negative = critical_negative or bool(domain.get("critical"))
        elif response == "uncertain":
            uncertainties += 1
    if critical_negative or negatives >= 2:
        return "high"
    if negatives == 1:
        return "moderate"
    if uncertainties >= 2:
        return "uncertain"
    if uncertainties == 1:
        return "moderate"
    return "low"


def validate_ai_suggestion(raw_response, chunks, domains, context_truncated=False):
    chunks_by_id = {str(item["id"]): item for item in chunks}
    raw_response = raw_response if isinstance(raw_response, dict) else {}
    raw_domains = {
        str(item.get("domain_code")): item
        for item in (raw_response.get("domains") or [])
        if isinstance(item, dict)
    }
    results = []
    warnings = []
    for domain in domains:
        raw = raw_domains.get(domain["code"], {})
        response = str(raw.get("response") or "uncertain").strip().lower()
        if response not in RESPONSES:
            response = "uncertain"
        evidence = []
        seen = set()
        for source in raw.get("evidence") or []:
            if not isinstance(source, dict):
                continue
            chunk_id = str(source.get("chunk_id") or "")
            quote = re.sub(r"\s+", " ", str(source.get("quote") or "")).strip()
            chunk = chunks_by_id.get(chunk_id)
            key = (chunk_id, normalizar_trecho(quote))
            if not chunk or not quote or key in seen:
                continue
            if normalizar_trecho(quote) not in normalizar_trecho(chunk.get("chunk_text")):
                continue
            seen.add(key)
            evidence.append(
                {"chunk_id": chunk_id, "page": chunk.get("page_number"), "quote": quote}
            )
        if response in {"yes", "no"} and not evidence:
            warnings.append(
                f"{domain['code']}: resposta alterada para incerta por ausência de citação literal válida"
            )
            response = "uncertain"
        try:
            confidence = max(0.0, min(1.0, float(raw.get("confidence", 0))))
        except (TypeError, ValueError):
            confidence = 0.0
        if not evidence:
            confidence = 0.0
        results.append(
            {
                "domain_code": domain["code"],
                "response": response,
                "rationale": str(raw.get("rationale") or "Evidência insuficiente.").strip(),
                "confidence": confidence,
                "evidence": evidence,
            }
        )
    return {
        "schema_version": INSTRUMENT_SCHEMA_VERSION,
        "domains": results,
        "suggested_overall_rating": calculate_overall_rating(results, domains),
        "overall_rationale": str(raw_response.get("overall_rationale") or "").strip(),
        "validation_warnings": warnings,
        "document_scope": {"chunks_used": len(chunks_by_id), "truncated": bool(context_truncated)},
    }


def ensure_default_instrument(project_id):
    project_id = str(project_id)
    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT id FROM review_projects WHERE id = %s FOR UPDATE", (project_id,))
        if not cursor.fetchone():
            raise ValueError("Projeto não encontrado.")
        cursor.execute(
            """
            SELECT id, project_id, version, name, description, schema_version,
                   domains_jsonb, change_reason, is_active, created_at
            FROM methodological_assessment_instruments
            WHERE project_id = %s AND is_active = TRUE
            """,
            (project_id,),
        )
        current = _row_as_dict(cursor, cursor.fetchone())
        if current:
            return current
        cursor.execute(
            """
            INSERT INTO methodological_assessment_instruments
                (project_id, version, name, description, domains_jsonb, change_reason)
            VALUES (%s, 1, %s, %s, %s, 'Criação do instrumento padrão')
            RETURNING id, project_id, version, name, description, schema_version,
                      domains_jsonb, change_reason, is_active, created_at
            """,
            (project_id, DEFAULT_INSTRUMENT_NAME, DEFAULT_INSTRUMENT_DESCRIPTION, Json(list(DEFAULT_DOMAINS))),
        )
        return _row_as_dict(cursor, cursor.fetchone())


def create_instrument_version(project_id, name, description, domains, change_reason):
    project_id = str(project_id)
    name, description, change_reason = (str(value or "").strip() for value in (name, description, change_reason))
    if len(name) < 5 or len(description) < 10 or len(change_reason) < 5:
        raise ValueError("Informe nome, descrição e motivo da nova versão.")
    domains = validate_domains(domains)
    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT id FROM review_projects WHERE id = %s FOR UPDATE", (project_id,))
        if not cursor.fetchone():
            raise ValueError("Projeto não encontrado.")
        cursor.execute(
            "SELECT COALESCE(MAX(version), 0) FROM methodological_assessment_instruments WHERE project_id = %s",
            (project_id,),
        )
        version = int(cursor.fetchone()[0]) + 1
        cursor.execute(
            "UPDATE methodological_assessment_instruments SET is_active = FALSE WHERE project_id = %s AND is_active = TRUE",
            (project_id,),
        )
        cursor.execute(
            """
            INSERT INTO methodological_assessment_instruments
                (project_id, version, name, description, domains_jsonb, change_reason)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (project_id, version, name, description, Json(domains), change_reason),
        )
        return {"id": str(cursor.fetchone()[0]), "version": version}


def list_instrument_versions(project_id):
    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT id, version, name, description, schema_version, domains_jsonb,
                   change_reason, is_active, created_at
            FROM methodological_assessment_instruments
            WHERE project_id = %s ORDER BY version DESC
            """,
            (str(project_id),),
        )
        columns = [item[0] for item in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


def list_eligible_assessments(project_id, instrument_id=None):
    instrument = ensure_default_instrument(project_id)
    instrument_id = str(instrument_id or instrument["id"])
    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT p.id AS paper_id, p.title, a.id AS assessment_id,
                   a.ai_suggestion_jsonb, a.human_assessment_jsonb,
                   a.overall_rating, a.review_status, a.review_notes,
                   a.updated_at, a.reviewed_at
            FROM deduplicated_papers p
            LEFT JOIN methodological_assessments a
              ON a.project_id = p.project_id AND a.paper_id = p.id AND a.instrument_id = %s
            WHERE p.project_id = %s
              AND EXISTS (
                  SELECT 1 FROM screening_decisions s
                  WHERE s.paper_id = p.id AND s.human_decision = 'Incluir'
              )
              AND EXISTS (
                  SELECT 1 FROM paper_chunks pc
                  WHERE pc.paper_id = p.id
                    AND pc.chunk_type LIKE 'full_text_part_%%'
                    AND pc.metadata_jsonb->>'source_type' = 'pdf'
                    AND pc.metadata_jsonb ? 'page_start'
              )
            ORDER BY p.title
            """,
            (instrument_id, str(project_id)),
        )
        columns = [item[0] for item in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _load_pdf_chunks(project_id, paper_id):
    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT pc.id, pc.chunk_text, (pc.metadata_jsonb->>'page_start')::INTEGER
            FROM paper_chunks pc
            JOIN deduplicated_papers p ON p.id = pc.paper_id
            WHERE p.project_id = %s AND p.id = %s
              AND pc.chunk_type LIKE 'full_text_part_%%'
              AND pc.metadata_jsonb->>'source_type' = 'pdf'
              AND pc.metadata_jsonb ? 'page_start'
            ORDER BY (pc.metadata_jsonb->>'page_start')::INTEGER,
                     COALESCE((pc.metadata_jsonb->>'page_chunk_index')::INTEGER, 1), pc.id
            """,
            (str(project_id), str(paper_id)),
        )
        all_chunks = [
            {"id": str(row[0]), "chunk_text": row[1], "page_number": row[2]}
            for row in cursor.fetchall()
        ]
    selected, size = [], 0
    for chunk in all_chunks:
        if selected and size + len(chunk["chunk_text"]) > MAX_CONTEXT_CHARACTERS:
            break
        selected.append(chunk)
        size += len(chunk["chunk_text"])
    return selected, len(selected) < len(all_chunks)


def _context(chunks):
    return "\n\n".join(
        f"[chunk_id={item['id']} | página={item['page_number']}]\n{item['chunk_text']}"
        for item in chunks
    )


def _persist_ai_suggestion(project_id, paper_id, instrument, suggestion):
    assessment_id = str(uuid.uuid4())
    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO methodological_assessments
                (id, project_id, paper_id, instrument_id, ai_suggestion_jsonb)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (project_id, paper_id, instrument_id) DO UPDATE
            SET ai_suggestion_jsonb = EXCLUDED.ai_suggestion_jsonb,
                human_assessment_jsonb = NULL, overall_rating = NULL,
                review_status = 'pending', review_notes = NULL,
                reviewed_at = NULL, updated_at = CURRENT_TIMESTAMP
            RETURNING id
            """,
            (assessment_id, str(project_id), str(paper_id), str(instrument["id"]), Json(suggestion)),
        )
        assessment_id = str(cursor.fetchone()[0])
        cursor.execute("DELETE FROM methodological_assessment_sources WHERE assessment_id = %s", (assessment_id,))
        for domain in suggestion["domains"]:
            for order, source in enumerate(domain["evidence"]):
                cursor.execute(
                    """
                    INSERT INTO methodological_assessment_sources
                        (assessment_id, domain_code, evidence_order, chunk_id,
                         page_number, quote, quote_validated, human_validated)
                    VALUES (%s, %s, %s, %s, %s, %s, TRUE, FALSE)
                    """,
                    (assessment_id, domain["domain_code"], order, source["chunk_id"], source["page"], source["quote"]),
                )
    return assessment_id


def create_manual_assessment(project_id, paper_id):
    """Abre uma avaliação sem consumir IA, preservando o mesmo instrumento ativo."""
    project_id, paper_id = str(project_id), str(paper_id)
    instrument = ensure_default_instrument(project_id)
    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT 1 FROM deduplicated_papers p
            WHERE p.id = %s AND p.project_id = %s
              AND EXISTS (SELECT 1 FROM screening_decisions s WHERE s.paper_id = p.id AND s.human_decision = 'Incluir')
              AND EXISTS (
                  SELECT 1 FROM paper_chunks pc WHERE pc.paper_id = p.id
                    AND pc.chunk_type LIKE 'full_text_part_%%'
                    AND pc.metadata_jsonb->>'source_type' = 'pdf'
              )
            """,
            (paper_id, project_id),
        )
        if not cursor.fetchone():
            raise ValueError("Artigo incluído com PDF indexado não encontrado no projeto ativo.")
        assessment_id = str(uuid.uuid4())
        cursor.execute(
            """
            INSERT INTO methodological_assessments (id, project_id, paper_id, instrument_id)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (project_id, paper_id, instrument_id) DO UPDATE
            SET updated_at = CURRENT_TIMESTAMP
            RETURNING id
            """,
            (assessment_id, project_id, paper_id, str(instrument["id"])),
        )
        return str(cursor.fetchone()[0])


def analyze_paper_with_ai(project_id, paper_id):
    project_id, paper_id = str(project_id), str(paper_id)
    instrument = ensure_default_instrument(project_id)
    chunks, truncated = _load_pdf_chunks(project_id, paper_id)
    if not chunks:
        raise ValueError("O artigo não possui texto integral rastreável neste projeto.")
    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT p.title,
                   EXISTS (
                       SELECT 1 FROM methodological_assessments a
                       WHERE a.project_id = p.project_id AND a.paper_id = p.id
                         AND a.instrument_id = %s AND a.review_status = 'reviewed'
                   ) AS already_reviewed
            FROM deduplicated_papers p
            WHERE p.id = %s AND p.project_id = %s
              AND EXISTS (SELECT 1 FROM screening_decisions s WHERE s.paper_id = p.id AND s.human_decision = 'Incluir')
            """,
            (str(instrument["id"]), paper_id, project_id),
        )
        row = cursor.fetchone()
        if not row:
            raise ValueError("Artigo incluído não encontrado no projeto ativo.")
        title = row[0]
        if row[1]:
            raise ValueError(
                "A versão ativa já possui revisão humana para este artigo. "
                "Crie uma nova versão do instrumento para reavaliá-lo sem apagar o histórico."
            )
    domains_json = json.dumps(instrument["domains_jsonb"], ensure_ascii=False, indent=2)
    prompt = f"""
Você auxilia uma avaliação de qualidade metodológica, mas a decisão final pertence ao humano.
Analise SOMENTE os trechos do PDF. Para cada domínio abaixo, responda yes, no,
uncertain ou not_applicable. Respostas yes/no devem conter ao menos uma citação
literal e o chunk_id exato. Não use conhecimento externo nem preencha lacunas.

Artigo: {title}
Instrumento genérico v{instrument['version']}:
{domains_json}

Responda exclusivamente em JSON:
{{
  "domains": [
    {{"domain_code": "codigo", "response": "uncertain", "rationale": "...",
      "confidence": 0.0, "evidence": [{{"chunk_id": "uuid", "quote": "trecho literal"}}]}}
  ],
  "overall_rationale": "síntese breve das incertezas e possíveis vieses"
}}

TRECHOS DO PDF:
{_context(chunks)}
"""
    last_error = None
    for attempt in range(3):
        try:
            response = generate_content(
                TASK_METHOD_QUALITY, contents=prompt, response_mime_type="application/json"
            )
            suggestion = validate_ai_suggestion(
                json.loads(response.text), chunks, instrument["domains_jsonb"], truncated
            )
            assessment_id = _persist_ai_suggestion(project_id, paper_id, instrument, suggestion)
            log_interacao_agente(
                project_id,
                "methodological_quality_agent",
                {
                    "paper_id": paper_id,
                    "instrument_id": str(instrument["id"]),
                    "instrument_version": instrument["version"],
                    "chunk_ids": [item["id"] for item in chunks],
                    "context_truncated": truncated,
                },
                {"assessment_id": assessment_id, "suggestion": suggestion},
                get_generation_config(TASK_METHOD_QUALITY).metadata(),
            )
            return assessment_id
        except APIError as error:
            last_error = error
            if error.code not in {429, 500, 502, 503, 504} or attempt == 2:
                raise
            time.sleep(2 ** attempt)
    raise last_error


def load_assessment_sources(assessment_id, project_id):
    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT s.id, s.domain_code, s.evidence_order, s.chunk_id,
                   s.page_number, s.quote, s.quote_validated, s.human_validated
            FROM methodological_assessment_sources s
            JOIN methodological_assessments a ON a.id = s.assessment_id
            WHERE s.assessment_id = %s AND a.project_id = %s
            ORDER BY s.domain_code, s.evidence_order
            """,
            (str(assessment_id), str(project_id)),
        )
        columns = [item[0] for item in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


def save_human_assessment(
    project_id, assessment_id, domain_answers, overall_rating, review_notes, confirmed_source_ids=None
):
    project_id, assessment_id = str(project_id), str(assessment_id)
    overall_rating = str(overall_rating or "").strip().lower()
    review_notes = str(review_notes or "").strip()
    if overall_rating not in RATINGS:
        raise ValueError("Selecione uma classificação final válida.")
    if len(review_notes) < 5:
        raise ValueError("Registre uma justificativa geral com ao menos 5 caracteres.")
    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT i.domains_jsonb
            FROM methodological_assessments a
            JOIN methodological_assessment_instruments i ON i.id = a.instrument_id
            WHERE a.id = %s AND a.project_id = %s
            FOR UPDATE
            """,
            (assessment_id, project_id),
        )
        row = cursor.fetchone()
        if not row:
            raise ValueError("Avaliação não encontrada no projeto ativo.")
        domains = row[0]
        normalized = []
        for domain in domains:
            answer = domain_answers.get(domain["code"], {})
            response = str(answer.get("response") or "").strip().lower()
            justification = str(answer.get("justification") or "").strip()
            if response not in RESPONSES:
                raise ValueError(f"Resposta inválida no domínio {domain['label']}.")
            if len(justification) < 5:
                raise ValueError(f"Justifique a avaliação do domínio {domain['label']}.")
            normalized.append(
                {"domain_code": domain["code"], "response": response, "justification": justification}
            )
        cursor.execute(
            """
            UPDATE methodological_assessments
            SET human_assessment_jsonb = %s, overall_rating = %s,
                review_status = 'reviewed', review_notes = %s,
                reviewed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s AND project_id = %s
            """,
            (Json({"schema_version": INSTRUMENT_SCHEMA_VERSION, "domains": normalized}), overall_rating, review_notes, assessment_id, project_id),
        )
        cursor.execute(
            "UPDATE methodological_assessment_sources SET human_validated = FALSE WHERE assessment_id = %s",
            (assessment_id,),
        )
        confirmed = [str(value) for value in (confirmed_source_ids or [])]
        if confirmed:
            cursor.execute(
                """
                UPDATE methodological_assessment_sources s SET human_validated = TRUE
                FROM methodological_assessments a
                WHERE s.assessment_id = a.id AND a.id = %s AND a.project_id = %s
                  AND s.id = ANY(%s::uuid[]) AND s.quote_validated = TRUE
                """,
                (assessment_id, project_id, confirmed),
            )


def methodological_summary(project_id, active_only=True):
    where_active = "AND i.is_active = TRUE" if active_only else ""
    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT a.id, a.paper_id, p.title, i.id AS instrument_id,
                   i.version AS instrument_version, i.name AS instrument_name,
                   i.domains_jsonb, a.human_assessment_jsonb, a.overall_rating,
                   a.review_notes, a.reviewed_at,
                   COUNT(s.id) FILTER (WHERE s.human_validated = TRUE) AS confirmed_sources,
                   COALESCE(
                       jsonb_agg(
                           jsonb_build_object(
                               'domain_code', s.domain_code,
                               'page', s.page_number,
                               'quote', s.quote,
                               'chunk_id', s.chunk_id
                           ) ORDER BY s.domain_code, s.evidence_order
                       ) FILTER (WHERE s.human_validated = TRUE),
                       '[]'::jsonb
                   ) AS confirmed_source_details
            FROM methodological_assessments a
            JOIN methodological_assessment_instruments i ON i.id = a.instrument_id
            JOIN deduplicated_papers p ON p.id = a.paper_id
            LEFT JOIN methodological_assessment_sources s ON s.assessment_id = a.id
            WHERE a.project_id = %s AND a.review_status = 'reviewed' {where_active}
            GROUP BY a.id, p.title, i.id
            ORDER BY p.title
            """,
            (str(project_id),),
        )
        columns = [item[0] for item in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
