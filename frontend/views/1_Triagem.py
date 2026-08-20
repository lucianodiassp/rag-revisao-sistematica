from pathlib import Path
import sys

import streamlit as st

# Adiciona o caminho raiz para podermos importar o agente de triagem
sys.path.append(str(Path(__file__).resolve().parents[2]))

# Importação da função geradora (UI-ready) do backend
from backend.agentes.agente_triagem import executar_pipeline_triagem_ui
from backend.app.screening_service import (
    EXCLUSION_REASON_LABELS,
    get_next_pending_human_screening,
    get_screening_summary,
    save_human_screening_decision,
)
from frontend.project_selector import selecionar_projeto_ativo

# ==========================================
# INTERFACE GRÁFICA (STREAMLIT)
# ==========================================
st.set_page_config(page_title="Triagem de Artigos", page_icon="🧑‍⚕️", layout="wide")
projeto = selecionar_projeto_ativo()
project_id = str(projeto["id"])

st.title("🧑‍⚕️ Triagem Humana (Human-in-the-Loop)")
st.caption(f"Projeto ativo: **{projeto['title']}**")

try:
    resumo = get_screening_summary(project_id)
except Exception as exc:
    st.error(f"Não foi possível calcular as pendências da triagem: {exc}")
    st.stop()

# --- CABEÇALHO COM BOTÃO DE AÇÃO INTERATIVO ---
col1, col2 = st.columns([2, 1])
with col1:
    st.markdown("Revise a sugestão da Inteligência Artificial e tome a decisão final sobre os artigos recolhidos.")
with col2:
    if st.button(
        "🤖 Rodar IA nos Novos Artigos",
        type="primary",
        use_container_width=True,
        disabled=resumo["awaiting_ai"] == 0,
        help=(
            f"{resumo['awaiting_ai']} artigo(s) possui(em) resumo e ainda aguardam a IA."
            if resumo["awaiting_ai"]
            else "Não há artigos com resumo adequado aguardando avaliação da IA."
        ),
    ):
        # Componentes visuais para suavizar a espera (Requisito de UX)
        barra_progresso = st.progress(0)
        texto_status = st.empty()
        
        try:
            # Consome o gerador do backend passo a passo em tempo real
            for passo in executar_pipeline_triagem_ui(project_id):
                if passo["total"] > 0:
                    # Calcula e atualiza a barra de progresso (0 a 100)
                    percentagem = int((passo["atual"] / passo["total"]) * 100)
                    barra_progresso.progress(min(percentagem, 100))
                
                # Atualiza a mensagem de texto logo abaixo da barra
                texto_status.markdown(f"{passo['msg']}")
            
            # Finalização com sucesso
            st.success("Pré-triagem concluída com sucesso!")
            import time
            time.sleep(1.5) # Pequena pausa de cortesia para leitura da mensagem
            st.rerun() # Recarrega a página para carregar o primeiro artigo processado
            
        except Exception as e:
            st.error(f"Erro ao executar a IA: {e}")

st.divider()

st.subheader("Situação da triagem")
metricas = st.columns(5)
metricas[0].metric("Artigos únicos", resumo["total_papers"])
metricas[1].metric("Aguardando IA", resumo["awaiting_ai"])
metricas[2].metric("Aguardando humano", resumo["awaiting_human"])
metricas[3].metric("Decisões finais", resumo["final_decisions"])
metricas[4].metric("Talvez", resumo["maybe"])

st.caption(
    f"Incluídos: {resumo['included']} · Excluídos: {resumo['excluded']} · "
    f"Sem resumo adequado: {resumo['without_usable_abstract']} · "
    f"Pendentes na deduplicação: {resumo['awaiting_deduplication']}"
)

if resumo["accounted_papers"] != resumo["total_papers"] or resumo["unknown_decision"]:
    st.error(
        "A contagem encontrou um estado de triagem não reconhecido. "
        "Consulte os registros antes de continuar."
    )

st.divider()

try:
    artigo_atual = get_next_pending_human_screening(project_id)
except Exception as exc:
    st.error(f"Não foi possível carregar a fila de validação humana: {exc}")
    st.stop()

