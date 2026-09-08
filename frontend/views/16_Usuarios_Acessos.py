"""Administração de convites, membros e contas da instalação."""

from __future__ import annotations

import streamlit as st

from backend.app.database import listar_projetos
from backend.app.user_access_admin import (
    change_project_member_role,
    invite_project_member,
    list_application_users,
    list_project_access,
    revoke_project_invitation,
    revoke_project_membership,
    set_application_user_status,
    transfer_project_ownership,
)
from backend.app.user_identity import current_user, current_user_is_operator


ROLE_LABELS = {"owner": "Proprietário", "editor": "Editor", "viewer": "Leitor"}
ROLE_VALUES = {label: role for role, label in ROLE_LABELS.items() if role != "owner"}


def _flash(message, level="success"):
    st.session_state["access_admin_flash"] = (level, message)
    st.rerun()


def _show_error(error):
    if isinstance(error, (ValueError, PermissionError)):
        st.warning(str(error))
    else:
        st.error(f"Não foi possível concluir a operação: {error}")


st.title("👥 Usuários e Acessos")
st.write(
    "Administre quem poderá colaborar em cada projeto e qual será o papel de cada "
    "pessoa. Senhas e tokens de autenticação não são armazenados aqui."
)
st.info(
    "O modo multiusuário ainda não está liberado no servidor. Os convites abaixo "
    "funcionam como **pré-autorização por e-mail verificado** e não enviam mensagem "
    "automaticamente."
)

if flash := st.session_state.pop("access_admin_flash", None):
    getattr(st, flash[0])(flash[1])

projects = [
    item
    for item in listar_projetos(incluir_arquivados=True)
    if item.get("access_role") == "owner"
]

st.header("1. Acesso aos projetos")
if not projects:
    st.info("Você não possui projetos sob sua titularidade para administrar.")
