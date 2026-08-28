import json
from unittest.mock import patch

from backend.app.operational_health import HealthCheck, build_health_report, main


def _check(code, status):
    return HealthCheck(
        code=code,
        label=code,
        status=status,
        category="application",
        message="mensagem segura",
        details={},
    )


@patch("backend.app.operational_health.recent_job_failures", return_value=[])
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
    assert len(report["checks"]) == 10


@patch("backend.app.operational_health.recent_job_failures", return_value=[])
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
