import os
import psycopg2
import streamlit as st
from dotenv import load_dotenv

# ==========================================
# CONFIGURAÇÃO DE AMBIENTE E CONEXÃO
# ==========================================
load_dotenv()

def get_conexao():
    """Estabelece a conexão estritamente via variáveis de ambiente."""
    # Se DB_USER ou DB_PASSWORD não existirem no .env, o sistema falha com segurança
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"), # Host e Port podem ter fallback pois não são sensíveis
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "rag_systematic_review"),
        user=os.environ["DB_USER"],         # Usa os.environ para forçar erro se não existir
        password=os.environ["DB_PASSWORD"]  # Força a leitura exclusiva do .env
    )

def buscar_artigo_pendente():
    """Busca 1 artigo triado pela IA, mas que ainda aguarda a validação do Humano."""
    try:
        conexao = get_conexao()
        cursor = conexao.cursor()
        
        # Fazemos um JOIN para pegar os dados do artigo E a sugestão da IA
        cursor.execute("""
            SELECT d.id, d.title, d.abstract, s.suggested_decision, s.rationale_jsonb
            FROM deduplicated_papers d
            JOIN screening_decisions s ON d.id = s.paper_id
            WHERE s.human_decision IS NULL
            LIMIT 1;
        """)
        artigo = cursor.fetchone()
        conexao.close()
        return artigo
    except Exception as e:
        st.error(f"Erro ao conectar ao banco de dados: {e}")
        return None

def salvar_decisao_humana(paper_id, human_decision, justification):
    """Atualiza a linha no banco de dados com a decisão final humana."""
    try:
        conexao = get_conexao()
        cursor = conexao.cursor()
        
        # Agora usamos UPDATE em vez de INSERT, pois a IA já criou a linha
        cursor.execute("""
            UPDATE screening_decisions 
            SET human_decision = %s, justification = %s, reviewed_at = NOW()
            WHERE paper_id = %s
        """, (human_decision, justification, paper_id))
        
        conexao.commit()
        conexao.close()
    except Exception as e:
        st.error(f"Erro ao gravar a decisão no banco de dados: {e}")

# ==========================================
# INTERFACE GRÁFICA (STREAMLIT)
# ==========================================
st.set_page_config(page_title="Triagem de Artigos", page_icon="🧑‍⚕️", layout="wide")

st.title("🧑‍⚕️ Triagem Humana (Human-in-the-Loop)")
st.markdown("Revise a sugestão da Inteligência Artificial e tome a decisão final.")
st.divider()

artigo_atual = buscar_artigo_pendente()

if artigo_atual:
    paper_id, titulo, abstract, sugestao_ia, rationale_ia = artigo_atual
    
    st.subheader(titulo)
    st.write("**Abstract:**")
    st.info(abstract)
    
    # --- NOVO BLOCO: O PARECER DA IA ---
    st.divider()
    st.write("### 🤖 Parecer do Agente de IA")
    
    # Definindo cores para facilitar a leitura visual
    cor_sugestao = "green" if sugestao_ia == "Incluir" else "red" if sugestao_ia == "Excluir" else "orange"
    st.markdown(f"**Sugestão:** :{cor_sugestao}[**{sugestao_ia}**]")
    
    # Extraindo a justificativa do JSON gerado pela IA
    if rationale_ia and isinstance(rationale_ia, dict):
        justificativa_ia = rationale_ia.get("justification", "Sem justificativa detalhada.")
        confianca = rationale_ia.get("confidence", 0.0)
        st.write(f"**Confiança do Modelo:** {confianca * 100:.1f}%")
        st.write(f"**Justificativa:** {justificativa_ia}")
    
    st.divider()
    
    # --- FORMULÁRIO DO HUMANO ---
    st.write("### 🧑‍⚕️ O seu Veredito Final")
    with st.form("form_triagem", clear_on_submit=True):
        col1, col2 = st.columns(2)
        
        with col1:
            # Pré-seleciona a decisão da IA para poupar cliques
            idx_padrao = ["Incluir", "Excluir", "Talvez"].index(sugestao_ia) if sugestao_ia in ["Incluir", "Excluir", "Talvez"] else 0
            
            decisao = st.radio(
                "Decisão Final:",
                options=["Incluir", "Excluir", "Talvez"],
                index=idx_padrao,
                horizontal=True
            )
        
        with col2:
            justificativa = st.text_input("Observações (Opcional caso concorde com a IA):", placeholder="Motivo da discordância ou nota técnica...")
            
        botao_salvar = st.form_submit_button("💾 Confirmar e Próximo", type="primary")
        
        if botao_salvar:
            if decisao != sugestao_ia and not justificativa:
                st.warning("⚠️ Você discordou da IA. Por favor, insira uma observação justificando sua escolha.")
            else:
                salvar_decisao_humana(paper_id, decisao, justificativa)
                st.success("✅ Decisão atualizada no banco de dados!")
                st.rerun()
else:
    st.balloons()
    st.success("🎉 Todos os artigos já foram validados por você!")