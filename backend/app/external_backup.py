"""Backup criptografado agendado para armazenamento externo compatível com S3."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import threading
from dataclasses import dataclass
from datetime import datetime, time as datetime_time, timedelta, timezone
from pathlib import Path
from typing import Mapping
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from backend.app.backup_service import BACKUP_EXTENSION, create_backup
from backend.app.observability import log_event
from backend.app.storage_service import backup_directory, private_directory
from backend.app.version import APP_VERSION


STATUS_FILENAME = "external-backup-status.json"
REQUEST_FILENAME = "external-backup-request.json"
SCHEDULED_PREFIX = "scheduled-backup"
STATUS_FORMAT_VERSION = 1


class ExternalBackupConfigurationError(ValueError):
    """Configuração externa ausente ou insegura."""


class ExternalBackupError(RuntimeError):
    """Falha segura no fluxo de cópia externa."""


def _text(value) -> str:
    return str(value or "").strip()


def _enabled(value) -> bool:
    return _text(value).lower() in {"1", "true", "yes", "sim", "on"}


def _integer(value, default, minimum, maximum, name, errors) -> int:
    try:
        parsed = int(_text(value) or default)
    except ValueError:
        parsed = 0
    if parsed < minimum or parsed > maximum:
        errors.append(f"{name} deve estar entre {minimum} e {maximum}.")
        return default
    return parsed


def _https_url(value: str) -> bool:
    if not value:
        return True
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.netloc) and not parsed.username


@dataclass(frozen=True)
class ExternalBackupSettings:
    enabled: bool
    bucket: str
    prefix: str
    region: str
    endpoint_url: str
    access_key_id: str
    secret_access_key: str
    session_token: str
    password: str
    schedule_hour_utc: int
    retry_minutes: int
    local_retention: int
    remote_retention: int
    addressing_style: str
    alert_webhook_url: str

    def public_summary(self) -> dict:
        return {
            "enabled": self.enabled,
            "provider": "S3 compatível" if self.enabled else "Não configurado",
            "bucket_configured": bool(self.bucket),
            "prefix": self.prefix,
            "region": self.region,
            "custom_endpoint": bool(self.endpoint_url),
            "credential_configured": bool(
                self.access_key_id and self.secret_access_key
            ),
            "schedule_hour_utc": self.schedule_hour_utc,
            "retry_minutes": self.retry_minutes,
            "local_retention": self.local_retention,
            "remote_retention": self.remote_retention,
            "alert_configured": bool(self.alert_webhook_url),
        }


def external_backup_configuration(
    environ: Mapping[str, object] | None = None,
) -> tuple[ExternalBackupSettings, list[str]]:
    environ = environ or os.environ
    errors: list[str] = []
    enabled = _enabled(environ.get("RAG_EXTERNAL_BACKUP_ENABLED"))
    prefix = _text(environ.get("RAG_EXTERNAL_BACKUP_PREFIX")) or (
        "rag-revisao-sistematica"
    )
    settings = ExternalBackupSettings(
        enabled=enabled,
        bucket=_text(environ.get("RAG_EXTERNAL_BACKUP_BUCKET")),
        prefix=prefix.strip("/"),
        region=_text(environ.get("RAG_EXTERNAL_BACKUP_REGION")) or "us-east-1",
        endpoint_url=_text(environ.get("RAG_EXTERNAL_BACKUP_ENDPOINT_URL")),
        access_key_id=_text(environ.get("RAG_EXTERNAL_BACKUP_ACCESS_KEY_ID")),
        secret_access_key=_text(environ.get("RAG_EXTERNAL_BACKUP_SECRET_ACCESS_KEY")),
        session_token=_text(environ.get("RAG_EXTERNAL_BACKUP_SESSION_TOKEN")),
        password=_text(environ.get("RAG_EXTERNAL_BACKUP_PASSWORD")),
        schedule_hour_utc=_integer(
            environ.get("RAG_EXTERNAL_BACKUP_SCHEDULE_HOUR_UTC"),
            3,
            0,
            23,
            "RAG_EXTERNAL_BACKUP_SCHEDULE_HOUR_UTC",
            errors,
        ),
        retry_minutes=_integer(
            environ.get("RAG_EXTERNAL_BACKUP_RETRY_MINUTES"),
            60,
            5,
            1440,
            "RAG_EXTERNAL_BACKUP_RETRY_MINUTES",
            errors,
        ),
        local_retention=_integer(
            environ.get("RAG_EXTERNAL_BACKUP_LOCAL_RETENTION"),
            3,
            1,
            30,
            "RAG_EXTERNAL_BACKUP_LOCAL_RETENTION",
            errors,
        ),
        remote_retention=_integer(
            environ.get("RAG_EXTERNAL_BACKUP_REMOTE_RETENTION"),
            14,
            1,
            365,
            "RAG_EXTERNAL_BACKUP_REMOTE_RETENTION",
            errors,
        ),
        addressing_style=(
            _text(environ.get("RAG_EXTERNAL_BACKUP_ADDRESSING_STYLE")) or "auto"
        ).lower(),
        alert_webhook_url=_text(
            environ.get("RAG_EXTERNAL_BACKUP_ALERT_WEBHOOK_URL")
        ),
    )
    if not enabled:
        return settings, []
    if not settings.bucket:
        errors.append("RAG_EXTERNAL_BACKUP_BUCKET deve ser configurado.")
    if not settings.access_key_id or not settings.secret_access_key:
        errors.append("As credenciais do armazenamento externo devem ser configuradas.")
    if len(settings.password) < 12:
        errors.append("RAG_EXTERNAL_BACKUP_PASSWORD deve possuir ao menos 12 caracteres.")
    if not settings.prefix or ".." in settings.prefix.split("/"):
        errors.append("RAG_EXTERNAL_BACKUP_PREFIX contém um caminho inválido.")
    if settings.addressing_style not in {"auto", "path", "virtual"}:
        errors.append(
            "RAG_EXTERNAL_BACKUP_ADDRESSING_STYLE deve ser auto, path ou virtual."
        )
    if not _https_url(settings.endpoint_url):
        errors.append("RAG_EXTERNAL_BACKUP_ENDPOINT_URL deve usar HTTPS.")
    if not _https_url(settings.alert_webhook_url):
        errors.append("RAG_EXTERNAL_BACKUP_ALERT_WEBHOOK_URL deve usar HTTPS.")
    return settings, errors


def load_external_backup_settings(
    environ: Mapping[str, object] | None = None,
) -> ExternalBackupSettings:
    settings, errors = external_backup_configuration(environ)
    if errors:
        raise ExternalBackupConfigurationError(" ".join(errors))
    return settings


def status_path() -> Path:
    return private_directory() / STATUS_FILENAME


def request_path() -> Path:
    return private_directory() / REQUEST_FILENAME


def _atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def read_external_backup_status() -> dict:
    path = status_path()
    if not path.is_file():
        return {
            "format_version": STATUS_FORMAT_VERSION,
            "state": "never_run",
            "message": "Nenhum backup externo foi executado nesta instalação.",
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, ValueError, json.JSONDecodeError):
        return {
            "format_version": STATUS_FORMAT_VERSION,
            "state": "invalid_status",
            "message": "O estado do backup externo não pôde ser lido.",
        }


def write_external_backup_status(payload: dict) -> dict:
    safe = {
        "format_version": STATUS_FORMAT_VERSION,
        "application_version": APP_VERSION,
        **payload,
    }
    _atomic_json(status_path(), safe)
    return safe


def request_external_backup_now() -> None:
    settings = load_external_backup_settings()
    if not settings.enabled:
        raise ExternalBackupConfigurationError("O backup externo não está habilitado.")
    _atomic_json(
        request_path(),
        {
            "requested_at": datetime.now(timezone.utc).isoformat(),
            "application_version": APP_VERSION,
        },
    )


def _consume_request() -> bool:
    path = request_path()
    if not path.is_file():
        return False
    try:
        path.unlink()
        return True
    except OSError:
        return False


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


class S3BackupStore:
    def __init__(self, settings: ExternalBackupSettings, client=None):
        self.settings = settings
        if client is not None:
            self.client = client
            return
        import boto3
        from botocore.config import Config

        options = {
            "service_name": "s3",
            "region_name": settings.region,
            "aws_access_key_id": settings.access_key_id,
            "aws_secret_access_key": settings.secret_access_key,
            "config": Config(s3={"addressing_style": settings.addressing_style}),
        }
        if settings.endpoint_url:
            options["endpoint_url"] = settings.endpoint_url
        if settings.session_token:
            options["aws_session_token"] = settings.session_token
        self.client = boto3.client(**options)

    def key_for(self, filename: str) -> str:
        return f"{self.settings.prefix}/{filename}".lstrip("/")

    def upload_verified(self, path: Path, digest: str) -> str:
        key = self.key_for(path.name)
        self.client.upload_file(
            str(path),
            self.settings.bucket,
            key,
            ExtraArgs={
                "Metadata": {
                    "sha256": digest,
                    "application-version": APP_VERSION,
                }
            },
        )
        head = self.client.head_object(Bucket=self.settings.bucket, Key=key)
        if int(head.get("ContentLength") or -1) != path.stat().st_size:
            raise ExternalBackupError("O arquivo remoto não passou na validação de tamanho.")
        metadata = head.get("Metadata") or {}
        if metadata.get("sha256") != digest:
            raise ExternalBackupError("O arquivo remoto não passou na validação de integridade.")
        return key

    def apply_retention(self) -> int:
        prefix = f"{self.settings.prefix}/{SCHEDULED_PREFIX}-".lstrip("/")
        paginator = self.client.get_paginator("list_objects_v2")
        objects = []
        for page in paginator.paginate(Bucket=self.settings.bucket, Prefix=prefix):
            objects.extend(page.get("Contents") or [])
        objects.sort(key=lambda item: item.get("LastModified"), reverse=True)
        expired = objects[self.settings.remote_retention :]
        if expired:
            result = self.client.delete_objects(
                Bucket=self.settings.bucket,
                Delete={"Objects": [{"Key": item["Key"]} for item in expired]},
            )
            if result.get("Errors"):
                raise ExternalBackupError(
                    "O destino externo não confirmou a política de retenção."
                )
        return len(expired)


def apply_local_retention(settings: ExternalBackupSettings) -> int:
    directory = backup_directory()
    files = sorted(
        directory.glob(f"{SCHEDULED_PREFIX}-*{BACKUP_EXTENSION}"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    expired = files[settings.local_retention :]
    deleted = 0
    for path in expired:
        try:
            path.unlink()
            deleted += 1
        except OSError:
            continue
    return deleted


def _notify_failure(settings: ExternalBackupSettings, occurred_at: str) -> None:
    if not settings.alert_webhook_url:
        return
    payload = json.dumps(
        {
            "event": "rag_external_backup_failed",
            "status": "error",
            "occurred_at": occurred_at,
            "application_version": APP_VERSION,
            "message": "O backup externo da aplicação requer atenção.",
        }
    ).encode("utf-8")
    request = Request(
        settings.alert_webhook_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=10) as response:
            if response.status >= 400:
                raise ExternalBackupError("O alerta de backup foi recusado.")
    except Exception:
        log_event(
            "external_backup_alert_failed",
            component="backup-scheduler",
            level="warning",
            category="storage",
            message="Não foi possível enviar o alerta configurado.",
        )


def run_external_backup(
    settings: ExternalBackupSettings | None = None,
    *,
    store: S3BackupStore | None = None,
) -> dict:
    settings = settings or load_external_backup_settings()
    if not settings.enabled:
        raise ExternalBackupConfigurationError("O backup externo não está habilitado.")
    started_at = datetime.now(timezone.utc).isoformat()
    previous = read_external_backup_status()
    write_external_backup_status(
        {
            **previous,
            "state": "running",
            "last_attempt_at": started_at,
            "message": "Backup externo em execução.",
        }
    )
    try:
        result = create_backup(settings.password, prefix=SCHEDULED_PREFIX)
        path = Path(result["path"])
        digest = _sha256(path)
        remote = store or S3BackupStore(settings)
        remote_key = remote.upload_verified(path, digest)
        remote_deleted = remote.apply_retention()
        local_deleted = apply_local_retention(settings)
        completed_at = datetime.now(timezone.utc).isoformat()
        status = write_external_backup_status(
            {
                "state": "success",
                "message": "Backup externo concluído e verificado.",
                "last_attempt_at": started_at,
                "last_success_at": completed_at,
                "filename": path.name,
                "remote_key": remote_key,
                "size_bytes": path.stat().st_size,
                "sha256": digest,
                "local_deleted": local_deleted,
                "remote_deleted": remote_deleted,
            }
        )
        log_event(
            "external_backup_succeeded",
            component="backup-scheduler",
            category="storage",
            size_bytes=status["size_bytes"],
            local_deleted=local_deleted,
            remote_deleted=remote_deleted,
        )
        return status
    except Exception as error:
        failed_at = datetime.now(timezone.utc).isoformat()
        status = write_external_backup_status(
            {
                "state": "error",
                "message": "O backup externo não foi concluído. Consulte o diagnóstico.",
                "last_attempt_at": started_at,
                "last_failure_at": failed_at,
                "failure_type": type(error).__name__[:100],
                "last_success_at": previous.get("last_success_at"),
            }
        )
        log_event(
            "external_backup_failed",
            component="backup-scheduler",
            level="error",
            category="storage",
            message=status["message"],
            failure_type=status["failure_type"],
        )
        _notify_failure(settings, failed_at)
        raise ExternalBackupError(status["message"]) from error


def _parse_timestamp(value) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(_text(value).replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def external_backup_is_stale(
    status: Mapping[str, object],
    *,
    now: datetime | None = None,
    maximum_hours: int = 48,
) -> bool:
    last_success = _parse_timestamp(status.get("last_success_at"))
    if last_success is None:
        return False
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return current - last_success > timedelta(hours=maximum_hours)


def external_backup_run_is_stale(
    settings: ExternalBackupSettings,
    status: Mapping[str, object],
    *,
    now: datetime | None = None,
) -> bool:
    if status.get("state") != "running":
        return False
    last_attempt = _parse_timestamp(status.get("last_attempt_at"))
    if last_attempt is None:
        return True
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return current - last_attempt > timedelta(minutes=settings.retry_minutes * 2)


def next_scheduled_run(
    settings: ExternalBackupSettings,
    status: Mapping[str, object] | None = None,
    *,
    now: datetime | None = None,
) -> datetime:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    today = datetime.combine(
        now.date(), datetime_time(settings.schedule_hour_utc), tzinfo=timezone.utc
    )
    last_attempt = _parse_timestamp((status or {}).get("last_attempt_at"))
    if now < today:
        return today
    if last_attempt is None or last_attempt < today:
        return now
    if (status or {}).get("state") in {"error", "running"}:
        retry = last_attempt + timedelta(minutes=settings.retry_minutes)
        return max(now, retry) if retry.date() == now.date() else today + timedelta(days=1)
    return today + timedelta(days=1)


class BackupScheduler:
    def __init__(self, settings: ExternalBackupSettings | None = None):
        self.settings = settings or load_external_backup_settings()
        self.stop_event = threading.Event()

    def request_stop(self, *_args):
        self.stop_event.set()

    def run_forever(self):
        log_event(
            "external_backup_scheduler_started",
            component="backup-scheduler",
            category="storage",
            enabled=self.settings.enabled,
        )
        while not self.stop_event.is_set():
            if not self.settings.enabled:
                self.stop_event.wait(60)
                continue
            status = read_external_backup_status()
            due = next_scheduled_run(self.settings, status)
            requested = _consume_request()
            if requested or datetime.now(timezone.utc) >= due:
                try:
                    run_external_backup(self.settings)
                except ExternalBackupError:
                    pass
                continue
            wait_seconds = min(30, max(1, (due - datetime.now(timezone.utc)).total_seconds()))
            self.stop_event.wait(wait_seconds)
        log_event(
            "external_backup_scheduler_stopped",
            component="backup-scheduler",
            category="storage",
        )


def healthcheck() -> int:
    try:
        settings = load_external_backup_settings()
    except ExternalBackupConfigurationError:
        return 1
    if not settings.enabled:
        return 0
    status = read_external_backup_status()
    if status.get("state") in {"error", "invalid_status"}:
        return 1
    if external_backup_run_is_stale(settings, status):
        return 1
    if external_backup_is_stale(status):
        return 1
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-once", action="store_true")
    parser.add_argument("--healthcheck", action="store_true")
    arguments = parser.parse_args(argv)
    if arguments.healthcheck:
        return healthcheck()
    settings = load_external_backup_settings()
    if arguments.run_once:
        run_external_backup(settings)
        return 0
    scheduler = BackupScheduler(settings)
    signal.signal(signal.SIGTERM, scheduler.request_stop)
    signal.signal(signal.SIGINT, scheduler.request_stop)
    scheduler.run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
