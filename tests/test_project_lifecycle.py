from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from backend.app.demo_project import DEMO_SEED_ID
from backend.app.project_lifecycle import (
    archive_project,
    deletion_preview,
    permanently_delete_project,
    restore_project,
)
from backend.app.background_jobs import JOB_FINAL_REPORT, enqueue_job


PROJECT_ID = "10000000-0000-0000-0000-000000000001"
PAPER_ID = "20000000-0000-0000-0000-000000000002"
NOW = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)


def _project(*, archived=False, demo=False):
    criteria = {"_demo": {"seed_id": DEMO_SEED_ID}} if demo else {}
    return {
        "id": PROJECT_ID,
        "title": "Revisão a arquivar",
        "question": "Pergunta",
        "criteria_jsonb": criteria,
        "status": "search_ready",
        "protocol_version": 3,
        "archived_at": NOW if archived else None,
        "archived_reason": "Revisão encerrada com sucesso." if archived else None,
        "created_at": NOW - timedelta(days=10),
        "updated_at": NOW,
    }


def _counts(*, active_jobs=0):
    return {
        "searches": 2,
        "records": 8,
        "papers": 5,
        "interactions": 12,
        "evaluations": 1,
        "jobs": 3,
        "active_jobs": active_jobs,
        "visual_artifacts": 4,
        "visual_interpretations": 2,
    }


def _context_connection(fetchone_values, *, fetchall_values=None):
    connection = Mock()
    connection.__enter__ = Mock(return_value=connection)
    connection.__exit__ = Mock(return_value=False)
    cursor = Mock()
    cursor.__enter__ = Mock(return_value=cursor)
    cursor.__exit__ = Mock(return_value=False)
    cursor.fetchone.side_effect = fetchone_values
    cursor.fetchall.return_value = fetchall_values or []
    connection.cursor.return_value = cursor
    return Mock(return_value=connection), connection, cursor


def test_archive_project_records_receipt_and_keeps_scientific_status():
    factory, _connection, cursor = _context_connection(
        [
            _project(),
            _counts(),
            {"active_projects": 2},
            {"archived_at": NOW},
            {"id": "event-1", "created_at": NOW},
        ]
    )

    result = archive_project(
        PROJECT_ID,
        "Revisão concluída e retirada da operação.",
        actor="pesquisador@example.test",
        connection_factory=factory,
    )

    update_sql, update_params = cursor.execute.call_args_list[3].args
    event_sql, event_params = cursor.execute.call_args_list[4].args
    assert "archived_at = CURRENT_TIMESTAMP" in update_sql
    assert "status =" not in update_sql
    assert update_params[1] == PROJECT_ID
    assert "project_lifecycle_events" in event_sql
    assert event_params[2] == "pesquisador@example.test"
    assert result["event_id"] == "event-1"


@pytest.mark.parametrize(
    ("project", "counts", "active_count", "message"),
    [
        (_project(demo=True), _counts(), {"active_projects": 2}, "demonstrativo"),
        (_project(), _counts(active_jobs=1), {"active_projects": 2}, "tarefas em andamento"),
        (_project(), _counts(), {"active_projects": 1}, "último projeto ativo"),
    ],
)
def test_archive_project_enforces_safety_barriers(project, counts, active_count, message):
    factory, _connection, _cursor = _context_connection(
        [project, counts, active_count]
    )
    with pytest.raises(ValueError, match=message):
        archive_project(
            PROJECT_ID,
            "Motivo suficientemente detalhado.",
            connection_factory=factory,
        )


def test_restore_project_clears_archive_fields_and_records_receipt():
    factory, _connection, cursor = _context_connection(
        [_project(archived=True), {"id": "event-2", "created_at": NOW}]
    )

    result = restore_project(PROJECT_ID, connection_factory=factory)

    update_sql = cursor.execute.call_args_list[1].args[0]
    assert "archived_at = NULL" in update_sql
    assert "archived_reason = NULL" in update_sql
    assert result["event_id"] == "event-2"


