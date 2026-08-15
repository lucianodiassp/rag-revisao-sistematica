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
from backend.app.demo_project import ensure_demo_project  # noqa: E402
from backend.coleta.orquestrador_coleta import iniciar_recolha  # noqa: E402
from backend.coleta.importador_bibtex import (  # noqa: E402
    ErroBibTeX,
    analisar_bibtex,
    importar_bibtex,
)
from frontend.project_selector import (  # noqa: E402
    CHAVE_PROJETO_ATIVO,
    selecionar_projeto_ativo,
)


st.set_page_config(page_title="Configuração da Pesquisa", page_icon="⚙️", layout="wide")


with st.sidebar.expander("🧪 Projeto demonstrativo", expanded=False):
    st.caption(
        "Carrega um exemplo auditável com artigos reais, deduplicação, triagem, "
        "cartões PDF, matriz de evidências, PRISMA e Golden Set. Não utiliza chaves de IA."
    )
    abrir_demo = st.button(
        "Criar / abrir demonstração",
        use_container_width=True,
        key="open_demo_project",
    )
    confirmar_restauracao = st.checkbox(
        "Confirmo que desejo descartar alterações feitas somente na demonstração",
        key="confirm_demo_reset",
    )
    restaurar_demo = st.button(
        "Restaurar dados originais",
        use_container_width=True,
        disabled=not confirmar_restauracao,
        key="reset_demo_project",
    )

    if abrir_demo or restaurar_demo:
        try:
            resultado_demo = ensure_demo_project(reset=bool(restaurar_demo))
        except Exception as erro:
            st.error(f"Não foi possível preparar a demonstração: {erro}")
        else:
            demo_id = str(resultado_demo["project_id"])
            st.session_state[CHAVE_PROJETO_ATIVO] = demo_id
            st.session_state["project_selector_widget"] = demo_id
            st.session_state["demo_project_message"] = (
                "Demonstração restaurada com os dados originais."
                if resultado_demo.get("restored")
                else "Projeto demonstrativo pronto para exploração."
            )
            st.rerun()


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

mensagem_demo = st.session_state.pop("demo_project_message", None)
if mensagem_demo:
    st.success(mensagem_demo)

if projeto is None:
    st.info("Crie o primeiro projeto no painel lateral para iniciar a revisão.")
    st.stop()

project_id = str(projeto["id"])
protocolo_atual = projeto.get("criteria_jsonb") or {}

if (protocolo_atual.get("_demo") or {}).get("seed_id"):
    st.info(
        "Esta demonstração usa metadados de publicações reais e cartões de evidência "
        "gerados localmente. Ela permite percorrer o fluxo sem consumir APIs; os cartões "
        "não substituem a leitura dos artigos integrais."
    )

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
aba_apis, aba_bibtex = st.tabs(["Consultar APIs", "Importar BibTeX"])

with aba_apis:
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
            "Nenhuma fonte bibliográfica está habilitada. "
            "Configure as fontes antes de iniciar a coleta por API."
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
                    qtd_salvos, qtd_encontrados, qtd_mesclados, qtd_pendentes = iniciar_recolha(
                        nova_string,
                        project_id=project_id,
                        max_por_fonte=qtd_artigos,
                    )
                    if qtd_encontrados == 0:
                        st.warning("Nenhum artigo foi encontrado. Ajuste a estratégia de busca.")
                    elif qtd_salvos == 0 and qtd_pendentes == 0:
                        st.info(
                            f"Os {qtd_encontrados} registros já existiam neste projeto; "
                            "a proveniência das fontes foi atualizada."
                        )
                    else:
                        st.success(
                            f"Coleta concluída: {qtd_salvos} novo(s), "
                            f"{qtd_mesclados} mesclado(s) por DOI e "
                            f"{qtd_pendentes} candidato(s) aguardando revisão, em "
                            f"{qtd_encontrados} registro(s) recuperado(s)."
                        )
                except Exception as erro:
                    st.error(f"Erro durante a coleta: {erro}")

with aba_bibtex:
    st.markdown(
        "Importe uma exportação `.bib` do Web of Science ou de outro gerenciador. "
        "Os registros entram na mesma triagem dos artigos coletados por API e são "
        "deduplicados por DOI ou título, sem aplicação automática dos critérios PICO."
    )
    arquivo_bibtex = st.file_uploader(
        "Arquivo BibTeX",
        type=["bib"],
        key=f"bibtex_uploader_{project_id}",
    )

    if arquivo_bibtex is not None:
        conteudo_bibtex = arquivo_bibtex.getvalue()
        try:
            analise = analisar_bibtex(conteudo_bibtex, arquivo_bibtex.name)
        except ErroBibTeX as erro:
            st.error(f"Arquivo BibTeX inválido: {erro}")
        except Exception as erro:
            st.error(f"Não foi possível analisar o arquivo: {erro}")
        else:
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Entradas", analise["total_entries"])
            col2.metric("Válidas", analise["valid_entries"])
            col3.metric("Sem abstract", analise["without_abstract"])
            col4.metric("Sem DOI", analise["without_doi"])
            st.caption(
                f"Codificação: {analise['encoding']} · "
                f"SHA-256: `{analise['file_sha256'][:16]}…`"
            )

            if analise["invalid_entries"]:
                st.warning(
                    f"{analise['invalid_entries']} entrada(s) sem título serão ignoradas."
                )
            if analise["duplicates_in_file"]:
                st.info(
                    f"O arquivo contém {analise['duplicates_in_file']} possível(is) "
                    "duplicata(s), que serão consolidadas pela proveniência."
                )

            st.write("**Prévia dos primeiros registros válidos**")
            st.dataframe(analise["preview"], use_container_width=True, hide_index=True)

            if st.button(
                "📥 Importar registros para o projeto ativo",
                type="primary",
                use_container_width=True,
                disabled=analise["valid_entries"] == 0,
            ):
                with st.spinner("A importar, deduplicar e registrar a proveniência..."):
                    try:
                        relatorio = importar_bibtex(
                            project_id,
                            conteudo_bibtex,
                            arquivo_bibtex.name,
                        )
                    except Exception as erro:
                        st.error(f"Erro durante a importação: {erro}")
                    else:
                        if relatorio["persistence_errors"]:
                            st.warning(
                                "Importação concluída com "
                                f"{relatorio['persistence_errors']} erro(s) de persistência."
                            )
                        else:
                            st.success("Importação BibTeX concluída e registrada.")
                        resultado1, resultado2, resultado3, resultado4 = st.columns(4)
                        resultado1.metric("Novos artigos", relatorio["new_papers"])
                        resultado2.metric("Mesclados por DOI", relatorio["merged_records"])
                        resultado3.metric(
                            "Revisão de duplicatas",
                            relatorio.get("pending_deduplication_review", 0),
                        )
                        resultado4.metric("Entradas inválidas", relatorio["invalid_entries"])
                        st.caption(
                            "Novos artigos já estão na Triagem; candidatos por título precisam "
                            "ser decididos na página Deduplicação. "
                            f"Execução: `{relatorio['search_query_id']}`"
                        )
