"""Administração segura de usuários, convites e papéis por projeto.

Esta camada prepara o compartilhamento futuro sem habilitar o perfil multiusuário.
Todas as mutações de projeto revalidam o proprietário dentro da mesma transação.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from psycopg2.extras import Json, RealDictCursor

from backend.app.auth import normalize_email, parse_allowed_emails
from backend.app.user_identity import (
    current_user,
    current_user_id,
    require_installation_operator,
    require_project_access,
)


ASSIGNABLE_PROJECT_ROLES = ("editor", "viewer")


def _factory(connection_factory=None):
    if connection_factory is not None:
        return connection_factory
    from backend.app.database import get_connection

    return get_connection


def _validated_email(value) -> str:
    email = normalize_email(value)
    try:
        parsed = parse_allowed_emails(email)
    except Exception as error:
        raise ValueError("Informe um e-mail válido para o convite.") from error
    if len(parsed) != 1 or parsed[0] != email:
        raise ValueError("Informe um único e-mail válido para o convite.")
    return email


def _validated_role(value) -> str:
    role = str(value or "").strip().lower()
    if role not in ASSIGNABLE_PROJECT_ROLES:
        raise ValueError("O papel deve ser editor ou leitor.")
    return role


def _require_owner(cursor, project_id, actor_id):
    cursor.execute(
        """
        SELECT project.id, project.title, membership.role
        FROM review_projects AS project
        JOIN project_memberships AS membership
          ON membership.project_id = project.id
        JOIN application_users AS application_user
          ON application_user.id = membership.user_id
        WHERE project.id = %s
          AND membership.user_id = %s
          AND membership.role = 'owner'
          AND membership.is_active = TRUE
          AND application_user.status = 'active'
        FOR UPDATE OF project, membership
        """,
        (str(project_id), str(actor_id)),
    )
    row = cursor.fetchone()
    if not row:
        raise PermissionError("Somente o proprietário pode administrar este projeto.")
    return dict(row)


def _record_event(
    cursor,
    *,
    project_id=None,
    project_title=None,
    action,
    actor_user_id,
    target_user_id=None,
    target_email=None,
    previous_role=None,
    new_role=None,
    details=None,
):
    cursor.execute(
        """
        INSERT INTO project_access_events
            (target_project_id, project_title, action, actor_user_id,
             target_user_id, target_email, previous_role, new_role, details_jsonb)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id, created_at
        """,
        (
            str(project_id) if project_id else None,
            project_title,
            action,
            str(actor_user_id),
            str(target_user_id) if target_user_id else None,
            target_email,
            previous_role,
            new_role,
            Json(details or {}),
        ),
    )
    return dict(cursor.fetchone())


def list_project_access(project_id, *, connection_factory=None) -> dict:
    """Lista membros, convites pendentes e recibos para o proprietário."""

    access = require_project_access(
        project_id,
        "owner",
        connection_factory=_factory(connection_factory),
    )
    factory = _factory(connection_factory)
    with factory() as connection, connection.cursor(
        cursor_factory=RealDictCursor
    ) as cursor:
        cursor.execute(
            "SELECT id, title FROM review_projects WHERE id = %s",
            (str(project_id),),
        )
        project = cursor.fetchone()
        if not project:
            raise ValueError("Projeto não encontrado.")
        cursor.execute(
            """
            SELECT application_user.id, application_user.email,
                   application_user.display_name, application_user.status,
                   application_user.is_operator, membership.role,
                   membership.is_active, membership.updated_at
            FROM project_memberships AS membership
            JOIN application_users AS application_user
              ON application_user.id = membership.user_id
            WHERE membership.project_id = %s
            ORDER BY CASE membership.role
                WHEN 'owner' THEN 1 WHEN 'editor' THEN 2 ELSE 3 END,
                lower(application_user.display_name)
            """,
            (str(project_id),),
        )
        members = [dict(row) for row in cursor.fetchall()]
        cursor.execute(
            """
            UPDATE project_invitations
            SET status = 'expired', updated_at = CURRENT_TIMESTAMP
            WHERE project_id = %s AND status = 'pending'
              AND expires_at <= CURRENT_TIMESTAMP
            """,
            (str(project_id),),
        )
        cursor.execute(
            """
            SELECT id, email, role, status, expires_at, created_at
            FROM project_invitations
            WHERE project_id = %s AND status = 'pending'
            ORDER BY created_at DESC
            """,
            (str(project_id),),
        )
        invitations = [dict(row) for row in cursor.fetchall()]
        cursor.execute(
            """
            SELECT id, action, target_email, previous_role, new_role, created_at
            FROM project_access_events
            WHERE target_project_id = %s
            ORDER BY created_at DESC
            LIMIT 30
            """,
            (str(project_id),),
        )
        events = [dict(row) for row in cursor.fetchall()]
    return {
        "project": dict(project),
        "members": members,
        "invitations": invitations,
        "events": events,
        "actor_role": access.role,
    }


def invite_project_member(
    project_id,
    email,
    role,
    *,
    expires_in_days=7,
    connection_factory=None,
) -> dict:
    """Registra uma pré-autorização; contas existentes recebem acesso já."""

    actor = current_user()
    if not actor or actor.status != "active":
        raise PermissionError("Não há identidade ativa para criar o convite.")
    email = _validated_email(email)
    role = _validated_role(role)
    if actor.email and normalize_email(actor.email) == email:
        raise ValueError("O proprietário já possui acesso ao projeto.")
    days = int(expires_in_days)
    if days < 1 or days > 30:
        raise ValueError("A validade do convite deve ficar entre 1 e 30 dias.")
    expires_at = datetime.now(timezone.utc) + timedelta(days=days)
    factory = _factory(connection_factory)
    with factory() as connection, connection.cursor(
        cursor_factory=RealDictCursor
    ) as cursor:
        project = _require_owner(cursor, project_id, actor.id)
        cursor.execute(
            """
            SELECT id, email, status
            FROM application_users
            WHERE lower(email) = %s
            ORDER BY created_at ASC
            LIMIT 1
            FOR UPDATE
            """,
            (email,),
        )
        target = cursor.fetchone()
        if target and target["status"] != "active":
            raise ValueError("A conta correspondente está desativada.")
        if target:
            cursor.execute(
                """
                SELECT role, is_active FROM project_memberships
                WHERE project_id = %s AND user_id = %s
                FOR UPDATE
                """,
                (str(project_id), str(target["id"])),
            )
            membership = cursor.fetchone()
            if membership and membership["is_active"]:
                raise ValueError("Esta pessoa já possui acesso ativo ao projeto.")

        cursor.execute(
            """
            UPDATE project_invitations
            SET role = %s, expires_at = %s, invited_by_user_id = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE project_id = %s AND lower(email) = %s AND status = 'pending'
            RETURNING id, email, role, status, expires_at
            """,
            (role, expires_at, actor.id, str(project_id), email),
        )
        invitation = cursor.fetchone()
        if not invitation:
            cursor.execute(
                """
                INSERT INTO project_invitations
                    (project_id, email, role, status, invited_by_user_id, expires_at)
                VALUES (%s, %s, %s, 'pending', %s, %s)
                RETURNING id, email, role, status, expires_at
                """,
                (str(project_id), email, role, actor.id, expires_at),
            )
            invitation = cursor.fetchone()

        accepted = False
        if target:
            cursor.execute(
                """
                INSERT INTO project_memberships
                    (project_id, user_id, role, is_active, updated_at)
                VALUES (%s, %s, %s, TRUE, CURRENT_TIMESTAMP)
                ON CONFLICT (project_id, user_id) DO UPDATE
                SET role = EXCLUDED.role, is_active = TRUE,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (str(project_id), str(target["id"]), role),
            )
            cursor.execute(
                """
                UPDATE project_invitations
                SET status = 'accepted', accepted_by_user_id = %s,
                    accepted_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (str(target["id"]), str(invitation["id"])),
            )
            accepted = True
        event = _record_event(
            cursor,
            project_id=project_id,
            project_title=project["title"],
            action="invitation_accepted" if accepted else "invited",
            actor_user_id=actor.id,
            target_user_id=target["id"] if target else None,
            target_email=email,
            new_role=role,
            details={"invitation_id": str(invitation["id"]), "expires_in_days": days},
        )
    result = dict(invitation)
    result.update({"accepted": accepted, "event_id": str(event["id"])})
    return result


def revoke_project_invitation(invitation_id, *, connection_factory=None) -> dict:
    actor = current_user()
    if not actor or actor.status != "active":
        raise PermissionError("Não há identidade ativa para revogar o convite.")
    factory = _factory(connection_factory)
    with factory() as connection, connection.cursor(
        cursor_factory=RealDictCursor
    ) as cursor:
        cursor.execute(
            """
            SELECT invitation.id, invitation.project_id, invitation.email,
                   invitation.role, invitation.status, project.title
            FROM project_invitations AS invitation
            JOIN review_projects AS project ON project.id = invitation.project_id
            WHERE invitation.id = %s
            FOR UPDATE OF invitation, project
            """,
            (str(invitation_id),),
        )
        invitation = cursor.fetchone()
        if not invitation:
            raise ValueError("Convite não encontrado.")
        project = _require_owner(cursor, invitation["project_id"], actor.id)
        if invitation["status"] != "pending":
            raise ValueError("Somente convites pendentes podem ser revogados.")
        cursor.execute(
            """
            UPDATE project_invitations
            SET status = 'revoked', updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (str(invitation_id),),
        )
        event = _record_event(
            cursor,
            project_id=invitation["project_id"],
            project_title=project["title"],
            action="invitation_revoked",
            actor_user_id=actor.id,
            target_email=invitation["email"],
            previous_role=invitation["role"],
        )
    return {"event_id": str(event["id"]), "email": invitation["email"]}


