"""Fluxo PRISMA operacional, determinístico, exportável e versionado."""

import csv
import html
import io
import json
import textwrap
from datetime import date, datetime

from psycopg2.extras import Json

from backend.app.screening_service import EXCLUSION_REASON_LABELS


METRIC_LABELS = {
    "records_identified": "Registros identificados",
    "duplicates_removed": "Duplicatas removidas",
    "deduplication_pending": "Casos de deduplicação pendentes",
    "records_after_deduplication": "Registros únicos após deduplicação",
    "screened_by_ai": "Registros avaliados pela IA",
    "screening_completed": "Decisões humanas definitivas",
    "screening_uncertain": "Decisões marcadas como talvez",
    "screening_pending": "Registros sem decisão humana",
    "screening_excluded": "Excluídos na triagem",
    "reports_sought": "Textos integrais procurados",
    "reports_not_retrieved": "Textos integrais não obtidos",
    "returned_to_screening": "Devolvidos para nova triagem",
    "reports_awaiting_pdf": "Textos integrais ainda pendentes",
    "reports_assessed": "Textos integrais indexados e avaliáveis",
    "full_text_excluded": "Excluídos após busca do texto integral",
    "studies_selected": "Artigos atualmente selecionados",
    "evidence_extracted": "Artigos com evidência extraída",
    "studies_included_synthesis": "Estudos incluídos na síntese",
}

FULL_TEXT_NOT_RETRIEVED_REASONS = {"restricted_access", "pdf_not_found"}


