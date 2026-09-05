"""Arquivamento reversível e exclusão permanente protegida de projetos."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from psycopg2.extras import Json, RealDictCursor

from backend.app.backup_service import BACKUP_EXTENSION, default_backup_directory
from backend.app.database import get_connection
from backend.app.demo_project import is_demo_project
from backend.app.storage_service import pdf_directory


ACTIVE_JOB_STATUSES = ("queued", "running", "retry_wait")
ARCHIVE_REASON_MIN_LENGTH = 10


def _row_to_dict(row):
    if not row:
        return None
    result = dict(row)
    if result.get("id") is not None:
        result["id"] = str(result["id"])
    return result


def _safe_actor(actor):
    value = str(actor or "operador não informado").strip()
    return value[:200] or "operador não informado"


def _load_project(cursor, project_id, *, lock=False):
    cursor.execute(
        f"""
        SELECT id, title, question, criteria_jsonb, status, protocol_version,
               archived_at, archived_reason, created_at, updated_at
        FROM review_projects
        WHERE id = %s
        {"FOR UPDATE" if lock else ""}
        """,
        (str(project_id),),
    )
    project = _row_to_dict(cursor.fetchone())
    if not project:
        raise ValueError("Projeto não encontrado.")
    return project


def _load_counts(cursor, project_id):
    cursor.execute(
        """
        SELECT
            (SELECT COUNT(*) FROM search_queries WHERE project_id = %s) AS searches,
            (SELECT COUNT(*) FROM retrieved_records WHERE project_id = %s) AS records,
            (SELECT COUNT(*) FROM deduplicated_papers WHERE project_id = %s) AS papers,
            (SELECT COUNT(*) FROM agent_interactions WHERE project_id = %s) AS interactions,
            (SELECT COUNT(*) FROM evaluation_runs WHERE project_id = %s) AS evaluations,
            (SELECT COUNT(*) FROM background_jobs WHERE project_id = %s) AS jobs,
            (SELECT COUNT(*) FROM background_jobs
             WHERE project_id = %s AND status IN ('queued', 'running', 'retry_wait')) AS active_jobs,
            (SELECT COUNT(*) FROM visual_artifacts WHERE project_id = %s) AS visual_artifacts,
            (SELECT COUNT(*) FROM visual_interpretations WHERE project_id = %s) AS visual_interpretations
        """,
        (str(project_id),) * 9,
    )
    row = cursor.fetchone()
    return {key: int(value or 0) for key, value in dict(row).items()}


def _paper_ids(cursor, project_id):
    cursor.execute(
        "SELECT id FROM deduplicated_papers WHERE project_id = %s ORDER BY id",
        (str(project_id),),
    )
    return [str(row[0] if not isinstance(row, dict) else row["id"]) for row in cursor.fetchall()]


def _latest_backup(directory: Path):
    if not directory.is_dir():
        return None
    candidates = [
        item
        for item in directory.glob(f"*{BACKUP_EXTENSION}")
        if item.is_file() and not item.is_symlink()
    ]
    if not candidates:
        return None
    latest = max(candidates, key=lambda item: item.stat().st_mtime)
    return {
        "filename": latest.name,
        "created_at": datetime.fromtimestamp(latest.stat().st_mtime, tz=timezone.utc),
        "size_bytes": latest.stat().st_size,
    }


def list_projects_for_lifecycle(*, connection_factory=None):
    factory = connection_factory or get_connection
    with factory() as connection, connection.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """
            SELECT id, title, question, criteria_jsonb, status, protocol_version,
                   archived_at, archived_reason, created_at, updated_at
            FROM review_projects
            ORDER BY archived_at NULLS FIRST, updated_at DESC, created_at DESC
            """
        )
        return [_row_to_dict(row) for row in cursor.fetchall()]


def deletion_preview(
    project_id,
    *,
    connection_factory=None,
    pdf_root: Path | None = None,
    backup_root: Path | None = None,
):
    factory = connection_factory or get_connection
    with factory() as connection, connection.cursor(cursor_factory=RealDictCursor) as cursor:
        project = _load_project(cursor, project_id)
        counts = _load_counts(cursor, project_id)
        paper_ids = _paper_ids(cursor, project_id)

    root = Path(pdf_root or pdf_directory()).resolve()
    pdf_paths = []
    pdf_bytes = 0
    for paper_id in paper_ids:
        candidate = (root / f"{paper_id}.pdf").resolve()
        if candidate.parent != root:
            raise RuntimeError("Foi identificado um caminho de PDF fora do armazenamento seguro.")
        if candidate.is_file() and not candidate.is_symlink():
            pdf_paths.append(candidate)
            pdf_bytes += candidate.stat().st_size

    latest_backup = _latest_backup(Path(backup_root or default_backup_directory()).resolve())
    archived_at = project.get("archived_at")
    backup_after_archive = bool(
        archived_at
        and latest_backup
        and latest_backup["created_at"] >= archived_at.astimezone(timezone.utc)
    )
    protected_reason = None
    if is_demo_project(project):
        protected_reason = "O projeto demonstrativo é protegido e pode ser restaurado pela carga oficial."

    return {
        "project": project,
        "counts": counts,
        "pdf_count": len(pdf_paths),
        "pdf_bytes": pdf_bytes,
        "latest_backup": latest_backup,
        "backup_after_archive": backup_after_archive,
        "protected_reason": protected_reason,
    }


def archive_project(project_id, reason, *, actor=None, connection_factory=None):
    reason = str(reason or "").strip()
    if len(reason) < ARCHIVE_REASON_MIN_LENGTH:
        raise ValueError(
            f"Informe uma justificativa com pelo menos {ARCHIVE_REASON_MIN_LENGTH} caracteres."
        )
    factory = connection_factory or get_connection
    with factory() as connection, connection.cursor(cursor_factory=RealDictCursor) as cursor:
        project = _load_project(cursor, project_id, lock=True)
        if project.get("archived_at"):
            raise ValueError("Este projeto já está arquivado.")
        if is_demo_project(project):
            raise ValueError("O projeto demonstrativo é protegido e não pode ser arquivado.")
        counts = _load_counts(cursor, project_id)
        if counts["active_jobs"]:
            raise ValueError(
                "Aguarde a conclusão ou falha das tarefas em andamento antes de arquivar."
            )
        cursor.execute(
            "SELECT COUNT(*) AS active_projects FROM review_projects WHERE archived_at IS NULL"
        )
        if int(cursor.fetchone()["active_projects"]) <= 1:
            raise ValueError("O último projeto ativo da instalação não pode ser arquivado.")
        cursor.execute(
            """
            UPDATE review_projects
            SET archived_at = CURRENT_TIMESTAMP, archived_reason = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            RETURNING archived_at
            """,
            (reason, str(project_id)),
        )
        archived_at = cursor.fetchone()["archived_at"]
        cursor.execute(
            """
            INSERT INTO project_lifecycle_events
                (target_project_id, project_title, action, actor_identifier, details_jsonb)
            VALUES (%s, %s, 'archived', %s, %s)
            RETURNING id, created_at
            """,
            (
                str(project_id),
                project["title"],
                _safe_actor(actor),
                Json({"reason": reason, "counts": counts}),
            ),
        )
        event = cursor.fetchone()
        event_id, created_at = event["id"], event["created_at"]
    return {
        "event_id": str(event_id),
        "project_id": str(project_id),
        "title": project["title"],
        "archived_at": archived_at,
        "created_at": created_at,
    }


def restore_project(project_id, *, actor=None, connection_factory=None):
    factory = connection_factory or get_connection
    with factory() as connection, connection.cursor(cursor_factory=RealDictCursor) as cursor:
        project = _load_project(cursor, project_id, lock=True)
        if not project.get("archived_at"):
            raise ValueError("Este projeto já está ativo.")
        cursor.execute(
            """
            UPDATE review_projects
            SET archived_at = NULL, archived_reason = NULL, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (str(project_id),),
        )
        cursor.execute(
            """
            INSERT INTO project_lifecycle_events
                (target_project_id, project_title, action, actor_identifier, details_jsonb)
            VALUES (%s, %s, 'restored', %s, %s)
            RETURNING id, created_at
            """,
            (
                str(project_id),
                project["title"],
                _safe_actor(actor),
                Json({"previous_archived_at": project["archived_at"].isoformat()}),
            ),
        )
        event = cursor.fetchone()
        event_id, created_at = event["id"], event["created_at"]
    return {
        "event_id": str(event_id),
        "project_id": str(project_id),
        "title": project["title"],
        "created_at": created_at,
    }