def change_project_member_role(
    project_id, target_user_id, role, *, connection_factory=None
) -> dict:
    actor = current_user()
    if not actor or actor.status != "active":
        raise PermissionError("Não há identidade ativa para alterar o acesso.")
    role = _validated_role(role)
    factory = _factory(connection_factory)
    with factory() as connection, connection.cursor(
        cursor_factory=RealDictCursor
    ) as cursor:
        project = _require_owner(cursor, project_id, actor.id)
        cursor.execute(
            """
            SELECT membership.role, membership.is_active, application_user.email
            FROM project_memberships AS membership
            JOIN application_users AS application_user
              ON application_user.id = membership.user_id
            WHERE membership.project_id = %s AND membership.user_id = %s
            FOR UPDATE OF membership
            """,
            (str(project_id), str(target_user_id)),
        )
        membership = cursor.fetchone()
        if not membership or not membership["is_active"]:
            raise ValueError("A associação informada não está ativa.")
        if membership["role"] == "owner":
            raise ValueError("Use a transferência de titularidade para alterar o proprietário.")
        previous_role = membership["role"]
        cursor.execute(
            """
            UPDATE project_memberships
            SET role = %s, updated_at = CURRENT_TIMESTAMP
            WHERE project_id = %s AND user_id = %s
            """,
            (role, str(project_id), str(target_user_id)),
        )
        event = _record_event(
            cursor,
            project_id=project_id,
            project_title=project["title"],
            action="role_changed",
            actor_user_id=actor.id,
            target_user_id=target_user_id,
            target_email=membership["email"],
            previous_role=previous_role,
            new_role=role,
        )
    return {"event_id": str(event["id"]), "role": role}


