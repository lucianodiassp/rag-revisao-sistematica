import os
import sys
import json
import psycopg2
import pandas as pd
import streamlit as st
from dotenv import load_dotenv, find_dotenv

# Adiciona o caminho raiz para podermos importar o agente extrator
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from backend.agentes.agente_extrator import executar_pipeline_extracao
from frontend.project_selector import selecionar_projeto_ativo

# ==========================================
# CONFIGURAÇÃO DE AMBIENTE E CONEXÃO
# ==========================================
load_dotenv(find_dotenv())

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

def carregar_matriz_evidencias(project_id):
    """Busca as evidências extraídas e cruza com o título do artigo."""
    try:
        conexao = get_conexao()
        cursor = conexao.cursor()
        
        # AQUI ESTÁ A CORREÇÃO: O 'ORDER BY' foi removido da query.
        cursor.execute("""
            SELECT p.title, e.extraction_jsonb, e.human_review_status
            FROM extracted_evidence e
            JOIN deduplicated_papers p ON p.id = e.paper_id
            WHERE p.project_id = %s;
        """, (project_id,))
        
        resultados = cursor.fetchall()
        conexao.close()
        
        # Transformar os dados SQL brutos numa lista de dicionários para o Pandas
        dados_formatados = []
        for titulo, jsonb_data, status in resultados:
            # O PostgreSQL pode retornar o JSONB já como dicionário Python ou como string
            if isinstance(jsonb_data, str):
                jsonb_data = json.loads(jsonb_data)
                
            dados_formatados.append({
                "Título do Artigo": titulo,
                "Objetivo": jsonb_data.get("objective", "N/A"),
                "Método": jsonb_data.get("method", "N/A"),
                "Dataset": jsonb_data.get("dataset", "N/A"),
                "Métricas": ", ".join(jsonb_data.get("metrics", [])),
                "Principais Resultados": jsonb_data.get("main_results", "N/A"),
                "Limitações": ", ".join(jsonb_data.get("limitations", [])),
                "Status da Extração": status.capitalize()
            })
            
        return dados_formatados
    except Exception as e:
        st.error(f"Erro ao ligar à base de dados: {e}")
        return []

# ==========================================
# INTERFACE GRÁFICA (STREAMLIT)
# ==========================================
st.set_page_config(page_title="Matriz de Evidências", page_icon="📊", layout="wide")
projeto = selecionar_projeto_ativo()
project_id = str(projeto["id"])

st.title("📊 Matriz de Evidências")
st.caption(f"Projeto ativo: **{projeto['title']}**")

# Layout do cabeçalho com botão de ação para automatizar a extração
col1, col2 = st.columns([3, 1])

with col1:
    st.markdown("""
    Aqui estão os dados estruturados extraídos automaticamente pela Inteligência Artificial dos artigos que você aprovou na Triagem.
    Estes dados estão prontos para compor o **Relatório Final da Revisão Sistemática**.
    """)

with col2:
    # O botão mágico de automatização
    if st.button("🔄 Extrair Novas Evidências", type="primary", use_container_width=True):
        with st.spinner("A IA está a ler e a estruturar os novos artigos. Pode demorar alguns instantes..."):
            executar_pipeline_extracao(project_id)
        st.success("Extração concluída com sucesso!")
        st.rerun() # Recarrega a página para exibir os novos dados

st.divider()

# Carrega e converte os dados para um DataFrame do Pandas
dados = carregar_matriz_evidencias(project_id)

if dados:
    df = pd.DataFrame(dados)
    
    # 1. Mostrar a Tabela de forma interativa no Streamlit
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        height=400
    )
    
    st.divider()
    
    # 2. Configurar o Download em formato CSV (Requisito RF14)
    st.write("### 📥 Exportação de Dados")
    csv = df.to_csv(index=False).encode('utf-8')
    
    st.download_button(
        label="Download Matriz de Evidências (CSV)",
        data=csv,
        file_name="matriz_evidencias_revisao.csv",
        mime="text/csv",
        type="primary"
    )
else:
    st.info("Ainda não há evidências extraídas. Vá à página de Triagem, aprove os artigos que desejar e depois volte aqui para clicar no botão 'Extrair Novas Evidências'.")