def _json_default(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def _normalizar_contagens(rows):
    return {str(key): int(value) for key, value in rows}


def calcular_fluxo_prisma(project_id, connection_factory=None):
    """Calcula o fluxo atual somente a partir dos dados persistidos do projeto."""
    project_id = str(project_id or "").strip()
    if not project_id:
        raise ValueError("O projeto é obrigatório para calcular o fluxo PRISMA.")

    if connection_factory is None:
        from backend.app.database import get_connection

        connection_factory = get_connection

    with connection_factory() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT title, protocol_version
            FROM review_projects
            WHERE id = %s
            """,
            (project_id,),
        )
        project = cursor.fetchone()
        if not project:
            raise ValueError("Projeto não encontrado.")
        project_title, protocol_version = project

        cursor.execute(
            """
            SELECT source, COUNT(*)
            FROM retrieved_records
            WHERE project_id = %s
            GROUP BY source
            ORDER BY source
            """,
            (project_id,),
        )
        source_counts = _normalizar_contagens(cursor.fetchall())

        cursor.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM retrieved_records WHERE project_id = %s),
                (SELECT COUNT(*) FROM deduplicated_papers WHERE project_id = %s),
                (SELECT COUNT(*) FROM deduplication_decisions
                 WHERE project_id = %s AND review_status = 'pending'),
                (SELECT COUNT(DISTINCT pc.paper_id)
                 FROM paper_chunks pc
                 JOIN deduplicated_papers p ON p.id = pc.paper_id
                 WHERE p.project_id = %s AND pc.chunk_type LIKE 'full_text_part_%%'),
                (SELECT COUNT(*)
                 FROM extracted_evidence e
                 JOIN deduplicated_papers p ON p.id = e.paper_id
                 WHERE p.project_id = %s),
                (SELECT COUNT(*)
                 FROM extracted_evidence e
                 JOIN deduplicated_papers p ON p.id = e.paper_id
                 WHERE p.project_id = %s
                   AND e.human_review_status IN ('approved', 'corrected')
                   AND e.schema_version = 'traceable-v1'
                   AND EXISTS (
                       SELECT 1 FROM evidence_field_sources efs
                       WHERE efs.extraction_id = e.id
                         AND efs.quote_validated = TRUE
                   ))
            """,
            (project_id,) * 6,
        )
        (
            records_identified,
            records_after_deduplication,
            deduplication_pending,
            reports_assessed,
            evidence_extracted,
            studies_included_synthesis,
        ) = [int(value) for value in cursor.fetchone()]

        cursor.execute(
            """
            SELECT s.human_decision, s.exclusion_reason_code,
                   latest.action, latest.reason_code, COUNT(*)
            FROM screening_decisions s
            JOIN deduplicated_papers p ON p.id = s.paper_id
            LEFT JOIN LATERAL (
                SELECT sr.action, sr.reason_code
                FROM screening_reassessments sr
                WHERE sr.project_id = p.project_id
                  AND sr.paper_id = p.id
                ORDER BY sr.created_at DESC, sr.id DESC
                LIMIT 1
            ) latest ON TRUE
            WHERE p.project_id = %s
            GROUP BY s.human_decision, s.exclusion_reason_code,
                     latest.action, latest.reason_code
            """,
            (project_id,),
        )
        screening_rows = cursor.fetchall()

        cursor.execute(
            """
            SELECT
                (SELECT COUNT(DISTINCT sought.paper_id)
                 FROM (
                     SELECT s.paper_id
                     FROM screening_decisions s
                     JOIN deduplicated_papers p ON p.id = s.paper_id
                     WHERE p.project_id = %s AND s.human_decision = 'Incluir'
                     UNION
                     SELECT sr.paper_id
                     FROM screening_reassessments sr
                     WHERE sr.project_id = %s
                 ) sought),
                (SELECT COUNT(*)
                 FROM screening_decisions s
                 JOIN deduplicated_papers p ON p.id = s.paper_id
                 WHERE p.project_id = %s
                   AND s.human_decision = 'Incluir'
                   AND NOT EXISTS (
                       SELECT 1 FROM paper_chunks pc
                       WHERE pc.paper_id = p.id
                         AND pc.chunk_type LIKE 'full_text_part_%%'
                   ))
            """,
            (project_id, project_id, project_id),
        )
        reports_sought, reports_awaiting_pdf = [int(value) for value in cursor.fetchone()]

    screened_by_ai = sum(int(row[4]) for row in screening_rows)
    included = excluded = uncertain = 0
    screening_excluded = reports_not_retrieved = full_text_excluded = 0
    returned_to_screening = 0
    screening_reasons = {}
    full_text_reasons = {}

    for decision, decision_reason, latest_action, latest_reason, raw_count in screening_rows:
        count = int(raw_count)
        if latest_action == "return_to_screening" and decision in (None, "Talvez"):
            returned_to_screening += count
        if decision == "Incluir":
            included += count
        elif decision == "Talvez":
            uncertain += count
        elif decision == "Excluir":
            excluded += count
            if latest_action == "exclude":
                reason = latest_reason or decision_reason or "other"
                full_text_reasons[reason] = full_text_reasons.get(reason, 0) + count
                if reason in FULL_TEXT_NOT_RETRIEVED_REASONS:
                    reports_not_retrieved += count
                else:
                    full_text_excluded += count
            else:
                reason = decision_reason or "other"
                screening_reasons[reason] = screening_reasons.get(reason, 0) + count
                screening_excluded += count

    screening_completed = included + excluded
    screening_pending = max(
        records_after_deduplication - screening_completed - uncertain,
        0,
    )
    duplicates_removed = max(
        records_identified - records_after_deduplication - deduplication_pending,
        0,
    )
    metrics = {
        "records_identified": records_identified,
        "duplicates_removed": duplicates_removed,
        "deduplication_pending": deduplication_pending,
        "records_after_deduplication": records_after_deduplication,
        "screened_by_ai": screened_by_ai,
        "screening_completed": screening_completed,
        "screening_uncertain": uncertain,
        "screening_pending": screening_pending,
        "screening_excluded": screening_excluded,
        "reports_sought": reports_sought,
        "reports_not_retrieved": reports_not_retrieved,
        "returned_to_screening": returned_to_screening,
        "reports_awaiting_pdf": reports_awaiting_pdf,
        "reports_assessed": reports_assessed,
        "full_text_excluded": full_text_excluded,
        "studies_selected": included,
        "evidence_extracted": evidence_extracted,
        "studies_included_synthesis": studies_included_synthesis,
    }

    interpretations = [
        (
            f"Foram identificados {records_identified} registros em "
            f"{len(source_counts)} fonte(s), resultando em "
            f"{records_after_deduplication} artigos únicos."
        ),
        (
            f"A triagem possui {screening_completed} decisões definitivas, "
            f"{uncertain} caso(s) como talvez e {screening_pending} sem decisão humana."
        ),
        (
            f"Dos {reports_sought} textos integrais procurados, {reports_assessed} "
            f"já foram indexados, {reports_not_retrieved} não foram obtidos e "
            f"{reports_awaiting_pdf} ainda aguardam PDF ou indexação."
        ),
        (
            f"A síntese final contém {studies_included_synthesis} estudo(s) com "
            "evidências aprovadas ou corrigidas e fontes literais validadas."
        ),
    ]
    warnings = []
    if deduplication_pending:
        warnings.append("Há casos de deduplicação pendentes de revisão humana.")
    if screening_pending or uncertain:
        warnings.append("A triagem ainda não está concluída.")
    if screening_reasons.get("other"):
        warnings.append(
            "Há exclusões classificadas como 'Outro'; revise as justificativas para maior precisão."
        )
    if reports_awaiting_pdf:
        warnings.append("Há artigos selecionados sem texto integral indexado.")

    return {
        "schema_version": "prisma-operational-v1",
        "project_id": project_id,
        "project_title": project_title,
        "protocol_version": int(protocol_version),
        "calculated_at": datetime.now().astimezone().isoformat(),
        "metrics": metrics,
        "source_counts": source_counts,
        "exclusion_reasons": {
            "screening": screening_reasons,
            "full_text": full_text_reasons,
        },
        "interpretation": {
            "statements": interpretations,
            "warnings": warnings,
            "definitions": {
                "records_identified": "Todos os registros brutos persistidos após coleta ou importação.",
                "reports_assessed": "Artigos com ao menos um chunk de texto integral indexado.",
                "studies_included_synthesis": (
                    "Extrações aprovadas ou corrigidas por humano, com fonte literal validada."
                ),
            },
        },
    }


