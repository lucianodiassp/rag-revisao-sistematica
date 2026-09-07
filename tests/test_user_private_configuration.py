"""Isolamento de credenciais, preferências e clientes por identidade."""

from unittest.mock import Mock, patch

import pytest

from backend.app import ai_config, bibliographic_config
from backend.app.ai_admin_service import import_environment_provider_key
from backend.app.ai_config_repository import (
    get_installation_credential as get_ai_credential,
    save_installation_credential as save_ai_credential,
)
from backend.app.bibliographic_config_repository import get_installation_source_settings
from backend.app.gemini_client import clear_ai_client_cache, get_gemini_client
from backend.app.openai_client import clear_openai_client_cache, get_openai_client
from backend.app.bibliographic_admin_service import import_environment_source_key
from backend.app.user_identity import (
    ApplicationUser,
    bind_current_user,
    current_configuration_scope,
)


USER_A = "10000000-0000-0000-0000-000000000001"
USER_B = "10000000-0000-0000-0000-000000000002"


def _user(user_id):
    return ApplicationUser(user_id, "issuer", f"subject-{user_id}", None, "Pessoa")


def _connection(*, fetchone=None, fetchone_side_effect=None, fetchall=None, description=None):
    connection = Mock()
    connection.__enter__ = Mock(return_value=connection)
    connection.__exit__ = Mock(return_value=False)
    cursor = Mock()
    cursor.__enter__ = Mock(return_value=cursor)
    cursor.__exit__ = Mock(return_value=False)
    if fetchone_side_effect is not None:
        cursor.fetchone.side_effect = fetchone_side_effect
    else:
        cursor.fetchone.return_value = fetchone
    cursor.fetchall.return_value = fetchall or []
    cursor.description = description or []
    connection.cursor.return_value = cursor
    return Mock(return_value=connection), cursor


def teardown_function(_function=None):
    bind_current_user(None)
    ai_config.clear_ai_settings_cache()
    bibliographic_config.clear_bibliographic_settings_cache()
    clear_ai_client_cache()
    clear_openai_client_cache()


def test_configuration_scope_uses_current_identity(monkeypatch):
    monkeypatch.setenv("RAG_USER_MODE", "single_user")
    assert current_configuration_scope() == ("installation", None)

    bind_current_user(_user(USER_A))
    assert current_configuration_scope() == ("user", USER_A)


def test_configuration_scope_fails_closed_without_identity_in_multi_user(monkeypatch):
    monkeypatch.setenv("RAG_USER_MODE", "multi_user")

    with pytest.raises(PermissionError, match="identidade autenticada"):
        current_configuration_scope()


def test_ai_credential_query_is_scoped_to_current_user():
    bind_current_user(_user(USER_A))
    factory, cursor = _connection(fetchone=None)

    with patch("backend.app.ai_config_repository.get_connection", factory):
        assert get_ai_credential("openai") is None

    sql, params = cursor.execute.call_args.args
    assert "owner_user_id IS NOT DISTINCT FROM %s" in sql
    assert params == ("openai", "user", USER_A)


def test_ai_credential_insert_records_user_scope():
    bind_current_user(_user(USER_A))
    factory, cursor = _connection(fetchone_side_effect=[None, ("credential-id",)])

    with patch("backend.app.ai_config_repository.get_connection", factory):
        credential_id = save_ai_credential(
            "openai", "Chave", "segredo-cifrado", "final", "valid"
        )

    assert credential_id == "credential-id"
    insert_sql, insert_params = cursor.execute.call_args_list[1].args
    assert "scope_type, owner_user_id" in insert_sql
    assert insert_params[-2:] == ("user", USER_A)
    audit_sql, audit_params = cursor.execute.call_args_list[2].args
    assert "owner_user_id" in audit_sql
    assert audit_params[1:3] == ("user", USER_A)


def test_bibliographic_settings_query_is_scoped_to_current_user():
    bind_current_user(_user(USER_B))
    factory, cursor = _connection(fetchall=[])

    with patch("backend.app.bibliographic_config_repository.get_connection", factory):
        assert get_installation_source_settings() == {}

    sql, params = cursor.execute.call_args.args
    assert "owner_user_id IS NOT DISTINCT FROM %s" in sql
    assert params == ("user", USER_B)