def test_deletion_preview_counts_only_regular_project_pdfs_and_requires_new_backup(tmp_path):
    pdf_root = tmp_path / "pdfs"
    backup_root = tmp_path / "backups"
    pdf_root.mkdir()
    backup_root.mkdir()
    pdf_path = pdf_root / f"{PAPER_ID}.pdf"
    pdf_path.write_bytes(b"%PDF-project")
    backup_path = backup_root / "post-archive.ragbackup"
    backup_path.write_bytes(b"encrypted")
    timestamp = (NOW + timedelta(minutes=2)).timestamp()
    backup_path.touch()
    import os

    os.utime(backup_path, (timestamp, timestamp))
    factory, _connection, _cursor = _context_connection(
        [_project(archived=True), _counts()],
        fetchall_values=[(PAPER_ID,)],
    )

    preview = deletion_preview(
        PROJECT_ID,
        connection_factory=factory,
        pdf_root=pdf_root,
        backup_root=backup_root,
    )

    assert preview["pdf_count"] == 1
    assert preview["pdf_bytes"] == len(b"%PDF-project")
    assert preview["backup_after_archive"] is True


def test_permanent_delete_removes_database_and_pdf_after_post_archive_backup(tmp_path):
    pdf_root = tmp_path / "pdfs"
    backup_root = tmp_path / "backups"
    pdf_root.mkdir()
    backup_root.mkdir()
    pdf_path = pdf_root / f"{PAPER_ID}.pdf"
    pdf_path.write_bytes(b"%PDF-project")
    backup_path = backup_root / "post-archive.ragbackup"
    backup_path.write_bytes(b"encrypted")
    import os

    timestamp = (NOW + timedelta(minutes=1)).timestamp()
    os.utime(backup_path, (timestamp, timestamp))
    factory, connection, cursor = _context_connection(
        [_project(archived=True), _counts(), {"created_at": NOW + timedelta(minutes=3)}],
        fetchall_values=[(PAPER_ID,)],
    )
    cursor.rowcount = 1

    result = permanently_delete_project(
        PROJECT_ID,
        "Revisão a arquivar",
        backup_confirmed=True,
        connection_factory=factory,
        pdf_root=pdf_root,
        backup_root=backup_root,
    )

    assert not pdf_path.exists()
    assert result["pdf_files_removed"] == 1
    assert result["event_id"]
    assert any(
        "DELETE FROM review_projects" in call.args[0]
        for call in cursor.execute.call_args_list
    )
    connection.commit.assert_called_once()


def test_permanent_delete_restores_pdf_when_database_transaction_fails(tmp_path):
    pdf_root = tmp_path / "pdfs"
    backup_root = tmp_path / "backups"
    pdf_root.mkdir()
    backup_root.mkdir()
    pdf_path = pdf_root / f"{PAPER_ID}.pdf"
    pdf_path.write_bytes(b"%PDF-project")
    backup_path = backup_root / "post-archive.ragbackup"
    backup_path.write_bytes(b"encrypted")
    import os

    timestamp = (NOW + timedelta(minutes=1)).timestamp()
    os.utime(backup_path, (timestamp, timestamp))
    factory, connection, cursor = _context_connection(
        [_project(archived=True), _counts()],
        fetchall_values=[(PAPER_ID,)],
    )
    cursor.rowcount = 0

    with pytest.raises(RuntimeError, match="não foi removido"):
        permanently_delete_project(
            PROJECT_ID,
            "Revisão a arquivar",
            backup_confirmed=True,
            connection_factory=factory,
            pdf_root=pdf_root,
            backup_root=backup_root,
        )

    assert pdf_path.read_bytes() == b"%PDF-project"
    connection.rollback.assert_called_once()


def test_permanent_delete_requires_archived_project_exact_title_and_backup_confirmation():
    for project, title, backup_confirmed, message in (
        (_project(), "Revisão a arquivar", True, "Arquive"),
        (_project(archived=True), "Título errado", True, "não corresponde"),
        (_project(archived=True), "Revisão a arquivar", False, "backup"),
    ):
        factory, connection, _cursor = _context_connection([project])
        with pytest.raises(ValueError, match=message):
            permanently_delete_project(
                PROJECT_ID,
                title,
                backup_confirmed=backup_confirmed,
                connection_factory=factory,
                pdf_root=Path("unused"),
                backup_root=Path("unused"),
            )
        connection.rollback.assert_called_once()


@patch("backend.app.background_jobs.get_connection")
def test_background_job_rejects_archived_project_under_row_lock(get_connection):
    connection = Mock()
    cursor = Mock()
    cursor.__enter__ = Mock(return_value=cursor)
    cursor.__exit__ = Mock(return_value=False)
    connection.cursor.return_value = cursor
    get_connection.return_value = connection
    cursor.fetchone.return_value = {"archived_at": NOW}

    with pytest.raises(ValueError, match="Projeto ativo"):
        enqueue_job(PROJECT_ID, JOB_FINAL_REPORT)

    sql = cursor.execute.call_args.args[0]
    assert "FOR UPDATE" in sql
    connection.close.assert_called_once()
