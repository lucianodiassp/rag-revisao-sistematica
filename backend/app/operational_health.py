"""Diagnóstico seguro da aplicação e health checks usados pelo Docker."""

from __future__ import annotations

import argparse
import json
import os
import socket
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from urllib.request import urlopen

from psycopg2.extras import Json, RealDictCursor

from backend.app.database import get_connection
from backend.app.observability import classify_error, sanitize_fields
from backend.app.version import APP_VERSION, application_metadata


LATEST_REQUIRED_MIGRATION = "016_visual_artifacts.sql"
REQUIRED_TABLES = (
    "review_projects",
    "background_jobs",
    "background_job_events",
    "schema_migrations",
    "service_heartbeats",
    "visual_artifacts",
    "visual_artifact_review_events",
)


@dataclass(frozen=True)
class HealthCheck:
    code: str
    label: str
    status: str
    category: str
    message: str
    details: dict

    def as_dict(self):
        return asdict(self)


def _check(code, label, status, category, message, details=None):
    return HealthCheck(
        code=code,
        label=label,
        status=status,
        category=category,
        message=message,
        details=sanitize_fields(details or {}),
    )


def _safe_int_env(name, default, minimum=1, maximum=3600):
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


def record_service_heartbeat(service_name, instance_id, metadata=None):
    if service_name not in {"app", "worker"}:
        raise ValueError("Serviço desconhecido para o sinal de vida.")
    profile = application_metadata()["deployment_profile"]
    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO service_heartbeats
                (service_name, instance_id, app_version, deployment_profile,
                 metadata_jsonb, started_at, last_seen_at)
            VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (service_name, instance_id) DO UPDATE
            SET app_version = EXCLUDED.app_version,
                deployment_profile = EXCLUDED.deployment_profile,
                metadata_jsonb = EXCLUDED.metadata_jsonb,
                last_seen_at = CURRENT_TIMESTAMP
            """,
            (
                service_name,
                str(instance_id)[:200],
                APP_VERSION,
                profile,
                Json(sanitize_fields(metadata or {})),
            ),
        )
        cursor.execute(
            """
            DELETE FROM service_heartbeats
            WHERE last_seen_at < CURRENT_TIMESTAMP - INTERVAL '30 days'
            """
        )


class ServiceHeartbeatThread(threading.Thread):
    def __init__(self, service_name, *, instance_id=None, metadata=None):
        super().__init__(daemon=True)
        self.service_name = service_name
        self.instance_id = instance_id or (
            f"{socket.gethostname()}:{os.getpid()}:{str(uuid.uuid4())[:8]}"
        )
        self.metadata = metadata or {}
        self.interval = _safe_int_env("RAG_SERVICE_HEARTBEAT_SECONDS", 15, 5, 300)
        self.stop_event = threading.Event()

    def run(self):
        while not self.stop_event.is_set():
            try:
                record_service_heartbeat(
                    self.service_name, self.instance_id, self.metadata
                )
            except Exception:
                # A indisponibilidade será detectada pelo health check; o sinal de vida
                # nunca deve derrubar o processo principal nem imprimir credenciais.
                pass
            self.stop_event.wait(self.interval)

    def stop(self):
        self.stop_event.set()


def check_application_configuration():
    try:
        metadata = application_metadata()
        return _check(
            "application_configuration",
            "Configuração da aplicação",
            "ok",
            "configuration",
            "Versão e perfil de implantação reconhecidos.",
            {
                "version": metadata["version"],
                "deployment_profile": metadata["deployment_profile"],
                "user_mode": metadata["user_mode"],
            },
        )
    except Exception as error:
        issue = classify_error(error, component_hint="configuration")
        return _check(
            "application_configuration",
            "Configuração da aplicação",
            "error",
            issue.category,
            issue.user_message,
            {"action": issue.recommended_action},
        )


def check_database():
    try:
        with get_connection() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return _check(
            "database",
            "PostgreSQL",
            "ok",
            "database",
            "Conexão com o banco estabelecida.",
        )
    except Exception as error:
        issue = classify_error(error, component_hint="database")
        return _check(
            "database",
            "PostgreSQL",
            "error",
            "database",
            issue.user_message,
            {"action": issue.recommended_action},
        )


def check_migrations():
    try:
        with get_connection() as connection, connection.cursor(
            cursor_factory=RealDictCursor
        ) as cursor:
            cursor.execute(
                """
                SELECT name, to_regclass('public.' || name) IS NOT NULL AS present
                FROM unnest(%s::text[]) AS name
                """,
                (list(REQUIRED_TABLES),),
            )
            tables = {row["name"]: bool(row["present"]) for row in cursor.fetchall()}
            if not all(tables.values()):
                missing = [name for name, present in tables.items() if not present]
                return _check(
                    "migrations",
                    "Migrações",
                    "error",
                    "database",
                    "O esquema do banco está incompleto.",
                    {
                        "missing_tables": missing,
                        "action": "Execute novamente o serviço migrate antes da aplicação.",
                    },
                )
            cursor.execute(
                """
                SELECT migration_name, last_verified_at
                FROM schema_migrations
                WHERE migration_name = %s
                """,
                (LATEST_REQUIRED_MIGRATION,),
            )
            latest = cursor.fetchone()
        if not latest:
            return _check(
                "migrations",
                "Migrações",
                "error",
                "database",
                "A migração mais recente ainda não foi registrada.",
                {
                    "required_migration": LATEST_REQUIRED_MIGRATION,
                    "action": "Execute novamente o serviço migrate.",
                },
            )
        return _check(
            "migrations",
            "Migrações",
            "ok",
            "database",
            "Esquema e registro de migrações estão atualizados.",
            {
                "latest_required": LATEST_REQUIRED_MIGRATION,
                "last_verified_at": latest["last_verified_at"],
            },
        )
    except Exception as error:
        issue = classify_error(error, component_hint="database")
        return _check(
            "migrations",
            "Migrações",
            "error",
            "database",
            "Não foi possível confirmar o estado das migrações.",
            {"action": issue.recommended_action},
        )


def check_storage():
    try:
        from backend.app.storage_service import storage_overview

        statuses = storage_overview()
        unhealthy = [item.label for item in statuses if not item.healthy]
        details = {
            "areas": [
                {
                    "label": item.label,
                    "healthy": item.healthy,
                    "writable": item.writable,
                    "free_mb": item.free_bytes // (1024 * 1024),
                    "stored_mb": item.stored_bytes // (1024 * 1024),
                    "minimum_free_mb": item.minimum_free_bytes // (1024 * 1024),
                }
                for item in statuses
            ]
        }
        if unhealthy:
            details["action"] = (
                "Confira volumes, permissões e espaço livre nas áreas indicadas."
            )
            return _check(
                "storage",
                "Armazenamento persistente",
                "error",
                "storage",
                "Uma ou mais áreas persistentes requerem atenção.",
                details,
            )
        return _check(
            "storage",
            "Armazenamento persistente",
            "ok",
            "storage",
            "Volumes graváveis e com reserva livre suficiente.",
            details,
        )
    except Exception as error:
        issue = classify_error(error, component_hint="storage")
        return _check(
            "storage",
            "Armazenamento persistente",
            "error",
            "storage",
            issue.user_message,
            {"action": issue.recommended_action},
        )


def check_http(url="http://localhost:8501/_stcore/health"):
    try:
        with urlopen(url, timeout=2) as response:
            healthy = response.status == 200
        if not healthy:
            raise RuntimeError("A interface respondeu com status inesperado.")
        return _check(
            "http",
            "Interface Web",
            "ok",
            "application",
            "A interface está respondendo internamente.",
        )
    except Exception:
        return _check(
            "http",
            "Interface Web",
            "error",
            "application",
            "A interface não respondeu ao health check interno.",
            {"action": "Consulte os logs do serviço app e confirme a porta interna 8501."},
        )


def check_worker():
    stale_seconds = _safe_int_env("RAG_SERVICE_STALE_SECONDS", 60, 15, 3600)
    try:
        with get_connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - MAX(last_seen_at)))
                FROM service_heartbeats WHERE service_name = 'worker'
                """
            )
            age = cursor.fetchone()[0]
        if age is None:
            return _check(
                "worker",
                "Processamento em segundo plano",
                "error",
                "worker",
                "Nenhum sinal de vida do worker foi registrado.",
                {"action": "Confira se o serviço worker foi iniciado após as migrações."},
            )
        age_seconds = float(age)
        if age_seconds > stale_seconds:
            return _check(
                "worker",
                "Processamento em segundo plano",
                "error",
                "worker",
                "O sinal de vida do worker está desatualizado.",
                {
                    "age_seconds": round(age_seconds, 1),
                    "limit_seconds": stale_seconds,
                    "action": "Consulte os logs do worker e reinicie somente esse serviço.",
                },
            )
        return _check(
            "worker",
            "Processamento em segundo plano",
            "ok",
            "worker",
            "O worker está ativo e registrando sinais de vida.",
            {"age_seconds": round(age_seconds, 1), "limit_seconds": stale_seconds},
        )
    except Exception:
        return _check(
            "worker",
            "Processamento em segundo plano",
            "error",
            "worker",
            "Não foi possível consultar o sinal de vida do worker.",
            {"action": "Confirme as migrações e consulte os logs do serviço worker."},
        )


