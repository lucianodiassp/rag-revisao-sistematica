import os
import sys
import psycopg2
import streamlit as st
from dotenv import load_dotenv

# Adiciona o caminho raiz para podermos importar o agente de triagem
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

# Importação da função geradora (UI-ready) do backend
from backend.agentes.agente_triagem import executar_pipeline_triagem_ui
from frontend.project_selector import selecionar_projeto_ativo

# ==========================================
# CONFIGURAÇÃO DE AMBIENTE E CONEXÃO
# ==========================================
load_dotenv()

def get_conexao():
    """Estabelece a conexão estritamente via variáveis de ambiente."""
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "rag_systematic_review"),
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"]
    )

def buscar_artigo_pendente(project_id):
    """Busca 1 artigo triado pela IA, mas que ainda aguarda a validação do Humano."""
    try:
        conexao = get_conexao()
        cursor = conexao.cursor()
        
        # Fazemos um JOIN para pegar os dados do artigo E a sugestão da IA
        cursor.execute("""
            SELECT d.id, d.title, d.abstract, s.suggested_decision, s.rationale_jsonb,
                   r.reason_code, r.reason, r.created_at
            FROM deduplicated_papers d
            JOIN screening_decisions s ON d.id = s.paper_id
            LEFT JOIN LATERAL (
                SELECT reason_code, reason, created_at
                FROM screening_reassessments sr
                WHERE sr.paper_id = d.id
                  AND sr.project_id = d.project_id
                  AND sr.action = 'return_to_screening'
                ORDER BY sr.created_at DESC
                LIMIT 1
            ) r ON TRUE
            WHERE d.project_id = %s
              AND s.human_decision IS NULL
            LIMIT 1;
        """, (project_id,))
        artigo = cursor.fetchone()
        conexao.close()
        return artigo
    except Exception as e:
        st.error(f"Erro ao conectar ao banco de dados: {e}")
        return None

def salvar_decisao_humana(project_id, paper_id, human_decision, justification):
    """Atualiza a linha no banco de dados com a decisão final humana."""
    try:
        conexao = get_conexao()
        cursor = conexao.cursor()
        
        cursor.execute("""
            UPDATE screening_decisions 
            SET human_decision = %s, justification = %s, reviewed_at = NOW()
            WHERE paper_id = %s
              AND EXISTS (
                  SELECT 1 FROM deduplicated_papers p
                  WHERE p.id = screening_decisions.paper_id AND p.project_id = %s
              )
        """, (human_decision, justification, paper_id, project_id))
        
        conexao.commit()
        conexao.close()
    except Exception as e:
        st.error(f"Erro ao gravar a decisão no banco de dados: {e}")

# ==========================================
# INTERFACE GRÁFICA (STREAMLIT)
# ==========================================
st.set_page_config(page_title="Triagem de Artigos", page_icon="🧑‍⚕️", layout="wide")
projeto = selecionar_projeto_ativo()
project_id = str(projeto["id"])

st.title("🧑‍⚕️ Triagem Humana (Human-in-the-Loop)")
st.caption(f"Projeto ativo: **{projeto['title']}**")

# --- CABEÇALHO COM BOTÃO DE AÇÃO INTERATIVO ---
col1, col2 = st.columns([2, 1])
with col1:
    st.markdown("Revise a sugestão da Inteligência Artificial e tome a decisão final sobre os artigos recolhidos.")
with col2:
    if st.button("🤖 Rodar IA nos Novos Artigos", type="primary", use_container_width=True):
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

artigo_atual = buscar_artigo_pendente(project_id)

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
            justificativa = st.text_input("Observações (Opcional caso concorde com a IA):", placeholder="Motivo da discordância ou nota técnica...")
            
        botao_salvar = st.form_submit_button("💾 Confirmar e Próximo", type="primary")
        
        if botao_salvar:
            if decisao != sugestao_ia and not justificativa:
                st.warning("⚠️ Você discordou da IA. Por favor, insira uma observação justificando sua escolha.")
            else:
                salvar_decisao_humana(project_id, paper_id, decisao, justificativa)
                st.success("✅ Decisão updated no banco de dados!")
                st.rerun()
else:
    st.balloons()
    st.success("🎉 Todos os artigos já foram validados por você!")
    st.info("👉 Se acabou de realizar uma nova pesquisa, clique no botão superior direito **'🤖 Rodar IA nos Novos Artigos'** para que o agente processe as novidades.")
