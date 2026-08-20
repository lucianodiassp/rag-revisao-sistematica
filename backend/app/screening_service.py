"""Decisões humanas de triagem com motivo estruturado e isolamento por projeto."""

DECISION_INCLUDE = "Incluir"
DECISION_EXCLUDE = "Excluir"
DECISION_MAYBE = "Talvez"
ALLOWED_DECISIONS = {DECISION_INCLUDE, DECISION_EXCLUDE, DECISION_MAYBE}

UNUSABLE_ABSTRACTS = (
    "Abstract indisponível.",
    "Abstract extraído do índice (simplificado para este exemplo).",
    "Abstract via PubMed E-Summary (Requer E-Fetch para texto completo).",
)

EXCLUSION_REASON_LABELS = {
    "population_mismatch": "População fora do escopo",
    "intervention_mismatch": "Intervenção ou exposição fora do escopo",
    "outcome_mismatch": "Desfecho fora do escopo",
    "study_design_mismatch": "Desenho do estudo incompatível",
    "publication_type": "Tipo de publicação não elegível",
    "language": "Idioma fora dos critérios",
    "date_range": "Período de publicação fora dos critérios",
    "insufficient_information": "Informações insuficientes para elegibilidade",
    "restricted_access": "Texto integral com acesso restrito",
    "pdf_not_found": "Texto integral não localizado",
    "metadata_mismatch": "PDF não corresponde ao artigo",
    "other": "Outro motivo",
}


def get_screening_summary(project_id, connection_factory=None):
    """Conta estados mutuamente exclusivos da triagem no projeto informado."""
    project_id = str(project_id or "").strip()
    if not project_id:
        raise ValueError("Projeto é obrigatório.")

    if connection_factory is None:
        from backend.app.database import get_connection

        connection_factory = get_connection

    with connection_factory() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            WITH latest_screening AS (
                SELECT DISTINCT ON (s.paper_id)
                       s.paper_id, s.human_decision
                FROM screening_decisions s
                JOIN deduplicated_papers scoped_paper ON scoped_paper.id = s.paper_id
                WHERE scoped_paper.project_id = %s
                ORDER BY s.paper_id, s.reviewed_at DESC NULLS LAST, s.id DESC
            )
            SELECT
                COUNT(p.id) AS total_papers,
                COUNT(p.id) FILTER (
                    WHERE s.paper_id IS NULL
                      AND NULLIF(BTRIM(p.abstract), '') IS NOT NULL
                      AND BTRIM(p.abstract) NOT IN (%s, %s, %s)
                ) AS awaiting_ai,
                COUNT(p.id) FILTER (
                    WHERE s.paper_id IS NULL
                      AND (
                          NULLIF(BTRIM(p.abstract), '') IS NULL
                          OR BTRIM(p.abstract) IN (%s, %s, %s)
                      )
                ) AS without_usable_abstract,
                COUNT(p.id) FILTER (
                    WHERE s.paper_id IS NOT NULL AND s.human_decision IS NULL
                ) AS awaiting_human,
                COUNT(p.id) FILTER (WHERE s.human_decision = 'Incluir') AS included,
                COUNT(p.id) FILTER (WHERE s.human_decision = 'Excluir') AS excluded,
                COUNT(p.id) FILTER (WHERE s.human_decision = 'Talvez') AS maybe,
                COUNT(p.id) FILTER (
                    WHERE s.human_decision IS NOT NULL
                      AND s.human_decision NOT IN ('Incluir', 'Excluir', 'Talvez')
                ) AS unknown_decision,
                (SELECT COUNT(*)
                 FROM deduplication_decisions dd
                 WHERE dd.project_id = %s AND dd.review_status = 'pending')
                    AS awaiting_deduplication
            FROM deduplicated_papers p
            LEFT JOIN latest_screening s ON s.paper_id = p.id
            WHERE p.project_id = %s
            """,
            (
                project_id,
                *UNUSABLE_ABSTRACTS,
                *UNUSABLE_ABSTRACTS,
                project_id,
                project_id,
            ),
        )
        row = cursor.fetchone()

    keys = (
        "total_papers",
        "awaiting_ai",
        "without_usable_abstract",
        "awaiting_human",
        "included",
        "excluded",
        "maybe",
        "unknown_decision",
        "awaiting_deduplication",
    )
    summary = dict(zip(keys, (int(value or 0) for value in row)))
    summary["final_decisions"] = summary["included"] + summary["excluded"]
    summary["human_reviewed"] = summary["final_decisions"] + summary["maybe"]
    summary["accounted_papers"] = sum(summary[key] for key in keys[1:8])
    summary["is_complete"] = bool(
        summary["total_papers"]
        and summary["final_decisions"] == summary["total_papers"]
        and not summary["awaiting_deduplication"]
    )
    return summary


def get_next_pending_human_screening(project_id, connection_factory=None):
    """Retorna o próximo parecer da IA que aguarda decisão humana."""
    project_id = str(project_id or "").strip()
    if not project_id:
        raise ValueError("Projeto é obrigatório.")

    if connection_factory is None:
        from backend.app.database import get_connection

        connection_factory = get_connection

    with connection_factory() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT d.id, d.title, d.abstract, s.suggested_decision, s.rationale_jsonb,
                   r.reason_code, r.reason, r.created_at
            FROM deduplicated_papers d
            JOIN screening_decisions s ON d.id = s.paper_id
            LEFT JOIN LATERAL (
                SELECT reason_code, reason, created_at
                FROM screening_reassessments sr
                WHERE sr.paper_id = d.id
                  AND sr.project_id = d.project_id
                  AND sr.action = 'return_to_screening'
                ORDER BY sr.created_at DESC
                LIMIT 1
            ) r ON TRUE
            WHERE d.project_id = %s
              AND s.human_decision IS NULL
            ORDER BY r.created_at DESC NULLS LAST, s.reviewed_at, d.created_at, d.id
            LIMIT 1
            """,
            (project_id,),
        )
        return cursor.fetchone()


