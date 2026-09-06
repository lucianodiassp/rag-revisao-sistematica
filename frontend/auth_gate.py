"""Barreira visual de autenticação aplicada antes da navegação Streamlit."""

from __future__ import annotations

import streamlit as st

from backend.app.auth import AuthConfigurationError, evaluate_access
from backend.app.observability import log_event
from backend.app.user_identity import (
    bind_current_user,
    ensure_application_user,
)


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
    log_event(
        "authentication_configuration_failed",
        component="app",
        level="error",
        category="configuration",
        message="A autenticação Web não está configurada.",
    )
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

    # Nunca reutilizar a identidade vinculada por uma execução anterior da thread.
    bind_current_user(None)
    is_web = metadata["deployment_profile"] == "web_private"
    if is_web and not _oidc_is_configured():
        _render_configuration_error(
            "Arquivo .streamlit/secrets.toml sem a seção [auth]."
        )

    identity = _current_identity() if is_web else None
    try:
        decision = evaluate_access(
            deployment_profile=metadata["deployment_profile"],
            user_mode=metadata["user_mode"],
            identity=identity,
        )
    except AuthConfigurationError as error:
        _render_configuration_error(str(error))

    if decision.code == "login_required":
        log_event(
            "authentication_required",
            component="app",
            category="authentication",
        )
        st.title("🔐 Acesso à versão Web privada")
        st.write(
            "Entre com a conta autorizada para acessar seus projetos de revisão "
            "sistemática."
        )
        if st.button("Entrar", type="primary"):
            st.login()
        st.stop()

    if not decision.authorized:
        log_event(
            "authentication_denied",
            component="app",
            level="warning",
            category="authentication",
            decision_code=decision.code,
        )
        st.title("⛔ Acesso não autorizado")
        if decision.code == "email_unverified":
            st.error("O provedor não confirmou a verificação do e-mail desta conta.")
        elif decision.code == "email_missing":
            st.error("O provedor não informou um e-mail para esta conta.")
        elif decision.code == "identity_subject_missing":
            st.error("O provedor não informou uma identidade estável para esta conta.")
        else:
            st.error("Esta conta não está autorizada a acessar a aplicação.")
        if decision.email:
            st.caption(f"Conta autenticada: {decision.email}")
        if st.button("Sair e usar outra conta"):
            st.logout()
        st.stop()

    identity_key = (
        decision.identity_provider,
        decision.subject,
        decision.email,
    )
    cached = st.session_state.get("application_user")
    if cached and tuple(cached.get("identity_key") or ()) != identity_key:
        for key in (
            "active_project_id",
            "project_selector_widget",
            "mensagens_por_projeto",
            "relatorio_compilado",
        ):
            st.session_state.pop(key, None)
    try:
        # A consulta em cada rerun é intencional: uma identidade desativada não
        # pode continuar autorizada apenas por estar presente na sessão do navegador.
        user = ensure_application_user(
            decision,
            user_mode=metadata["user_mode"],
        )
    except Exception:
        log_event(
            "user_scope_activation_failed",
            component="app",
            level="error",
            category="authentication",
        )
        st.error("Não foi possível preparar o escopo seguro dos projetos.")
        st.stop()
    st.session_state["application_user"] = {
        "identity_key": identity_key,
        "user": {
            "id": user.id,
            "identity_provider": user.identity_provider,
            "subject": user.subject,
            "email": user.email,
            "display_name": user.display_name,
            "status": user.status,
        }
    }

    if not st.session_state.get("authentication_success_logged"):
        log_event(
            "authentication_succeeded",
            component="app",
            category="authentication",
        )
        st.session_state["authentication_success_logged"] = True
    if is_web:
        st.sidebar.caption(f"Conectado como **{decision.display_name}**")
        st.sidebar.caption(decision.email)
        if st.sidebar.button("Sair", use_container_width=True):
            st.session_state.pop("application_user", None)
            bind_current_user(None)
            st.logout()
    return decision