def check_ai_configuration():
    try:
        from backend.app.ai_config import get_ai_settings, get_provider_api_key

        settings = get_ai_settings()
        providers = sorted(
            {config.provider for config in settings.generation.values()}
            | {settings.embedding.provider}
        )
        missing_providers = [
            provider for provider in providers if not get_provider_api_key(provider)
        ]
        configured = not missing_providers
        return _check(
            "ai_configuration",
            "Provedor de IA",
            "ok" if configured else "warning",
            "ai_provider",
            (
                "Configuração de IA carregada com credencial disponível."
                if configured
                else "Modelos configurados, mas nenhuma credencial de IA está disponível."
            ),
            {
                "providers": providers,
                "missing_providers": missing_providers,
                "access_configured": configured,
                "generation_tasks": len(settings.generation),
                "embedding_model": settings.embedding.model,
                "action": (
                    None
                    if configured
                    else "Cadastre e valide uma credencial na tela Configuração de IA."
                ),
            },
        )
    except Exception as error:
        issue = classify_error(error, component_hint="configuration")
        return _check(
            "ai_configuration",
            "Provedor de IA",
            "error",
            "configuration",
            "A configuração de IA não pôde ser carregada.",
            {"action": issue.recommended_action},
        )


def check_bibliographic_sources():
    try:
        from backend.app.bibliographic_config import get_bibliographic_settings

        settings = get_bibliographic_settings()
        enabled = [item for item in settings.values() if item.enabled]
        status = "ok" if enabled else "warning"
        return _check(
            "bibliographic_sources",
            "Fontes bibliográficas",
            status,
            "bibliographic_source",
            (
                f"{len(enabled)} fonte(s) habilitada(s)."
                if enabled
                else "Nenhuma fonte bibliográfica está habilitada."
            ),
            {
                "sources": [
                    {
                        "source_code": item.source_code,
                        "enabled": item.enabled,
                        "authenticated": bool(item.api_key),
                        "configuration_source": item.source,
                    }
                    for item in settings.values()
                ],
                "action": (
                    None
                    if enabled
                    else "Habilite ao menos uma fonte na tela Fontes Bibliográficas."
                ),
            },
        )
    except Exception:
        return _check(
            "bibliographic_sources",
            "Fontes bibliográficas",
            "error",
            "configuration",
            "A configuração das fontes bibliográficas não pôde ser carregada.",
            {"action": "Revise a configuração das fontes e a chave-mestra local."},
        )