else:
    by_id = {str(item["id"]): item for item in projects}
    selected_id = st.selectbox(
        "Projeto",
        options=list(by_id),
        format_func=lambda project_id: by_id[project_id]["title"],
        key="access_admin_project",
    )
    try:
        access = list_project_access(selected_id)
    except Exception as error:
        _show_error(error)
        st.stop()

    st.subheader("Membros")
    active_members = [item for item in access["members"] if item["is_active"]]
    st.dataframe(
        [
            {
                "Nome": item["display_name"],
                "E-mail": item.get("email") or "—",
                "Papel": ROLE_LABELS.get(item["role"], item["role"]),
                "Conta": "Ativa" if item["status"] == "active" else "Desativada",
            }
            for item in active_members
        ],
        use_container_width=True,
        hide_index=True,
    )

    manageable = [item for item in active_members if item["role"] != "owner"]
    if manageable:
        with st.expander("Alterar ou revogar acesso de um membro"):
            member_by_id = {str(item["id"]): item for item in manageable}
            member_id = st.selectbox(
                "Membro",
                options=list(member_by_id),
                format_func=lambda user_id: (
                    member_by_id[user_id].get("email")
                    or member_by_id[user_id]["display_name"]
                ),
                key="access_member",
            )
            member = member_by_id[member_id]
            role_labels = list(ROLE_VALUES)
            current_label = ROLE_LABELS.get(member["role"], "Leitor")
            selected_role_label = st.selectbox(
                "Papel",
                role_labels,
                index=role_labels.index(current_label),
                key="access_member_role",
            )
            left, right = st.columns(2)
            if left.button("Salvar novo papel", use_container_width=True):
                try:
                    change_project_member_role(
                        selected_id, member_id, ROLE_VALUES[selected_role_label]
                    )
                except Exception as error:
                    _show_error(error)
                else:
                    _flash("Papel atualizado e registrado no histórico de acesso.")
            if right.button("Revogar acesso", type="secondary", use_container_width=True):
                try:
                    revoke_project_membership(selected_id, member_id)
                except Exception as error:
                    _show_error(error)
                else:
                    _flash("Acesso revogado e registrado no histórico.")

    st.subheader("Convidar colaborador")
    with st.form("invite_project_member", clear_on_submit=True):
        invitation_email = st.text_input("E-mail verificado da pessoa")
        invitation_role_label = st.selectbox("Papel inicial", list(ROLE_VALUES))
        invitation_days = st.number_input(
            "Validade da pré-autorização (dias)", min_value=1, max_value=30, value=7
        )
        invitation_submitted = st.form_submit_button(
            "Registrar convite", use_container_width=True
        )
    if invitation_submitted:
        try:
            invitation = invite_project_member(
                selected_id,
                invitation_email,
                ROLE_VALUES[invitation_role_label],
                expires_in_days=invitation_days,
            )
        except Exception as error:
            _show_error(error)
        else:
            if invitation["accepted"]:
                _flash("A conta já existia e recebeu acesso imediatamente.")
            _flash(
                "Pré-autorização registrada. Nenhum e-mail foi enviado pela aplicação."
            )

    if access["invitations"]:
        st.subheader("Convites pendentes")
        for invitation in access["invitations"]:
            columns = st.columns([3, 2, 2, 1])
            columns[0].write(invitation["email"])
            columns[1].write(ROLE_LABELS[invitation["role"]])
            columns[2].write(str(invitation["expires_at"]))
            if columns[3].button(
                "Revogar",
                key=f"revoke_invitation_{invitation['id']}",
            ):
                try:
                    revoke_project_invitation(invitation["id"])
                except Exception as error:
                    _show_error(error)
                else:
                    _flash("Convite revogado e registrado no histórico.")

    st.subheader("Transferência de titularidade")
    st.warning(
        "A transferência é atômica: o novo proprietário assume o projeto e você "
        "permanece como editor. O projeto nunca fica sem proprietário."
    )
    eligible = [
        item
        for item in manageable
        if item["status"] == "active" and item["is_active"]
    ]
    if not eligible:
        st.caption("Adicione ao menos um membro ativo antes de transferir a titularidade.")
    else:
        eligible_by_id = {str(item["id"]): item for item in eligible}
        with st.form("transfer_project_ownership", clear_on_submit=True):
            new_owner_id = st.selectbox(
                "Novo proprietário",
                options=list(eligible_by_id),
                format_func=lambda user_id: (
                    eligible_by_id[user_id].get("email")
                    or eligible_by_id[user_id]["display_name"]
                ),
            )
            st.caption(
                f"Para confirmar, digite exatamente: **{access['project']['title']}**"
            )
            confirmation_title = st.text_input("Título do projeto")
            transfer_ack = st.checkbox(
                "Entendo que deixarei de ser o proprietário e permanecerei como editor."
            )
            transfer_submitted = st.form_submit_button(
                "Transferir titularidade",
                type="primary",
                use_container_width=True,
            )
        if transfer_submitted:
            try:
                if not transfer_ack:
                    raise ValueError(
                        "Confirme que compreendeu a mudança de titularidade."
                    )
                transfer_project_ownership(
                    selected_id, new_owner_id, confirmation_title
                )
            except Exception as error:
                _show_error(error)
            else:
                _flash("Titularidade transferida com recibo de auditoria.")

    with st.expander("Histórico de administração de acesso"):
        if access["events"]:
            st.dataframe(access["events"], use_container_width=True, hide_index=True)
        else:
            st.caption("Ainda não há eventos de administração para este projeto.")


if current_user_is_operator():
    st.divider()
    st.header("2. Contas da instalação")
    st.caption(
        "Somente o operador pode ativar ou desativar contas. Uma conta proprietária "
        "não pode ser desativada antes da transferência de seus projetos."
    )
    try:
        users = list_application_users()
    except Exception as error:
        _show_error(error)
    else:
        connected = current_user()
        st.dataframe(
            [
                {
                    "Nome": item["display_name"],
                    "E-mail": item.get("email") or "—",
                    "Estado": "Ativa" if item["status"] == "active" else "Desativada",
                    "Operador": "Sim" if item["is_operator"] else "Não",
                    "Projetos": item["active_projects"],
                    "Titular": item["owned_projects"],
                }
                for item in users
            ],
            use_container_width=True,
            hide_index=True,
        )
        controllable = [item for item in users if str(item["id"]) != connected.id]
        if controllable:
            user_by_id = {str(item["id"]): item for item in controllable}
            account_id = st.selectbox(
                "Conta a administrar",
                options=list(user_by_id),
                format_func=lambda user_id: (
                    user_by_id[user_id].get("email")
                    or user_by_id[user_id]["display_name"]
                ),
                key="installation_account",
            )
            account = user_by_id[account_id]
            target_status = "disabled" if account["status"] == "active" else "active"
            button_label = (
                "Desativar conta" if target_status == "disabled" else "Reativar conta"
            )
            if st.button(button_label, use_container_width=True):
                try:
                    set_application_user_status(account_id, target_status)
                except Exception as error:
                    _show_error(error)
                else:
                    _flash(f"Conta atualizada para o estado {target_status}.")
        else:
            st.caption("Não há outra conta registrada para administrar.")
