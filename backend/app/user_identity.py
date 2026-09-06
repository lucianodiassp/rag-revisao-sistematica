"""Identidade persistente e associação inicial entre usuários e projetos.

Esta camada prepara o isolamento multiusuário, mas não o habilita. O preflight Web
continua aceitando apenas ``single_user`` até que todas as operações por projeto
adotem autorização obrigatória no backend.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import asdict, dataclass
from typing import Mapping

from psycopg2.extras import RealDictCursor


LOCAL_IDENTITY_PROVIDER = "local"
LOCAL_IDENTITY_SUBJECT = "single-user-installation"
PROJECT_ROLES = ("owner", "editor", "viewer")
PROJECT_ROLE_LEVELS = {"viewer": 10, "editor": 20, "owner": 30}


@dataclass(frozen=True)
class ApplicationUser:
    id: str
    identity_provider: str
    subject: str
    email: str | None
    display_name: str
    status: str = "active"


@dataclass(frozen=True)
class ProjectAccess:
    project_id: str
    user: ApplicationUser
    role: str


_CURRENT_USER: ContextVar[ApplicationUser | None] = ContextVar(
    "rag_current_application_user",
    default=None,
)


def current_user() -> ApplicationUser | None:
    return _CURRENT_USER.get()


def current_user_id() -> str | None:
    user = current_user()
    return user.id if user else None


def bind_current_user(user: ApplicationUser | Mapping | None) -> ApplicationUser | None:
    if user is None:
        _CURRENT_USER.set(None)
        return None
    if not isinstance(user, ApplicationUser):
        user = ApplicationUser(
            id=str(user["id"]),
            identity_provider=str(user["identity_provider"]),
            subject=str(user["subject"]),
            email=str(user["email"]) if user.get("email") else None,
            display_name=str(user.get("display_name") or user.get("email") or "Usuário"),
            status=str(user.get("status") or "active"),
        )
    _CURRENT_USER.set(user)
    return user


def serialize_current_user() -> dict | None:
    user = current_user()
    return asdict(user) if user else None


def _normalized_identity(decision) -> tuple[str, str, str | None, str]:
    provider = str(
        getattr(decision, "identity_provider", None) or LOCAL_IDENTITY_PROVIDER
    ).strip()[:255]
    subject = str(
        getattr(decision, "subject", None) or LOCAL_IDENTITY_SUBJECT
    ).strip()[:512]
    email = str(getattr(decision, "email", None) or "").strip().lower() or None
    display_name = str(
        getattr(decision, "display_name", None) or email or "Usuário local"
    ).strip()[:255]
    if not provider or not subject:
        raise ValueError("A identidade autenticada não possui provedor e sujeito estáveis.")
    return provider, subject, email, display_name


def ensure_application_user(
    decision,
    *,
    user_mode: str,
    connection_factory=None,
) -> ApplicationUser:
    """Persiste a identidade e adota apenas projetos ainda sem proprietário.

    No modo atual de usuário único, essa adoção migra instalações existentes sem
    atribuir silenciosamente projetos que já pertençam a outra identidade.
    """

    if connection_factory is None:
        from backend.app.database import get_connection

        connection_factory = get_connection
    provider, subject, email, display_name = _normalized_identity(decision)
    with connection_factory() as connection, connection.cursor(
        cursor_factory=RealDictCursor
    ) as cursor:
        cursor.execute(
            """
            INSERT INTO application_users
                (identity_provider, subject, email, display_name, status,
                 last_login_at, updated_at)
            VALUES (%s, %s, %s, %s, 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (identity_provider, subject) DO UPDATE
            SET email = EXCLUDED.email,
                display_name = EXCLUDED.display_name,
                last_login_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            RETURNING id, identity_provider, subject, email, display_name, status
            """,
            (provider, subject, email, display_name),
        )
        row = dict(cursor.fetchone())
        if row.get("status") != "active":
            raise PermissionError("A identidade da aplicação está desativada.")
        user_id = str(row["id"])
        if user_mode == "single_user":
            cursor.execute(
                """
                INSERT INTO project_memberships (project_id, user_id, role, is_active)
                SELECT project.id, %s, 'owner', TRUE
                FROM review_projects AS project
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM project_memberships AS membership
                    WHERE membership.project_id = project.id
                      AND membership.is_active = TRUE
                )
                ON CONFLICT (project_id, user_id) DO UPDATE
                SET role = 'owner', is_active = TRUE, updated_at = CURRENT_TIMESTAMP
                """,
                (user_id,),
            )
            cursor.execute(
                """
                UPDATE project_lifecycle_events AS event
                SET owner_user_id = %s
                WHERE event.owner_user_id IS NULL
                  AND (
                    EXISTS (
                        SELECT 1 FROM project_memberships AS membership
                        WHERE membership.project_id = event.target_project_id
                          AND membership.user_id = %s
                    )
                    OR NOT EXISTS (
                        SELECT 1 FROM review_projects AS project
                        WHERE project.id = event.target_project_id
                    )
                  )
                """,
                (user_id, user_id),
            )
    row["id"] = user_id
    return bind_current_user(row)


def ensure_project_owner(project_id, *, connection_factory=None) -> bool:
    """Associa ao usuário corrente um projeto recém-criado pela interface."""

    user_id = current_user_id()
    if not user_id:
        return False
    if connection_factory is None:
        from backend.app.database import get_connection

        connection_factory = get_connection
    with connection_factory() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO project_memberships (project_id, user_id, role, is_active)
            VALUES (%s, %s, 'owner', TRUE)
            ON CONFLICT (project_id, user_id) DO UPDATE
            SET role = 'owner', is_active = TRUE, updated_at = CURRENT_TIMESTAMP
            """,
            (str(project_id), user_id),
        )
    return True


