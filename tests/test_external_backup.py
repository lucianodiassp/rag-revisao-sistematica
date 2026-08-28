from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend.app import external_backup
from backend.app.external_backup import (
    ExternalBackupConfigurationError,
    S3BackupStore,
    apply_local_retention,
    external_backup_is_stale,
    external_backup_run_is_stale,
    external_backup_configuration,
    load_external_backup_settings,
    next_scheduled_run,
    read_external_backup_status,
    request_external_backup_now,
    run_external_backup,
)


def _environment(**overrides):
    values = {
        "RAG_EXTERNAL_BACKUP_ENABLED": "true",
        "RAG_EXTERNAL_BACKUP_BUCKET": "rag-backups",
        "RAG_EXTERNAL_BACKUP_PREFIX": "instalacao-principal",
        "RAG_EXTERNAL_BACKUP_REGION": "auto",
        "RAG_EXTERNAL_BACKUP_ENDPOINT_URL": "https://s3.example.org",
        "RAG_EXTERNAL_BACKUP_ACCESS_KEY_ID": "access-id-valido",
        "RAG_EXTERNAL_BACKUP_SECRET_ACCESS_KEY": "segredo-externo-valido",
        "RAG_EXTERNAL_BACKUP_PASSWORD": "SenhaForteDoBackup-2026!",
        "RAG_EXTERNAL_BACKUP_SCHEDULE_HOUR_UTC": "3",
        "RAG_EXTERNAL_BACKUP_RETRY_MINUTES": "60",
        "RAG_EXTERNAL_BACKUP_LOCAL_RETENTION": "3",
        "RAG_EXTERNAL_BACKUP_REMOTE_RETENTION": "14",
        "RAG_EXTERNAL_BACKUP_ADDRESSING_STYLE": "path",
    }
    values.update(overrides)
    return values


def test_disabled_external_backup_is_valid_and_safe_by_default():
    settings, errors = external_backup_configuration({})

    assert errors == []
    assert settings.enabled is False
    assert settings.public_summary()["credential_configured"] is False


def test_enabled_external_backup_requires_complete_secure_configuration():
    settings, errors = external_backup_configuration(
        {"RAG_EXTERNAL_BACKUP_ENABLED": "true"}
    )

    assert settings.enabled is True
    assert any("BUCKET" in error for error in errors)
    assert any("credenciais" in error for error in errors)
    assert any("PASSWORD" in error for error in errors)
    assert "segredo" not in " ".join(errors).lower()


def test_valid_configuration_exposes_only_operational_summary():
    settings = load_external_backup_settings(_environment())
    summary = settings.public_summary()

    assert settings.enabled is True
    assert summary["provider"] == "S3 compatível"
    assert summary["credential_configured"] is True
    assert settings.secret_access_key not in str(summary)
    assert settings.password not in str(summary)


def test_rejects_insecure_endpoint_and_invalid_retention():
    _, errors = external_backup_configuration(
        _environment(
            RAG_EXTERNAL_BACKUP_ENDPOINT_URL="http://s3.example.org",
            RAG_EXTERNAL_BACKUP_REMOTE_RETENTION="0",
        )
    )

    assert any("HTTPS" in error for error in errors)
    assert any("REMOTE_RETENTION" in error for error in errors)


def test_next_run_honors_daily_hour_and_failure_retry():
    settings = load_external_backup_settings(_environment())
    before = datetime(2026, 8, 28, 2, 0, tzinfo=timezone.utc)
    assert next_scheduled_run(settings, {}, now=before) == datetime(
        2026, 8, 28, 3, 0, tzinfo=timezone.utc
    )

    after = datetime(2026, 8, 28, 4, 0, tzinfo=timezone.utc)
    failed = {
        "state": "error",
        "last_attempt_at": "2026-08-28T03:30:00+00:00",
    }
    assert next_scheduled_run(settings, failed, now=after) == datetime(
        2026, 8, 28, 4, 30, tzinfo=timezone.utc
    )


def test_stale_status_is_detected_after_two_days():
    status = {"last_success_at": "2026-08-26T02:00:00+00:00"}

    assert external_backup_is_stale(
        status, now=datetime(2026, 8, 28, 3, 0, tzinfo=timezone.utc)
    ) is True


def test_interrupted_running_status_is_retried_and_detected():
    settings = load_external_backup_settings(_environment())
    status = {
        "state": "running",
        "last_attempt_at": "2026-08-28T03:00:00+00:00",
    }
    now = datetime(2026, 8, 28, 5, 30, tzinfo=timezone.utc)

    assert next_scheduled_run(settings, status, now=now) == now
    assert external_backup_run_is_stale(settings, status, now=now) is True


def test_manual_request_is_recorded_without_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("PRIVATE_DIRECTORY", str(tmp_path))
    settings = load_external_backup_settings(_environment())
    monkeypatch.setattr(external_backup, "load_external_backup_settings", lambda: settings)

    request_external_backup_now()

    content = (tmp_path / external_backup.REQUEST_FILENAME).read_text(encoding="utf-8")
    assert "requested_at" in content
    assert settings.password not in content
    assert settings.secret_access_key not in content


