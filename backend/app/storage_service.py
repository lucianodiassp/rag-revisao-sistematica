"""Capacidade, limites e caminhos do armazenamento persistente da aplicação."""

from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from platformdirs import user_data_path
from backend.app.observability import log_event


PDF_DIRECTORY_ENV = "PDF_DIRECTORY"
BACKUP_DIRECTORY_ENV = "BACKUP_DIRECTORY"
PRIVATE_DIRECTORY_ENV = "PRIVATE_DIRECTORY"
MAX_UPLOAD_ENV = "RAG_MAX_UPLOAD_MB"
MAX_PDF_UPLOAD_ENV = "RAG_MAX_PDF_UPLOAD_MB"
MAX_BACKUP_UPLOAD_ENV = "RAG_MAX_BACKUP_UPLOAD_MB"
MIN_FREE_STORAGE_ENV = "RAG_MIN_FREE_STORAGE_MB"

DEFAULT_MAX_UPLOAD_MB = 2048
DEFAULT_MAX_PDF_UPLOAD_MB = 100
DEFAULT_MAX_BACKUP_UPLOAD_MB = 2048
DEFAULT_MIN_FREE_STORAGE_MB = 256
MEBIBYTE = 1024 * 1024
APP_DATA_NAME = "rag-revisao-sistematica"


class StorageConfigurationError(ValueError):
    """Configuração de armazenamento ausente ou inválida."""


class StorageCapacityError(RuntimeError):
    """A operação excede um limite ou a capacidade segura disponível."""


@dataclass(frozen=True)
class StorageLimits:
    server_upload_mb: int
    pdf_upload_mb: int
    backup_upload_mb: int
    minimum_free_mb: int


@dataclass(frozen=True)
class StorageStatus:
    label: str
    path: str
    writable: bool
    total_bytes: int
    used_bytes: int
    free_bytes: int
    stored_bytes: int
    minimum_free_bytes: int
    healthy: bool

    def as_dict(self) -> dict:
        return asdict(self)


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def pdf_directory() -> Path:
    configured = os.getenv(PDF_DIRECTORY_ENV)
    return (
        Path(configured).expanduser().resolve()
        if configured
        else project_root() / "data" / "pdfs"
    )


def backup_directory() -> Path:
    configured = os.getenv(BACKUP_DIRECTORY_ENV)
    return (
        Path(configured).expanduser().resolve()
        if configured
        else project_root() / "data" / "backups"
    )


def private_directory() -> Path:
    configured = os.getenv(PRIVATE_DIRECTORY_ENV)
    if not configured and os.getenv("AI_LOCAL_MASTER_KEY_PATH"):
        configured = str(Path(os.environ["AI_LOCAL_MASTER_KEY_PATH"]).expanduser().parent)
    return (
        Path(configured).expanduser().resolve()
        if configured
        else Path(user_data_path(APP_DATA_NAME, appauthor=False)).resolve()
    )


def _positive_integer(name: str, default: int, *, maximum: int = 1024 * 1024) -> int:
    raw = str(os.getenv(name, default)).strip()
    try:
        value = int(raw)
    except ValueError as error:
        raise StorageConfigurationError(f"{name} deve ser um número inteiro positivo.") from error
    if value <= 0 or value > maximum:
        raise StorageConfigurationError(
            f"{name} deve estar entre 1 e {maximum} MB."
        )
    return value


def storage_limits() -> StorageLimits:
    server = _positive_integer(MAX_UPLOAD_ENV, DEFAULT_MAX_UPLOAD_MB, maximum=10240)
    pdf = _positive_integer(MAX_PDF_UPLOAD_ENV, DEFAULT_MAX_PDF_UPLOAD_MB, maximum=10240)
    backup = _positive_integer(
        MAX_BACKUP_UPLOAD_ENV,
        min(DEFAULT_MAX_BACKUP_UPLOAD_MB, server),
        maximum=10240,
    )
    minimum_free = _positive_integer(
        MIN_FREE_STORAGE_ENV,
        DEFAULT_MIN_FREE_STORAGE_MB,
        maximum=1024 * 1024,
    )
    if pdf > server:
        raise StorageConfigurationError(
            f"{MAX_PDF_UPLOAD_ENV} não pode exceder {MAX_UPLOAD_ENV}."
        )
    if backup > server:
        raise StorageConfigurationError(
            f"{MAX_BACKUP_UPLOAD_ENV} não pode exceder {MAX_UPLOAD_ENV}."
        )
    return StorageLimits(server, pdf, backup, minimum_free)


