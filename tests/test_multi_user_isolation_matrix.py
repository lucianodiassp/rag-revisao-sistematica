"""Matriz negativa de identidade, projeto, papel e administração global."""

from unittest.mock import Mock, patch

import pytest

from backend.app import database, demo_project, reproducibility_import
from backend.app.user_identity import (
    ApplicationUser,
    bind_current_user,
    enforce_authenticated_identity,
    require_installation_operator,
    require_project_access,
)


PROJECT_A = "10000000-0000-0000-0000-00000000000a"
PROJECT_B = "10000000-0000-0000-0000-00000000000b"
OWNER_A = "20000000-0000-0000-0000-00000000000a"
EDITOR_A = "20000000-0000-0000-0000-00000000000b"
VIEWER_A = "20000000-0000-0000-0000-00000000000c"
OWNER_B = "20000000-0000-0000-0000-00000000000d"
OPERATOR = "20000000-0000-0000-0000-00000000000e"


def _user(user_id, *, operator=False, status="active"):
    return ApplicationUser(
        user_id,
        "test-issuer",
        f"subject:{user_id}",
        f"{user_id[-1]}@example.test",
        f"Pessoa {user_id[-1]}",
        status,
        operator,
    )


def _access_row(user_id, role, *, operator=False):
    return {
        "id": user_id,
        "identity_provider": "test-issuer",
        "subject": f"subject:{user_id}",
        "email": f"{user_id[-1]}@example.test",
        "display_name": f"Pessoa {user_id[-1]}",
        "status": "active",
        "is_operator": operator,
        "role": role,
    }


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


@pytest.mark.parametrize(
    ("actor", "project_id", "minimum_role", "database_row", "allowed"),
    [
        (_user(OWNER_A), PROJECT_A, "viewer", _access_row(OWNER_A, "owner"), True),
        (_user(OWNER_A), PROJECT_A, "editor", _access_row(OWNER_A, "owner"), True),
        (_user(OWNER_A), PROJECT_A, "owner", _access_row(OWNER_A, "owner"), True),
        (_user(EDITOR_A), PROJECT_A, "viewer", _access_row(EDITOR_A, "editor"), True),
        (_user(EDITOR_A), PROJECT_A, "editor", _access_row(EDITOR_A, "editor"), True),
        (_user(EDITOR_A), PROJECT_A, "owner", _access_row(EDITOR_A, "editor"), False),
        (_user(VIEWER_A), PROJECT_A, "viewer", _access_row(VIEWER_A, "viewer"), True),
        (_user(VIEWER_A), PROJECT_A, "editor", _access_row(VIEWER_A, "viewer"), False),
        (_user(VIEWER_A), PROJECT_A, "owner", _access_row(VIEWER_A, "viewer"), False),
        (_user(OWNER_B), PROJECT_B, "owner", _access_row(OWNER_B, "owner"), True),
        (_user(OWNER_A), PROJECT_B, "viewer", None, False),
        (_user(OWNER_B), PROJECT_A, "viewer", None, False),
        (_user(OPERATOR, operator=True), PROJECT_A, "viewer", None, False),
        (_user(EDITOR_A), PROJECT_A, "viewer", None, False),
    ],
    ids=[
        "owner-a-reads-a",
        "owner-a-edits-a",
        "owner-a-administers-a",
        "editor-a-reads-a",
        "editor-a-edits-a",
        "editor-a-cannot-administer-a",
        "viewer-a-reads-a",
        "viewer-a-cannot-edit-a",
        "viewer-a-cannot-administer-a",
        "owner-b-administers-b",
        "owner-a-cannot-read-b",
        "owner-b-cannot-read-a",
        "global-operator-has-no-project-bypass",
        "revoked-membership-has-no-residual-access",
    ],
)
def test_project_role_and_identity_isolation_matrix(
    actor,
    project_id,
    minimum_role,
    database_row,
    allowed,
):
    bind_current_user(actor)
    factory, cursor = _connection(database_row)

    if allowed:
        access = require_project_access(
            project_id,
            minimum_role,
            connection_factory=factory,
        )
        assert access.project_id == project_id
        assert access.user.id == actor.id
    else:
        with pytest.raises(PermissionError, match="permissão suficiente"):
            require_project_access(
                project_id,
                minimum_role,
                connection_factory=factory,
            )

    _sql, params = cursor.execute.call_args.args
    assert params == (project_id, actor.id)


def test_project_owner_without_operator_role_cannot_administer_installation():
    bind_current_user(_user(OWNER_A))
    factory = Mock()

    with pytest.raises(PermissionError, match="operador da instalação"):
        require_installation_operator(connection_factory=factory)

    factory.assert_not_called()


def test_disabled_identity_is_rejected_before_project_creation(monkeypatch):
    monkeypatch.setenv("RAG_USER_MODE", "multi_user")
    bind_current_user(_user(OWNER_A, status="disabled"))

    with pytest.raises(PermissionError, match="desativada"):
        enforce_authenticated_identity()


