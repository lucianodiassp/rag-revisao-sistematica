"""Barreira visual de autenticação aplicada antes da navegação Streamlit."""

from __future__ import annotations

import streamlit as st

from backend.app.auth import AuthConfigurationError, evaluate_access


def _oidc_is_configured() -> bool:
    try:
        return bool(st.secrets.get("auth"))
    except (FileNotFoundError, KeyError):
        return False


def _current_identity() -> dict:
    try:
        return st.user.to_dict()
    except (AttributeError, KeyError):
        return {}


def _render_configuration_error(message: str) -> None:
    st.title("🔐 Acesso à versão Web privada")
    st.error("A autenticação ainda não está configurada com segurança.")
    st.code(message, language=None)
    st.info(
        "Configure o provedor OIDC e o e-mail autorizado antes de disponibilizar "
        "esta implantação na Web."
    )
    st.stop()


def enforce_access(metadata: dict):
    """Interrompe a execução antes das páginas quando o acesso não for permitido."""

    if metadata["deployment_profile"] != "web_private":
        return None
    if not _oidc_is_configured():
        _render_configuration_error(
            "Arquivo .streamlit/secrets.toml sem a seção [auth]."
        )

    try:
        decision = evaluate_access(
            deployment_profile=metadata["deployment_profile"],
            user_mode=metadata["user_mode"],
            identity=_current_identity(),
        )
    except AuthConfigurationError as error:
        _render_configuration_error(str(error))

    if decision.code == "login_required":
        st.title("🔐 Acesso à versão Web privada")
        st.write(
            "Entre com a conta autorizada para acessar seus projetos de revisão "
            "sistemática."
        )
        if st.button("Entrar", type="primary"):
            st.login()
        st.stop()

    if not decision.authorized:
        st.title("⛔ Acesso não autorizado")
        if decision.code == "email_unverified":
            st.error("O provedor não confirmou a verificação do e-mail desta conta.")
        elif decision.code == "email_missing":
            st.error("O provedor não informou um e-mail para esta conta.")
        else:
            st.error("Esta conta não está autorizada a acessar a aplicação.")
        if decision.email:
            st.caption(f"Conta autenticada: {decision.email}")
        if st.button("Sair e usar outra conta"):
            st.logout()
        st.stop()

    st.sidebar.caption(f"Conectado como **{decision.display_name}**")
    st.sidebar.caption(decision.email)
    if st.sidebar.button("Sair", use_container_width=True):
        st.logout()
    return decision
