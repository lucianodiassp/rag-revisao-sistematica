from pathlib import Path

from backend.app.web_deployment import (
    main,
    validate_web_configuration,
    validate_web_files,
)


def _valid_environment():
    return {
        "RAG_DOMAIN": "rag.example.org",
        "RAG_DEPLOYMENT_PROFILE": "web_private",
        "RAG_USER_MODE": "single_user",
        "RAG_AUTH_ALLOWED_EMAILS": "pesquisador@example.org",
        "DB_NAME": "rag_systematic_review",
        "DB_USER": "rag_web_user",
        "DB_PASSWORD": "V4lida-Longa-Aleatoria-2026!",
    }


def _valid_auth():
    return {
        "redirect_uri": "https://rag.example.org/oauth2callback",
        "cookie_secret": "2GHf!9qLx8vN4bWs7KmP3cRt6YzA5dEu1IoJ",
        "client_id": "oidc-client-id-configurado",
        "client_secret": "credencial-oidc-real-9f3A7k",
        "server_metadata_url": (
            "https://accounts.google.com/.well-known/openid-configuration"
        ),
    }


def test_accepts_complete_web_configuration():
    assert validate_web_configuration(_valid_environment(), _valid_auth()) == []


def test_rejects_local_or_multi_user_profile():
    environment = _valid_environment()
    environment["RAG_DEPLOYMENT_PROFILE"] = "local"
    environment["RAG_USER_MODE"] = "multi_user"

    errors = validate_web_configuration(environment, _valid_auth())

    assert any("web_private" in error for error in errors)
    assert any("single_user" in error for error in errors)


def test_rejects_non_public_domain_and_redirect_without_https():
    environment = _valid_environment()
    environment["RAG_DOMAIN"] = "localhost:8501"
    auth = _valid_auth()
    auth["redirect_uri"] = "http://localhost:8501/oauth2callback"

    errors = validate_web_configuration(environment, auth)

    assert any("domínio público" in error for error in errors)
    assert any("auth.redirect_uri" in error for error in errors)


def test_rejects_weak_database_and_cookie_secrets():
    environment = _valid_environment()
    environment["DB_PASSWORD"] = "rag_password"
    auth = _valid_auth()
    auth["cookie_secret"] = "xxx"

    errors = validate_web_configuration(environment, auth)

    assert any("DB_PASSWORD" in error for error in errors)
    assert any("cookie_secret" in error for error in errors)


def test_rejects_missing_oidc_credentials_and_invalid_email():
    environment = _valid_environment()
    environment["RAG_AUTH_ALLOWED_EMAILS"] = "nao-e-email"
    auth = _valid_auth()
    auth["client_id"] = ""
    auth["client_secret"] = "change-me"
    auth["server_metadata_url"] = "http://provider.example.org/config"

    errors = validate_web_configuration(environment, auth)

    assert any("e-mail inválido" in error for error in errors)
    assert any("client_id" in error for error in errors)
    assert any("client_secret" in error for error in errors)
    assert any("server_metadata_url" in error for error in errors)


def test_validates_files_without_exposing_values(tmp_path):
    env_path = tmp_path / "web.env"
    env_path.write_text(
        "\n".join(f"{key}={value}" for key, value in _valid_environment().items()),
        encoding="utf-8",
    )
    auth = _valid_auth()
    secrets_path = tmp_path / "secrets.toml"
    secrets_path.write_text(
        "[auth]\n" + "\n".join(f'{key} = "{value}"' for key, value in auth.items()),
        encoding="utf-8",
    )

    assert validate_web_files(env_path, secrets_path) == []


def test_reports_missing_files_with_safe_messages(tmp_path):
    errors = validate_web_files(tmp_path / "missing.env", tmp_path / "missing.toml")

    assert errors == [
        "Arquivo de ambiente Web não encontrado.",
        "Arquivo OIDC secrets.toml não encontrado.",
    ]


def test_cli_returns_failure_without_printing_secret(tmp_path, capsys):
    env_path = tmp_path / "web.env"
    environment = _valid_environment()
    sensitive_password = "ValorQueNuncaPodeAparecer-2026"
    environment["DB_PASSWORD"] = sensitive_password
    environment["RAG_DOMAIN"] = "localhost"
    env_path.write_text(
        "\n".join(f"{key}={value}" for key, value in environment.items()),
        encoding="utf-8",
    )
    secrets_path = tmp_path / "secrets.toml"
    secrets_path.write_text("[auth]\nclient_secret = \"segredo\"", encoding="utf-8")

    exit_code = main(
        ["--env-file", str(env_path), "--secrets-file", str(secrets_path)]
    )
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "Configuração Web inválida" in output
    assert sensitive_password not in output
