"""Validação segura e sem vazamento da configuração da implantação Web."""

from __future__ import annotations

import argparse
import ipaddress
import re
from pathlib import Path
from typing import Mapping
from urllib.parse import urlparse

from dotenv import dotenv_values

from backend.app.auth import AuthConfigurationError, parse_allowed_emails

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib


_DOMAIN_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_DATABASE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]{0,62}$")
_PLACEHOLDER_PARTS = (
    "change-me",
    "troque-",
    "substitua-",
    "example",
    "exemplo",
    "password",
    "senha",
    "secret",
    "xxx",
)
_KNOWN_WEAK_PASSWORDS = {
    "postgres",
    "rag_password",
    "rag-password",
    "admin",
    "12345678",
}


def _text(value) -> str:
    return str(value or "").strip()


def _looks_like_placeholder(value) -> bool:
    normalized = _text(value).lower()
    return not normalized or any(part in normalized for part in _PLACEHOLDER_PARTS)


def _valid_public_domain(value: str) -> bool:
    domain = value.lower().rstrip(".")
    if not domain or len(domain) > 253 or "://" in domain or "/" in domain or ":" in domain:
        return False
    try:
        ipaddress.ip_address(domain)
        return False
    except ValueError:
        pass
    if domain == "localhost" or domain.endswith(
        (".localhost", ".local", ".internal", ".home.arpa")
    ):
        return False
    labels = domain.split(".")
    return len(labels) >= 2 and all(_DOMAIN_LABEL.fullmatch(label) for label in labels)


def _valid_https_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.netloc) and not parsed.username


def _configured_integer(
    environ: Mapping[str, object],
    name: str,
    *,
    minimum: int,
    maximum: int,
    errors: list[str],
) -> int | None:
    raw = _text(environ.get(name))
    try:
        value = int(raw)
    except ValueError:
        value = 0
    if value < minimum or value > maximum:
        errors.append(f"{name} deve estar entre {minimum} e {maximum} MB.")
        return None
    return value


def validate_web_configuration(
    environ: Mapping[str, object], auth_config: Mapping[str, object]
) -> list[str]:
    """Retorna erros seguros, sem incluir valores recebidos na resposta."""

    errors: list[str] = []
    domain = _text(environ.get("RAG_DOMAIN")).lower().rstrip(".")
    if not _valid_public_domain(domain):
        errors.append(
            "RAG_DOMAIN deve conter um domínio público, sem protocolo, porta ou caminho."
        )
    if _text(environ.get("RAG_DEPLOYMENT_PROFILE")) != "web_private":
        errors.append("RAG_DEPLOYMENT_PROFILE deve ser web_private.")
    if _text(environ.get("RAG_USER_MODE")) != "single_user":
        errors.append("A primeira versão Web exige RAG_USER_MODE=single_user.")

    try:
        emails = parse_allowed_emails(environ.get("RAG_AUTH_ALLOWED_EMAILS"))
        if len(emails) != 1:
            errors.append("RAG_AUTH_ALLOWED_EMAILS deve conter exatamente um e-mail.")
    except AuthConfigurationError:
        errors.append("RAG_AUTH_ALLOWED_EMAILS contém um e-mail inválido.")

    db_name = _text(environ.get("DB_NAME"))
    db_user = _text(environ.get("DB_USER"))
    db_password = _text(environ.get("DB_PASSWORD"))
    if not _DATABASE_IDENTIFIER.fullmatch(db_name):
        errors.append("DB_NAME está ausente ou possui formato inseguro.")
    if not _DATABASE_IDENTIFIER.fullmatch(db_user):
        errors.append("DB_USER está ausente ou possui formato inseguro.")
    if (
        len(db_password) < 16
        or db_password.lower() in _KNOWN_WEAK_PASSWORDS
        or _looks_like_placeholder(db_password)
        or db_password in {db_name, db_user}
    ):
        errors.append("DB_PASSWORD deve ser uma senha forte com pelo menos 16 caracteres.")

    server_upload = _configured_integer(
        environ,
        "RAG_MAX_UPLOAD_MB",
        minimum=1,
        maximum=10240,
        errors=errors,
    )
    pdf_upload = _configured_integer(
        environ,
        "RAG_MAX_PDF_UPLOAD_MB",
        minimum=1,
        maximum=10240,
        errors=errors,
    )
    backup_upload = _configured_integer(
        environ,
        "RAG_MAX_BACKUP_UPLOAD_MB",
        minimum=1,
        maximum=10240,
        errors=errors,
    )
    _configured_integer(
        environ,
        "RAG_MIN_FREE_STORAGE_MB",
        minimum=256,
        maximum=1024 * 1024,
        errors=errors,
    )
    if server_upload is not None and pdf_upload is not None and pdf_upload > server_upload:
        errors.append("RAG_MAX_PDF_UPLOAD_MB não pode exceder RAG_MAX_UPLOAD_MB.")
    if (
        server_upload is not None
        and backup_upload is not None
        and backup_upload > server_upload
    ):
        errors.append("RAG_MAX_BACKUP_UPLOAD_MB não pode exceder RAG_MAX_UPLOAD_MB.")

    redirect_uri = _text(auth_config.get("redirect_uri"))
    expected_redirect = f"https://{domain}/oauth2callback" if domain else ""
    if not expected_redirect or redirect_uri != expected_redirect:
        errors.append("auth.redirect_uri deve usar HTTPS, o domínio configurado e /oauth2callback.")

    cookie_secret = _text(auth_config.get("cookie_secret"))
    if (
        len(cookie_secret) < 32
        or len(set(cookie_secret)) < 12
        or _looks_like_placeholder(cookie_secret)
    ):
        errors.append("auth.cookie_secret deve ser uma chave aleatória forte.")
    if _looks_like_placeholder(auth_config.get("client_id")):
        errors.append("auth.client_id não foi configurado.")
    if _looks_like_placeholder(auth_config.get("client_secret")):
        errors.append("auth.client_secret não foi configurado.")
    if not _valid_https_url(_text(auth_config.get("server_metadata_url"))):
        errors.append("auth.server_metadata_url deve ser uma URL HTTPS válida.")

    return errors


def validate_web_files(env_file: Path | str, secrets_file: Path | str) -> list[str]:
    errors: list[str] = []
    env_path = Path(env_file)
    secrets_path = Path(secrets_file)
    if not env_path.is_file():
        errors.append("Arquivo de ambiente Web não encontrado.")
    if not secrets_path.is_file():
        errors.append("Arquivo OIDC secrets.toml não encontrado.")
    if errors:
        return errors

    try:
        environment = dotenv_values(env_path)
    except (OSError, ValueError):
        return ["Não foi possível ler o arquivo de ambiente Web."]
    try:
        with secrets_path.open("rb") as stream:
            secrets = tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError):
        return ["O arquivo OIDC secrets.toml não contém TOML válido."]

    auth_config = secrets.get("auth")
    if not isinstance(auth_config, Mapping):
        return ["O arquivo OIDC secrets.toml não contém a seção [auth]."]
    return validate_web_configuration(environment, auth_config)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", default="deploy/web.env")
    parser.add_argument("--secrets-file", default=".streamlit/secrets.toml")
    arguments = parser.parse_args(argv)
    errors = validate_web_files(arguments.env_file, arguments.secrets_file)
    if errors:
        print("Configuração Web inválida:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Configuração Web validada com segurança.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
