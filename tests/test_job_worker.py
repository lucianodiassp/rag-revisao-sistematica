from unittest.mock import MagicMock, patch

from backend.app import job_worker


def _job(job_type="pdf_indexing"):
    return {
        "id": "00000000-0000-0000-0000-000000000101",
        "project_id": "00000000-0000-0000-0000-000000000001",
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


@patch("backend.app.job_worker.HeartbeatThread")
@patch("backend.app.job_worker.complete_job")
@patch("backend.app.job_worker.execute_job", return_value={"processados": 2})
@patch("backend.app.job_worker.claim_next_job", return_value=_job())
def test_worker_completes_claimed_job(
    _claim, _execute, complete, heartbeat_class, monkeypatch
):
    monkeypatch.setenv("RAG_JOB_POLL_SECONDS", "1")
    heartbeat_class.return_value = MagicMock()
    worker = job_worker.JobWorker()

    assert worker.run_once() is True
    complete.assert_called_once_with(_job()["id"], {"processados": 2})
    heartbeat_class.return_value.stop.assert_called_once()


@patch("backend.app.job_worker.HeartbeatThread")
@patch("backend.app.job_worker.fail_job")
@patch(
    "backend.app.job_worker.execute_job",
    side_effect=RuntimeError("503 provider temporarily unavailable"),
)
@patch("backend.app.job_worker.claim_next_job", return_value=_job("final_report"))
def test_worker_schedules_retry_for_transient_failure(
    _claim, _execute, fail, heartbeat_class, monkeypatch
):
    monkeypatch.setenv("RAG_JOB_POLL_SECONDS", "1")
    heartbeat_class.return_value = MagicMock()
    worker = job_worker.JobWorker()

    assert worker.run_once() is True
    assert fail.call_args.kwargs["retryable"] is True
    assert fail.call_args.kwargs["error_code"] == "transient_provider_error"
