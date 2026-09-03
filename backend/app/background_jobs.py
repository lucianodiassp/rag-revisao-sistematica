"""Fila persistente para operações demoradas da revisão sistemática."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from psycopg2 import IntegrityError
from psycopg2.extras import Json, RealDictCursor

from backend.app.database import get_connection


JOB_BIBLIOGRAPHIC_SEARCH = "bibliographic_search"
JOB_PDF_INDEXING = "pdf_indexing"
JOB_EVIDENCE_EXTRACTION = "evidence_extraction"
JOB_FINAL_REPORT = "final_report"
JOB_RAG_BENCHMARK = "rag_benchmark"
JOB_VISUAL_CATALOGING = "visual_cataloging"

JOB_TYPES = {
    JOB_BIBLIOGRAPHIC_SEARCH,
    JOB_PDF_INDEXING,
    JOB_EVIDENCE_EXTRACTION,
    JOB_FINAL_REPORT,
    JOB_RAG_BENCHMARK,
    JOB_VISUAL_CATALOGING,
}
ACTIVE_STATUSES = {"queued", "running", "retry_wait"}


def _env_int(name, default, minimum, maximum):
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


def _json_safe(value):
    """Normaliza resultados de agentes para armazenamento em JSONB."""
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def _row_to_dict(row):
    if not row:
        return None
    result = dict(row)
    for key in ("id", "project_id"):
        if result.get(key) is not None:
            result[key] = str(result[key])
    return result


def _record_event(cursor, job_id, event_type, details=None):
    cursor.execute(
        """
        INSERT INTO background_job_events (job_id, event_type, details_jsonb)
        VALUES (%s, %s, %s)
        """,
        (job_id, event_type, Json(_json_safe(details or {}))),
    )


def enqueue_job(project_id, job_type, parameters=None, max_attempts=None):
    """Cria um trabalho ou devolve o trabalho ativo equivalente já existente."""
    if job_type not in JOB_TYPES:
        raise ValueError(f"Tipo de processamento inválido: {job_type}")
    if max_attempts is None:
        attempts = _env_int("RAG_JOB_MAX_ATTEMPTS", 3, 1, 10)
    else:
        attempts = max(1, min(int(max_attempts), 10))
    parameters = _json_safe(parameters or {})

    connection = get_connection()
    try:
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("SELECT 1 FROM review_projects WHERE id = %s", (project_id,))
            if not cursor.fetchone():
                raise ValueError("Projeto não encontrado para iniciar o processamento.")
            try:
                cursor.execute(
                    """
                    INSERT INTO background_jobs
                        (project_id, job_type, parameters_jsonb, max_attempts,
                         progress_message)
                    VALUES (%s, %s, %s, %s, 'Aguardando início')
                    RETURNING *
                    """,
                    (project_id, job_type, Json(parameters), attempts),
                )
                row = cursor.fetchone()
                _record_event(cursor, row["id"], "queued", {"parameters": parameters})
                connection.commit()
                return _row_to_dict(row), True
            except IntegrityError as error:
                connection.rollback()
                if getattr(error, "pgcode", None) != "23505":
                    raise
                with connection.cursor(cursor_factory=RealDictCursor) as active_cursor:
                    active_cursor.execute(
                        """
                        SELECT * FROM background_jobs
                        WHERE project_id = %s AND job_type = %s
                          AND status IN ('queued', 'running', 'retry_wait')
                        ORDER BY created_at DESC LIMIT 1
                        """,
                        (project_id, job_type),
                    )
                    return _row_to_dict(active_cursor.fetchone()), False
    finally:
        connection.close()


def get_job(job_id, project_id=None):
    with get_connection() as connection, connection.cursor(
        cursor_factory=RealDictCursor
    ) as cursor:
        query = "SELECT * FROM background_jobs WHERE id = %s"
        params = [job_id]
        if project_id is not None:
            query += " AND project_id = %s"
            params.append(project_id)
        cursor.execute(query, params)
        return _row_to_dict(cursor.fetchone())


def get_latest_job(project_id, job_type):
    with get_connection() as connection, connection.cursor(
        cursor_factory=RealDictCursor
    ) as cursor:
        cursor.execute(
            """
            SELECT * FROM background_jobs
            WHERE project_id = %s AND job_type = %s
            ORDER BY created_at DESC LIMIT 1
            """,
            (project_id, job_type),
        )
        return _row_to_dict(cursor.fetchone())


def get_latest_successful_job(project_id, job_type):
    with get_connection() as connection, connection.cursor(
        cursor_factory=RealDictCursor
    ) as cursor:
        cursor.execute(
            """
            SELECT * FROM background_jobs
            WHERE project_id = %s AND job_type = %s AND status = 'succeeded'
            ORDER BY finished_at DESC, created_at DESC LIMIT 1
            """,
            (project_id, job_type),
        )
        return _row_to_dict(cursor.fetchone())


def list_job_events(job_id):
    with get_connection() as connection, connection.cursor(
        cursor_factory=RealDictCursor
    ) as cursor:
        cursor.execute(
            """
            SELECT event_type, details_jsonb, created_at
            FROM background_job_events
            WHERE job_id = %s ORDER BY created_at, id
            """,
            (job_id,),
        )
        return [dict(row) for row in cursor.fetchall()]


def claim_next_job(worker_id):
    """Reserva atomicamente um trabalho disponível entre vários processos."""
    with get_connection() as connection, connection.cursor(
        cursor_factory=RealDictCursor
    ) as cursor:
        cursor.execute(
            """
            WITH candidate AS (
                SELECT id FROM background_jobs
                WHERE status IN ('queued', 'retry_wait')
                  AND available_at <= CURRENT_TIMESTAMP
                ORDER BY available_at, created_at
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            )
            UPDATE background_jobs AS job
            SET status = 'running',
                attempt_count = attempt_count + 1,
                worker_id = %s,
                heartbeat_at = CURRENT_TIMESTAMP,
                started_at = COALESCE(started_at, CURRENT_TIMESTAMP),
                finished_at = NULL,
                progress_message = 'Processamento iniciado',
                updated_at = CURRENT_TIMESTAMP
            FROM candidate
            WHERE job.id = candidate.id
            RETURNING job.*
            """,
            (worker_id,),
        )
        row = cursor.fetchone()
        if row:
            _record_event(
                cursor,
                row["id"],
                "started",
                {"attempt": row["attempt_count"], "worker_id": worker_id},
            )
        return _row_to_dict(row)


def heartbeat_job(job_id):
    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE background_jobs
            SET heartbeat_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s AND status = 'running'
            """,
            (job_id,),
        )