def check_job_queue():
    try:
        with get_connection() as connection, connection.cursor(
            cursor_factory=RealDictCursor
        ) as cursor:
            cursor.execute(
                """
                SELECT
                    COUNT(*) FILTER (WHERE status = 'queued') AS queued,
                    COUNT(*) FILTER (WHERE status = 'running') AS running,
                    COUNT(*) FILTER (WHERE status = 'retry_wait') AS retry_wait,
                    COUNT(*) FILTER (
                        WHERE status = 'failed'
                          AND finished_at >= CURRENT_TIMESTAMP - INTERVAL '24 hours'
                    ) AS failed_24h,
                    COUNT(*) FILTER (
                        WHERE status = 'running'
                          AND heartbeat_at < CURRENT_TIMESTAMP - INTERVAL '5 minutes'
                    ) AS stale_running
                FROM background_jobs
                """
            )
            summary = dict(cursor.fetchone())
        stale = int(summary.get("stale_running") or 0)
        failed = int(summary.get("failed_24h") or 0)
        status = "error" if stale else "warning" if failed else "ok"
        message = (
            "Há processamento em execução com sinal de vida desatualizado."
            if stale
            else "Há falhas registradas nas últimas 24 horas."
            if failed
            else "A fila não possui falhas recentes ou tarefas órfãs."
        )
        summary["action"] = (
            "Consulte o histórico abaixo e os logs do worker."
            if status != "ok"
            else None
        )
        return _check(
            "job_queue",
            "Fila de processamento",
            status,
            "worker",
            message,
            summary,
        )
    except Exception:
        return _check(
            "job_queue",
            "Fila de processamento",
            "error",
            "worker",
            "Não foi possível consultar a fila persistente.",
            {"action": "Confirme o banco, as migrações e o serviço worker."},
        )