def salvar_snapshot_prisma(project_id, connection_factory=None):
    """Registra uma versão imutável do fluxo, vinculada à versão do protocolo."""
    snapshot = calcular_fluxo_prisma(project_id, connection_factory=connection_factory)
    if connection_factory is None:
        from backend.app.database import get_connection

        connection_factory = get_connection

    with connection_factory() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT protocol_version FROM review_projects WHERE id = %s FOR UPDATE",
            (snapshot["project_id"],),
        )
        project = cursor.fetchone()
        if not project:
            raise ValueError("Projeto não encontrado ao salvar o snapshot PRISMA.")
        cursor.execute(
            """
            SELECT COALESCE(MAX(snapshot_version), 0) + 1
            FROM prisma_flow_snapshots
            WHERE project_id = %s
            """,
            (snapshot["project_id"],),
        )
        version = int(cursor.fetchone()[0])
        cursor.execute(
            """
            INSERT INTO prisma_flow_snapshots
                (project_id, snapshot_version, protocol_version, metrics_jsonb,
                 source_counts_jsonb, exclusion_reasons_jsonb, interpretation_jsonb)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id, created_at
            """,
            (
                snapshot["project_id"],
                version,
                int(project[0]),
                Json(snapshot["metrics"]),
                Json(snapshot["source_counts"]),
                Json(snapshot["exclusion_reasons"]),
                Json(snapshot["interpretation"]),
            ),
        )
        snapshot_id, created_at = cursor.fetchone()

    snapshot.update(
        {
            "id": str(snapshot_id),
            "snapshot_version": version,
            "protocol_version": int(project[0]),
            "created_at": created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at),
        }
    )
    return snapshot


