import os
import sys
import psycopg2
import pandas as pd
import streamlit as st
from dotenv import load_dotenv, find_dotenv

# Adiciona o caminho raiz para podermos importar o agente relator dinâmico
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from backend.agentes.agente_relator import gerar_relatorio_final

# ==========================================
# CONFIGURAÇÃO DE AMBIENTE
# ==========================================
load_dotenv(find_dotenv())

def carregar_metricas_auditoria_legada():
    """Lê o ficheiro CSV gerado pelo Agente Juiz (módulo RAG)."""
    raiz_projeto = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
    caminho_csv = os.path.join(raiz_projeto, 'metricas_rag_auditoria.csv')
    
    try:
        if os.path.exists(caminho_csv):
            return pd.read_csv(caminho_csv)
    except Exception:
        pass
    return None

# ==========================================
# INTERFACE GRÁFICA (STREAMLIT)
# ==========================================
st.set_page_config(page_title="Relatório Final", page_icon="📑", layout="wide")

st.title("📑 Relatório Final e Auditoria")
st.markdown("""
Consolidação das métricas do fluxo de seleção (inspirado no PRISMA), 
auditoria dos agentes e síntese académica automatizada dos artigos incluídos.
""")
st.divider()

# MECANISMO DE SEGURANÇA: Inicializa o estado da sessão para evitar múltiplas chamadas à API do Gemini
if "relatorio_compilado" not in st.session_state:
    st.session_state.relatorio_compilado = None

# Cabeçalho de Comando de Compilação
col_tit, col_btn = st.columns([2, 1])
with col_tit:
    st.write("### ⚙️ Central de Consolidação do Sistema")
with col_btn:
    if st.button("🚀 Gerar / Atualizar Relatório Final", type="primary", use_container_width=True):
        with st.spinner("A extrair dados do PostgreSQL e a invocar o Agente Relator..."):
            try:
                # Invoca o backend e armazena em cache na sessão
                st.session_state.relatorio_compilado = gerar_relatorio_final()
                st.success("Relatório compilado com sucesso!")
            except Exception as e:
                st.error(f"Erro ao executar o Agente Relator: {e}")

st.divider()

# Renderização Condicional: Só renderiza o painel se houver dados em cache
if st.session_state.relatorio_compilado is not None:
    resultado = st.session_state.relatorio_compilado
    metricas_prisma = resultado["metricas"]
    texto_relatorio = resultado["relatorio_md"]
    
    # 1. Painel Superior: Métricas Reais do Banco de Dados (Fluxo de Triagem Humana/IA)
    st.subheader("📊 Mapeamento de Fluxo Quantitativo (Inspirado no PRISMA)")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("1. Artigos Únicos", metricas_prisma.get('total_unicos', 0))
    m2.metric("2. Triados pela IA", metricas_prisma.get('triados_ia', 0))
    m3.metric("3. Aprovados (Humano)", metricas_prisma.get('aprovados_humano', 0))
    m4.metric("4. Evidências Extraídas", metricas_prisma.get('evidencias_extraidas', 0))
    
    st.divider()
    
    # 2. Corpo Central: Duas colunas distribuindo o Relatório e a Auditoria Externa
    col_visualizacao, col_auditoria = st.columns([2, 1])
    
    with col_visualizacao:
        st.subheader("📝 Síntese Académica das Evidências (Gerada por IA)")
        with st.container(height=500, border=True):
            st.markdown(texto_relatorio)
            
        st.write("### 📥 Exportação do Documento")
        st.download_button(
            label="📄 Baixar Relatório Completo (Markdown)",
            data=texto_relatorio.encode('utf-8'),
            file_name="Relatorio_Final_Revisao_Sistematica.md",
            mime="text/markdown",
            type="primary",
            use_container_width=True
        )
        
    with col_auditoria:
        st.subheader("🛡️ Auditoria de RAG Integrada")
        
        # Tenta carregar os dados locais legados do CSV do Agente Juiz
        df_juiz = carregar_metricas_auditoria_legada()
        if df_juiz is not None:
            st.markdown("**Métricas de Avaliação (LLM-as-a-Judge):**")
            media_fid = df_juiz['Fidelidade (0-10)'].mean()
            media_rel = df_juiz['Relevância (0-10)'].mean()
            
            st.metric(label="Fidelidade Média (Anti-Alucinação)", value=f"{media_fid:.1f} / 10")
            st.metric(label="Relevância Média das Respostas", value=f"{media_rel:.1f} / 10")
            
            with st.expander("Ver logs detalhados do Juiz"):
                st.dataframe(df_juiz[['Pergunta', 'Fidelidade (0-10)', 'Relevância (0-10)']], hide_index=True)
        else:
            st.info("ℹ️ Os logs quantitativos adicionais do Agente Juiz ficarão visíveis aqui assim que o módulo de testes vetoriais do RAG for executado.")

else:
    st.info("👉 O relatório final ainda não foi gerado nesta sessão de uso. Clique no botão **'Gerar / Atualizar Relatório Final'** localizado no canto superior direito para iniciar a compilação de dados.")