def check_external_backup():
    try:
        from backend.app.external_backup import (
            external_backup_configuration,
            external_backup_is_stale,
            external_backup_run_is_stale,
            next_scheduled_run,
            read_external_backup_status,
        )

        settings, errors = external_backup_configuration()
        profile = application_metadata()["deployment_profile"]
        if errors:
            return _check(
                "external_backup",
                "Backup externo",
                "error",
                "storage",
                "A configuração do backup externo está incompleta.",
                {
                    "action": "Revise deploy/web.env e execute novamente o preflight.",
                    "error_count": len(errors),
                },
            )
        if not settings.enabled:
            web_profile = profile == "web_private"
            return _check(
                "external_backup",
                "Backup externo",
                "warning" if web_profile else "ok",
                "storage",
                (
                    "A instalação Web ainda depende de cópias manuais fora do servidor."
                    if web_profile
                    else "Backup externo opcional no perfil local."
                ),
                {
                    "enabled": False,
                    "action": (
                        "Configure um destino S3 compatível em deploy/web.env."
                        if web_profile
                        else None
                    ),
                },
            )

        status = read_external_backup_status()
        state = status.get("state")
        details = settings.public_summary()
        details.update(
            {
                "state": state,
                "last_attempt_at": status.get("last_attempt_at"),
                "last_success_at": status.get("last_success_at"),
                "next_run_at": next_scheduled_run(settings, status).isoformat(),
            }
        )
        if state in {"error", "invalid_status"}:
            details["action"] = (
                "Consulte os logs do serviço backup-scheduler e teste o destino externo."
            )
            return _check(
                "external_backup",
                "Backup externo",
                "error",
                "storage",
                "A última tentativa de backup externo falhou.",
                details,
            )
        if external_backup_run_is_stale(settings, status):
            details["action"] = "Reinicie somente o serviço backup-scheduler."
            return _check(
                "external_backup",
                "Backup externo",
                "error",
                "storage",
                "Uma execução de backup externo ficou sem conclusão.",
                details,
            )
        if state == "never_run":
            details["action"] = "Solicite uma primeira execução na tela Backup e Restauração."
            return _check(
                "external_backup",
                "Backup externo",
                "warning",
                "storage",
                "O destino está configurado, mas ainda não há backup externo confirmado.",
                details,
            )
        if external_backup_is_stale(status):
            details["action"] = (
                "Consulte o serviço backup-scheduler e solicite uma nova execução."
            )
            return _check(
                "external_backup",
                "Backup externo",
                "error",
                "storage",
                "O último backup externo confirmado está atrasado.",
                details,
            )
        return _check(
            "external_backup",
            "Backup externo",
            "ok",
            "storage",
            "O backup externo está configurado e sem falha registrada.",
            details,
        )
    except Exception:
        return _check(
            "external_backup",
            "Backup externo",
            "error",
            "storage",
            "Não foi possível verificar o estado do backup externo.",
            {"action": "Confira a configuração e o serviço backup-scheduler."},
        )