def revoke_project_membership(
    project_id, target_user_id, *, connection_factory=None
) -> dict:
    actor = current_user()
    if not actor or actor.status != "active":
        raise PermissionError("Não há identidade ativa para revogar o acesso.")
    factory = _factory(connection_factory)
    with factory() as connection, connection.cursor(
        cursor_factory=RealDictCursor
    ) as cursor:
        project = _require_owner(cursor, project_id, actor.id)
        cursor.execute(
            """
            SELECT membership.role, membership.is_active, application_user.email
            FROM project_memberships AS membership
            JOIN application_users AS application_user
              ON application_user.id = membership.user_id
            WHERE membership.project_id = %s AND membership.user_id = %s
            FOR UPDATE OF membership
            """,
            (str(project_id), str(target_user_id)),
        )
        membership = cursor.fetchone()
        if not membership or not membership["is_active"]:
            raise ValueError("A associação informada não está ativa.")
        if membership["role"] == "owner":
            raise ValueError("Transfira a titularidade antes de remover o proprietário.")
        cursor.execute(
            """
            UPDATE project_memberships
            SET is_active = FALSE, updated_at = CURRENT_TIMESTAMP
            WHERE project_id = %s AND user_id = %s
            """,
            (str(project_id), str(target_user_id)),
        )
        event = _record_event(
            cursor,
            project_id=project_id,
            project_title=project["title"],
            action="membership_revoked",
            actor_user_id=actor.id,
            target_user_id=target_user_id,
            target_email=membership["email"],
            previous_role=membership["role"],
        )
    return {"event_id": str(event["id"]), "email": membership["email"]}