def carregar_ultimo_snapshot_prisma(project_id, connection_factory=None):
    """Carrega o último retrato versionado do projeto, quando existir."""
    if connection_factory is None:
        from backend.app.database import get_connection

        connection_factory = get_connection
    with connection_factory() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT ps.id, ps.snapshot_version, ps.protocol_version,
                   ps.metrics_jsonb, ps.source_counts_jsonb,
                   ps.exclusion_reasons_jsonb, ps.interpretation_jsonb,
                   ps.created_at, p.title
            FROM prisma_flow_snapshots ps
            JOIN review_projects p ON p.id = ps.project_id
            WHERE ps.project_id = %s
            ORDER BY ps.snapshot_version DESC
            LIMIT 1
            """,
            (str(project_id),),
        )
        row = cursor.fetchone()
    if not row:
        return None
    return {
        "schema_version": "prisma-operational-v1",
        "id": str(row[0]),
        "project_id": str(project_id),
        "project_title": row[8],
        "snapshot_version": int(row[1]),
        "protocol_version": int(row[2]),
        "metrics": row[3],
        "source_counts": row[4],
        "exclusion_reasons": row[5],
        "interpretation": row[6],
        "created_at": row[7].isoformat() if hasattr(row[7], "isoformat") else str(row[7]),
    }


def prisma_para_json(snapshot):
    return json.dumps(snapshot, ensure_ascii=False, indent=2, default=_json_default)


def prisma_para_csv(snapshot):
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter=";")
    writer.writerow(["seção", "código", "descrição", "quantidade"])
    for code, value in snapshot["metrics"].items():
        writer.writerow(["fluxo", code, METRIC_LABELS.get(code, code), value])
    for source, value in snapshot.get("source_counts", {}).items():
        writer.writerow(["fonte", source, f"Registros da fonte {source}", value])
    for stage, reasons in snapshot.get("exclusion_reasons", {}).items():
        for code, value in reasons.items():
            writer.writerow(
                [f"exclusão_{stage}", code, EXCLUSION_REASON_LABELS.get(code, code), value]
            )
    return "\ufeff" + output.getvalue()


def gerar_prisma_svg(snapshot):
    """Gera um diagrama vetorial independente de bibliotecas de renderização."""
    metrics = snapshot["metrics"]
    source_summary = ", ".join(
        f"{source}: {count}" for source, count in snapshot.get("source_counts", {}).items()
    ) or "nenhuma fonte registrada"

    def reason_summary(stage, include_codes=None, exclude_codes=None):
        reasons = snapshot.get("exclusion_reasons", {}).get(stage, {})
        if include_codes is not None:
            reasons = {code: count for code, count in reasons.items() if code in include_codes}
        if exclude_codes is not None:
            reasons = {code: count for code, count in reasons.items() if code not in exclude_codes}
        if not reasons:
            return "Nenhum motivo registrado"
        return "; ".join(
            f"{EXCLUSION_REASON_LABELS.get(code, code)}: {count}"
            for code, count in sorted(reasons.items(), key=lambda item: (-item[1], item[0]))
        )

    boxes = [
        ("Identificação", f"Registros identificados (n = {metrics['records_identified']})", source_summary),
        ("Deduplicação", f"Registros únicos (n = {metrics['records_after_deduplication']})", f"Duplicatas removidas: {metrics['duplicates_removed']} | Pendências: {metrics['deduplication_pending']}"),
        ("Triagem", f"Decisões humanas definitivas (n = {metrics['screening_completed']})", f"Sem decisão: {metrics['screening_pending']} | Talvez: {metrics['screening_uncertain']}"),
        ("Elegibilidade", f"Textos integrais procurados (n = {metrics['reports_sought']})", f"Não obtidos: {metrics['reports_not_retrieved']} | Pendentes: {metrics['reports_awaiting_pdf']}"),
        ("Texto integral", f"PDFs indexados e avaliáveis (n = {metrics['reports_assessed']})", f"Excluídos após busca do texto: {metrics['full_text_excluded']}"),
        ("Extração", f"Artigos com evidência extraída (n = {metrics['evidence_extracted']})", f"Artigos atualmente selecionados: {metrics['studies_selected']}"),
        ("Síntese", f"Estudos incluídos na síntese (n = {metrics['studies_included_synthesis']})", "Evidência revisada por humano e fonte literal validada"),
    ]
    side_boxes = {
        2: (f"Excluídos na triagem (n = {metrics['screening_excluded']})", reason_summary("screening")),
        3: (
            f"Textos não obtidos (n = {metrics['reports_not_retrieved']})",
            reason_summary("full_text", include_codes=FULL_TEXT_NOT_RETRIEVED_REASONS),
        ),
        4: (
            f"Excluídos após texto integral (n = {metrics['full_text_excluded']})",
            reason_summary("full_text", exclude_codes=FULL_TEXT_NOT_RETRIEVED_REASONS),
        ),
    }
    # Mantém todo o fluxo compacto e reserva 60 px após a última caixa. Essa
    # folga protege a borda inferior mesmo quando o componente aplica escala.
    width, height = 1200, 1110
    main_x, main_w, box_h, gap = 85, 680, 120, 22
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#f7f9fc"/>',
        '<style>text{font-family:Arial,sans-serif;fill:#18324a}.stage{font-size:15px;font-weight:700;fill:#176b87}.title{font-size:21px;font-weight:700}.detail{font-size:15px}.side-title{font-size:17px;font-weight:700;fill:#8a2d2d}.side-detail{font-size:14px}</style>',
        '<text x="600" y="34" text-anchor="middle" class="title">Fluxo PRISMA rastreável</text>',
        f'<text x="600" y="60" text-anchor="middle" class="detail">{html.escape(str(snapshot.get("project_title", "Projeto")))}</text>',
    ]

    def add_lines(text, x, start_y, css_class, width_chars, max_lines=3):
        for index, line in enumerate(textwrap.wrap(str(text), width=width_chars)[:max_lines]):
            parts.append(
                f'<text x="{x}" y="{start_y + index * 19}" text-anchor="middle" class="{css_class}">{html.escape(line)}</text>'
            )

    for index, (stage, title, detail) in enumerate(boxes):
        y = 78 + index * (box_h + gap)
        parts.append(
            f'<rect x="{main_x}" y="{y}" width="{main_w}" height="{box_h}" rx="12" fill="#ffffff" stroke="#2f7693" stroke-width="2"/>'
        )
        parts.append(f'<text x="{main_x + 18}" y="{y + 24}" class="stage">{html.escape(stage.upper())}</text>')
        add_lines(title, main_x + main_w / 2, y + 58, "title", 58, 2)
        add_lines(detail, main_x + main_w / 2, y + 91, "detail", 76, 2)
        if index < len(boxes) - 1:
            arrow_x = main_x + main_w / 2
            parts.append(
                f'<line x1="{arrow_x}" y1="{y + box_h}" x2="{arrow_x}" y2="{y + box_h + gap - 7}" stroke="#2f7693" stroke-width="3"/>'
            )
            parts.append(
                f'<polygon points="{arrow_x - 7},{y + box_h + gap - 10} {arrow_x + 7},{y + box_h + gap - 10} {arrow_x},{y + box_h + gap}" fill="#2f7693"/>'
            )
        if index in side_boxes:
            side_title, side_detail = side_boxes[index]
            side_x, side_w = 830, 310
            parts.append(
                f'<line x1="{main_x + main_w}" y1="{y + box_h / 2}" x2="{side_x}" y2="{y + box_h / 2}" stroke="#a94b4b" stroke-width="2"/>'
            )
            parts.append(
                f'<rect x="{side_x}" y="{y}" width="{side_w}" height="{box_h}" rx="12" fill="#fff8f8" stroke="#a94b4b" stroke-width="2"/>'
            )
            add_lines(side_title, side_x + side_w / 2, y + 34, "side-title", 33, 2)
            add_lines(side_detail, side_x + side_w / 2, y + 70, "side-detail", 38, 3)

    parts.append("</svg>")
    return "".join(parts)
