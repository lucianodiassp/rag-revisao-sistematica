"""Decisões humanas de triagem com motivo estruturado e isolamento por projeto."""

DECISION_INCLUDE = "Incluir"
DECISION_EXCLUDE = "Excluir"
DECISION_MAYBE = "Talvez"
ALLOWED_DECISIONS = {DECISION_INCLUDE, DECISION_EXCLUDE, DECISION_MAYBE}

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
