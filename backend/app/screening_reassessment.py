"""Reavaliação rastreável de artigos após a decisão inicial de triagem."""


ACTION_RETURN_TO_SCREENING = "return_to_screening"
ACTION_EXCLUDE = "exclude"
ALLOWED_ACTIONS = {ACTION_RETURN_TO_SCREENING, ACTION_EXCLUDE}

REASON_RESTRICTED_ACCESS = "restricted_access"
REASON_PDF_NOT_FOUND = "pdf_not_found"
REASON_METADATA_MISMATCH = "metadata_mismatch"
REASON_OTHER = "other"
ALLOWED_REASON_CODES = {
    REASON_RESTRICTED_ACCESS,
    REASON_PDF_NOT_FOUND,
    REASON_METADATA_MISMATCH,
    REASON_OTHER,
}


def reassess_included_paper(
    project_id,
    paper_id,
    action,
    reason_code,
    reason,
    connection_factory=None,
):
    """Reabre ou exclui um artigo incluído, preservando a decisão anterior."""
    project_id = str(project_id or "").strip()
    paper_id = str(paper_id or "").strip()
    action = str(action or "").strip()
    reason_code = str(reason_code or "").strip()
    reason = " ".join(str(reason or "").split()).strip()

    if not project_id or not paper_id:
        raise ValueError("Projeto e artigo são obrigatórios.")
    if action not in ALLOWED_ACTIONS:
        raise ValueError("Ação de reavaliação inválida.")
    if reason_code not in ALLOWED_REASON_CODES:
        raise ValueError("Categoria da justificativa inválida.")
    if len(reason) < 5:
        raise ValueError("Informe uma justificativa com pelo menos 5 caracteres.")

    if connection_factory is None:
        from backend.app.database import get_connection

        connection_factory = get_connection

    resulting_decision = None if action == ACTION_RETURN_TO_SCREENING else "Excluir"

    with connection_factory() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT s.id, s.human_decision, s.justification, d.title
            FROM screening_decisions s
            JOIN deduplicated_papers d ON d.id = s.paper_id
            WHERE d.project_id = %s
              AND d.id = %s
            ORDER BY s.reviewed_at DESC NULLS LAST, s.id
            LIMIT 1
            FOR UPDATE OF s
            """,
            (project_id, paper_id),
        )
        current = cursor.fetchone()
        if not current:
            raise ValueError("Decisão de triagem não encontrada no projeto ativo.")

        decision_id, previous_decision, previous_justification, title = current
        if previous_decision != "Incluir":
            raise ValueError("Apenas artigos atualmente incluídos podem ser reavaliados aqui.")

        if action == ACTION_RETURN_TO_SCREENING:
            cursor.execute(
                """
                UPDATE screening_decisions
                SET human_decision = NULL,
                    justification = NULL,
                    exclusion_reason_code = NULL,
                    reviewed_at = NULL
                WHERE id = %s
                """,
                (str(decision_id),),
            )
        else:
            cursor.execute(
                """
                UPDATE screening_decisions
                SET human_decision = 'Excluir',
                    justification = %s,
                    exclusion_reason_code = %s,
                    reviewed_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (reason, reason_code, str(decision_id)),
            )

        cursor.execute(
            """
            INSERT INTO screening_reassessments
                (project_id, screening_decision_id, paper_id, action,
                 reason_code, reason, previous_human_decision,
                 previous_justification, resulting_human_decision, origin)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'pdf_management')
            RETURNING id, created_at
            """,
            (
                project_id,
                str(decision_id),
                paper_id,
                action,
                reason_code,
                reason,
                previous_decision,
                previous_justification,
                resulting_decision,
            ),
        )
        reassessment_id, created_at = cursor.fetchone()

    return {
        "id": str(reassessment_id),
        "project_id": project_id,
        "paper_id": paper_id,
        "title": title,
        "action": action,
        "reason_code": reason_code,
        "reason": reason,
        "previous_human_decision": previous_decision,
        "resulting_human_decision": resulting_decision,
        "created_at": created_at,
    }
