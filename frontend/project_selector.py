import streamlit as st

from backend.app.database import listar_projetos


CHAVE_PROJETO_ATIVO = "active_project_id"
ACCESS_ROLE_LABELS = {
    "owner": "Proprietário",
    "editor": "Editor",
    "viewer": "Leitor",
}


def selecionar_projeto_ativo(obrigatorio=True):
    """Exibe o seletor compartilhado e retorna o projeto ativo da sessão."""
    projetos = listar_projetos()
    if not projetos:
        if obrigatorio:
            st.warning("Crie um projeto na página **Configuração Pesquisa** antes de continuar.")
            st.stop()
        return None

    projetos_por_id = {str(projeto["id"]): projeto for projeto in projetos}
    atual = st.session_state.get(CHAVE_PROJETO_ATIVO)
    if atual not in projetos_por_id:
        atual = next(iter(projetos_por_id))

    ids = list(projetos_por_id)
    selecionado = st.sidebar.selectbox(
        "Projeto ativo",
        options=ids,
        index=ids.index(atual),
        format_func=lambda projeto_id: projetos_por_id[projeto_id]["title"],
        key="project_selector_widget",
    )

    if selecionado != st.session_state.get(CHAVE_PROJETO_ATIVO):
        st.session_state[CHAVE_PROJETO_ATIVO] = selecionado
        st.session_state.pop("relatorio_compilado", None)

    projeto = projetos_por_id[selecionado]
    access_label = ACCESS_ROLE_LABELS.get(projeto.get("access_role"))
    access_suffix = f" · acesso: {access_label}" if access_label else ""
    st.sidebar.caption(
        f"Protocolo v{projeto['protocol_version']} · status: {projeto['status']}"
        f"{access_suffix}"
    )
    demo = ((projeto.get("criteria_jsonb") or {}).get("_demo") or {})
    if demo.get("seed_id"):
        st.sidebar.info(
            "🧪 **Projeto demonstrativo**\n\n"
            "Metadados reais e cartões de evidência gerados localmente. "
            "Não utilize seus resultados como conclusão científica."
        )
    return projeto