def _stage_project_pdfs(root: Path, paper_ids, event_id):
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    staging_parent = (root / ".project-deletion-staging").resolve()
    if staging_parent.parent != root:
        raise RuntimeError("Diretório temporário de exclusão inválido.")
    staging = (staging_parent / str(event_id)).resolve()
    if staging.parent != staging_parent:
        raise RuntimeError("Diretório temporário de exclusão inválido.")
    staging.mkdir(parents=True, exist_ok=False)
    moved = []
    try:
        for paper_id in paper_ids:
            source = (root / f"{paper_id}.pdf").resolve()
            if source.parent != root:
                raise RuntimeError("Foi identificado um caminho de PDF fora do armazenamento seguro.")
            if not source.exists():
                continue
            if source.is_symlink() or not source.is_file():
                raise RuntimeError("Um PDF associado não é um arquivo regular seguro.")
            target = staging / source.name
            os.replace(source, target)
            moved.append((source, target))
        return staging, moved
    except Exception:
        for source, target in reversed(moved):
            if target.exists():
                os.replace(target, source)
        if staging.exists() and not any(staging.iterdir()):
            staging.rmdir()
        if staging_parent.exists() and not any(staging_parent.iterdir()):
            staging_parent.rmdir()
        raise


def _restore_staged_pdfs(staging, moved):
    for source, target in reversed(moved):
        if target.exists():
            os.replace(target, source)
    if staging.exists() and not any(staging.iterdir()):
        staging.rmdir()
    parent = staging.parent
    if parent.exists() and not any(parent.iterdir()):
        parent.rmdir()


