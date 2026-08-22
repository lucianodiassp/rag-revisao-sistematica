"""Identidade versionada da aplicação, separada dos formatos de dados."""

from __future__ import annotations

import os
import re
from pathlib import Path


APPLICATION_NAME = "RAG para Revisão Sistemática"
SEMVER_PATTERN = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)
DEPLOYMENT_LABELS = {
    "local": "Local",
    "web_private": "Web privada",
}
USER_MODE_LABELS = {
    "single_user": "Usuário único",
    "multi_user": "Múltiplos usuários",
}


def version_file_path() -> Path:
    return Path(__file__).resolve().parents[2] / "VERSION"


def read_application_version(path: Path | str | None = None) -> str:
    source = Path(path or version_file_path())
    try:
        value = source.read_text(encoding="utf-8").strip()
    except OSError as error:
        raise RuntimeError(f"Arquivo de versão não encontrado: {source}") from error
    if not SEMVER_PATTERN.fullmatch(value):
        raise RuntimeError(f"Versão da aplicação inválida em {source}: {value!r}")
    return value


APP_VERSION = read_application_version()


def application_metadata(environ=None) -> dict:
    environment = os.environ if environ is None else environ
    deployment_profile = str(
        environment.get("RAG_DEPLOYMENT_PROFILE", "local")
    ).strip().lower()
    user_mode = str(environment.get("RAG_USER_MODE", "single_user")).strip().lower()
    if deployment_profile not in DEPLOYMENT_LABELS:
        raise RuntimeError(
            "RAG_DEPLOYMENT_PROFILE deve ser 'local' ou 'web_private'."
        )
    if user_mode not in USER_MODE_LABELS:
        raise RuntimeError("RAG_USER_MODE deve ser 'single_user' ou 'multi_user'.")
    return {
        "name": APPLICATION_NAME,
        "version": APP_VERSION,
        "deployment_profile": deployment_profile,
        "deployment_label": DEPLOYMENT_LABELS[deployment_profile],
        "user_mode": user_mode,
        "user_mode_label": USER_MODE_LABELS[user_mode],
    }


def application_caption(environ=None) -> str:
    metadata = application_metadata(environ=environ)
    return (
        f"Versão {metadata['version']} · {metadata['deployment_label']} · "
        f"{metadata['user_mode_label']}"
    )
