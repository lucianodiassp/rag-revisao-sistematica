import os
import sys
import json
import psycopg2
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from dotenv import load_dotenv, find_dotenv

# Adiciona o caminho raiz para podermos importar o agente relator e avaliador
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from backend.agentes.agente_relator import gerar_relatorio_final
from backend.agentes.agente_avaliador import executar_auditoria # <-- NOVO IMPORT DO AVALIADOR

# ==========================================
# CONFIGURAÇÃO DE AMBIENTE
# ==========================================
st.set_page_config(page_title="Relatório e Auditoria", page_icon="📊", layout="wide")
load_dotenv(find_dotenv())

CAMINHO_JSON_AUDITORIA = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../audit_questions.json'))

def get_conexao():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "rag_systematic_review"),
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"]
    )

@st.cache_data(ttl=60)
def carregar_dados_triagem():
    """Consulta rápida ao PostgreSQL para alimentar os gráficos em tempo real."""
    conexao = get_conexao()
    df_total = pd.read_sql("SELECT COUNT(*) as total FROM deduplicated_papers", conexao)
    df_decisoes = pd.read_sql("""
        SELECT human_decision, COUNT(*) as quantidade 
        FROM screening_decisions 
        WHERE human_decision IS NOT NULL
        GROUP BY human_decision
    """, conexao)
    conexao.close()
    return df_total.iloc[0]['total'], df_decisoes

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
st.title("📊 Painel de Relatório e Auditoria (SAD)")
st.markdown("Acompanhe o funil da Revisão Sistemática, as métricas de IA e a síntese final do conhecimento.")
st.divider()

# --- 1. DASHBOARD VISUAL (PRISMA) ---
st.header("1. Fluxo Quantitativo de Triagem")

total_artigos, df_decisoes = carregar_dados_triagem()
aprovados = df_decisoes[df_decisoes['human_decision'] == 'Incluir']['quantidade'].sum() if not df_decisoes.empty and 'Incluir' in df_decisoes['human_decision'].values else 0
rejeitados = df_decisoes[df_decisoes['human_decision'] == 'Excluir']['quantidade'].sum() if not df_decisoes.empty and 'Excluir' in df_decisoes['human_decision'].values else 0
pendentes = total_artigos - (aprovados + rejeitados)

col1, col2, col3, col4 = st.columns(4)
col1.metric("📚 Total Coletado", total_artigos)
col2.metric("⏳ Pendentes", pendentes)
col3.metric("✅ Incluídos (RAG)", aprovados)
col4.metric("❌ Excluídos", rejeitados)

st.write("") # Espaçamento

col_chart1, col_chart2 = st.columns(2)
with col_chart1:
    fig_funil = go.Figure(go.Funnel(
        y=["Identificados", "Triados (Decididos)", "Incluídos (Final)"],
        x=[total_artigos, (aprovados + rejeitados), aprovados],
        textinfo="value+percent initial",
        marker={"color": ["#1f77b4", "#ff7f0e", "#2ca02c"]}
    ))
    fig_funil.update_layout(title="Funil PRISMA de Seleção", margin=dict(l=20, r=20, t=40, b=20))
    st.plotly_chart(fig_funil, use_container_width=True)

with col_chart2:
    if not df_decisoes.empty:
        fig_pie = px.pie(df_decisoes, values='quantidade', names='human_decision', 
                         color='human_decision',
                         color_discrete_map={'Incluir':'#2ca02c', 'Excluir':'#d62728'})
        fig_pie.update_layout(title="Distribuição das Decisões Humanas", margin=dict(l=20, r=20, t=40, b=20))
        st.plotly_chart(fig_pie, use_container_width=True)
    else:
        st.info("Ainda não existem decisões de triagem registadas.")

st.divider()

# --- 2. AUDITORIA DO SISTEMA RAG ---
st.header("2. Auditoria do Agente de Busca (LLM-as-a-Judge)")