def update_job_progress(job_id, current, total, message):
    current = max(0, int(current or 0))
    total = max(0, int(total or 0))
    safe_message = str(message or "Processando")[:1000]
    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE background_jobs
            SET progress_current = %s,
                progress_total = %s,
                progress_message = %s,
                heartbeat_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s AND status = 'running'
            """,
            (current, total, safe_message, job_id),
        )
        if cursor.rowcount:
            _record_event(
                cursor,
                job_id,
                "progress",
                {"current": current, "total": total, "message": safe_message},
            )


def complete_job(job_id, result):
    result = _json_safe(result or {})
    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE background_jobs
            SET status = 'succeeded', result_jsonb = %s,
                progress_current = CASE
                    WHEN progress_total > 0 THEN progress_total ELSE progress_current
                END,
                progress_message = 'Processamento concluído',
                error_code = NULL, error_message = NULL,
                heartbeat_at = CURRENT_TIMESTAMP,
                finished_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s AND status = 'running'
            """,
            (Json(result), job_id),
        )
        if cursor.rowcount:
            _record_event(
                cursor,
                job_id,
                "succeeded",
                {"result_keys": sorted(result.keys()) if isinstance(result, dict) else []},
            )


def fail_job(job_id, error, *, retryable=False, error_code=None):
    """Registra a falha e agenda nova tentativa somente para erro transitório."""
    message = str(error or "Falha não identificada").replace("\x00", "")[:2000]
    base_delay = _env_int("RAG_JOB_RETRY_BASE_SECONDS", 15, 1, 300)
    with get_connection() as connection, connection.cursor(
        cursor_factory=RealDictCursor
    ) as cursor:
        cursor.execute(
            "SELECT attempt_count, max_attempts FROM background_jobs WHERE id = %s FOR UPDATE",
            (job_id,),
        )
        row = cursor.fetchone()
        if not row:
            return
        will_retry = retryable and row["attempt_count"] < row["max_attempts"]
        delay = min(base_delay * (2 ** max(row["attempt_count"] - 1, 0)), 300)
        if will_retry:
            cursor.execute(
                """
                UPDATE background_jobs
                SET status = 'retry_wait',
                    available_at = CURRENT_TIMESTAMP + (%s * INTERVAL '1 second'),
                    progress_message = %s, error_code = %s, error_message = %s,
                    heartbeat_at = NULL, worker_id = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (delay, f"Nova tentativa automática em {delay}s", error_code, message, job_id),
            )
            _record_event(
                cursor,
                job_id,
                "retry_scheduled",
                {"delay_seconds": delay, "error_code": error_code, "error": message},
            )
        else:
            cursor.execute(
                """
                UPDATE background_jobs
                SET status = 'failed', progress_message = 'Processamento não concluído',
                    error_code = %s, error_message = %s,
                    heartbeat_at = CURRENT_TIMESTAMP,
                    finished_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (error_code, message, job_id),
            )
            _record_event(
                cursor,
                job_id,
                "failed",
                {"error_code": error_code, "error": message},
            )