def _directory_size(path: Path) -> int:
    if not path.is_dir():
        return 0
    total = 0
    for item in path.rglob("*"):
        try:
            if item.is_file() and not item.is_symlink():
                total += item.stat().st_size
        except OSError:
            continue
    return total


def _usage_path(path: Path) -> Path:
    candidate = path
    while not candidate.exists() and candidate != candidate.parent:
        candidate = candidate.parent
    return candidate


def inspect_storage(label: str, path: Path | str) -> StorageStatus:
    directory = Path(path).expanduser().resolve()
    usage = shutil.disk_usage(_usage_path(directory))
    minimum = storage_limits().minimum_free_mb * MEBIBYTE
    writable = directory.is_dir() and os.access(directory, os.W_OK)
    return StorageStatus(
        label=label,
        path=str(directory),
        writable=writable,
        total_bytes=usage.total,
        used_bytes=usage.used,
        free_bytes=usage.free,
        stored_bytes=_directory_size(directory),
        minimum_free_bytes=minimum,
        healthy=writable and usage.free >= minimum,
    )


def storage_overview() -> list[StorageStatus]:
    return [
        inspect_storage("PDFs", pdf_directory()),
        inspect_storage("Backups", backup_directory()),
        inspect_storage("Dados privados", private_directory()),
    ]


def ensure_free_space(
    path: Path | str,
    required_bytes: int = 0,
    *,
    operation: str = "operação",
) -> None:
    directory = Path(path).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    if not os.access(directory, os.W_OK):
        raise StorageCapacityError(
            f"O diretório persistente necessário para {operation} não permite gravação."
        )
    free = shutil.disk_usage(directory).free
    reserve = storage_limits().minimum_free_mb * MEBIBYTE
    required = max(0, int(required_bytes)) + reserve
    if free < required:
        required_mb = (required + MEBIBYTE - 1) // MEBIBYTE
        free_mb = free // MEBIBYTE
        raise StorageCapacityError(
            f"Espaço insuficiente para {operation}: são necessários aproximadamente "
            f"{required_mb} MB com a reserva de segurança, mas há {free_mb} MB livres."
        )


def ensure_upload_allowed(
    size_bytes: int,
    kind: str,
    destination_directory: Path | str,
    *,
    overhead_factor: int = 1,
) -> None:
    size = int(size_bytes or 0)
    if size <= 0:
        raise StorageCapacityError("O arquivo enviado está vazio.")
    limits = storage_limits()
    normalized_kind = str(kind).strip().lower()
    if normalized_kind == "pdf":
        limit_mb = limits.pdf_upload_mb
        label = "PDF"
    elif normalized_kind == "backup":
        limit_mb = limits.backup_upload_mb
        label = "backup"
    else:
        raise ValueError("Tipo de upload não reconhecido.")
    if size > limit_mb * MEBIBYTE:
        raise StorageCapacityError(
            f"O arquivo excede o limite de {limit_mb} MB definido para {label}."
        )
    ensure_free_space(
        destination_directory,
        size * max(1, int(overhead_factor)),
        operation=f"armazenar o {label}",
    )


def save_upload_atomic(data, destination: Path | str, *, kind: str) -> Path:
    destination_path = Path(destination).expanduser().resolve()
    size = len(data)
    ensure_upload_allowed(size, kind, destination_path.parent)
    if kind.lower() == "pdf" and bytes(data[:5]) != b"%PDF-":
        raise StorageCapacityError("O arquivo enviado não possui uma assinatura PDF válida.")

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination_path.name}.",
        suffix=".upload",
        dir=destination_path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination_path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return destination_path


def validate_startup_storage() -> list[StorageStatus]:
    for directory in (pdf_directory(), backup_directory(), private_directory()):
        directory.mkdir(parents=True, exist_ok=True)
        ensure_free_space(directory, operation="iniciar a aplicação")
    return storage_overview()


def main() -> int:
    try:
        statuses = validate_startup_storage()
    except (StorageConfigurationError, StorageCapacityError, OSError) as error:
        log_event(
            "storage_startup_failed",
            component="entrypoint",
            level="error",
            category="storage",
            message="Armazenamento persistente inválido.",
            issue_type=type(error).__name__,
        )
        return 1
    minimum = storage_limits().minimum_free_mb
    log_event(
        "storage_startup_succeeded",
        component="entrypoint",
        category="storage",
        area_count=len(statuses),
        minimum_free_mb=minimum,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