def require_project_access(
    project_id,
    minimum_role="viewer",
    *,
    user_id=None,
    bind=False,
    connection_factory=None,
) -> ProjectAccess:
    """Autoriza uma operação no projeto usando uma associação ativa.

    O identificador explícito é reservado a processos internos, como o worker.
    Chamadas da interface usam sempre a identidade vinculada à execução atual.
    """

    minimum_role = str(minimum_role).strip().lower()
    if minimum_role not in PROJECT_ROLE_LEVELS:
        raise ValueError(f"Papel mínimo inválido: {minimum_role}")
    actor_id = str(user_id or current_user_id() or "").strip()
    if not actor_id:
        raise PermissionError("Não há identidade ativa para acessar este projeto.")
    if connection_factory is None:
        from backend.app.database import get_connection

        connection_factory = get_connection
    with connection_factory() as connection, connection.cursor(
        cursor_factory=RealDictCursor
    ) as cursor:
        cursor.execute(
            """
            SELECT application_user.id, application_user.identity_provider,
                   application_user.subject, application_user.email,
                   application_user.display_name, application_user.status,
                   membership.role
            FROM project_memberships AS membership
            JOIN application_users AS application_user
              ON application_user.id = membership.user_id
            WHERE membership.project_id = %s
              AND membership.user_id = %s
              AND membership.is_active = TRUE
              AND application_user.status = 'active'
            """,
            (str(project_id), actor_id),
        )
        row = cursor.fetchone()
    role = str((row or {}).get("role") or "")
    if not row or PROJECT_ROLE_LEVELS.get(role, 0) < PROJECT_ROLE_LEVELS[minimum_role]:
        raise PermissionError(
            "A identidade atual não possui permissão suficiente para este projeto."
        )
    user = ApplicationUser(
        id=str(row["id"]),
        identity_provider=str(row["identity_provider"]),
        subject=str(row["subject"]),
        email=str(row["email"]) if row.get("email") else None,
        display_name=str(row["display_name"]),
        status=str(row["status"]),
    )
    if bind:
        bind_current_user(user)
    return ProjectAccess(project_id=str(project_id), user=user, role=role)
