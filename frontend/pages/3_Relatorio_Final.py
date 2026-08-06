import os
import sys
import psycopg2
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from dotenv import load_dotenv, find_dotenv

# Adiciona o caminho raiz para podermos importar o agente relator e avaliador
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from backend.agentes.agente_relator import gerar_relatorio_final
from backend.agentes.agente_avaliador import PERGUNTAS_PADRAO, executar_auditoria
from backend.app.database import carregar_ultima_execucao_avaliacao, salvar_protocolo_projeto
from frontend.project_selector import selecionar_projeto_ativo

# ==========================================
# CONFIGURAÇÃO DE AMBIENTE
# ==========================================
st.set_page_config(page_title="Relatório e Auditoria", page_icon="📊", layout="wide")
load_dotenv(find_dotenv())

def get_conexao():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "rag_systematic_review"),
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"]
    )

@st.cache_data(ttl=60)
def carregar_dados_triagem(project_id):
    """Consulta rápida ao PostgreSQL para alimentar os gráficos em tempo real."""
    conexao = get_conexao()
    df_total = pd.read_sql(
        "SELECT COUNT(*) as total FROM deduplicated_papers WHERE project_id = %s",
        conexao,
        params=(project_id,),
    )
    df_decisoes = pd.read_sql("""
        SELECT human_decision, COUNT(*) as quantidade 
        FROM screening_decisions s
        JOIN deduplicated_papers p ON p.id = s.paper_id
        WHERE p.project_id = %s AND human_decision IS NOT NULL
        GROUP BY human_decision
    """, conexao, params=(project_id,))
    conexao.close()
    return df_total.iloc[0]['total'], df_decisoes

def carregar_metricas_auditoria(project_id):
    execucao = carregar_ultima_execucao_avaliacao(project_id)
    if not execucao:
        return None
    resultados = (execucao.get("metrics") or {}).get("results", [])
    return pd.DataFrame(resultados) if resultados else None

# ==========================================
# INTERFACE GRÁFICA (STREAMLIT)
# ==========================================
st.title("📊 Painel de Relatório e Auditoria (SAD)")
projeto = selecionar_projeto_ativo()
project_id = str(projeto["id"])
protocolo = projeto.get("criteria_jsonb") or {}
st.caption(f"Projeto ativo: **{projeto['title']}**")
st.markdown("Acompanhe o funil da Revisão Sistemática, as métricas de IA e a síntese final do conhecimento.")
st.divider()

# --- 1. DASHBOARD VISUAL (PRISMA) ---
st.header("1. Fluxo Quantitativo de Triagem")

total_artigos, df_decisoes = carregar_dados_triagem(project_id)
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
    
    perguntas_atuais = protocolo.get("audit_questions") or PERGUNTAS_PADRAO

    texto_padrao = "\n".join(perguntas_atuais)
    perguntas_input = st.text_area("Perguntas de Teste Ativas:", value=texto_padrao, height=130)
    
    if st.button("💾 Salvar Perguntas de Auditoria", type="secondary"):
        novas_perguntas = [p.strip() for p in perguntas_input.split('\n') if p.strip()]
        protocolo_atualizado = dict(protocolo)
        protocolo_atualizado["audit_questions"] = novas_perguntas
        salvar_protocolo_projeto(
            project_id,
            projeto["question"],
            protocolo_atualizado,
            motivo="Atualização das perguntas de auditoria",
        )
        st.success("✅ Perguntas salvas em uma nova versão do protocolo.")
        st.rerun()

st.write("")

# Layout de execução e exibição de resultados
df_juiz = carregar_metricas_auditoria(project_id)

col_info_auditoria, col_btn_auditoria = st.columns([2, 1])
with col_info_auditoria:
    st.write("Dispare o agente avaliador para testar a robustez, fidelidade contextual e o nível de recusa do sistema RAG.")
with col_btn_auditoria:
    if st.button("⚖️ Executar Nova Auditoria (Juiz)", type="primary", use_container_width=True):
        with st.spinner("O Juiz está a processar as respostas e a calcular os índices. Isto pode demorar devido às pausas de segurança da API..."):
            try:
                executar_auditoria(project_id)
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

if "relatorios_por_projeto" not in st.session_state:
    st.session_state.relatorios_por_projeto = {}

col_tit, col_btn = st.columns([2, 1])
with col_tit:
    st.write("Acione o Agente Relator para ler as evidências extraídas e gerar o texto final no padrão académico.")
with col_btn:
    if st.button("🚀 Gerar / Atualizar Relatório Final", type="primary", use_container_width=True):
        with st.spinner("A invocar o Agente Relator (Pode demorar alguns segundos)..."):
            try:
                st.session_state.relatorios_por_projeto[project_id] = gerar_relatorio_final(project_id)
                st.success("Relatório compilado com sucesso!")
            except Exception as e:
                st.error(f"Erro ao executar o Agente Relator: {e}")

relatorio_compilado = st.session_state.relatorios_por_projeto.get(project_id)
if relatorio_compilado is not None:
    texto_relatorio = relatorio_compilado["relatorio_md"]
    
    with st.container(height=500, border=True):
        st.markdown(texto_relatorio)
        
    st.download_button(
        label="📄 Baixar Relatório Completo (Markdown)",
        data=texto_relatorio.encode('utf-8'),
        file_name="Relatorio_Final_Revisao_Sistematica.md",
        mime="text/markdown",
        type="primary"
    )
