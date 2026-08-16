import hashlib
import json
import os
import zipfile

import pytest

import backend.app.backup_service as backup_service
from backend.app.backup_service import (
    BACKUP_FORMAT,
    BACKUP_VERSION,
    BackupError,
    DatabaseSettings,
    RestoreError,
    decrypt_file,
    encrypt_file,
    inspect_backup,
    restore_backup,
    validate_backup_password,
)


PASSWORD = "senha-forte-de-teste"


def test_encrypted_file_round_trip_uses_multiple_chunks(tmp_path):
    source = tmp_path / "source.bin"
    encrypted = tmp_path / "backup.ragbackup"
    restored = tmp_path / "restored.bin"
    content = os.urandom(2 * 1024 * 1024 + 137)
    source.write_bytes(content)

    encrypt_file(source, encrypted, PASSWORD)
    decrypt_file(encrypted, restored, PASSWORD)

    assert encrypted.read_bytes() != content
    assert restored.read_bytes() == content


def test_wrong_password_does_not_leave_decrypted_file(tmp_path):
    source = tmp_path / "source.bin"
    encrypted = tmp_path / "backup.ragbackup"
    restored = tmp_path / "restored.bin"
    source.write_bytes(b"conteudo protegido")
    encrypt_file(source, encrypted, PASSWORD)

    with pytest.raises(BackupError, match="Senha incorreta|corrompido"):
        decrypt_file(encrypted, restored, "outra-senha-forte")

    assert not restored.exists()


def test_inspect_backup_validates_manifest_and_hashes(tmp_path):
    dump = tmp_path / "database.dump"
    dump.write_bytes(b"dump de teste")
    entry = {
        "path": "database.dump",
        "size": dump.stat().st_size,
        "sha256": hashlib.sha256(dump.read_bytes()).hexdigest(),
    }
    manifest = {
        "format": BACKUP_FORMAT,
        "version": BACKUP_VERSION,
        "created_at": "2026-08-16T00:00:00+00:00",
        "database": {"name": "test", "counts": {"projects": 1}},
        "pdf_count": 0,
        "includes_master_key": False,
        "entries": [entry],
    }
    payload = tmp_path / "payload.zip"
    with zipfile.ZipFile(payload, "w") as archive:
        archive.write(dump, "database.dump")
        archive.writestr("manifest.json", json.dumps(manifest))
    encrypted = tmp_path / "valid.ragbackup"
    encrypt_file(payload, encrypted, PASSWORD)

    inspected = inspect_backup(encrypted, PASSWORD)

    assert inspected["database"]["counts"]["projects"] == 1
    assert inspected["includes_master_key"] is False


def test_inspect_backup_rejects_tampered_component(tmp_path):
    manifest = {
        "format": BACKUP_FORMAT,
        "version": BACKUP_VERSION,
        "created_at": "2026-08-16T00:00:00+00:00",
        "database": {"name": "test", "counts": {}},
        "pdf_count": 0,
        "includes_master_key": False,
        "entries": [
            {
                "path": "database.dump",
                "size": 13,
                "sha256": hashlib.sha256(b"dump original").hexdigest(),
            }
        ],
    }
    payload = tmp_path / "tampered.zip"
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr("database.dump", b"dump alterado")
        archive.writestr("manifest.json", json.dumps(manifest))
    encrypted = tmp_path / "tampered.ragbackup"
    encrypt_file(payload, encrypted, PASSWORD)

    with pytest.raises(BackupError, match="[Ii]ntegridade|[Tt]amanho"):
        inspect_backup(encrypted, PASSWORD)


def test_restore_requires_exact_confirmation(tmp_path):
    with pytest.raises(ValueError, match="RESTAURAR BACKUP"):
        restore_backup(tmp_path / "inexistente.ragbackup", PASSWORD, "restaurar")


def test_restore_failure_applies_automatic_recovery(tmp_path, monkeypatch):
    incoming = tmp_path / "incoming.ragbackup"
    recovery = tmp_path / "pre-restore.ragbackup"
    calls = []
    settings = DatabaseSettings("db", "5432", "test", "user", "password")
    manifest = {"format": BACKUP_FORMAT, "version": BACKUP_VERSION}

    monkeypatch.setattr(backup_service, "inspect_backup", lambda *_: manifest)
    monkeypatch.setattr(
        backup_service,
        "create_backup",
        lambda *_, **__: {"path": recovery},
    )

    def fake_apply(source, *_, **__):
        calls.append(source)
        if source == incoming.resolve():
            raise BackupError("falha simulada")
        return manifest

    monkeypatch.setattr(backup_service, "_decrypt_and_apply", fake_apply)

    with pytest.raises(RestoreError, match="recuperado automaticamente"):
        restore_backup(
            incoming,
            PASSWORD,
            "RESTAURAR BACKUP",
            settings=settings,
            pdf_directory=tmp_path / "pdfs",
            master_key_path=tmp_path / "master.key",
            backup_directory=tmp_path / "backups",
        )

    assert calls == [incoming.resolve(), recovery]


@pytest.mark.parametrize("password", ["", "curta", "            "])
def test_backup_password_rejects_weak_values(password):
    with pytest.raises(ValueError):
        validate_backup_password(password)
