"""Catálogo rastreável de tabelas e figuras detectadas em PDFs."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import fitz
from psycopg2.extras import Json, RealDictCursor

from backend.app.database import get_connection
from backend.app.storage_service import pdf_directory


ARTIFACT_TYPES = {"figure", "table"}
REVIEW_STATUSES = {"pending", "approved", "corrected", "rejected"}
CAPTION_PATTERN = re.compile(
    r"^\s*(fig(?:ure|ura)?\.?|table|tabela|quadro)\s*[\divxlcdm]+(?:\s*[:.\-–—]|\s)",
    re.IGNORECASE,
)
MAX_CONTEXT_CHARACTERS = 1800
MAX_TABLE_ROWS = 50
MAX_TABLE_COLUMNS = 20
MAX_CELL_CHARACTERS = 500


def _sanitize(value, maximum=None):
    text = str(value or "").replace("\x00", "").strip()
    return text[:maximum] if maximum else text


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _bbox(value):
    if value is None:
        return None
    values = [round(float(item), 2) for item in value]
    if len(values) != 4 or values[2] <= values[0] or values[3] <= values[1]:
        return None
    return values


def _area(box):
    return max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])


def _intersection_ratio(first, second):
    left = max(first[0], second[0])
    top = max(first[1], second[1])
    right = min(first[2], second[2])
    bottom = min(first[3], second[3])
    intersection = max(0.0, right - left) * max(0.0, bottom - top)
    minimum = min(_area(first), _area(second))
    return intersection / minimum if minimum else 0.0


def _caption_kind(text):
    match = CAPTION_PATTERN.match(text or "")
    if not match:
        return None
    prefix = match.group(1).lower()
    return "table" if prefix in {"table", "tabela", "quadro"} else "figure"


def _caption_for(box, captions, artifact_type):
    candidates = []
    center_x = (box[0] + box[2]) / 2
    for caption in captions:
        if caption["artifact_type"] != artifact_type:
            continue
        caption_box = caption["bbox"]
        caption_center = (caption_box[0] + caption_box[2]) / 2
        horizontal = abs(center_x - caption_center)
        vertical = min(abs(caption_box[1] - box[3]), abs(box[1] - caption_box[3]))
        if vertical <= 160 and horizontal <= max(220, box[2] - box[0]):
            candidates.append((vertical + horizontal * 0.15, caption))
    return min(candidates, default=(None, None), key=lambda item: item[0])[1]


def _context(page_text, caption):
    text = _sanitize(page_text)
    if not text:
        return None
    needle = _sanitize(caption)
    if needle:
        position = text.lower().find(needle.lower()[:120])
        if position >= 0:
            start = max(0, position - 500)
            end = min(len(text), position + len(needle) + 900)
            return text[start:end].strip()
    return text[:MAX_CONTEXT_CHARACTERS]


def _table_content(table):
    try:
        rows = table.extract() or []
    except Exception:
        return None
    normalized = []
    for row in rows[:MAX_TABLE_ROWS]:
        normalized.append(
            [_sanitize(cell, MAX_CELL_CHARACTERS) for cell in list(row or [])[:MAX_TABLE_COLUMNS]]
        )
    if not normalized:
        return None
    return {
        "rows": normalized,
        "row_count_detected": len(rows),
        "row_count_preserved": len(normalized),
        "column_limit": MAX_TABLE_COLUMNS,
    }


def _detection_key(file_hash, page_number, artifact_type, box, caption, method):
    payload = json.dumps(
        {
            "file": file_hash,
            "page": page_number,
            "type": artifact_type,
            "bbox": box,
            "caption": _sanitize(caption).casefold(),
            "method": method,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def detect_visual_artifacts(path) -> dict:
    """Detecta candidatos sem IA e sem atribuir significado científico."""
    pdf_path = Path(path).resolve()
    file_hash = _file_sha256(pdf_path)
    artifacts = []
    warnings = []

    with fitz.open(pdf_path) as document:
        total_pages = len(document)
        for page_number, page in enumerate(document, start=1):
            page_box = _bbox(page.rect)
            page_area = _area(page_box)
            page_text = _sanitize(page.get_text("text"))
            text_blocks = []
            for block in page.get_text("blocks") or []:
                if len(block) < 7 or int(block[6]) != 0:
                    continue
                text = _sanitize(block[4], 1200)
                box = _bbox(block[:4])
                if text and box:
                    text_blocks.append({"text": text, "bbox": box})
            captions = []
            for block in text_blocks:
                kind = _caption_kind(block["text"])
                if kind:
                    captions.append({**block, "artifact_type": kind})

            page_candidates = []
            try:
                table_finder = page.find_tables()
                for table in getattr(table_finder, "tables", []) or []:
                    box = _bbox(table.bbox)
                    if not box or _area(box) / page_area < 0.01:
                        continue
                    caption = _caption_for(box, captions, "table")
                    page_candidates.append(
                        {
                            "artifact_type": "table",
                            "bbox": box,
                            "caption": caption["text"] if caption else None,
                            "detection_method": "table_structure",
                            "extracted_content": _table_content(table),
                        }
                    )
            except Exception as error:
                warnings.append(
                    {
                        "page_number": page_number,
                        "stage": "table_detection",
                        "message": _sanitize(error, 300) or error.__class__.__name__,
                    }
                )

            try:
                dictionary = page.get_text("dict") or {}
                for block in dictionary.get("blocks", []):
                    if int(block.get("type", 0)) != 1:
                        continue
                    box = _bbox(block.get("bbox"))
                    if not box:
                        continue
                    ratio = _area(box) / page_area
                    width = box[2] - box[0]
                    height = box[3] - box[1]
                    if ratio < 0.02 or ratio > 0.85 or width < 72 or height < 72:
                        continue
                    caption = _caption_for(box, captions, "figure")
                    page_candidates.append(
                        {
                            "artifact_type": "figure",
                            "bbox": box,
                            "caption": caption["text"] if caption else None,
                            "detection_method": "embedded_image",
                            "extracted_content": None,
                        }
                    )
            except Exception as error:
                warnings.append(
                    {
                        "page_number": page_number,
                        "stage": "image_detection",
                        "message": _sanitize(error, 300) or error.__class__.__name__,
                    }
                )

            for caption in captions:
                if any(
                    candidate["artifact_type"] == caption["artifact_type"]
                    and candidate.get("caption") == caption["text"]
                    for candidate in page_candidates
                ):
                    continue
                page_candidates.append(
                    {
                        "artifact_type": caption["artifact_type"],
                        "bbox": None,
                        "caption": caption["text"],
                        "detection_method": "caption_only",
                        "extracted_content": None,
                    }
                )

            deduplicated = []
            for candidate in page_candidates:
                duplicate = False
                for current in deduplicated:
                    if candidate["artifact_type"] != current["artifact_type"]:
                        continue
                    if candidate["bbox"] and current["bbox"]:
                        duplicate = _intersection_ratio(candidate["bbox"], current["bbox"]) >= 0.8
                    elif candidate.get("caption") and current.get("caption"):
                        duplicate = candidate["caption"].casefold() == current["caption"].casefold()
                    if duplicate:
                        if not current.get("caption") and candidate.get("caption"):
                            current["caption"] = candidate["caption"]
                        break
                if not duplicate:
                    deduplicated.append(candidate)

            counters = {"figure": 0, "table": 0}
            for candidate in sorted(
                deduplicated,
                key=lambda item: (
                    item["artifact_type"],
                    (item.get("bbox") or [0, 0, 0, 0])[1],
                ),
            ):
                artifact_type = candidate["artifact_type"]
                counters[artifact_type] += 1
                box = candidate.get("bbox")
                caption = candidate.get("caption")
                method = candidate["detection_method"]
                artifacts.append(
                    {
                        "detection_key": _detection_key(
                            file_hash, page_number, artifact_type, box, caption, method
                        ),
                        "file_sha256": file_hash,
                        "page_number": page_number,
                        "artifact_type": artifact_type,
                        "artifact_order": counters[artifact_type],
                        "caption": caption,
                        "context_text": _context(page_text, caption),
                        "bbox": box,
                        "detection_method": method,
                        "detection_metadata": {
                            "detector": "pymupdf-rules-v1",
                            "page_width": page_box[2] - page_box[0],
                            "page_height": page_box[3] - page_box[1],
                            "semantic_interpretation": False,
                        },
                        "extracted_content": candidate.get("extracted_content"),
                    }
                )

    return {
        "file_sha256": file_hash,
        "total_pages": total_pages,
        "artifacts": artifacts,
        "warnings": warnings,
    }


def catalog_project_visuals(project_id, progress_callback=None) -> dict:
    """Cataloga PDFs incluídos e preserva revisões de detecções ainda idênticas."""
    project_id = str(project_id)
    root = pdf_directory()
    summary = {
        "papers_eligible": 0,
        "pdfs_found": 0,
        "papers_processed": 0,
        "papers_failed": 0,
        "artifacts_current": 0,
        "figures": 0,
        "tables": 0,
        "warnings": 0,
    }
    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT p.id, p.title
            FROM deduplicated_papers p
            WHERE p.project_id = %s
              AND EXISTS (
                  SELECT 1 FROM screening_decisions s
                  WHERE s.paper_id = p.id AND s.human_decision = 'Incluir'
              )
            ORDER BY p.title, p.id
            """,
            (project_id,),
        )
        papers = cursor.fetchall()
    summary["papers_eligible"] = len(papers)

    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE visual_artifacts a
            SET is_current = FALSE, updated_at = CURRENT_TIMESTAMP
            WHERE a.project_id = %s
              AND a.is_current = TRUE
              AND NOT EXISTS (
                  SELECT 1
                  FROM screening_decisions s
                  WHERE s.paper_id = a.paper_id AND s.human_decision = 'Incluir'
              )
            """,
            (project_id,),
        )

    for index, (paper_id, title) in enumerate(papers, start=1):
        path = root / f"{paper_id}.pdf"
        if not path.is_file():
            with get_connection() as connection, connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE visual_artifacts
                    SET is_current = FALSE, updated_at = CURRENT_TIMESTAMP
                    WHERE project_id = %s AND paper_id = %s AND is_current = TRUE
                    """,
                    (project_id, paper_id),
                )
            continue
        summary["pdfs_found"] += 1
        if progress_callback:
            progress_callback(index - 1, len(papers), f"Catalogando PDF {index}/{len(papers)}")
        try:
            detected = detect_visual_artifacts(path)
            with get_connection() as connection, connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE visual_artifacts SET is_current = FALSE, updated_at = CURRENT_TIMESTAMP
                    WHERE project_id = %s AND paper_id = %s AND is_current = TRUE
                    """,
                    (project_id, paper_id),
                )
                for artifact in detected["artifacts"]:
                    cursor.execute(
                        """
                        INSERT INTO visual_artifacts
                            (project_id, paper_id, detection_key, file_sha256,
                             page_number, artifact_type, artifact_order, caption,
                             context_text, bbox_jsonb, detection_method,
                             detection_metadata_jsonb, extracted_content_jsonb)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (project_id, paper_id, detection_key) DO UPDATE
                        SET page_number = EXCLUDED.page_number,
                            artifact_order = EXCLUDED.artifact_order,
                            caption = CASE
                                WHEN visual_artifacts.review_status = 'corrected'
                                    THEN visual_artifacts.caption
                                ELSE EXCLUDED.caption
                            END,
                            context_text = EXCLUDED.context_text,
                            bbox_jsonb = EXCLUDED.bbox_jsonb,
                            detection_method = EXCLUDED.detection_method,
                            detection_metadata_jsonb = EXCLUDED.detection_metadata_jsonb,
                            extracted_content_jsonb = EXCLUDED.extracted_content_jsonb,
                            is_current = TRUE,
                            updated_at = CURRENT_TIMESTAMP
                        """,
                        (
                            project_id,
                            paper_id,
                            artifact["detection_key"],
                            artifact["file_sha256"],
                            artifact["page_number"],
                            artifact["artifact_type"],
                            artifact["artifact_order"],
                            artifact["caption"],
                            artifact["context_text"],
                            Json(artifact["bbox"]) if artifact["bbox"] else None,
                            artifact["detection_method"],
                            Json(artifact["detection_metadata"]),
                            Json(artifact["extracted_content"])
                            if artifact["extracted_content"] is not None
                            else None,
                        ),
                    )
            summary["papers_processed"] += 1
            summary["artifacts_current"] += len(detected["artifacts"])
            summary["figures"] += sum(
                item["artifact_type"] == "figure" for item in detected["artifacts"]
            )
            summary["tables"] += sum(
                item["artifact_type"] == "table" for item in detected["artifacts"]
            )
            summary["warnings"] += len(detected["warnings"])
        except Exception:
            summary["papers_failed"] += 1

    if progress_callback:
        progress_callback(len(papers), len(papers), "Catálogo visual atualizado")
    return summary


def list_visual_artifacts(project_id, *, current_only=True, review_status=None):
    params = [str(project_id)]
    filters = ["a.project_id = %s"]
    if current_only:
        filters.append("a.is_current = TRUE")
    if review_status:
        if review_status not in REVIEW_STATUSES:
            raise ValueError("Estado de revisão visual inválido.")
        filters.append("a.review_status = %s")
        params.append(review_status)
    with get_connection() as connection, connection.cursor(
        cursor_factory=RealDictCursor
    ) as cursor:
        cursor.execute(
            f"""
            SELECT a.*, p.title AS paper_title
            FROM visual_artifacts a
            JOIN deduplicated_papers p ON p.id = a.paper_id
            WHERE {' AND '.join(filters)}
            ORDER BY p.title, a.page_number, a.artifact_type, a.artifact_order
            """,
            params,
        )
        return [dict(row) for row in cursor.fetchall()]


def summarize_visual_artifacts(artifacts) -> dict:
    values = list(artifacts)
    return {
        "total": len(values),
        "figures": sum(item.get("artifact_type") == "figure" for item in values),
        "tables": sum(item.get("artifact_type") == "table" for item in values),
        "pending": sum(item.get("review_status") == "pending" for item in values),
        "reviewed": sum(item.get("review_status") in {"approved", "corrected", "rejected"} for item in values),
    }


def _review_snapshot(row):
    return {
        "artifact_type": row.get("artifact_type"),
        "caption": row.get("caption"),
        "review_status": row.get("review_status"),
        "human_description": row.get("human_description"),
        "human_notes": row.get("human_notes"),
        "reviewer_name": row.get("reviewer_name"),
    }


def review_visual_artifact(
    project_id,
    artifact_id,
    action,
    reviewer_name,
    *,
    artifact_type=None,
    caption=None,
    human_description=None,
    human_notes=None,
):
    if action not in {"approved", "corrected", "rejected"}:
        raise ValueError("Decisão de revisão visual inválida.")
    reviewer = _sanitize(reviewer_name, 200)
    description = _sanitize(human_description)
    notes = _sanitize(human_notes)
    if len(reviewer) < 2:
        raise ValueError("Informe o nome do responsável pela revisão.")
    if action in {"approved", "corrected"} and len(description) < 10:
        raise ValueError("Descreva o conteúdo visual em pelo menos 10 caracteres.")
    if action == "rejected" and len(notes) < 5:
        raise ValueError("Justifique a rejeição do candidato visual.")
    corrected_type = artifact_type if action == "corrected" else None
    if corrected_type and corrected_type not in ARTIFACT_TYPES:
        raise ValueError("Tipo visual corrigido inválido.")

    with get_connection() as connection, connection.cursor(
        cursor_factory=RealDictCursor
    ) as cursor:
        cursor.execute(
            """
            SELECT * FROM visual_artifacts
            WHERE id = %s AND project_id = %s AND is_current = TRUE
            FOR UPDATE
            """,
            (str(artifact_id), str(project_id)),
        )
        previous = cursor.fetchone()
        if not previous:
            raise ValueError("Candidato visual atual não encontrado no projeto.")
        final_type = corrected_type or previous["artifact_type"]
        final_caption = _sanitize(caption) if action == "corrected" else previous["caption"]
        cursor.execute(
            """
            UPDATE visual_artifacts
            SET artifact_type = %s, caption = %s, review_status = %s,
                human_description = %s, human_notes = %s, reviewer_name = %s,
                reviewed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            RETURNING *
            """,
            (
                final_type,
                final_caption,
                action,
                description or None,
                notes or None,
                reviewer,
                str(artifact_id),
            ),
        )
        current = cursor.fetchone()
        # Qualquer nova decisão sobre o candidato invalida interpretações anteriores.
        # Uma nova chamada multimodal deverá refletir a descrição humana atual.
        cursor.execute(
            """
            UPDATE visual_interpretations
            SET is_current = FALSE, updated_at = CURRENT_TIMESTAMP
            WHERE project_id = %s AND artifact_id = %s AND is_current = TRUE
            """,
            (str(project_id), str(artifact_id)),
        )
        cursor.execute(
            """
            INSERT INTO visual_artifact_review_events
                (project_id, artifact_id, action, previous_jsonb,
                 current_jsonb, reviewer_name)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                str(project_id),
                str(artifact_id),
                action,
                Json(_review_snapshot(previous)),
                Json(_review_snapshot(current)),
                reviewer,
            ),
        )
        return dict(current)


