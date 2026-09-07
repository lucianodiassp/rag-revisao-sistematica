"""Autorização das operações globais da instalação."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from backend.app.installation_admin_service import (
    build_installation_health_report,
    create_installation_backup,
    inspect_installation_backup,
    request_installation_external_backup,
    restore_installation_backup,
)
from backend.app.user_identity import (
    ApplicationUser,
    bind_current_user,
    current_user_is_operator,
    require_installation_operator,
)


USER_ID = "10000000-0000-0000-0000-000000000001"
ROOT = Path(__file__).resolve().parents[1]


def _user(is_operator=False):
    return ApplicationUser(
        USER_ID,
        "issuer",
        "subject",
        "pessoa@example.org",
        "Pessoa",
        "active",
        is_operator,
    )


def _connection(row):
    connection = Mock()
    connection.__enter__ = Mock(return_value=connection)
    connection.__exit__ = Mock(return_value=False)
    cursor = Mock()
    cursor.__enter__ = Mock(return_value=cursor)
    cursor.__exit__ = Mock(return_value=False)
    cursor.fetchone.return_value = row
    connection.cursor.return_value = cursor
    return Mock(return_value=connection), cursor


def teardown_function(_function=None):
    bind_current_user(None)


def test_operator_flag_requires_active_bound_operator():
    assert current_user_is_operator() is False
    bind_current_user(_user(False))
    assert current_user_is_operator() is False
    bind_current_user(_user(True))
    assert current_user_is_operator() is True


def test_non_operator_is_rejected_before_database_access():
    bind_current_user(_user(False))
    factory = Mock()

    with pytest.raises(PermissionError, match="operador da instalação"):
        require_installation_operator(connection_factory=factory)

    factory.assert_not_called()


def test_operator_is_revalidated_in_database():
    bind_current_user(_user(True))
    factory, cursor = _connection(
        {
            "id": USER_ID,
            "identity_provider": "issuer",
            "subject": "subject",
            "email": "pessoa@example.org",
            "display_name": "Pessoa",
            "status": "active",
            "is_operator": True,
        }
    )

    operator = require_installation_operator(connection_factory=factory)

    assert operator.id == USER_ID
    assert operator.is_operator is True
    sql, params = cursor.execute.call_args.args
    assert "is_operator = TRUE" in sql
    assert "status = 'active'" in sql
    assert params == (USER_ID,)


def test_revoked_operator_is_rejected_at_action_time():
    bind_current_user(_user(True))
    factory, _cursor = _connection(None)

    with pytest.raises(PermissionError, match="operador da instalação"):
        require_installation_operator(connection_factory=factory)


@pytest.mark.parametrize(
    ("operation", "dependency"),
    [
        (lambda: create_installation_backup("senha-forte"), "create_backup"),
        (
            lambda: inspect_installation_backup("arquivo.ragbackup", "senha-forte"),
            "inspect_backup",
        ),
        (
            lambda: restore_installation_backup(
                "arquivo.ragbackup", "senha-forte", "RESTAURAR BACKUP"
            ),
            "restore_backup",
        ),
        (request_installation_external_backup, "request_external_backup_now"),
        (build_installation_health_report, "build_health_report"),
    ],
)
def test_admin_facade_denies_before_global_operation(operation, dependency):
    bind_current_user(_user(False))
    with patch(
        f"backend.app.installation_admin_service.{dependency}"
    ) as protected_dependency:
        with pytest.raises(PermissionError, match="operador da instalação"):
            operation()
    protected_dependency.assert_not_called()


def test_admin_facade_calls_dependency_after_authorization():
    with (
        patch(
            "backend.app.installation_admin_service.require_installation_operator"
        ),
        patch(
            "backend.app.installation_admin_service.build_health_report",
            return_value={"overall_status": "healthy"},
        ) as build_report,
    ):
        report = build_installation_health_report()

    assert report == {"overall_status": "healthy"}
    build_report.assert_called_once_with("full")


def test_operator_migration_promotes_only_the_sole_active_identity():
    migration = (
        ROOT / "database/scripts/023_installation_operator.sql"
    ).read_text(encoding="utf-8")

    assert "ADD COLUMN IF NOT EXISTS is_operator" in migration
    assert "HAVING COUNT(*) = 1" in migration
    assert "SET is_operator = TRUE" in migration
    assert "WHERE is_operator = TRUE" in migration