def test_ai_settings_cache_does_not_cross_user_boundary():
    ai_config.clear_ai_settings_cache()
    with (
        patch("backend.app.ai_config.get_environment_ai_settings", return_value=object()),
        patch(
            "backend.app.ai_config._apply_database_overrides",
            side_effect=lambda _settings: current_configuration_scope()[1],
        ) as apply_overrides,
    ):
        bind_current_user(_user(USER_A))
        assert ai_config.get_ai_settings() == USER_A
        bind_current_user(_user(USER_B))
        assert ai_config.get_ai_settings() == USER_B
        bind_current_user(_user(USER_A))
        assert ai_config.get_ai_settings() == USER_A

    assert apply_overrides.call_count == 2


def test_gemini_client_cache_does_not_cross_user_boundary():
    clear_ai_client_cache()
    with (
        patch(
            "backend.app.gemini_client.get_provider_api_key",
            side_effect=lambda _provider: f"key-{current_configuration_scope()[1]}",
        ),
        patch(
            "backend.app.gemini_client.genai.Client",
            side_effect=lambda api_key: {"api_key": api_key},
        ) as client_factory,
    ):
        bind_current_user(_user(USER_A))
        client_a = get_gemini_client()
        bind_current_user(_user(USER_B))
        client_b = get_gemini_client()
        bind_current_user(_user(USER_A))
        assert get_gemini_client() is client_a

    assert client_a["api_key"] == f"key-{USER_A}"
    assert client_b["api_key"] == f"key-{USER_B}"
    assert client_factory.call_count == 2


def test_openai_client_cache_does_not_cross_user_boundary():
    clear_openai_client_cache()
    with (
        patch(
            "backend.app.openai_client.get_provider_api_key",
            side_effect=lambda _provider: f"key-{current_configuration_scope()[1]}",
        ),
        patch(
            "backend.app.openai_client.OpenAIResponsesClient",
            side_effect=lambda api_key: {"api_key": api_key},
        ) as client_factory,
    ):
        bind_current_user(_user(USER_A))
        client_a = get_openai_client()
        bind_current_user(_user(USER_B))
        client_b = get_openai_client()
        bind_current_user(_user(USER_A))
        assert get_openai_client() is client_a

    assert client_a["api_key"] == f"key-{USER_A}"
    assert client_b["api_key"] == f"key-{USER_B}"
    assert client_factory.call_count == 2


def test_multi_user_ai_does_not_fall_back_to_server_key(monkeypatch):
    monkeypatch.setenv("RAG_USER_MODE", "multi_user")
    monkeypatch.setenv("GEMINI_API_KEY", "server-secret")
    bind_current_user(_user(USER_A))
    ai_config.clear_ai_settings_cache()

    assert ai_config.get_environment_ai_settings().api_key is None

    with (
        patch(
            "backend.app.ai_config_repository.configuration_tables_available",
            return_value=True,
        ),
        patch(
            "backend.app.ai_config_repository.get_installation_credential",
            return_value=None,
        ),
    ):
        assert ai_config.get_provider_api_key("google_gemini") is None


def test_multi_user_bibliography_hides_server_key_and_email(monkeypatch):
    monkeypatch.setenv("RAG_USER_MODE", "multi_user")
    monkeypatch.setenv("OPENALEX_API_KEY", "server-secret")
    monkeypatch.setenv("BIBLIOGRAPHIC_CONTACT_EMAIL", "server@example.org")
    bind_current_user(_user(USER_A))
    bibliographic_config.clear_bibliographic_settings_cache()

    environment_config = bibliographic_config.get_environment_bibliographic_settings()[
        "openalex"
    ]
    assert environment_config.api_key is None
    assert environment_config.contact_email is None

    with patch(
        "backend.app.bibliographic_config_repository.bibliographic_tables_available",
        return_value=False,
    ):
        config = bibliographic_config.get_source_config("openalex")

    assert config.api_key is None
    assert config.contact_email is None
    assert config.credential_source == "not_configured"


def test_multi_user_cannot_import_server_credentials_without_identity(monkeypatch):
    monkeypatch.setenv("RAG_USER_MODE", "multi_user")
    monkeypatch.setenv("OPENAI_API_KEY", "server-secret")
    monkeypatch.setenv("OPENALEX_API_KEY", "server-secret")
    bind_current_user(None)

    with pytest.raises(PermissionError, match="identidade autenticada"):
        import_environment_provider_key("openai")
    with pytest.raises(PermissionError, match="identidade autenticada"):
        import_environment_source_key("openalex")


def test_disabled_identity_cannot_access_private_configuration():
    bind_current_user(
        ApplicationUser(USER_A, "issuer", "subject", None, "Pessoa", "disabled")
    )

    with pytest.raises(PermissionError, match="desativada"):
        current_configuration_scope()