@pytest.mark.parametrize(
    ("operation", "gate_target", "protected_target"),
    [
        (
            lambda: database.criar_projeto("Projeto", "Pergunta"),
            "backend.app.database.enforce_authenticated_identity",
            "backend.app.database.get_connection",
        ),
        (
            lambda: reproducibility_import.import_reproducibility_package(b"package"),
            "backend.app.user_identity.enforce_authenticated_identity",
            "backend.app.reproducibility_import.validate_reproducibility_package",
        ),
        (
            demo_project.ensure_demo_project,
            "backend.app.user_identity.enforce_authenticated_identity",
            "backend.app.demo_project.build_demo_dataset",
        ),
    ],
    ids=["new-project", "reproducibility-import", "demo-project"],
)
def test_project_creation_flows_fail_closed_without_identity(
    monkeypatch,
    operation,
    gate_target,
    protected_target,
):
    monkeypatch.setenv("RAG_USER_MODE", "multi_user")
    bind_current_user(None)
    with (
        patch(gate_target, side_effect=PermissionError("identity required")) as gate,
        patch(protected_target) as protected_dependency,
    ):
        with pytest.raises(PermissionError, match="identity required"):
            operation()

    gate.assert_called_once_with()
    protected_dependency.assert_not_called()


@pytest.mark.parametrize(
    ("operation", "connection_target"),
    [
        (database.listar_projetos, "backend.app.database.get_connection"),
        (
            lambda: database.obter_projeto(PROJECT_A),
            "backend.app.database.get_connection",
        ),
    ],
    ids=["project-list", "project-detail"],
)
def test_project_queries_fail_closed_without_identity(
    monkeypatch,
    operation,
    connection_target,
):
    monkeypatch.setenv("RAG_USER_MODE", "multi_user")
    bind_current_user(None)
    with patch(connection_target) as connection:
        with pytest.raises(PermissionError, match="identidade autenticada"):
            operation()

    connection.assert_not_called()


def test_regular_project_creation_assigns_owner_in_same_transaction():
    bind_current_user(_user(OWNER_A))
    factory, cursor = _connection(None)

    with patch("backend.app.database.get_connection", factory):
        project_id = database.criar_projeto("Projeto isolado", "Pergunta científica")

    membership_call = next(
        call
        for call in cursor.execute.call_args_list
        if "INSERT INTO project_memberships" in call.args[0]
    )
    assert membership_call.args[1] == (project_id, OWNER_A)


def test_imported_project_assigns_owner_before_transaction_commit():
    bind_current_user(_user(OWNER_A))
    factory, cursor = _connection(None)
    prepared = {
        "project_id": PROJECT_A,
        "title": "Projeto importado",
        "source_project_id": "source-project",
    }
    validated = {
        "dataset": {},
        "manifest": {"generated_at": None, "application": {}, "counts": {}},
        "sha256": "a" * 64,
        "warnings": [],
    }

    with (
        patch.object(
            reproducibility_import,
            "validate_reproducibility_package",
            return_value=validated,
        ),
        patch.object(reproducibility_import, "_prepare_import", return_value=prepared),
        patch.object(reproducibility_import, "_insert_import") as insert_import,
    ):
        result = reproducibility_import.import_reproducibility_package(
            b"package",
            connection_factory=factory,
        )

    insert_import.assert_called_once()
    membership_call = next(
        call
        for call in cursor.execute.call_args_list
        if "INSERT INTO project_memberships" in call.args[0]
    )
    assert membership_call.args[1] == (PROJECT_A, OWNER_A)
    assert result["project_id"] == PROJECT_A


def test_demo_project_assigns_owner_in_creation_transaction(tmp_path):
    bind_current_user(_user(OWNER_A))
    factory, cursor = _connection(None)
    dataset = {"project_id": demo_project.DEMO_PROJECT_ID}

    with (
        patch.object(demo_project, "build_demo_dataset", return_value=dataset),
        patch.object(demo_project, "_insert_dataset") as insert_dataset,
        patch.object(
            demo_project,
            "_ensure_demo_pdfs",
            return_value={"created": 0},
        ),
        patch(
            "backend.app.prisma.salvar_snapshot_prisma",
            return_value={"snapshot_version": 1},
        ),
    ):
        result = demo_project.ensure_demo_project(
            connection_factory=factory,
            pdf_directory=tmp_path,
        )

    insert_dataset.assert_called_once_with(cursor, dataset)
    membership_call = next(
        call
        for call in cursor.execute.call_args_list
        if "INSERT INTO project_memberships" in call.args[0]
    )
    assert membership_call.args[1] == (demo_project.DEMO_PROJECT_ID, OWNER_A)
    assert result["project_id"] == demo_project.DEMO_PROJECT_ID
