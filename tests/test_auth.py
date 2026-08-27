import pytest

from backend.app.auth import (
    AuthConfigurationError,
    evaluate_access,
    normalize_email,
    parse_allowed_emails,
)


def _web_access(identity=None, emails="pesquisador@example.org", user_mode="single_user"):
    return evaluate_access(
        deployment_profile="web_private",
        user_mode=user_mode,
        identity=identity,
        environ={"RAG_AUTH_ALLOWED_EMAILS": emails},
    )


def test_normalizes_and_deduplicates_allowed_emails():
    assert normalize_email(" Pesquisador@Example.ORG ") == "pesquisador@example.org"
    assert parse_allowed_emails(
        "Pesquisador@example.org; colaborador@example.org pesquisador@example.org"
    ) == ("pesquisador@example.org", "colaborador@example.org")


def test_rejects_invalid_allowed_email():
    with pytest.raises(AuthConfigurationError, match="E-mail inválido"):
        parse_allowed_emails("nao-e-um-email")


def test_local_profile_remains_accessible_without_auth_configuration():
    decision = evaluate_access(
        deployment_profile="local",
        user_mode="single_user",
        identity=None,
        environ={},
    )

    assert decision.authorized is True
    assert decision.required is False
    assert decision.code == "local_access"


def test_web_profile_fails_closed_without_allowlist():
    with pytest.raises(AuthConfigurationError, match="RAG_AUTH_ALLOWED_EMAILS"):
        evaluate_access(
            deployment_profile="web_private",
            user_mode="single_user",
            identity=None,
            environ={},
        )


def test_single_user_profile_requires_exactly_one_allowed_email():
    with pytest.raises(AuthConfigurationError, match="exatamente um e-mail"):
        _web_access(
            emails="primeiro@example.org,segundo@example.org",
            user_mode="single_user",
        )


def test_web_profile_requests_login_before_authorizing():
    decision = _web_access({"is_logged_in": False})

    assert decision.authenticated is False
    assert decision.authorized is False
    assert decision.code == "login_required"


@pytest.mark.parametrize(
    ("identity", "expected_code"),
    [
        ({"is_logged_in": True}, "email_missing"),
        (
            {
                "is_logged_in": True,
                "email": "pesquisador@example.org",
                "email_verified": False,
            },
            "email_unverified",
        ),
        (
            {"is_logged_in": True, "email": "outra-pessoa@example.org"},
            "email_not_allowed",
        ),
    ],
)
def test_web_profile_rejects_incomplete_or_unauthorized_identity(
    identity, expected_code
):
    decision = _web_access(identity)

    assert decision.authenticated is True
    assert decision.authorized is False
    assert decision.code == expected_code


def test_web_profile_authorizes_configured_email_case_insensitively():
    decision = _web_access(
        {
            "is_logged_in": True,
            "email": "Pesquisador@Example.ORG",
            "email_verified": True,
            "name": "Pessoa Pesquisadora",
        }
    )

    assert decision.authorized is True
    assert decision.code == "access_granted"
    assert decision.email == "pesquisador@example.org"
    assert decision.display_name == "Pessoa Pesquisadora"


def test_multi_user_policy_can_receive_more_than_one_explicit_email():
    decision = _web_access(
        {"is_logged_in": True, "email": "segundo@example.org"},
        emails="primeiro@example.org,segundo@example.org",
        user_mode="multi_user",
    )

    assert decision.authorized is True
