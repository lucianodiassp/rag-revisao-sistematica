import os
import sys

import streamlit as st


sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from backend.agentes.agente_formulador import estruturar_pergunta_pesquisa  # noqa: E402
from backend.app.bibliographic_config import get_bibliographic_settings  # noqa: E402
from backend.app.database import (  # noqa: E402
    criar_projeto,
    salvar_protocolo_projeto,
)
from backend.coleta.orquestrador_coleta import iniciar_recolha  # noqa: E402
from frontend.project_selector import (  # noqa: E402
    CHAVE_PROJETO_ATIVO,
    selecionar_projeto_ativo,
)


st.set_page_config(page_title="Configuração da Pesquisa", page_icon="⚙️", layout="wide")


with st.sidebar.expander("➕ Novo projeto", expanded=False):
    with st.form("form_novo_projeto"):
        novo_titulo = st.text_input("Título do projeto")
        nova_pergunta = st.text_area("Pergunta inicial")
        criar = st.form_submit_button("Criar projeto", type="primary")
        if criar:
            if not novo_titulo.strip() or not nova_pergunta.strip():
                st.warning("Informe o título e a pergunta inicial.")
            else:
                novo_id = criar_projeto(novo_titulo, nova_pergunta)
                st.session_state[CHAVE_PROJETO_ATIVO] = novo_id
                st.session_state["project_selector_widget"] = novo_id
                st.rerun()


projeto = selecionar_projeto_ativo(obrigatorio=False)

st.title("⚙️ Formulação da Pergunta de Pesquisa")

if projeto is None:
    st.info("Crie o primeiro projeto no painel lateral para iniciar a revisão.")
    st.stop()

project_id = str(projeto["id"])
protocolo_atual = projeto.get("criteria_jsonb") or {}

st.caption(f"Projeto ativo: **{projeto['title']}** · protocolo v{projeto['protocol_version']}")
st.markdown(
    "Defina o escopo da revisão. A IA ajuda a estruturar a pergunta em PICO e a "
    "gerar a estratégia de busca, mas cada versão permanece registrada para auditoria."
)
st.divider()

pergunta_livre = st.text_area(
    "Qual é a sua pergunta de pesquisa ou tema principal?",
    value=projeto.get("question") or "",
    height=100,
)

if st.button("🧠 Estruturar Pergunta (IA)", type="primary"):
    if not pergunta_livre.strip():
        st.warning("Digite uma pergunta ou tema de pesquisa.")
    else:
        with st.spinner("A estruturar a pergunta e gerar a estratégia de busca..."):
            resultado = estruturar_pergunta_pesquisa(pergunta_livre, project_id)

        if resultado:
            resultado["audit_questions"] = protocolo_atual.get("audit_questions", [])
            versao = salvar_protocolo_projeto(
                project_id,
                pergunta_livre,
                resultado,
                motivo="Estruturação da pergunta pela IA com confirmação humana",
            )
            st.session_state[f"protocol_preview_{project_id}"] = resultado
            st.success(f"Protocolo salvo como versão {versao}.")
            protocolo_atual = resultado
        else:
            st.error("Não foi possível gerar a estrutura. Tente novamente.")

protocolo_exibido = st.session_state.get(f"protocol_preview_{project_id}", protocolo_atual)

if protocolo_exibido.get("pico"):
    st.subheader("1. Estrutura PICO")
    col1, col2, col3, col4 = st.columns(4)
    col1.info(f"**População (P):**\n{protocolo_exibido['pico'].get('population', '')}")
    col2.success(f"**Intervenção (I):**\n{protocolo_exibido['pico'].get('intervention', '')}")
    col3.warning(f"**Comparação (C):**\n{protocolo_exibido['pico'].get('comparison', '')}")
    col4.error(f"**Desfecho (O):**\n{protocolo_exibido['pico'].get('outcome', '')}")

    st.subheader("2. Critérios de elegibilidade")
    inclusao, exclusao = st.columns(2)
    with inclusao:
        st.write("**Inclusão**")
        for criterio in protocolo_exibido.get("inclusion_criteria", []):
            st.write(f"- ✅ {criterio}")
    with exclusao:
        st.write("**Exclusão**")
        for criterio in protocolo_exibido.get("exclusion_criteria", []):
            st.write(f"- ❌ {criterio}")

st.divider()
st.subheader("3. Estratégia de busca e coleta")

termo_busca = protocolo_exibido.get("search_string", "")
if not termo_busca:
    st.info("Estruture a pergunta antes de iniciar a coleta.")
    st.stop()

string_manual = st.text_area(
    "String de busca booleana",
    value=termo_busca,
    height=150,
    help="A alteração será registrada como uma nova versão do protocolo ao iniciar a coleta.",
)
qtd_artigos = st.slider(
    "Máximo de artigos por fonte",
    min_value=5,
    max_value=50,
    value=10,
    step=5,
)

fontes_ativas = [
    config.label
    for config in get_bibliographic_settings().values()
    if config.enabled
]
if fontes_ativas:
    st.caption(f"Fontes habilitadas: **{', '.join(fontes_ativas)}**")
else:
    st.warning(
        "Nenhuma fonte bibliográfica está habilitada. Configure as fontes antes de iniciar a coleta."
    )

if st.button(
    "🚀 Iniciar coleta nas fontes habilitadas",
    type="primary",
    use_container_width=True,
    disabled=not fontes_ativas,
):
    nova_string = string_manual.strip()
    if not nova_string:
        st.error("A string de busca não pode estar vazia.")
    else:
        if nova_string != termo_busca:
            protocolo_atualizado = dict(protocolo_exibido)
            protocolo_atualizado["search_string"] = nova_string
            salvar_protocolo_projeto(
                project_id,
                pergunta_livre,
                protocolo_atualizado,
                motivo="Ajuste manual da estratégia antes da coleta",
            )
            st.session_state[f"protocol_preview_{project_id}"] = protocolo_atualizado

        with st.spinner("A consultar as bases e registrar a proveniência por fonte..."):
            try:
                qtd_salvos, qtd_encontrados = iniciar_recolha(
                    nova_string,
                    project_id=project_id,
                    max_por_fonte=qtd_artigos,
                )
                if qtd_encontrados == 0:
                    st.warning("Nenhum artigo foi encontrado. Ajuste a estratégia de busca.")
                elif qtd_salvos == 0:
                    st.info(
                        f"Os {qtd_encontrados} registros já existiam neste projeto; "
                        "a proveniência das fontes foi atualizada."
                    )
                else:
                    st.success(
                        f"Coleta concluída: {qtd_salvos} novos artigos em "
                        f"{qtd_encontrados} registros recuperados."
                    )
            except Exception as erro:
                st.error(f"Erro durante a coleta: {erro}")