if artigo_atual:
    (
        paper_id,
        titulo,
        abstract,
        sugestao_ia,
        rationale_ia,
        motivo_reavaliacao,
        justificativa_reavaliacao,
        data_reavaliacao,
    ) = artigo_atual
    
    st.subheader(titulo)
    st.write("**Abstract:**")
    st.info(abstract)

    if justificativa_reavaliacao:
        st.warning(
            "**Artigo devolvido para nova triagem pela Gestão de PDFs**  \n"
            f"Motivo registrado: {justificativa_reavaliacao}  \n"
            f"Data: {data_reavaliacao:%d/%m/%Y %H:%M}"
        )
    
    # --- BLOCO: O PARECER DA IA ---
    st.divider()
    st.write("### 🤖 Parecer do Agente de IA")
    
    cor_sugestao = "green" if sugestao_ia == "Incluir" else "red" if sugestao_ia == "Excluir" else "orange"
    st.markdown(f"**Sugestão:** :{cor_sugestao}[**{sugestao_ia}**]")
    
    if rationale_ia and isinstance(rationale_ia, dict):
        justificativa_ia = rationale_ia.get("justification", "Sem justificativa detalhada.")
        confianca = rationale_ia.get("confidence", 0.0)
        st.write(f"**Confiança do Modelo:** {confianca * 100:.1f}%")
        st.write(f"**Justificativa:** {justificativa_ia}")
    
    st.divider()
    
    # --- FORMULÁRIO DO HUMANO ---
    st.write("### 🧑‍⚕️ O seu Veredito Final")
    with st.form("form_triagem", clear_on_submit=True):
        col_form1, col_form2 = st.columns(2)
        
        with col_form1:
            idx_padrao = ["Incluir", "Excluir", "Talvez"].index(sugestao_ia) if sugestao_ia in ["Incluir", "Excluir", "Talvez"] else 0
            decisao = st.radio(
                "Decisão Final:",
                options=["Incluir", "Excluir", "Talvez"],
                index=idx_padrao,
                horizontal=True
            )
        
        with col_form2:
            motivo_exclusao = st.selectbox(
                "Categoria da exclusão:",
                options=list(EXCLUSION_REASON_LABELS),
                format_func=lambda code: EXCLUSION_REASON_LABELS[code],
                help="Este campo só é aplicado quando a decisão final é Excluir.",
            )

        justificativa = st.text_area(
            "Justificativa ou observação:",
            placeholder=(
                "A justificativa é obrigatória para exclusões e quando a decisão humana "
                "for diferente da sugestão da IA."
            ),
            height=90,
        )
            
        botao_salvar = st.form_submit_button("💾 Confirmar e Próximo", type="primary")
        
        if botao_salvar:
            if decisao == "Excluir" and len(justificativa.strip()) < 5:
                st.warning("⚠️ Para excluir, selecione o motivo e descreva a justificativa.")
            elif decisao != sugestao_ia and len(justificativa.strip()) < 5:
                st.warning("⚠️ Você discordou da IA. Por favor, insira uma observação justificando sua escolha.")
            else:
                try:
                    save_human_screening_decision(
                        project_id,
                        paper_id,
                        decisao,
                        justificativa,
                        motivo_exclusao if decisao == "Excluir" else None,
                    )
                    st.success("✅ Decisão e justificativa registradas com rastreabilidade!")
                    st.rerun()
                except ValueError as exc:
                    st.warning(str(exc))
                except Exception as exc:
                    st.error(f"Erro ao gravar a decisão no banco de dados: {exc}")
else:
    if resumo["awaiting_ai"]:
        st.warning(
            f"🤖 **{resumo['awaiting_ai']} artigo(s) aguardam avaliação da IA.** "
            "Use o botão superior para processar essa fila."
        )
    if resumo["without_usable_abstract"]:
        st.warning(
            f"📄 **{resumo['without_usable_abstract']} artigo(s) não possuem resumo adequado "
            "para avaliação automática.** Complete os metadados ou avalie a origem antes "
            "de concluir a triagem."
        )
    if resumo["maybe"]:
        st.info(
            f"🟡 **{resumo['maybe']} artigo(s) estão marcados como Talvez.** "
            "Eles foram revisados, mas ainda não possuem decisão final de inclusão ou exclusão."
        )
    if resumo["awaiting_deduplication"]:
        st.info(
            f"🔎 **{resumo['awaiting_deduplication']} registro(s) aguardam revisão na "
            "Deduplicação.** Eles só entrarão nesta fila depois dessa decisão."
        )
    if resumo["is_complete"]:
        st.success("🎉 Todos os artigos passaram pela IA e receberam uma decisão humana final!")
    elif resumo["total_papers"] == 0 and not resumo["awaiting_deduplication"]:
        st.info("Ainda não há artigos liberados para triagem neste projeto.")
