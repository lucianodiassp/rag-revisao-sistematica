from pathlib import Path
from types import SimpleNamespace

import pytest

import backend.app.storage_service as storage
from backend.app.storage_service import (
    MEBIBYTE,
    StorageCapacityError,
    StorageConfigurationError,
    ensure_free_space,
    ensure_upload_allowed,
    save_upload_atomic,
    storage_limits,
)


def _configure_limits(monkeypatch, *, server=200, pdf=100, backup=200, minimum=10):
    monkeypatch.setenv("RAG_MAX_UPLOAD_MB", str(server))
    monkeypatch.setenv("RAG_MAX_PDF_UPLOAD_MB", str(pdf))
    monkeypatch.setenv("RAG_MAX_BACKUP_UPLOAD_MB", str(backup))
    monkeypatch.setenv("RAG_MIN_FREE_STORAGE_MB", str(minimum))


def test_storage_limits_require_specific_limits_within_server_limit(monkeypatch):
    _configure_limits(monkeypatch, server=100, pdf=101)

    with pytest.raises(StorageConfigurationError, match="não pode exceder"):
        storage_limits()


def test_upload_rejects_empty_and_oversized_pdf(tmp_path, monkeypatch):
    _configure_limits(monkeypatch, pdf=1)
    monkeypatch.setattr(
        storage.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(total=100 * MEBIBYTE, used=0, free=100 * MEBIBYTE),
    )

    with pytest.raises(StorageCapacityError, match="vazio"):
        ensure_upload_allowed(0, "pdf", tmp_path)
    with pytest.raises(StorageCapacityError, match="limite de 1 MB"):
        ensure_upload_allowed(MEBIBYTE + 1, "pdf", tmp_path)


def test_free_space_preserves_configured_reserve(tmp_path, monkeypatch):
    _configure_limits(monkeypatch, minimum=10)
    monkeypatch.setattr(
        storage.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(total=20 * MEBIBYTE, used=9 * MEBIBYTE, free=11 * MEBIBYTE),
    )

    with pytest.raises(StorageCapacityError, match="reserva de segurança"):
        ensure_free_space(tmp_path, 2 * MEBIBYTE, operation="teste")


def test_atomic_pdf_upload_validates_signature_and_replaces_destination(
    tmp_path, monkeypatch
):
    _configure_limits(monkeypatch)
    monkeypatch.setattr(
        storage.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(total=100 * MEBIBYTE, used=0, free=100 * MEBIBYTE),
    )
    destination = tmp_path / "paper.pdf"
    destination.write_bytes(b"%PDF-versao-anterior")

    with pytest.raises(StorageCapacityError, match="assinatura PDF"):
        save_upload_atomic(b"arquivo incorreto", destination, kind="pdf")
    assert destination.read_bytes() == b"%PDF-versao-anterior"

    save_upload_atomic(b"%PDF-1.7\nconteudo", destination, kind="pdf")
    assert destination.read_bytes() == b"%PDF-1.7\nconteudo"
    assert list(tmp_path.glob("*.upload")) == []


def test_storage_paths_can_be_redirected_to_persistent_volumes(tmp_path, monkeypatch):
    pdfs = tmp_path / "pdfs"
    backups = tmp_path / "backups"
    private = tmp_path / "private"
    monkeypatch.setenv("PDF_DIRECTORY", str(pdfs))
    monkeypatch.setenv("BACKUP_DIRECTORY", str(backups))
    monkeypatch.setenv("PRIVATE_DIRECTORY", str(private))

    assert storage.pdf_directory() == pdfs.resolve()
    assert storage.backup_directory() == backups.resolve()
    assert storage.private_directory() == private.resolve()
