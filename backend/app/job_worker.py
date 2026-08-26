"""Processo separado que executa a fila persistente de operações demoradas."""

from __future__ import annotations

import os
import re
import signal
import socket
import threading
import time
import uuid

from backend.app.background_jobs import (
    JOB_BIBLIOGRAPHIC_SEARCH,
    JOB_EVIDENCE_EXTRACTION,
    JOB_FINAL_REPORT,
    JOB_PDF_INDEXING,
    JOB_RAG_BENCHMARK,
    claim_next_job,
    complete_job,
    fail_job,
    heartbeat_job,
    recover_stale_jobs,
    update_job_progress,
)


TRANSIENT_MARKERS = (
    "429",
    "503",
    "unavailable",
    "resource_exhausted",
    "rate limit",
    "too many requests",
    "timed out",
    "timeout",
    "temporarily",
    "connection reset",
    "connection aborted",
    "connection refused",
    "remote disconnected",
)


def is_transient_error(error):
    message = str(error or "").lower()
    return isinstance(error, (TimeoutError, ConnectionError)) or any(
        marker in message for marker in TRANSIENT_MARKERS
    )


def safe_error_message(error):
    message = str(error or "Falha não identificada").replace("\x00", "")
    message = re.sub(
        r"(?i)(api[_-]?key|token|secret|password)(\s*[:=]\s*)[^\s,;]+",
        r"\1\2[oculto]",
        message,
    )
    return message[:2000]


def _progress(job_id):
    def callback(current, total, message):
        update_job_progress(job_id, current, total, message)

    return callback


def execute_job(job):
    """Executa um trabalho já reservado e devolve um resultado JSON seguro."""
    job_id = job["id"]
    project_id = job["project_id"]
    parameters = job.get("parameters_jsonb") or {}
    callback = _progress(job_id)

    if job["job_type"] == JOB_BIBLIOGRAPHIC_SEARCH:
        from backend.coleta.orquestrador_coleta import iniciar_recolha

        values = iniciar_recolha(
            parameters["query"],
            project_id=project_id,
            max_por_fonte=int(parameters.get("max_per_source", 5)),
            source_queries=parameters.get("source_queries") or {},
            progress_callback=callback,
        )
        return {
            "saved": values[0],
            "found": values[1],
            "merged": values[2],
            "pending_review": values[3],
        }

    if job["job_type"] == JOB_PDF_INDEXING:
        from backend.processamento.leitor_pdf import processar_pdfs

        return processar_pdfs(project_id, progress_callback=callback)

    if job["job_type"] == JOB_EVIDENCE_EXTRACTION:
        from backend.agentes.agente_extrator import executar_pipeline_extracao

        return executar_pipeline_extracao(project_id, progress_callback=callback)

    if job["job_type"] == JOB_FINAL_REPORT:
        from backend.agentes.agente_relator import gerar_relatorio_final

        return gerar_relatorio_final(project_id, progress_callback=callback)

    if job["job_type"] == JOB_RAG_BENCHMARK:
        from backend.app.rag_benchmark import run_rag_benchmark

        run = run_rag_benchmark(project_id, progress_callback=callback)
        return {
            "run_id": run["id"],
            "summary": (run.get("metrics") or {}).get("summary") or {},
        }

    raise ValueError(f"Tipo de processamento sem executor: {job['job_type']}")


class HeartbeatThread(threading.Thread):
    def __init__(self, job_id, interval_seconds):
        super().__init__(daemon=True)
        self.job_id = job_id
        self.interval_seconds = interval_seconds
        self.stop_event = threading.Event()

    def run(self):
        while not self.stop_event.wait(self.interval_seconds):
            try:
                heartbeat_job(self.job_id)
            except Exception as error:  # o trabalho continua; a falha fica no log do contêiner
                print(f"Não foi possível atualizar o sinal de vida: {safe_error_message(error)}")

    def stop(self):
        self.stop_event.set()


class JobWorker:
    def __init__(self):
        self.worker_id = (
            f"{socket.gethostname()}:{os.getpid()}:{str(uuid.uuid4())[:8]}"
        )
        self.poll_seconds = max(0.5, float(os.getenv("RAG_JOB_POLL_SECONDS", "2")))
        self.heartbeat_seconds = max(
            5.0, float(os.getenv("RAG_JOB_HEARTBEAT_SECONDS", "15"))
        )
        self.stop_event = threading.Event()

    def request_stop(self, *_args):
        self.stop_event.set()

    def run_once(self):
        job = claim_next_job(self.worker_id)
        if not job:
            return False

        heartbeat = HeartbeatThread(job["id"], self.heartbeat_seconds)
        heartbeat.start()
        try:
            result = execute_job(job)
            complete_job(job["id"], result)
        except Exception as error:
            transient = is_transient_error(error)
            fail_job(
                job["id"],
                safe_error_message(error),
                retryable=transient,
                error_code="transient_provider_error" if transient else "processing_error",
            )
            print(
                f"Trabalho {job['id']} falhou"
                f"{' e será repetido' if transient else ''}: {safe_error_message(error)}"
            )
        finally:
            heartbeat.stop()
            heartbeat.join(timeout=2)
        return True

    def run_forever(self):
        recovered = recover_stale_jobs()
        if recovered:
            print(f"{recovered} processamento(s) interrompido(s) foram sinalizados.")
        print(f"Processo de trabalho iniciado: {self.worker_id}")
        while not self.stop_event.is_set():
            try:
                worked = self.run_once()
            except Exception as error:
                worked = False
                print(f"Falha ao consultar a fila: {safe_error_message(error)}")
            if not worked:
                self.stop_event.wait(self.poll_seconds)


def main():
    configured_workers = int(os.getenv("RAG_JOB_WORKERS", "1"))
    if configured_workers != 1:
        raise RuntimeError(
            "A versão Web privada de usuário único exige RAG_JOB_WORKERS=1."
        )
    worker = JobWorker()
    signal.signal(signal.SIGTERM, worker.request_stop)
    signal.signal(signal.SIGINT, worker.request_stop)
    worker.run_forever()


if __name__ == "__main__":
    main()
