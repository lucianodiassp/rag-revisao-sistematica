import pytest

from backend.app.version import (
    APP_VERSION,
    application_caption,
    application_metadata,
    read_application_version,
    version_file_path,
)


def test_repository_version_is_valid_semver_and_single_source():
    assert APP_VERSION == "2.2.0-dev"
    assert read_application_version() == APP_VERSION
    assert version_file_path().name == "VERSION"


def test_application_metadata_identifies_local_single_user_profile():
    metadata = application_metadata({})

    assert metadata["version"] == "2.2.0-dev"
    assert metadata["deployment_profile"] == "local"
    assert metadata["deployment_label"] == "Local"
    assert metadata["user_mode"] == "single_user"
    assert application_caption({}) == "Versão 2.2.0-dev · Local · Usuário único"


def test_web_private_profile_is_ready_for_v2_configuration():
    metadata = application_metadata(
        {"RAG_DEPLOYMENT_PROFILE": "web_private", "RAG_USER_MODE": "single_user"}
    )

    assert metadata["deployment_label"] == "Web privada"
    assert metadata["user_mode_label"] == "Usuário único"


@pytest.mark.parametrize(
    "environment",
    [
        {"RAG_DEPLOYMENT_PROFILE": "public"},
        {"RAG_USER_MODE": "anonymous"},
    ],
)
def test_unknown_runtime_profile_fails_fast(environment):
    with pytest.raises(RuntimeError):
        application_metadata(environment)


def test_invalid_version_file_fails_fast(tmp_path):
    invalid = tmp_path / "VERSION"
    invalid.write_text("versao-final", encoding="utf-8")

    with pytest.raises(RuntimeError, match="Versão da aplicação inválida"):
        read_application_version(invalid)