def render_visual_artifact_preview(project_id, artifact_id, dpi=130) -> bytes:
    """Renderiza somente a página/região registrada, sem persistir cópias do PDF."""
    dpi = max(72, min(int(dpi), 180))
    with get_connection() as connection, connection.cursor(
        cursor_factory=RealDictCursor
    ) as cursor:
        cursor.execute(
            """
            SELECT paper_id, page_number, bbox_jsonb
            FROM visual_artifacts
            WHERE id = %s AND project_id = %s AND is_current = TRUE
            """,
            (str(artifact_id), str(project_id)),
        )
        artifact = cursor.fetchone()
    if not artifact:
        raise ValueError("Candidato visual atual não encontrado no projeto.")
    path = pdf_directory() / f"{artifact['paper_id']}.pdf"
    if not path.is_file():
        raise FileNotFoundError("O PDF original não está disponível no armazenamento.")
    with fitz.open(path) as document:
        page_index = int(artifact["page_number"]) - 1
        if page_index < 0 or page_index >= len(document):
            raise ValueError("A página registrada não existe mais no PDF.")
        page = document[page_index]
        clip = page.rect
        if artifact.get("bbox_jsonb"):
            candidate = fitz.Rect(*artifact["bbox_jsonb"])
            candidate.x0 -= 8
            candidate.y0 -= 8
            candidate.x1 += 8
            candidate.y1 += 8
            intersection = candidate & page.rect
            if not intersection.is_empty:
                clip = intersection
        pixmap = page.get_pixmap(dpi=dpi, clip=clip, alpha=False)
        return pixmap.tobytes("png")