def test_local_retention_only_removes_scheduled_backups(tmp_path, monkeypatch):
    monkeypatch.setenv("BACKUP_DIRECTORY", str(tmp_path))
    settings = load_external_backup_settings(
        _environment(RAG_EXTERNAL_BACKUP_LOCAL_RETENTION="2")
    )
    manual = tmp_path / "backup-manual.ragbackup"
    manual.write_bytes(b"manual")
    scheduled = []
    for index in range(4):
        path = tmp_path / f"scheduled-backup-20260828-00000{index}-abcd.ragbackup"
        path.write_bytes(str(index).encode())
        path.touch()
        scheduled.append(path)

    deleted = apply_local_retention(settings)

    assert deleted == 2
    assert manual.is_file()
    assert sum(path.is_file() for path in scheduled) == 2


def test_run_uploads_verifies_and_records_safe_status(tmp_path, monkeypatch):
    backups = tmp_path / "backups"
    private = tmp_path / "private"
    backups.mkdir()
    monkeypatch.setenv("BACKUP_DIRECTORY", str(backups))
    monkeypatch.setenv("PRIVATE_DIRECTORY", str(private))
    settings = load_external_backup_settings(_environment())

    generated = backups / "scheduled-backup-20260828-030000-abcd.ragbackup"

    def fake_create(_password, prefix):
        assert prefix == "scheduled-backup"
        generated.write_bytes(b"backup criptografado")
        return {"path": generated, "size": generated.stat().st_size}

    class FakeStore:
        def upload_verified(self, path, digest):
            assert path == generated
            assert len(digest) == 64
            return f"instalacao-principal/{path.name}"

        def apply_retention(self):
            return 2

    monkeypatch.setattr(external_backup, "create_backup", fake_create)
    status = run_external_backup(settings, store=FakeStore())

    assert status["state"] == "success"
    assert status["remote_deleted"] == 2
    assert status["remote_key"].endswith(generated.name)
    persisted = read_external_backup_status()
    assert persisted["sha256"] == status["sha256"]
    assert settings.password not in str(persisted)


def test_run_records_safe_failure_without_raw_provider_message(tmp_path, monkeypatch):
    monkeypatch.setenv("BACKUP_DIRECTORY", str(tmp_path / "backups"))
    monkeypatch.setenv("PRIVATE_DIRECTORY", str(tmp_path / "private"))
    settings = load_external_backup_settings(_environment())

    def fail_create(*_args, **_kwargs):
        raise RuntimeError("secret_access_key=valor-que-nao-pode-aparecer")

    monkeypatch.setattr(external_backup, "create_backup", fail_create)
    with pytest.raises(external_backup.ExternalBackupError):
        run_external_backup(settings)

    status = read_external_backup_status()
    assert status["state"] == "error"
    assert "valor-que-nao-pode-aparecer" not in str(status)


def test_s3_upload_requires_size_and_digest_confirmation(tmp_path):
    settings = load_external_backup_settings(_environment())
    source = tmp_path / "scheduled-backup-test.ragbackup"
    source.write_bytes(b"conteudo")
    digest = external_backup._sha256(source)

    class FakeClient:
        def upload_file(self, filename, bucket, key, ExtraArgs):
            self.filename = filename
            self.bucket = bucket
            self.key = key
            self.metadata = ExtraArgs["Metadata"]

        def head_object(self, Bucket, Key):
            return {"ContentLength": source.stat().st_size, "Metadata": self.metadata}

    client = FakeClient()
    key = S3BackupStore(settings, client=client).upload_verified(source, digest)

    assert key.endswith(source.name)
    assert client.bucket == settings.bucket
    assert client.metadata["sha256"] == digest


def test_remote_retention_deletes_only_expired_scheduled_objects():
    settings = load_external_backup_settings(
        _environment(RAG_EXTERNAL_BACKUP_REMOTE_RETENTION="2")
    )
    now = datetime(2026, 8, 28, tzinfo=timezone.utc)

    class FakePaginator:
        def paginate(self, Bucket, Prefix):
            assert Bucket == settings.bucket
            assert Prefix.endswith("scheduled-backup-")
            return [
                {
                    "Contents": [
                        {
                            "Key": f"{Prefix}{index}.ragbackup",
                            "LastModified": now.replace(day=index),
                        }
                        for index in range(1, 5)
                    ]
                }
            ]

    class FakeClient:
        def get_paginator(self, name):
            assert name == "list_objects_v2"
            return FakePaginator()

        def delete_objects(self, Bucket, Delete):
            self.deleted = [item["Key"] for item in Delete["Objects"]]
            return {"Deleted": Delete["Objects"]}

    client = FakeClient()
    deleted = S3BackupStore(settings, client=client).apply_retention()

    assert deleted == 2
    assert client.deleted[0].endswith("2.ragbackup")
    assert client.deleted[1].endswith("1.ragbackup")
