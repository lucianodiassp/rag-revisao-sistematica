"""Contratos de administração de usuários e acesso por projeto."""

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from backend.app.user_access_admin import (
    accept_pending_invitations_for_user,
    invite_project_member,
    set_application_user_status,
    transfer_project_ownership,
)
from backend.app.user_identity import ApplicationUser, bind_current_user


USER_ID = "10000000-0000-0000-0000-000000000001"
TARGET_ID = "10000000-0000-0000-0000-000000000002"
PROJECT_ID = "20000000-0000-0000-0000-000000000001"
INVITATION_ID = "30000000-0000-0000-0000-000000000001"
ROOT = Path(__file__).resolve().parents[1]


def _user(*, operator=False):
    return ApplicationUser(
        USER_ID,
        "issuer",
        "subject",
        "owner@example.org",
        "Pessoa Proprietária",
        "active",
        operator,
    )


def _connection(fetchone_values=None, fetchall_values=None):
    connection = Mock()
    connection.__enter__ = Mock(return_value=connection)
    connection.__exit__ = Mock(return_value=False)
    cursor = Mock()
    cursor.__enter__ = Mock(return_value=cursor)
    cursor.__exit__ = Mock(return_value=False)
    cursor.fetchone.side_effect = fetchone_values or []
    cursor.fetchall.side_effect = fetchall_values or []
    connection.cursor.return_value = cursor
    return Mock(return_value=connection), connection, cursor


def teardown_function(_function=None):
    bind_current_user(None)


def test_invitation_requires_active_identity_before_database_access():
    factory = Mock()

    with pytest.raises(PermissionError, match="identidade ativa"):
        invite_project_member(
            PROJECT_ID,
            "reader@example.org",
            "viewer",
            connection_factory=factory,
        )

    factory.assert_not_called()


def test_owner_can_register_pending_invitation_without_storing_secret():
    bind_current_user(_user())
    now = datetime.now(timezone.utc)
    factory, _connection_object, cursor = _connection(
        [
            {"id": PROJECT_ID, "title": "Projeto", "role": "owner"},
            None,
            None,
            {
                "id": INVITATION_ID,
                "email": "reader@example.org",
                "role": "viewer",
                "status": "pending",
                "expires_at": now,
            },
            {"id": "event-1", "created_at": now},
        ]
    )

    result = invite_project_member(
        PROJECT_ID,
        " Reader@Example.org ",
        "viewer",
        connection_factory=factory,
    )

    assert result["accepted"] is False
    assert result["email"] == "reader@example.org"
    statements = [call.args[0] for call in cursor.execute.call_args_list]
    assert "membership.role = 'owner'" in statements[0]
    assert any("INSERT INTO project_invitations" in sql for sql in statements)
    event_call = next(
        call for call in cursor.execute.call_args_list
        if "INSERT INTO project_access_events" in call.args[0]
    )
    assert event_call.args[1][2] == "invited"
    assert "secret" not in " ".join(statements).lower()


def test_ownership_transfer_demotes_current_owner_before_promoting_target():
    bind_current_user(_user())
    now = datetime.now(timezone.utc)
    factory, _connection_object, cursor = _connection(
        [
            {"id": PROJECT_ID, "title": "Projeto crítico", "role": "owner"},
            {
                "role": "editor",
                "is_active": True,
                "email": "new-owner@example.org",
                "status": "active",
            },
            {"id": "event-2", "created_at": now},
        ]
    )

    result = transfer_project_ownership(
        PROJECT_ID,
        TARGET_ID,
        "Projeto crítico",
        connection_factory=factory,
    )

    statements = [call.args[0] for call in cursor.execute.call_args_list]
    demote_index = next(i for i, sql in enumerate(statements) if "SET role = 'editor'" in sql)
    promote_index = next(i for i, sql in enumerate(statements) if "SET role = 'owner'" in sql)
    assert demote_index < promote_index
    assert result["new_owner_email"] == "new-owner@example.org"
    assert any(
        "ownership_transferred" in str(call.args[1])
        for call in cursor.execute.call_args_list
    )


def test_operator_cannot_disable_account_that_still_owns_projects():
    operator = _user(operator=True)
    bind_current_user(operator)
    factory, _connection_object, cursor = _connection(
        [
            {
                "id": TARGET_ID,
                "email": "target@example.org",
                "display_name": "Alvo",
                "status": "active",
                "is_operator": False,
            },
            {"owned_projects": 1},
        ]
    )

    with patch(
        "backend.app.user_access_admin.require_installation_operator",
        return_value=operator,
    ):
        with pytest.raises(ValueError, match="Transfira a titularidade"):
            set_application_user_status(
                TARGET_ID, "disabled", connection_factory=factory
            )

    assert not any(
        "UPDATE application_users" in call.args[0]
        for call in cursor.execute.call_args_list
    )


def test_valid_invitation_is_accepted_on_verified_login_transaction():
    cursor = Mock()
    cursor.fetchall.return_value = [
        {
            "id": INVITATION_ID,
            "project_id": PROJECT_ID,
            "role": "editor",
            "title": "Projeto",
        }
    ]
    cursor.fetchone.return_value = {
        "id": "event-3",
        "created_at": datetime.now(timezone.utc),
    }

    accepted = accept_pending_invitations_for_user(
        cursor,
        user_id=TARGET_ID,
        email="Target@Example.org",
    )

    assert accepted == [INVITATION_ID]
    statements = [call.args[0] for call in cursor.execute.call_args_list]
    assert any("INSERT INTO project_memberships" in sql for sql in statements)
    assert any("status = 'accepted'" in sql for sql in statements)
    assert any("invitation_accepted" in str(call.args[1]) for call in cursor.execute.call_args_list)


def test_access_administration_migration_has_required_integrity_guards():
    migration = (
        ROOT / "database/scripts/024_user_access_administration.sql"
    ).read_text(encoding="utf-8")

    assert "project_invitations" in migration
    assert "WHERE status = 'pending'" in migration
    assert "role IN ('editor', 'viewer')" in migration
    assert "project_access_events" in migration
    assert "ownership_transferred" in migration
    assert "ON DELETE CASCADE" in migration
