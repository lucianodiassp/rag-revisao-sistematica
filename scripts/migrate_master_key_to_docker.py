"""Copia a chave-mestra local existente para o volume privado do Compose."""

from __future__ import annotations

import argparse
import base64
import hashlib
import os
import subprocess
import sys
from pathlib import Path


APP_NAME = "rag-revisao-sistematica"


def default_master_key_path() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / APP_NAME / "master.key"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME / "master.key"
    base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / APP_NAME / "master.key"


def read_valid_key(path: Path) -> bytes:
    key = path.expanduser().resolve().read_bytes().strip()
    try:
        decoded = base64.urlsafe_b64decode(key)
    except (ValueError, TypeError) as error:
        raise ValueError("O arquivo não contém uma chave Fernet válida.") from error
    if len(decoded) != 32:
        raise ValueError("O arquivo não contém uma chave Fernet válida.")
    return key


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Importa a chave-mestra da instalação manual no volume privado do Docker."
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=default_master_key_path(),
        help="Caminho alternativo para master.key.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Substitui uma chave diferente que já exista no volume Docker.",
    )
    args = parser.parse_args()

    source = args.source.expanduser().resolve()
    if not source.is_file():
        parser.error(f"Chave-mestra não encontrada em: {source}")

    key = read_valid_key(source)
    local_fingerprint = hashlib.sha256(key).hexdigest()
    current = subprocess.run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "app",
            "python",
            "-c",
            (
                "from pathlib import Path; import hashlib; "
                "p=Path('/app/data/private/master.key'); "
                "print(hashlib.sha256(p.read_bytes().strip()).hexdigest() "
                "if p.is_file() else '')"
            ),
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if current == local_fingerprint:
        print("O volume Docker já contém esta chave-mestra; nenhuma alteração foi feita.")
        return 0
    if current and not args.force:
        parser.error(
            "O volume Docker já contém uma chave diferente. Faça backup antes de "
            "usar --force ou mantenha a chave atual e recadastre as credenciais."
        )

    subprocess.run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "app",
            "sh",
            "-c",
            "umask 077; cat > /app/data/private/master.key",
        ],
        input=key + b"\n",
        check=True,
    )
    subprocess.run(["docker", "compose", "restart", "app"], check=True)
    print("Chave-mestra importada no volume privado; a aplicação foi reiniciada.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