def recent_job_failures(limit=10):
    try:
        with get_connection() as connection, connection.cursor(
            cursor_factory=RealDictCursor
        ) as cursor:
            cursor.execute(
                """
                SELECT id, job_type, error_code, error_message, attempt_count,
                       max_attempts, finished_at
                FROM background_jobs
                WHERE status = 'failed'
                ORDER BY finished_at DESC NULLS LAST, created_at DESC
                LIMIT %s
                """,
                (max(1, min(int(limit), 50)),),
            )
            rows = cursor.fetchall()
        failures = []
        for row in rows:
            hint = (
                "bibliographic_source"
                if row["job_type"] == "bibliographic_search"
                else "ai_provider"
                if row["error_code"] == "transient_provider_error"
                else None
            )
            issue = classify_error(row.get("error_message"), component_hint=hint)
            failures.append(
                {
                    "job_id": str(row["id"]),
                    "job_type": row["job_type"],
                    "category": issue.category,
                    "code": row.get("error_code") or issue.code,
                    "message": issue.user_message,
                    "recommended_action": issue.recommended_action,
                    "attempts": f"{row['attempt_count']}/{row['max_attempts']}",
                    "finished_at": row["finished_at"],
                }
            )
        return failures
    except Exception:
        return []


def build_health_report(component="full", http_url=None):
    if component not in {"app", "worker", "full"}:
        raise ValueError("Componente de diagnóstico desconhecido.")
    checks = [check_application_configuration(), check_database(), check_migrations()]
    if component in {"app", "full"}:
        checks.extend(
            [
                check_storage(),
                check_http(http_url or "http://localhost:8501/_stcore/health"),
            ]
        )
    if component in {"worker", "full"}:
        checks.append(check_worker())
    if component == "full":
        checks.extend(
            [
                check_job_queue(),
                check_external_backup(),
                check_ai_configuration(),
                check_bibliographic_sources(),
            ]
        )
    statuses = [item.status for item in checks]
    overall = (
        "unhealthy"
        if "error" in statuses
        else "degraded"
        if "warning" in statuses
        else "healthy"
    )
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "application_version": APP_VERSION,
        "component": component,
        "overall_status": overall,
        "checks": [item.as_dict() for item in checks],
        "recent_job_failures": recent_job_failures() if component == "full" else [],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Diagnóstico operacional seguro")
    parser.add_argument("--component", choices=("app", "worker", "full"), default="full")
    parser.add_argument("--url", default=None)
    args = parser.parse_args(argv)
    report = build_health_report(args.component, args.url)
    print(json.dumps(report, ensure_ascii=False, default=str, sort_keys=True))
    return 1 if report["overall_status"] == "unhealthy" else 0


if __name__ == "__main__":
    raise SystemExit(main())
