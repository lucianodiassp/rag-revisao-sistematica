import os
import uuid
import psycopg2
import streamlit as st
from dotenv import load_dotenv

# ==========================================
# CONFIGURAÇÃO DE AMBIENTE E CONEXÃO
# ==========================================
# Carregar variáveis de ambiente (banco de dados e API Key)
load_dotenv()

def get_conexao():
    """Estabelece a conexão com o PostgreSQL utilizando variáveis de ambiente."""
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "rag_systematic_review"),
        user=os.getenv("DB_USER", "rag_user"),
        password=os.getenv("DB_PASSWORD", "rag_password")
    )

def buscar_artigo_pendente():
    """Busca 1 artigo que ainda não foi triado pelo humano, ignorando mensagens de erro das APIs."""
    try:
        conexao = get_conexao()
        cursor = conexao.cursor()
        
        # Adicionámos um filtro NOT IN para barrar o "lixo" diretamente na consulta SQL
        cursor.execute("""
            SELECT id, title, abstract 
            FROM deduplicated_papers 
            WHERE id NOT IN (SELECT paper_id FROM screening_decisions)
              AND abstract IS NOT NULL 
              AND abstract != ''
              AND abstract NOT IN (
                  'Abstract indisponível.',
                  'Abstract extraído do índice (simplificado para este exemplo).',
                  'Abstract via PubMed E-Summary (Requer E-Fetch para texto completo).'
              )
            LIMIT 1;
        """)
        artigo = cursor.fetchone()
        conexao.close()
        return artigo
    except Exception as e:
        st.error(f"Erro ao conectar ao banco de dados: {e}")
        return None

def salvar_decisao(paper_id, human_decision, justification):
    """Grava a decisão final na tabela de auditoria do PostgreSQL."""
    try:
        conexao = get_conexao()
        cursor = conexao.cursor()
        
        decisao_id = str(uuid.uuid4())
        suggested = "Pendente IA"  # Placeholder para quando a lógica de agentes for acoplada
        
        cursor.execute("""
            INSERT INTO screening_decisions 
            (id, paper_id, suggested_decision, human_decision, justification)
            VALUES (%s, %s, %s, %s, %s)
        """, (decisao_id, paper_id, suggested, human_decision, justification))
        
        conexao.commit()
        conexao.close()
    except Exception as e:
        st.error(f"Erro ao gravar a decisão no banco de dados: {e}")

# ==========================================
# INTERFACE GRÁFICA (STREAMLIT)
# ==========================================
st.set_page_config(page_title="Triagem de Artigos", page_icon="🧑‍⚕️", layout="wide")

st.title("🧑‍⚕️ Triagem Humana (Human-in-the-Loop)")
st.markdown("Leia o resumo e valide se o artigo atende aos critérios da revisão.")
st.divider()

artigo_atual = buscar_artigo_pendente()

if artigo_atual:
    paper_id, titulo, abstract = artigo_atual
    
    st.subheader(titulo)
    st.write("**Abstract:**")
    st.info(abstract)
    
    st.divider()
    
    st.write("### O seu Veredito")
    with st.form("form_triagem", clear_on_submit=True):
        col1, col2 = st.columns(2)
        
        with col1:
            decisao = st.radio(
                "Decisão:",
                options=["Incluir", "Excluir", "Talvez"],
                horizontal=True
            )
        
        with col2:
            justificativa = st.text_input("Justificativa (Obrigatório para Exclusão):", placeholder="Motivo técnico da escolha...")
            
        botao_salvar = st.form_submit_button("💾 Salvar Decisão e Próximo", type="primary")
        
        if botao_salvar:
            if decisao == "Excluir" and not justificativa:
                st.warning("⚠️ Para garantir a auditoria, insira uma justificativa ao excluir.")
            else:
                salvar_decisao(paper_id, decisao, justificativa)
                st.success("✅ Decisão registrada no banco!")
                st.rerun()
else:
    st.balloons()
    st.success("🎉 Todos os artigos coletados já foram triados!")