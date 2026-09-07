"""Fachada autorizada para operações que afetam toda a instalação."""

from pathlib import Path

from backend.app.backup_service import create_backup, inspect_backup, restore_backup
from backend.app.external_backup import request_external_backup_now
from backend.app.operational_health import build_health_report
from backend.app.user_identity import require_installation_operator


def create_installation_backup(password: str) -> dict:
    require_installation_operator()
    return create_backup(password)


def inspect_installation_backup(source: Path, password: str) -> dict:
    require_installation_operator()
    return inspect_backup(source, password)


def restore_installation_backup(
    source: Path,
    password: str,
    confirmation: str,
) -> dict:
    require_installation_operator()
    return restore_backup(source, password, confirmation)


def request_installation_external_backup() -> None:
    require_installation_operator()
    request_external_backup_now()


def build_installation_health_report() -> dict:
    require_installation_operator()
    return build_health_report("full")
