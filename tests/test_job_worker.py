import sys
from unittest.mock import MagicMock, patch

from backend.app import job_worker


def _job(job_type="pdf_indexing"):
    return {
        "id": "00000000-0000-0000-0000-000000000101",
        "project_id": "00000000-0000-0000-0000-000000000001",
        "requested_by_user_id": "00000000-0000-0000-0000-000000000201",
        "job_type": job_type,
        "parameters_jsonb": {},
    }


def test_classifies_only_temporary_provider_failures_for_automatic_retry():
    assert job_worker.is_transient_error(RuntimeError("503 UNAVAILABLE")) is True
    assert job_worker.is_transient_error(RuntimeError("429 rate limit")) is True
    assert job_worker.is_transient_error(ValueError("protocolo inválido")) is False


def test_safe_error_message_redacts_common_secret_assignments():
    message = job_worker.safe_error_message(
        RuntimeError("API_KEY=valor-secreto password:senha-secreta falhou")
    )

    assert "valor-secreto" not in message
    assert "senha-secreta" not in message
    assert "[oculto]" in message


@patch(
    "backend.processamento.leitor_pdf.processar_pdfs",
    return_value={"processados": 1, "falhas": 0},
)
@patch("backend.app.job_worker.update_job_progress")
def test_dispatches_pdf_indexing_with_persistent_progress(_progress, process):
    result = job_worker.execute_job(_job("pdf_indexing"))

    assert result == {"processados": 1, "falhas": 0}
    process.assert_called_once()
    assert process.call_args.args[0] == _job()["project_id"]
    assert callable(process.call_args.kwargs["progress_callback"])


@patch(
    "backend.app.visual_catalog.catalog_project_visuals",
    return_value={"papers_processed": 1, "figures": 2, "tables": 1},
)
@patch("backend.app.job_worker.update_job_progress")
def test_dispatches_visual_cataloging_with_persistent_progress(_progress, catalog):
    result = job_worker.execute_job(_job("visual_cataloging"))

    assert result == {"papers_processed": 1, "figures": 2, "tables": 1}
    catalog.assert_called_once()
    assert catalog.call_args.args[0] == _job()["project_id"]
    assert callable(catalog.call_args.kwargs["progress_callback"])


@patch(
    "backend.app.visual_interpretation.interpret_visual_artifact",
    return_value={"interpretation_id": "visual-result", "review_status": "pending"},
)
@patch("backend.app.job_worker.update_job_progress")
def test_dispatches_one_visual_interpretation_with_artifact_parameter(_progress, interpret):
    job = _job("visual_interpretation")
    job["parameters_jsonb"] = {"artifact_id": "visual-artifact"}

    result = job_worker.execute_job(job)

    assert result["review_status"] == "pending"
    interpret.assert_called_once()
    assert interpret.call_args.args == (job["project_id"], "visual-artifact")
    assert callable(interpret.call_args.kwargs["progress_callback"])


@patch("backend.app.job_worker.require_project_access")
@patch("backend.app.job_worker.HeartbeatThread")
@patch("backend.app.job_worker.complete_job")
@patch("backend.app.job_worker.execute_job", return_value={"processados": 2})
@patch("backend.app.job_worker.claim_next_job", return_value=_job())
def test_worker_completes_claimed_job(
    _claim, _execute, complete, heartbeat_class, authorize, monkeypatch
):
    monkeypatch.setenv("RAG_JOB_POLL_SECONDS", "1")
    heartbeat_class.return_value = MagicMock()
    worker = job_worker.JobWorker()

    with patch("backend.app.job_worker.reload_job_runtime_configuration") as reload_config:
        assert worker.run_once() is True
    reload_config.assert_called_once_with()
    authorize.assert_called_once_with(
        _job()["project_id"],
        "editor",
        user_id=_job()["requested_by_user_id"],
        bind=True,
    )
    complete.assert_called_once_with(_job()["id"], {"processados": 2})
    heartbeat_class.return_value.stop.assert_called_once()


@patch("backend.app.job_worker.require_project_access")
@patch("backend.app.job_worker.HeartbeatThread")
@patch("backend.app.job_worker.complete_job")
@patch("backend.app.job_worker.claim_next_job", return_value=_job())
def test_worker_suppresses_legacy_scientific_output(
    _claim, complete, heartbeat_class, _authorize, monkeypatch, capsys
):
    monkeypatch.setenv("RAG_JOB_POLL_SECONDS", "1")
    heartbeat_class.return_value = MagicMock()
    worker = job_worker.JobWorker()

    def execute_with_legacy_output(_claimed_job):
        print("PERGUNTA CIENTIFICA CONFIDENCIAL")
        print("TITULO DE ARTIGO CONFIDENCIAL", file=sys.stderr)
        return {"processados": 1}

    with patch(
        "backend.app.job_worker.reload_job_runtime_configuration"
    ), patch(
        "backend.app.job_worker.execute_job",
        side_effect=execute_with_legacy_output,
    ):
        assert worker.run_once() is True

    captured = capsys.readouterr()
    assert "PERGUNTA CIENTIFICA CONFIDENCIAL" not in captured.out
    assert "TITULO DE ARTIGO CONFIDENCIAL" not in captured.err
    complete.assert_called_once_with(_job()["id"], {"processados": 1})


@patch("backend.app.job_worker.require_project_access")
@patch("backend.app.job_worker.HeartbeatThread")
@patch("backend.app.job_worker.fail_job")
@patch(
    "backend.app.job_worker.execute_job",
    side_effect=RuntimeError("503 provider temporarily unavailable"),
)
@patch("backend.app.job_worker.claim_next_job", return_value=_job("final_report"))
def test_worker_schedules_retry_for_transient_failure(
    _claim, _execute, fail, heartbeat_class, _authorize, monkeypatch
):
    monkeypatch.setenv("RAG_JOB_POLL_SECONDS", "1")
    heartbeat_class.return_value = MagicMock()
    worker = job_worker.JobWorker()

    assert worker.run_once() is True
    assert fail.call_args.kwargs["retryable"] is True
    assert fail.call_args.kwargs["error_code"] == "transient_provider_error"


def test_worker_refuses_job_when_requester_lost_editor_access(monkeypatch):
    monkeypatch.setenv("RAG_JOB_POLL_SECONDS", "1")
    heartbeat = MagicMock()
    worker = job_worker.JobWorker()

    with patch(
        "backend.app.job_worker.claim_next_job", return_value=_job()
    ), patch(
        "backend.app.job_worker.HeartbeatThread", return_value=heartbeat
    ), patch(
        "backend.app.job_worker.require_project_access",
        side_effect=PermissionError("associação revogada"),
    ), patch(
        "backend.app.job_worker.execute_job"
    ) as execute, patch(
        "backend.app.job_worker.fail_job"
    ) as fail:
        assert worker.run_once() is True

    execute.assert_not_called()
    assert fail.call_args.kwargs["retryable"] is False
    assert fail.call_args.kwargs["error_code"] == "processing_error"
    heartbeat.stop.assert_called_once()