def retry_job(project_id, job_id):
    """Reabre manualmente uma falha, preservando seu histórico auditável."""
    connection = get_connection()
    try:
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            try:
                cursor.execute(
                    """
                    UPDATE background_jobs
                    SET status = 'queued', available_at = CURRENT_TIMESTAMP,
                        attempt_count = 0, started_at = NULL, finished_at = NULL,
                        worker_id = NULL, heartbeat_at = NULL,
                        error_code = NULL, error_message = NULL,
                        progress_current = 0, progress_total = 0,
                        progress_message = 'Aguardando nova tentativa',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s AND project_id = %s AND status = 'failed'
                    RETURNING *
                    """,
                    (job_id, project_id),
                )
                row = cursor.fetchone()
                if not row:
                    raise ValueError("Somente um processamento com falha pode ser repetido.")
                _record_event(cursor, job_id, "manual_retry")
                connection.commit()
                return _row_to_dict(row)
            except IntegrityError as exc:
                connection.rollback()
                raise ValueError("Já existe outro processamento deste tipo em andamento.") from exc
    finally:
        connection.close()


def recover_stale_jobs(stale_seconds=None):
    """Marca trabalhos órfãos como falha rastreável, sem repetir efeitos às cegas."""
    if stale_seconds is None:
        stale_seconds = _env_int("RAG_JOB_STALE_SECONDS", 300, 60, 3600)
    else:
        stale_seconds = max(60, int(stale_seconds))
    with get_connection() as connection, connection.cursor(
        cursor_factory=RealDictCursor
    ) as cursor:
        cursor.execute(
            """
            UPDATE background_jobs
            SET status = 'failed',
                error_code = 'worker_interrupted',
                error_message = 'O processo de trabalho foi interrompido. Revise o estado e tente novamente.',
                progress_message = 'Processamento interrompido',
                finished_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE status = 'running'
              AND heartbeat_at < CURRENT_TIMESTAMP - (%s * INTERVAL '1 second')
            RETURNING id
            """,
            (stale_seconds,),
        )
        rows = cursor.fetchall()
        for row in rows:
            _record_event(cursor, row["id"], "recovered_stale")
        return len(rows)


def utc_now():
    return datetime.now(timezone.utc)