def _purge_staged_pdfs(staging, moved):
    for _source, target in moved:
        if target.is_file() and not target.is_symlink():
            target.unlink()
    if staging.exists() and not any(staging.iterdir()):
        staging.rmdir()
    parent = staging.parent
    if parent.exists() and not any(parent.iterdir()):
        parent.rmdir()


def permanently_delete_project(
    project_id,
    typed_confirmation,
    *,
    backup_confirmed=False,
    actor=None,
    connection_factory=None,
    pdf_root: Path | None = None,
    backup_root: Path | None = None,
):
    """Exclui um projeto arquivado, preservando recibo sem FK e evitando PDFs órfãos."""
    factory = connection_factory or get_connection
    root = Path(pdf_root or pdf_directory()).resolve()
    backup_dir = Path(backup_root or default_backup_directory()).resolve()
    event_id = uuid.uuid4()
    staging = None
    moved = []
    connection = factory()
    try:
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            project = _load_project(cursor, project_id, lock=True)
            if not project.get("archived_at"):
                raise ValueError("Arquive o projeto antes de solicitar a exclusão permanente.")
            if is_demo_project(project):
                raise ValueError("O projeto demonstrativo é protegido e não pode ser excluído.")
            if str(typed_confirmation or "").strip() != project["title"]:
                raise ValueError("A confirmação digitada não corresponde ao título do projeto.")
            if not backup_confirmed:
                raise ValueError("Confirme que o backup de segurança foi validado.")
            counts = _load_counts(cursor, project_id)
            if counts["active_jobs"]:
                raise ValueError("Não é possível excluir um projeto com tarefas em andamento.")
            latest_backup = _latest_backup(backup_dir)
            if not latest_backup or latest_backup["created_at"] < project["archived_at"].astimezone(timezone.utc):
                raise ValueError(
                    "Crie um backup completo depois do arquivamento antes de excluir o projeto."
                )
            paper_ids = _paper_ids(cursor, project_id)
            staging, moved = _stage_project_pdfs(root, paper_ids, event_id)
            cursor.execute("DELETE FROM review_projects WHERE id = %s", (str(project_id),))
            if cursor.rowcount != 1:
                raise RuntimeError("O projeto não foi removido do banco de dados.")
            cursor.execute(
                """
                INSERT INTO project_lifecycle_events
                    (id, target_project_id, project_title, action, actor_identifier, details_jsonb)
                VALUES (%s, %s, %s, 'deleted', %s, %s)
                RETURNING created_at
                """,
                (
                    str(event_id),
                    str(project_id),
                    project["title"],
                    _safe_actor(actor),
                    Json(
                        {
                            "archived_at": project["archived_at"].isoformat(),
                            "archive_reason": project.get("archived_reason"),
                            "counts": counts,
                            "pdf_files_removed": len(moved),
                            "backup_filename": latest_backup["filename"],
                            "backup_created_at": latest_backup["created_at"].isoformat(),
                            "backup_validation_confirmed": True,
                        }
                    ),
                ),
            )
            created_at = cursor.fetchone()["created_at"]
        connection.commit()
    except Exception:
        connection.rollback()
        if staging is not None:
            _restore_staged_pdfs(staging, moved)
        raise
    finally:
        connection.close()

    cleanup_warning = None
    try:
        _purge_staged_pdfs(staging, moved)
    except OSError:
        cleanup_warning = (
            "O projeto foi excluído, mas alguns PDFs permaneceram na área temporária "
            "protegida e exigem limpeza operacional."
        )
    return {
        "event_id": str(event_id),
        "project_id": str(project_id),
        "title": project["title"],
        "created_at": created_at,
        "counts": counts,
        "pdf_files_removed": len(moved),
        "cleanup_warning": cleanup_warning,
    }


def list_lifecycle_events(limit=100, *, connection_factory=None):
    factory = connection_factory or get_connection
    safe_limit = max(1, min(int(limit), 500))
    with factory() as connection, connection.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """
            SELECT id, target_project_id, project_title, action,
                   actor_identifier, details_jsonb, created_at
            FROM project_lifecycle_events
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            (safe_limit,),
        )
        result = []
        for row in cursor.fetchall():
            item = dict(row)
            item["id"] = str(item["id"])
            item["target_project_id"] = str(item["target_project_id"])
            result.append(item)
        return result