def transfer_project_ownership(
    project_id,
    target_user_id,
    confirmation_title,
    *,
    connection_factory=None,
) -> dict:
    """Troca o proprietário atomicamente e mantém o anterior como editor."""

    actor = current_user()
    if not actor or actor.status != "active":
        raise PermissionError("Não há identidade ativa para transferir o projeto.")
    if str(target_user_id) == actor.id:
        raise ValueError("Escolha outra pessoa para receber a titularidade.")
    factory = _factory(connection_factory)
    with factory() as connection, connection.cursor(
        cursor_factory=RealDictCursor
    ) as cursor:
        project = _require_owner(cursor, project_id, actor.id)
        if str(confirmation_title or "").strip() != str(project["title"]):
            raise ValueError("Digite exatamente o título do projeto para confirmar.")
        cursor.execute(
            """
            SELECT membership.role, membership.is_active, application_user.email,
                   application_user.status
            FROM project_memberships AS membership
            JOIN application_users AS application_user
              ON application_user.id = membership.user_id
            WHERE membership.project_id = %s AND membership.user_id = %s
            FOR UPDATE OF membership, application_user
            """,
            (str(project_id), str(target_user_id)),
        )
        target = cursor.fetchone()
        if not target or not target["is_active"] or target["status"] != "active":
            raise ValueError("O novo proprietário deve ser um membro ativo do projeto.")
        previous_role = target["role"]
        if previous_role == "owner":
            raise ValueError("A pessoa selecionada já é proprietária.")
        cursor.execute(
            """
            UPDATE project_memberships
            SET role = 'editor', updated_at = CURRENT_TIMESTAMP
            WHERE project_id = %s AND user_id = %s AND role = 'owner'
            """,
            (str(project_id), actor.id),
        )
        cursor.execute(
            """
            UPDATE project_memberships
            SET role = 'owner', is_active = TRUE, updated_at = CURRENT_TIMESTAMP
            WHERE project_id = %s AND user_id = %s
            """,
            (str(project_id), str(target_user_id)),
        )
        event = _record_event(
            cursor,
            project_id=project_id,
            project_title=project["title"],
            action="ownership_transferred",
            actor_user_id=actor.id,
            target_user_id=target_user_id,
            target_email=target["email"],
            previous_role=previous_role,
            new_role="owner",
            details={"previous_owner_new_role": "editor"},
        )
    return {"event_id": str(event["id"]), "new_owner_email": target["email"]}