def save_human_screening_decision(
    project_id,
    paper_id,
    human_decision,
    justification=None,
    exclusion_reason_code=None,
    connection_factory=None,
):
    """Persiste a decisão humana e exige categoria para toda exclusão."""
    project_id = str(project_id or "").strip()
    paper_id = str(paper_id or "").strip()
    human_decision = str(human_decision or "").strip()
    justification = " ".join(str(justification or "").split()).strip() or None
    exclusion_reason_code = str(exclusion_reason_code or "").strip() or None

    if not project_id or not paper_id:
        raise ValueError("Projeto e artigo são obrigatórios.")
    if human_decision not in ALLOWED_DECISIONS:
        raise ValueError("Decisão de triagem inválida.")

    if human_decision == DECISION_EXCLUDE:
        if exclusion_reason_code not in EXCLUSION_REASON_LABELS:
            raise ValueError("Selecione uma categoria válida para a exclusão.")
        if not justification or len(justification) < 5:
            raise ValueError("Descreva a exclusão com pelo menos 5 caracteres.")
    else:
        exclusion_reason_code = None

    if connection_factory is None:
        from backend.app.database import get_connection

        connection_factory = get_connection

    with connection_factory() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE screening_decisions s
            SET human_decision = %s,
                justification = %s,
                exclusion_reason_code = %s,
                reviewed_at = CURRENT_TIMESTAMP
            FROM deduplicated_papers p
            WHERE p.id = s.paper_id
              AND s.paper_id = %s
              AND p.project_id = %s
            RETURNING s.id
            """,
            (
                human_decision,
                justification,
                exclusion_reason_code,
                paper_id,
                project_id,
            ),
        )
        row = cursor.fetchone()
        if not row:
            raise ValueError("Decisão de triagem não encontrada no projeto ativo.")

    return {
        "id": str(row[0]),
        "project_id": project_id,
        "paper_id": paper_id,
        "human_decision": human_decision,
        "justification": justification,
        "exclusion_reason_code": exclusion_reason_code,
    }