# --- NOVO BLOCO DE CONFIGURAÇÃO DINÂMICA DE PERGUNTAS ---
with st.expander("⚙️ Configurar Perguntas de Auditoria (Golden Queries)", expanded=False):
    st.markdown("Defina as perguntas de teste que o Juiz usará para avaliar a fidelidade e relevância do RAG. Insira **uma pergunta por linha**.")
    
    perguntas_atuais = []
    if os.path.exists(CAMINHO_JSON_AUDITORIA):
        try:
            with open(CAMINHO_JSON_AUDITORIA, 'r', encoding='utf-8') as f:
                dados = json.load(f)
                perguntas_atuais = dados.get("questions", [])
        except Exception:
            pass

    if not perguntas_atuais:
        # Sugestões padrão alinhadas ao escopo real atual do sistema
        perguntas_atuais = [
            "Como a integração de dados de GPS e temperatura contribui para a manutenção preditiva da frota?",
            "Quais algoritmos de Machine Learning são mais citados para prever falhas com base no histórico de manutenções?",
            "Quais as principais limitações na implementação de Sistemas de Apoio à Decisão (SAD) na logística?",
            "Qual é a capital da Austrália?" # Pegadinha de controle de escopo
        ]

    texto_padrao = "\n".join(perguntas_atuais)
    perguntas_input = st.text_area("Perguntas de Teste Ativas:", value=texto_padrao, height=130)
    
    if st.button("💾 Salvar Perguntas de Auditoria", type="secondary"):
        novas_perguntas = [p.strip() for p in perguntas_input.split('\n') if p.strip()]
        with open(CAMINHO_JSON_AUDITORIA, 'w', encoding='utf-8') as f:
            json.dump({"questions": novas_perguntas}, f, indent=4, ensure_ascii=False)
        st.success("✅ Perguntas salvas com sucesso no arquivo `audit_questions.json`!")
        st.rerun()

st.write("")

# Layout de execução e exibição de resultados
df_juiz = carregar_metricas_auditoria_legada()

col_info_auditoria, col_btn_auditoria = st.columns([2, 1])
with col_info_auditoria:
    st.write("Dispare o agente avaliador para testar a robustez, fidelidade contextual e o nível de recusa do sistema RAG.")
with col_btn_auditoria:
    if st.button("⚖️ Executar Nova Auditoria (Juiz)", type="primary", use_container_width=True):
        with st.spinner("O Juiz está a processar as respostas e a calcular os índices. Isto pode demorar devido às pausas de segurança da API..."):
            try:
                executar_auditoria()
                st.success("Auditoria realizada com sucesso! Atualizando métricas...")
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao executar o pipeline de auditoria: {e}")

st.write("")

if df_juiz is not None and not df_juiz.empty:
    media_fid = df_juiz['Fidelidade (0-10)'].mean()
    media_rel = df_juiz['Relevância (0-10)'].mean()
    
    col_kpi1, col_kpi2 = st.columns(2)
    col_kpi1.metric("Fidelidade Média (Anti-Alucinação)", f"{media_fid:.1f} / 10")
    col_kpi2.metric("Relevância Média das Respostas", f"{media_rel:.1f} / 10")
    
    with st.expander("Ver detalhes dos testes de Auditoria (Heatmap)", expanded=True):
        st.dataframe(
            df_juiz.style.background_gradient(cmap='Blues', subset=['Fidelidade (0-10)', 'Relevância (0-10)']),
            use_container_width=True, hide_index=True
        )
else:
    st.warning("⚠️ Nenhuma métrica encontrada. Use o botão acima para executar a primeira auditoria com as perguntas configuradas.")

st.divider()

# --- 3. SÍNTESE ACADÊMICA ---
st.header("3. Compilação da Síntese Final")

if "relatorio_compilado" not in st.session_state:
    st.session_state.relatorio_compilado = None

col_tit, col_btn = st.columns([2, 1])
with col_tit:
    st.write("Acione o Agente Relator para ler as evidências extraídas e gerar o texto final no padrão académico.")
with col_btn:
    if st.button("🚀 Gerar / Atualizar Relatório Final", type="primary", use_container_width=True):
        with st.spinner("A invocar o Agente Relator (Pode demorar alguns segundos)..."):
            try:
                st.session_state.relatorio_compilado = gerar_relatorio_final()
                st.success("Relatório compilado com sucesso!")
            except Exception as e:
                st.error(f"Erro ao executar o Agente Relator: {e}")

if st.session_state.relatorio_compilado is not None:
    texto_relatorio = st.session_state.relatorio_compilado["relatorio_md"]
    
    with st.container(height=500, border=True):
        st.markdown(texto_relatorio)
        
    st.download_button(
        label="📄 Baixar Relatório Completo (Markdown)",
        data=texto_relatorio.encode('utf-8'),
        file_name="Relatorio_Final_Revisao_Sistematica.md",
        mime="text/markdown",
        type="primary"
    )