def accept_pending_invitations_for_user(cursor, *, user_id, email) -> list[str]:
    """Aceita convites válidos dentro da transação que registra o login."""

    email = normalize_email(email)
    if not email:
        return []
    cursor.execute(
        """
        UPDATE project_invitations
        SET status = 'expired', updated_at = CURRENT_TIMESTAMP
        WHERE lower(email) = %s AND status = 'pending'
          AND expires_at <= CURRENT_TIMESTAMP
        """,
        (email,),
    )
    cursor.execute(
        """
        SELECT invitation.id, invitation.project_id, invitation.role,
               project.title
        FROM project_invitations AS invitation
        JOIN review_projects AS project ON project.id = invitation.project_id
        WHERE lower(invitation.email) = %s
          AND invitation.status = 'pending'
          AND invitation.expires_at > CURRENT_TIMESTAMP
        ORDER BY invitation.created_at
        FOR UPDATE OF invitation, project
        """,
        (email,),
    )
    invitations = [dict(row) for row in cursor.fetchall()]
    accepted_ids = []
    for invitation in invitations:
        cursor.execute(
            """
            INSERT INTO project_memberships
                (project_id, user_id, role, is_active, updated_at)
            VALUES (%s, %s, %s, TRUE, CURRENT_TIMESTAMP)
            ON CONFLICT (project_id, user_id) DO UPDATE
            SET role = CASE
                    WHEN project_memberships.role = 'owner' THEN 'owner'
                    ELSE EXCLUDED.role
                END,
                is_active = TRUE,
                updated_at = CURRENT_TIMESTAMP
            """,
            (str(invitation["project_id"]), str(user_id), invitation["role"]),
        )
        cursor.execute(
            """
            UPDATE project_invitations
            SET status = 'accepted', accepted_by_user_id = %s,
                accepted_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (str(user_id), str(invitation["id"])),
        )
        _record_event(
            cursor,
            project_id=invitation["project_id"],
            project_title=invitation["title"],
            action="invitation_accepted",
            actor_user_id=user_id,
            target_user_id=user_id,
            target_email=email,
            new_role=invitation["role"],
            details={"invitation_id": str(invitation["id"])},
        )
        accepted_ids.append(str(invitation["id"]))
    return accepted_ids


def list_application_users(*, connection_factory=None) -> list[dict]:
    factory = _factory(connection_factory)
    require_installation_operator(connection_factory=factory)
    with factory() as connection, connection.cursor(
        cursor_factory=RealDictCursor
    ) as cursor:
        cursor.execute(
            """
            SELECT application_user.id, application_user.email,
                   application_user.display_name, application_user.status,
                   application_user.is_operator, application_user.last_login_at,
                   COUNT(membership.project_id) FILTER (
                       WHERE membership.is_active = TRUE
                   ) AS active_projects,
                   COUNT(membership.project_id) FILTER (
                       WHERE membership.is_active = TRUE AND membership.role = 'owner'
                   ) AS owned_projects
            FROM application_users AS application_user
            LEFT JOIN project_memberships AS membership
              ON membership.user_id = application_user.id
            GROUP BY application_user.id
            ORDER BY application_user.status, lower(application_user.display_name)
            """
        )
        return [dict(row) for row in cursor.fetchall()]


def set_application_user_status(
    target_user_id, status, *, connection_factory=None
) -> dict:
    """Ativa/desativa conta sem permitir órfãos ou remover o último operador."""

    status = str(status or "").strip().lower()
    if status not in {"active", "disabled"}:
        raise ValueError("Estado de usuário inválido.")
    factory = _factory(connection_factory)
    operator = require_installation_operator(connection_factory=factory)
    if str(target_user_id) == operator.id:
        raise ValueError("O operador conectado não pode desativar a própria conta.")
    with factory() as connection, connection.cursor(
        cursor_factory=RealDictCursor
    ) as cursor:
        cursor.execute(
            """
            SELECT id, email, display_name, status, is_operator
            FROM application_users WHERE id = %s FOR UPDATE
            """,
            (str(target_user_id),),
        )
        target = cursor.fetchone()
        if not target:
            raise ValueError("Usuário não encontrado.")
        if status == "disabled":
            cursor.execute(
                """
                SELECT COUNT(*) AS owned_projects
                FROM project_memberships
                WHERE user_id = %s AND role = 'owner' AND is_active = TRUE
                """,
                (str(target_user_id),),
            )
            if int(cursor.fetchone()["owned_projects"] or 0):
                raise ValueError(
                    "Transfira a titularidade dos projetos antes de desativar esta conta."
                )
            if target["is_operator"]:
                cursor.execute(
                    """
                    SELECT COUNT(*) AS active_operators
                    FROM application_users
                    WHERE status = 'active' AND is_operator = TRUE
                    """
                )
                if int(cursor.fetchone()["active_operators"] or 0) <= 1:
                    raise ValueError("A instalação deve manter ao menos um operador ativo.")
        previous_status = target["status"]
        cursor.execute(
            """
            UPDATE application_users
            SET status = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (status, str(target_user_id)),
        )
        event = _record_event(
            cursor,
            action="user_enabled" if status == "active" else "user_disabled",
            actor_user_id=operator.id,
            target_user_id=target_user_id,
            target_email=target["email"],
            details={"previous_status": previous_status, "new_status": status},
        )
    return {"event_id": str(event["id"]), "status": status}
