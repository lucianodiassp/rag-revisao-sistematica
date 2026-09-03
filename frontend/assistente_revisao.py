"""Página do Assistente de Revisão Sistemática."""

import os
import sys

import streamlit as st


sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.agentes.agente_rag import responder_com_rag  # noqa: E402
from backend.app.visual_rag import (  # noqa: E402
    get_visual_rag_setting, set_visual_rag_setting, ensure_visual_evidence_current,
)
from frontend.project_selector import selecionar_projeto_ativo  # noqa: E402


projeto = selecionar_projeto_ativo()
project_id = str(projeto["id"])

st.title("📚 Assistente de Revisão Sistemática")
st.caption(f"Projeto ativo: **{projeto['title']}**")
st.markdown(
    """
Bem-vindo! Este assistente utiliza **Recuperação de Informação (pgvector)** e
**Inteligência Artificial configurável (Gemini ou OpenAI)** para responder a perguntas com base nos
artigos científicos recolhidos.
"""
)
st.divider()

try:
    visual_setting = get_visual_rag_setting(project_id)
except Exception:
    st.error("Não foi possível conferir a configuração visual. Verifique o diagnóstico operacional.")
    st.stop()
with st.expander("Uso de figuras e tabelas revisadas", expanded=False):
    st.caption("Opcional e desativado por padrão. Usa somente interpretações com duas revisões válidas e PDF atual. Não altera o Relatório Final nem envia novas imagens à IA.")
    with st.form(f"visual_rag_form_{project_id}"):
        visual_enabled = st.checkbox(
            "Permitir interpretações visuais revisadas nas respostas deste projeto",
            value=visual_setting["enabled"],
        )
        if st.form_submit_button("Salvar uso de evidências visuais"):
            try:
                set_visual_rag_setting(project_id, visual_enabled)
                st.session_state[f"visual_saved_{project_id}"] = True
                st.rerun()
            except Exception:
                st.error("Não foi possível salvar a configuração visual.")
if st.session_state.pop(f"visual_saved_{project_id}", False):
    st.success("Configuração visual salva para este projeto.")
st.caption("Evidência visual: " + ("habilitada — interpretações revisadas" if visual_setting["enabled"] else "desativada — somente texto"))

if "mensagens_por_projeto" not in st.session_state:
    st.session_state.mensagens_por_projeto = {}
mensagens = st.session_state.mensagens_por_projeto.setdefault(project_id, [])

for mensagem in mensagens:
    with st.chat_message(mensagem["role"]):
        try:
            ensure_visual_evidence_current(project_id, mensagem.get("visual_evidence") or [])
            st.markdown(mensagem["content"])
            if mensagem.get("visual_evidence"):
                st.caption("Resposta histórica com interpretação visual. Gere uma nova resposta para atualizar a análise.")
        except Exception:
            st.warning("Não foi possível confirmar a validade atual das fontes visuais desta resposta histórica.")
            with st.expander("Consultar resposta antiga — não representa evidência atual"):
                st.markdown(mensagem["content"])

pergunta_usuario = st.chat_input(
    "Faça uma pergunta sobre a literatura aprovada "
    "(ex: Quais as arquiteturas utilizadas no SAD?)"
)

if pergunta_usuario:
    with st.chat_message("user"):
        st.markdown(pergunta_usuario)
    mensagens.append({"role": "user", "content": pergunta_usuario})

    with st.chat_message("assistant"):
        with st.spinner("A pesquisar na base de dados e a ler artigos..."):
            try:
                resultado_rag = responder_com_rag(
                    pergunta_usuario,
                    project_id,
                    return_details=True,
                )
                resposta_agente = resultado_rag["answer"]

                st.markdown(resposta_agente)
                mensagens.append({"role": "assistant", "content": resposta_agente,
                                  "visual_evidence": [item for item in resultado_rag.get("evidence", [])
                                                      if item.get("source_type") == "visual_interpretation"]})

                trace = resultado_rag.get("reranking") or {}
                with st.expander("Como as evidências foram selecionadas"):
                    status = trace.get("status")
                    if status == "success":
                        peso_rrf = (trace.get("configuration") or {}).get(
                            "rrf_weight", 0.0
                        )
                        mensagem_status = (
                            "Reranking executado com sucesso após a busca híbrida RRF "
                            f"(peso RRF: {float(peso_rrf):.2f})."
                        )
                        if trace.get("recovered_after_retry"):
                            mensagem_status += (
                                f" Recuperado na tentativa {trace.get('attempts', 2)}."
                            )
                        st.success(mensagem_status)
                    elif status == "fallback_rrf":
                        st.warning(
                            "O reranking não pôde ser executado; a resposta utilizou "
                            "a ordem segura do RRF."
                        )
                        if trace.get("error"):
                            st.caption(f"Motivo registrado: {trace['error']}")
                    elif status == "disabled":
                        st.info("Reranking desativado; foi utilizada a ordem RRF.")
                    else:
                        st.info("Nenhuma evidência candidata foi encontrada.")

                    ranking = trace.get("final_ranking") or []
                    if ranking:
                        st.dataframe(
                            [
                                {
                                    "Artigo": item["paper_id"],
                                    "Título": item.get("paper_title"),
                                    "Página": item["page_number"],
                                    "Fonte": "Interpretação visual revisada" if item.get("artifact_id") else "Texto do PDF",
                                    "Figura/tabela ID": item.get("artifact_id"),
                                    "Tipo visual": item.get("artifact_type"),
                                    "Legenda": item.get("caption"),
                                    "Interpretação ID": item.get("interpretation_id"),
                                    "Posição RRF": item["original_rank"],
                                    "Posição IA": item.get("model_rank"),
                                    "Posição final": item["rerank_rank"],
                                    "Score RRF": item["rrf_score"],
                                    "Score reranking": item.get("rerank_score"),
                                    "Score de fusão": item.get("fusion_score"),
                                    "Justificativa": item.get("rerank_reason"),
                                }
                                for item in ranking
                            ],
                            hide_index=True,
                            use_container_width=True,
                        )

                    generation = resultado_rag.get("generation") or {}
                    if generation.get("refusal_reconsidered"):
                        if generation.get("refusal_recovered"):
                            st.info(
                                "Uma recusa inicial foi reavaliada e corrigida após "
                                "nova leitura das evidências selecionadas."
                            )
                        else:
                            st.info(
                                "A insuficiência de evidências foi confirmada em uma "
                                "segunda leitura conservadora."
                            )

                    validacao = resultado_rag.get("citation_validation") or {}
                    referencias_internas = validacao.get(
                        "internal_references_disambiguated"
                    ) or []
                    citacoes_invalidas = validacao.get(
                        "invalid_citations_removed"
                    ) or []
                    fontes_adicionadas = validacao.get(
                        "source_citations_appended"
                    ) or []
                    st.caption(
                        "Citações artigo/página validadas: "
                        f"{len(validacao.get('valid_citations') or [])}."
                    )
                    if referencias_internas:
                        st.info(
                            "Referências numéricas internas desambiguadas: "
                            + ", ".join(f"[{item}]" for item in referencias_internas)
                        )
                    if citacoes_invalidas:
                        st.warning(
                            "Uma ou mais citações de fonte não validadas foram removidas."
                        )
                    if fontes_adicionadas:
                        st.warning(
                            "O modelo não vinculou cada afirmação a uma fonte; o aviso de "
                            "rastreabilidade foi acrescentado à resposta."
                        )
            except Exception as exc:
                st.error(f"⚠️ Ocorreu um erro de comunicação com o backend: {exc}")
