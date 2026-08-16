"""Backup completo, criptografado e restaurável da instalação local."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import struct
import subprocess
import tempfile
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

import psycopg2
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from backend.app.secret_store import get_master_key_path


BACKUP_FORMAT = "rag-systematic-review-full-backup"
BACKUP_VERSION = 1
BACKUP_EXTENSION = ".ragbackup"
MAGIC = b"RAGBACKUP\x01\n"
TAG_SIZE = 16
CHUNK_SIZE = 1024 * 1024
MIN_PASSWORD_LENGTH = 12
KDF_N = 2**15
KDF_R = 8
KDF_P = 1
MAX_MANIFEST_SIZE = 1024 * 1024


class BackupError(RuntimeError):
    """Erro seguro e apresentável durante backup ou validação."""


class RestoreError(RuntimeError):
    """Erro durante restauração, incluindo eventual rollback."""


@dataclass(frozen=True)
class DatabaseSettings:
    host: str
    port: str
    database: str
    user: str
    password: str

    @classmethod
    def from_environment(cls) -> "DatabaseSettings":
        return cls(
            host=os.getenv("DB_HOST", "localhost"),
            port=os.getenv("DB_PORT", "5432"),
            database=os.getenv("DB_NAME", "rag_systematic_review"),
            user=os.environ["DB_USER"],
            password=os.environ["DB_PASSWORD"],
        )

    def command_environment(self) -> dict[str, str]:
        environment = os.environ.copy()
        environment["PGPASSWORD"] = self.password
        return environment


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_pdf_directory() -> Path:
    return project_root() / "data" / "pdfs"


def default_backup_directory() -> Path:
    configured = os.getenv("BACKUP_DIRECTORY")
    return Path(configured).expanduser().resolve() if configured else project_root() / "data" / "backups"


def validate_backup_password(password: str) -> str:
    password = str(password or "")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(
            f"A senha do backup deve possuir ao menos {MIN_PASSWORD_LENGTH} caracteres."
        )
    if password.isspace():
        raise ValueError("A senha do backup não pode conter somente espaços.")
    return password


def _derive_key(password: str, salt: bytes, *, n=KDF_N, r=KDF_R, p=KDF_P) -> bytes:
    return Scrypt(salt=salt, length=32, n=n, r=r, p=p).derive(
        password.encode("utf-8")
    )


def encrypt_file(source: Path, destination: Path, password: str) -> None:
    password = validate_backup_password(password)
    salt = os.urandom(16)
    nonce = os.urandom(12)
    header = json.dumps(
        {
            "cipher": "AES-256-GCM",
            "kdf": "scrypt",
            "n": KDF_N,
            "r": KDF_R,
            "p": KDF_P,
            "salt": base64.urlsafe_b64encode(salt).decode("ascii"),
            "nonce": base64.urlsafe_b64encode(nonce).decode("ascii"),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    prefix = MAGIC + struct.pack(">I", len(header)) + header
    encryptor = Cipher(
        algorithms.AES(_derive_key(password, salt)), modes.GCM(nonce)
    ).encryptor()
    encryptor.authenticate_additional_data(prefix)

    destination.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as input_file, destination.open("wb") as output_file:
        output_file.write(prefix)
        while chunk := input_file.read(CHUNK_SIZE):
            output_file.write(encryptor.update(chunk))
        output_file.write(encryptor.finalize())
        output_file.write(encryptor.tag)


def decrypt_file(source: Path, destination: Path, password: str) -> None:
    password = validate_backup_password(password)
    total_size = source.stat().st_size
    try:
        with source.open("rb") as input_file:
            magic = input_file.read(len(MAGIC))
            if magic != MAGIC:
                raise BackupError("O arquivo não possui um formato de backup reconhecido.")
            length_bytes = input_file.read(4)
            if len(length_bytes) != 4:
                raise BackupError("Cabeçalho do backup incompleto.")
            header_length = struct.unpack(">I", length_bytes)[0]
            if header_length <= 0 or header_length > 64 * 1024:
                raise BackupError("Cabeçalho do backup inválido.")
            header_bytes = input_file.read(header_length)
            header = json.loads(header_bytes.decode("utf-8"))
            if header.get("cipher") != "AES-256-GCM" or header.get("kdf") != "scrypt":
                raise BackupError("Algoritmo de proteção do backup não suportado.")
            if (
                int(header.get("n", 0)) != KDF_N
                or int(header.get("r", 0)) != KDF_R
                or int(header.get("p", 0)) != KDF_P
            ):
                raise BackupError("Parâmetros de derivação do backup não suportados.")

            prefix_length = len(MAGIC) + 4 + header_length
            ciphertext_length = total_size - prefix_length - TAG_SIZE
            if ciphertext_length < 0:
                raise BackupError("Arquivo de backup truncado.")
            input_file.seek(total_size - TAG_SIZE)
            tag = input_file.read(TAG_SIZE)
            input_file.seek(prefix_length)

            salt = base64.urlsafe_b64decode(header["salt"])
            nonce = base64.urlsafe_b64decode(header["nonce"])
            if len(salt) != 16 or len(nonce) != 12:
                raise BackupError("Parâmetros criptográficos do backup inválidos.")
            key = _derive_key(
                password,
                salt,
                n=int(header["n"]),
                r=int(header["r"]),
                p=int(header["p"]),
            )
            decryptor = Cipher(algorithms.AES(key), modes.GCM(nonce, tag)).decryptor()
            decryptor.authenticate_additional_data(magic + length_bytes + header_bytes)

            destination.parent.mkdir(parents=True, exist_ok=True)
            remaining = ciphertext_length
            with destination.open("wb") as output_file:
                while remaining:
                    chunk = input_file.read(min(CHUNK_SIZE, remaining))
                    if not chunk:
                        raise BackupError("Arquivo de backup truncado.")
                    output_file.write(decryptor.update(chunk))
                    remaining -= len(chunk)
                output_file.write(decryptor.finalize())
    except BackupError:
        destination.unlink(missing_ok=True)
        raise
    except (InvalidTag, KeyError, ValueError, json.JSONDecodeError) as error:
        destination.unlink(missing_ok=True)
        raise BackupError("Senha incorreta ou arquivo de backup corrompido.") from error


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while chunk := file.read(CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def _entry_metadata(path: Path, archive_path: str) -> dict:
    return {
        "path": archive_path,
        "size": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _run(command: list[str], settings: DatabaseSettings) -> None:
    result = subprocess.run(
        command,
        env=settings.command_environment(),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "falha sem detalhes").strip()
        raise BackupError(f"Comando PostgreSQL falhou: {detail}")


def _dump_database(destination: Path, settings: DatabaseSettings) -> None:
    _run(
        [
            "pg_dump",
            "--host",
            settings.host,
            "--port",
            settings.port,
            "--username",
            settings.user,
            "--dbname",
            settings.database,
            "--format=custom",
            "--compress=6",
            "--no-owner",
            "--no-acl",
            "--lock-wait-timeout=10s",
            "--file",
            str(destination),
        ],
        settings,
    )


def _restore_database(source: Path, settings: DatabaseSettings) -> None:
    _run(
        [
            "pg_restore",
            "--host",
            settings.host,
            "--port",
            settings.port,
            "--username",
            settings.user,
            "--dbname",
            settings.database,
            "--clean",
            "--if-exists",
            "--single-transaction",
            "--exit-on-error",
            "--no-owner",
            "--no-acl",
            str(source),
        ],
        settings,
    )


def _run_migrations(settings: DatabaseSettings, scripts_directory: Path | None = None) -> None:
    scripts = Path(scripts_directory or project_root() / "database" / "scripts")
    for migration in sorted(scripts.glob("0*.sql")):
        _run(
            [
                "psql",
                "--host",
                settings.host,
                "--port",
                settings.port,
                "--username",
                settings.user,
                "--dbname",
                settings.database,
                "--set",
                "ON_ERROR_STOP=1",
                "--file",
                str(migration),
            ],
            settings,
        )


def _database_counts(settings: DatabaseSettings) -> dict[str, int]:
    tables = {
        "projects": "review_projects",
        "records": "retrieved_records",
        "papers": "deduplicated_papers",
        "chunks": "paper_chunks",
        "extractions": "extracted_evidence",
        "agent_interactions": "agent_interactions",
        "evaluation_runs": "evaluation_runs",
    }
    counts = {}
    with psycopg2.connect(
        host=settings.host,
        port=settings.port,
        database=settings.database,
        user=settings.user,
        password=settings.password,
    ) as connection, connection.cursor() as cursor:
        for label, table in tables.items():
            cursor.execute(f"SELECT count(*) FROM {table}")
            counts[label] = int(cursor.fetchone()[0])
    return counts


def _safe_archive_name(name: str) -> bool:
    path = PurePosixPath(name)
    return bool(name) and not path.is_absolute() and ".." not in path.parts and "\\" not in name


def _validate_zip(zip_path: Path) -> dict:
    try:
        with zipfile.ZipFile(zip_path, "r") as archive:
            names = archive.namelist()
            if any(not _safe_archive_name(name) for name in names):
                raise BackupError("O backup contém caminhos internos inseguros.")
            if len(names) != len(set(names)):
                raise BackupError("O backup contém componentes internos duplicados.")
            if names.count("manifest.json") != 1 or names.count("database.dump") != 1:
                raise BackupError("O backup não contém manifesto e banco únicos.")
            info = archive.getinfo("manifest.json")
            if info.file_size > MAX_MANIFEST_SIZE:
                raise BackupError("Manifesto do backup excede o limite permitido.")
            manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
            if manifest.get("format") != BACKUP_FORMAT:
                raise BackupError("Formato lógico do backup não reconhecido.")
            if manifest.get("version") != BACKUP_VERSION:
                raise BackupError("Versão do backup ainda não suportada por esta aplicação.")

            entries = manifest.get("entries") or []
            declared = [entry.get("path") for entry in entries]
            if len(declared) != len(set(declared)) or "database.dump" not in declared:
                raise BackupError("Manifesto contém entradas ausentes ou duplicadas.")
            if set(names) != set(declared) | {"manifest.json"}:
                raise BackupError("Conteúdo do arquivo não corresponde ao manifesto.")
            has_key = "private/master.key" in declared
            if bool(manifest.get("includes_master_key")) != has_key:
                raise BackupError("Manifesto inconsistente quanto à chave-mestra.")
            for entry in entries:
                name = entry["path"]
                if not _safe_archive_name(name):
                    raise BackupError("Manifesto contém caminho inseguro.")
                member = archive.getinfo(name)
                if member.file_size != int(entry["size"]):
                    raise BackupError(f"Tamanho divergente no componente {name}.")
                digest = hashlib.sha256()
                with archive.open(name) as file:
                    while chunk := file.read(CHUNK_SIZE):
                        digest.update(chunk)
                if digest.hexdigest() != entry["sha256"]:
                    raise BackupError(f"Integridade inválida no componente {name}.")
            if archive.testzip() is not None:
                raise BackupError("O ZIP interno do backup está corrompido.")
            return manifest
    except (zipfile.BadZipFile, KeyError, ValueError, json.JSONDecodeError) as error:
        raise BackupError("Conteúdo interno do backup inválido.") from error


def create_backup(
    password: str,
    *,
    settings: DatabaseSettings | None = None,
    pdf_directory: Path | None = None,
    master_key_path: Path | None = None,
    backup_directory: Path | None = None,
    prefix: str = "backup",
) -> dict:
    password = validate_backup_password(password)
    settings = settings or DatabaseSettings.from_environment()
    pdf_directory = Path(pdf_directory or default_pdf_directory()).resolve()
    master_key_path = Path(master_key_path or get_master_key_path()).resolve()
    backup_directory = Path(backup_directory or default_backup_directory()).resolve()
    backup_directory.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc)
    suffix = uuid.uuid4().hex[:8]
    filename = f"{prefix}-{timestamp:%Y%m%d-%H%M%S}-{suffix}{BACKUP_EXTENSION}"
    destination = backup_directory / filename
    temporary_destination = destination.with_suffix(destination.suffix + ".tmp")

    try:
        with tempfile.TemporaryDirectory(prefix=".backup-build-", dir=backup_directory) as temp:
            temp_directory = Path(temp)
            dump_path = temp_directory / "database.dump"
            zip_path = temp_directory / "payload.zip"
            _dump_database(dump_path, settings)

            components: list[tuple[Path, str]] = [(dump_path, "database.dump")]
            if master_key_path.is_file():
                components.append((master_key_path, "private/master.key"))
            if pdf_directory.is_dir():
                for pdf in sorted(pdf_directory.glob("*.pdf")):
                    if pdf.is_file():
                        components.append((pdf, f"pdfs/{pdf.name}"))

            entries = [_entry_metadata(path, archive_name) for path, archive_name in components]
            manifest = {
                "format": BACKUP_FORMAT,
                "version": BACKUP_VERSION,
                "created_at": timestamp.isoformat(),
                "database": {
                    "name": settings.database,
                    "counts": _database_counts(settings),
                },
                "pdf_count": sum(1 for _, name in components if name.startswith("pdfs/")),
                "includes_master_key": any(name == "private/master.key" for _, name in components),
                "entries": entries,
            }
            with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_STORED) as archive:
                for path, archive_name in components:
                    archive.write(path, archive_name)
                archive.writestr(
                    "manifest.json",
                    json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"),
                )
            encrypt_file(zip_path, temporary_destination, password)
            os.replace(temporary_destination, destination)
    except Exception:
        temporary_destination.unlink(missing_ok=True)
        destination.unlink(missing_ok=True)
        raise

    return {
        "path": destination,
        "filename": filename,
        "size": destination.stat().st_size,
        "manifest": manifest,
    }


def inspect_backup(source: Path, password: str) -> dict:
    source = Path(source).expanduser().resolve()
    if not source.is_file():
        raise BackupError("Arquivo de backup não encontrado.")
    with tempfile.TemporaryDirectory(prefix="rag-backup-inspect-") as temp:
        zip_path = Path(temp) / "payload.zip"
        decrypt_file(source, zip_path, password)
        return _validate_zip(zip_path)


def _extract_validated_components(zip_path: Path, destination: Path) -> dict:
    manifest = _validate_zip(zip_path)
    with zipfile.ZipFile(zip_path, "r") as archive:
        database_dump = destination / "database.dump"
        with archive.open("database.dump") as source, database_dump.open("wb") as target:
            shutil.copyfileobj(source, target, CHUNK_SIZE)

        pdf_stage = destination / "pdfs"
        pdf_stage.mkdir()
        for entry in manifest["entries"]:
            name = entry["path"]
            if name.startswith("pdfs/"):
                filename = PurePosixPath(name).name
                if not filename.lower().endswith(".pdf"):
                    raise BackupError("O backup contém um arquivo inesperado na área de PDFs.")
                with archive.open(name) as source, (pdf_stage / filename).open("wb") as target:
                    shutil.copyfileobj(source, target, CHUNK_SIZE)

        key_stage = None
        if manifest.get("includes_master_key"):
            key_stage = destination / "master.key"
            with archive.open("private/master.key") as source, key_stage.open("wb") as target:
                shutil.copyfileobj(source, target, CHUNK_SIZE)
    return {
        "manifest": manifest,
        "database_dump": database_dump,
        "pdf_stage": pdf_stage,
        "key_stage": key_stage,
    }


def _replace_pdfs(staged: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for current in destination.glob("*.pdf"):
        if current.is_file():
            current.unlink()
    for pdf in staged.glob("*.pdf"):
        shutil.copy2(pdf, destination / pdf.name)


def _replace_master_key(staged: Path | None, destination: Path) -> None:
    if staged is None:
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".restore.tmp")
    temporary.write_bytes(staged.read_bytes())
    try:
        os.chmod(temporary, 0o600)
    except OSError:
        pass
    os.replace(temporary, destination)


def _apply_zip(
    zip_path: Path,
    *,
    settings: DatabaseSettings,
    pdf_directory: Path,
    master_key_path: Path,
    scripts_directory: Path | None = None,
) -> dict:
    with tempfile.TemporaryDirectory(prefix="rag-backup-apply-") as temp:
        components = _extract_validated_components(zip_path, Path(temp))
        _restore_database(components["database_dump"], settings)
        _run_migrations(settings, scripts_directory)
        _replace_pdfs(components["pdf_stage"], pdf_directory)
        _replace_master_key(components["key_stage"], master_key_path)
        return components["manifest"]


def _decrypt_and_apply(
    source: Path,
    password: str,
    *,
    settings: DatabaseSettings,
    pdf_directory: Path,
    master_key_path: Path,
    scripts_directory: Path | None = None,
) -> dict:
    with tempfile.TemporaryDirectory(prefix="rag-backup-restore-") as temp:
        zip_path = Path(temp) / "payload.zip"
        decrypt_file(source, zip_path, password)
        return _apply_zip(
            zip_path,
            settings=settings,
            pdf_directory=pdf_directory,
            master_key_path=master_key_path,
            scripts_directory=scripts_directory,
        )


def restore_backup(
    source: Path,
    password: str,
    confirmation: str,
    *,
    settings: DatabaseSettings | None = None,
    pdf_directory: Path | None = None,
    master_key_path: Path | None = None,
    backup_directory: Path | None = None,
    scripts_directory: Path | None = None,
) -> dict:
    if confirmation != "RESTAURAR BACKUP":
        raise ValueError("Digite exatamente RESTAURAR BACKUP para autorizar a operação.")
    password = validate_backup_password(password)
    source = Path(source).expanduser().resolve()
    settings = settings or DatabaseSettings.from_environment()
    pdf_directory = Path(pdf_directory or default_pdf_directory()).resolve()
    master_key_path = Path(master_key_path or get_master_key_path()).resolve()
    backup_directory = Path(backup_directory or default_backup_directory()).resolve()

    manifest = inspect_backup(source, password)
    recovery = create_backup(
        password,
        settings=settings,
        pdf_directory=pdf_directory,
        master_key_path=master_key_path,
        backup_directory=backup_directory,
        prefix="pre-restore",
    )
    try:
        applied_manifest = _decrypt_and_apply(
            source,
            password,
            settings=settings,
            pdf_directory=pdf_directory,
            master_key_path=master_key_path,
            scripts_directory=scripts_directory,
        )
    except Exception as restore_error:
        try:
            _decrypt_and_apply(
                recovery["path"],
                password,
                settings=settings,
                pdf_directory=pdf_directory,
                master_key_path=master_key_path,
                scripts_directory=scripts_directory,
            )
        except Exception as rollback_error:
            raise RestoreError(
                "A restauração falhou e o retorno automático também falhou. "
                f"Use o backup de recuperação em {recovery['path']}. "
                f"Falha original: {restore_error}; rollback: {rollback_error}"
            ) from restore_error
        raise RestoreError(
            "A restauração falhou, mas o estado anterior foi recuperado automaticamente. "
            f"Detalhe: {restore_error}"
        ) from restore_error

    return {
        "manifest": applied_manifest or manifest,
        "recovery_path": recovery["path"],
    }
