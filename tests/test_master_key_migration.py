import base64

import pytest

from scripts.migrate_master_key_to_docker import read_valid_key


def test_read_valid_key_accepts_fernet_format(tmp_path):
    expected = base64.urlsafe_b64encode(b"x" * 32)
    source = tmp_path / "master.key"
    source.write_bytes(expected + b"\n")

    assert read_valid_key(source) == expected


def test_read_valid_key_rejects_invalid_content(tmp_path):
    source = tmp_path / "master.key"
    source.write_text("not-a-fernet-key", encoding="utf-8")

    with pytest.raises(ValueError, match="Fernet válida"):
        read_valid_key(source)
