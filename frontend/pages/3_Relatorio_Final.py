import os
import json
import psycopg2
import pandas as pd
import streamlit as st
from dotenv import load_dotenv, find_dotenv

# ==========================================
# CONFIGURAÇÃO DE AMBIENTE
# ==========================================
load_dotenv(find_dotenv())

def get_conexao():
    """Lança a conexão com fallback seguro."""
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "127.0.0.1"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "rag_systematic_review"),
        user=os.getenv("DB_USER", "rag_user"),
        password=os.getenv("DB_PASSWORD", "rag_password")
    )

def carregar_matriz_evidencias():
    """Busca as evidências na base de dados."""
    try:
        conexao = get_conexao()
        cursor = conexao.cursor()
        cursor.execute("""
            SELECT p.title, e.extraction_jsonb
            FROM extracted_evidence e
            JOIN deduplicated_papers p ON p.id = e.paper_id;
        """)
        resultados = cursor.fetchall()
        conexao.close()
        
        dados_formatados = []
        for titulo, jsonb_data in resultados:
            if isinstance(jsonb_data, str):
                jsonb_data = json.loads(jsonb_data)
            
            dados_formatados.append({
                "Título": titulo,
                "Objetivo": jsonb_data.get("objective", "N/A"),
                "Método": jsonb_data.get("method", "N/A"),
                "Resultados": jsonb_data.get("main_results", "N/A")
            })
        return dados_formatados
    except Exception as e:
        return []

def carregar_metricas_auditoria():
    """Lê o ficheiro CSV gerado pelo Agente Juiz."""
    raiz_projeto = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
    caminho_csv = os.path.join(raiz_projeto, 'metricas_rag_auditoria.csv')
    
    try:
        if os.path.exists(caminho_csv):
            return pd.read_csv(caminho_csv)
    except Exception:
        pass
    return None

def gerar_markdown_relatorio(matriz, df_metricas):
    """Compila todos os dados num relatório Markdown estruturado."""
    md = "# Relatório Final da Revisão Sistemática\n\n"
    md += "Este documento foi gerado automaticamente pelo Sistema RAG de Apoio a Revisões Sistemáticas.\n\n"
    
    # 1. Secção de Auditoria (Métricas)
    md += "## 1. Auditoria Quantitativa do Modelo de IA\n"
    if df_metricas is not None:
        media_fidelidade = df_metricas['Fidelidade (0-10)'].mean()
        media_relevancia = df_metricas['Relevância (0-10)'].mean()
        md += f"- **Fidelidade Geral (Anti-Alucinação):** {media_fidelidade:.1f} / 10\n"
        md += f"- **Relevância Geral das Respostas:** {media_relevancia:.1f} / 10\n\n"
        md += "### Testes Realizados:\n"
        for index, row in df_metricas.iterrows():
            md += f"- **Q:** {row['Pergunta']}\n  - *Fidelidade:* {row['Fidelidade (0-10)']} | *Relevância:* {row['Relevância (0-10)']}\n  - *Parecer do Juiz:* {row['Justificativa do Juiz']}\n\n"
    else:
        md += "*Dados de auditoria quantitativa não disponíveis no momento.*\n\n"

    # 2. Secção de Evidências (Matriz)
    md += "---\n## 2. Matriz de Evidências Extraídas\n\n"
    if matriz:
        for idx, artigo in enumerate(matriz, 1):
            md += f"### {idx}. {artigo['Título']}\n"
            md += f"- **Objetivo:** {artigo['Objetivo']}\n"
            md += f"- **Método Aplicado:** {artigo['Método']}\n"
            md += f"- **Principais Resultados:** {artigo['Resultados']}\n\n"
    else:
        md += "*Nenhum artigo aprovado ou matriz extraída até ao momento.*\n"
        
    return md

# ==========================================
# INTERFACE GRÁFICA (STREAMLIT)
# ==========================================
st.set_page_config(page_title="Relatório Final", page_icon="📑", layout="wide")

st.title("📑 Relatório Final da Revisão Sistemática")
st.markdown("Consolidação das métricas de inteligência artificial e da extração de conhecimento da literatura indexada.")
st.divider()

# Carregar Dados
matriz_dados = carregar_matriz_evidencias()
metricas_df = carregar_metricas_auditoria()

# Layout em Duas Colunas
col1, col2 = st.columns([1, 2])

with col1:
    st.subheader("Desempenho do Agente (LLM-as-a-Judge)")
    if metricas_df is not None:
        media_fid = metricas_df['Fidelidade (0-10)'].mean()
        media_rel = metricas_df['Relevância (0-10)'].mean()
        
        st.metric(label="Média de Fidelidade (Zero Alucinação)", value=f"{media_fid:.1f} / 10")
        st.metric(label="Média de Relevância", value=f"{media_rel:.1f} / 10")
        
        with st.expander("Ver detalhes dos testes"):
            st.dataframe(metricas_df[['Pergunta', 'Fidelidade (0-10)', 'Relevância (0-10)']], hide_index=True)
    else:
        st.warning("⚠️ O ficheiro de métricas ainda não foi gerado. Rode o `agente_avaliador.py`.")

with col2:
    st.subheader("Pré-visualização do Relatório")
    relatorio_md = gerar_markdown_relatorio(matriz_dados, metricas_df)
    
    # Caixa com scroll para ler o relatório
    with st.container(height=400):
        st.markdown(relatorio_md)
    
    st.divider()
    st.write("### 📥 Exportação Oficial")
    
    # Botão para exportar em formato .MD (Pode ser aberto no Word, Notion, Obsidian, etc)
    st.download_button(
        label="📄 Baixar Relatório Completo (Markdown)",
        data=relatorio_md.encode('utf-8'),
        file_name="Relatorio_Final_Revisao_Sistematica.md",
        mime="text/markdown",
        type="primary",
        use_container_width=True
    )