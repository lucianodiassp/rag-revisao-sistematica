from unittest.mock import Mock, patch

from backend.app.auth import AccessDecision
from backend.app.database import listar_projetos, obter_projeto
from backend.app.user_identity import (
    ApplicationUser,
    bind_current_user,
    current_user_id,
    ensure_application_user,
    ensure_project_owner,
)


USER_ID = "10000000-0000-0000-0000-000000000001"
PROJECT_ID = "20000000-0000-0000-0000-000000000002"


def _connection(*, fetchone=None, fetchall=None, description=None):
    connection = Mock()
    connection.__enter__ = Mock(return_value=connection)
    connection.__exit__ = Mock(return_value=False)
    cursor = Mock()
    cursor.__enter__ = Mock(return_value=cursor)
    cursor.__exit__ = Mock(return_value=False)
    cursor.fetchone.return_value = fetchone
    cursor.fetchall.return_value = fetchall or []
    cursor.description = description or []
    connection.cursor.return_value = cursor
    return Mock(return_value=connection), cursor


def teardown_function(_function=None):
    bind_current_user(None)


def test_registers_oidc_user_and_claims_only_unassigned_projects_in_single_user_mode():
    factory, cursor = _connection(
        fetchone={
            "id": USER_ID,
            "identity_provider": "https://accounts.example.org",
            "subject": "subject-123",
            "email": "pesquisador@example.org",
            "display_name": "Pessoa Pesquisadora",
            "status": "active",
        }
    )
    decision = AccessDecision(
        required=True,
        authenticated=True,
        authorized=True,
        code="access_granted",
        email="pesquisador@example.org",
        display_name="Pessoa Pesquisadora",
        identity_provider="https://accounts.example.org",
        subject="subject-123",
    )

    user = ensure_application_user(
        decision,
        user_mode="single_user",
        connection_factory=factory,
    )

    assert user.id == USER_ID
    assert current_user_id() == USER_ID
    statements = [call.args[0] for call in cursor.execute.call_args_list]
    assert "INSERT INTO application_users" in statements[0]
    assert "NOT EXISTS" in statements[1]
    assert "INSERT INTO project_memberships" in statements[1]
    assert "UPDATE project_lifecycle_events" in statements[2]


def test_does_not_claim_legacy_projects_when_multi_user_mode_is_requested():
    factory, cursor = _connection(
        fetchone={
            "id": USER_ID,
            "identity_provider": "issuer",
            "subject": "subject",
            "email": "pessoa@example.org",
            "display_name": "Pessoa",
            "status": "active",
        }
    )
    decision = AccessDecision(
        required=True,
        authenticated=True,
        authorized=True,
        code="access_granted",
        email="pessoa@example.org",
        display_name="Pessoa",
        identity_provider="issuer",
        subject="subject",
    )

    ensure_application_user(
        decision,
        user_mode="multi_user",
        connection_factory=factory,
    )

    assert cursor.execute.call_count == 1


def test_assigns_new_project_to_current_user():
    bind_current_user(
        ApplicationUser(USER_ID, "local", "single-user", None, "Usuário local")
    )
    factory, cursor = _connection()

    assert ensure_project_owner(PROJECT_ID, connection_factory=factory) is True
    sql, params = cursor.execute.call_args.args
    assert "INSERT INTO project_memberships" in sql
    assert params == (PROJECT_ID, USER_ID)


def test_project_listing_is_scoped_to_current_membership():
    bind_current_user(
        ApplicationUser(USER_ID, "local", "single-user", None, "Usuário local")
    )
    row = (
        PROJECT_ID,
        "Projeto",
        "Pergunta",
        {},
        "draft_protocol",
        1,
        None,
        None,
        None,
        None,
        "owner",
    )
    factory, cursor = _connection(
        fetchall=[row],
        description=[
            ("id",),
            ("title",),
            ("question",),
            ("criteria_jsonb",),
            ("status",),
            ("protocol_version",),
            ("archived_at",),
            ("archived_reason",),
            ("created_at",),
            ("updated_at",),
            ("access_role",),
        ],
    )

    with patch("backend.app.database.get_connection", factory):
        projects = listar_projetos()

    sql, params = cursor.execute.call_args.args
    assert "JOIN project_memberships" in sql
    assert "membership.user_id = %s" in sql
    assert params == (USER_ID,)
    assert str(projects[0]["id"]) == PROJECT_ID
    assert projects[0]["access_role"] == "owner"


def test_project_lookup_fails_closed_for_current_user_without_membership():
    bind_current_user(
        ApplicationUser(USER_ID, "local", "single-user", None, "Usuário local")
    )
    factory, cursor = _connection(fetchone=None)

    with patch("backend.app.database.get_connection", factory):
        try:
            obter_projeto(PROJECT_ID)
        except ValueError as error:
            assert "sem acesso" in str(error)
        else:
            raise AssertionError("A consulta deveria falhar sem associação ao projeto.")

    sql, params = cursor.execute.call_args.args
    assert "project_memberships" in sql
    assert params == (PROJECT_ID, USER_ID)
