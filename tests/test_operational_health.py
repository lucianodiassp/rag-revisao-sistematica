import json
from unittest.mock import Mock, patch

from backend.app.operational_health import (
    LATEST_REQUIRED_MIGRATION,
    REQUIRED_TABLES,
    HealthCheck,
    build_health_report,
    check_access_integrity,
    main,
)


def test_latest_schema_is_required_by_operational_health():
    assert LATEST_REQUIRED_MIGRATION == "024_user_access_administration.sql"
    assert "application_users" in REQUIRED_TABLES
    assert "project_memberships" in REQUIRED_TABLES
    assert "visual_artifacts" in REQUIRED_TABLES
    assert "visual_artifact_review_events" in REQUIRED_TABLES
    assert "visual_interpretations" in REQUIRED_TABLES
    assert "visual_interpretation_review_events" in REQUIRED_TABLES
    assert "project_lifecycle_events" in REQUIRED_TABLES
    assert "project_invitations" in REQUIRED_TABLES
    assert "project_access_events" in REQUIRED_TABLES


def _check(code, status):
    return HealthCheck(
        code=code,
        label=code,
        status=status,
        category="application",
        message="mensagem segura",
        details={},
    )


def _connection(row):
    connection = Mock()
    connection.__enter__ = Mock(return_value=connection)
    connection.__exit__ = Mock(return_value=False)
    cursor = Mock()
    cursor.__enter__ = Mock(return_value=cursor)
    cursor.__exit__ = Mock(return_value=False)
    cursor.fetchone.return_value = row
    connection.cursor.return_value = cursor
    return Mock(return_value=connection), cursor


def test_access_integrity_reports_orphaned_projects_without_exposing_users():
    factory, cursor = _connection(
        {
            "orphaned_projects": 1,
            "active_operators": 1,
            "unsafe_pending_invitations": 0,
        }
    )
    with patch("backend.app.operational_health.get_connection", factory):
        check = check_access_integrity()

    assert check.status == "error"
    assert check.details["orphaned_projects"] == 1
    assert "email" not in check.details
    assert "active_owners <> 1" in cursor.execute.call_args.args[0]


@patch("backend.app.operational_health.recent_job_failures", return_value=[])
@patch("backend.app.operational_health.check_access_integrity", return_value=_check("access", "ok"))
@patch("backend.app.operational_health.check_bibliographic_sources", return_value=_check("sources", "ok"))
@patch("backend.app.operational_health.check_ai_configuration", return_value=_check("ai", "warning"))
@patch("backend.app.operational_health.check_external_backup", return_value=_check("backup", "ok"))
@patch("backend.app.operational_health.check_job_queue", return_value=_check("queue", "ok"))
@patch("backend.app.operational_health.check_worker", return_value=_check("worker", "ok"))
@patch("backend.app.operational_health.check_http", return_value=_check("http", "ok"))
@patch("backend.app.operational_health.check_storage", return_value=_check("storage", "ok"))
@patch("backend.app.operational_health.check_migrations", return_value=_check("migrations", "ok"))
@patch("backend.app.operational_health.check_database", return_value=_check("database", "ok"))
@patch("backend.app.operational_health.check_application_configuration", return_value=_check("config", "ok"))
def test_full_report_marks_warnings_as_degraded(*_mocks):
    report = build_health_report("full")

    assert report["overall_status"] == "degraded"
    assert len(report["checks"]) == 11


@patch("backend.app.operational_health.recent_job_failures", return_value=[])
@patch("backend.app.operational_health.check_access_integrity", return_value=_check("access", "ok"))
@patch("backend.app.operational_health.check_bibliographic_sources", return_value=_check("sources", "ok"))
@patch("backend.app.operational_health.check_ai_configuration", return_value=_check("ai", "ok"))
@patch("backend.app.operational_health.check_external_backup", return_value=_check("backup", "ok"))
@patch("backend.app.operational_health.check_job_queue", return_value=_check("queue", "ok"))
@patch("backend.app.operational_health.check_worker", return_value=_check("worker", "error"))
@patch("backend.app.operational_health.check_http", return_value=_check("http", "ok"))
@patch("backend.app.operational_health.check_storage", return_value=_check("storage", "ok"))
@patch("backend.app.operational_health.check_migrations", return_value=_check("migrations", "ok"))
@patch("backend.app.operational_health.check_database", return_value=_check("database", "ok"))
@patch("backend.app.operational_health.check_application_configuration", return_value=_check("config", "ok"))
def test_full_report_marks_core_failure_as_unhealthy(*_mocks):
    report = build_health_report("full")

    assert report["overall_status"] == "unhealthy"


@patch("backend.app.operational_health.build_health_report")
def test_cli_returns_failure_and_json_for_unhealthy_report(build, capsys):
    build.return_value = {
        "overall_status": "unhealthy",
        "checks": [],
        "recent_job_failures": [],
    }

    assert main(["--component", "app"]) == 1
    output = json.loads(capsys.readouterr().out)
    assert output["overall_status"] == "unhealthy"
