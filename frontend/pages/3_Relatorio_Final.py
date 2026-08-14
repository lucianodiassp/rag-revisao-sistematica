import os
import sys
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv, find_dotenv

# Adiciona o caminho raiz para podermos importar o agente relator e avaliador
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from backend.agentes.agente_relator import gerar_relatorio_final
from backend.agentes.agente_avaliador import PERGUNTAS_PADRAO, executar_auditoria
from backend.app.database import carregar_ultima_execucao_avaliacao, salvar_protocolo_projeto
from backend.app.prisma import (
    calcular_fluxo_prisma,
    carregar_ultimo_snapshot_prisma,
    gerar_prisma_svg,
    prisma_para_csv,
    prisma_para_json,
    salvar_snapshot_prisma,
)
from backend.app.screening_service import EXCLUSION_REASON_LABELS
from frontend.project_selector import selecionar_projeto_ativo

# ==========================================
# CONFIGURAÇÃO DE AMBIENTE
# ==========================================
st.set_page_config(page_title="Relatório e Auditoria", page_icon="📊", layout="wide")
load_dotenv(find_dotenv())

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

# --- 1. FLUXO PRISMA RASTREÁVEL ---
st.header("1. Fluxo PRISMA Rastreável")
st.caption(
    "Os números abaixo são calculados diretamente dos registros do projeto. "
    "Um snapshot preserva o retrato, a versão do protocolo e os motivos de exclusão."
)

try:
    fluxo_atual = calcular_fluxo_prisma(project_id)
    ultimo_snapshot = carregar_ultimo_snapshot_prisma(project_id)
except Exception as exc:
    st.error(f"Não foi possível calcular o fluxo PRISMA: {exc}")
    st.stop()

metricas = fluxo_atual["metrics"]
col1, col2, col3, col4 = st.columns(4)
col1.metric("📚 Registros identificados", metricas["records_identified"])
col2.metric("🧹 Artigos únicos", metricas["records_after_deduplication"])
col3.metric("📄 PDFs indexados", metricas["reports_assessed"])
col4.metric("✅ Estudos na síntese", metricas["studies_included_synthesis"])

col_status, col_snapshot = st.columns([2, 1])
with col_status:
    if ultimo_snapshot:
        mudou = ultimo_snapshot["metrics"] != fluxo_atual["metrics"]
        st.info(
            f"Último snapshot: versão {ultimo_snapshot['snapshot_version']} · "
            f"protocolo v{ultimo_snapshot['protocol_version']} · "
            f"{ultimo_snapshot['created_at']}"
        )
        if mudou:
            st.warning("O fluxo atual mudou desde o último snapshot. Registre uma nova versão.")
    else:
        st.info("Ainda não há snapshot PRISMA registrado para este projeto.")
with col_snapshot:
    if st.button("📌 Registrar snapshot PRISMA", type="primary", use_container_width=True):
        try:
            snapshot_criado = salvar_snapshot_prisma(project_id)
            st.success(f"Snapshot v{snapshot_criado['snapshot_version']} registrado.")
            st.rerun()
        except Exception as exc:
            st.error(f"Não foi possível registrar o snapshot: {exc}")

svg_fluxo = gerar_prisma_svg(fluxo_atual)
components.html(
    "<style>html,body{margin:0;padding:0;overflow:hidden;background:#f7f9fc}</style>"
    + svg_fluxo,
    height=1130,
    scrolling=False,
)

with st.expander("Ver interpretação e definições metodológicas", expanded=True):
    for statement in fluxo_atual["interpretation"]["statements"]:
        st.write(f"- {statement}")
    for warning in fluxo_atual["interpretation"]["warnings"]:
        st.warning(warning)
    st.caption(
        "PDF avaliado = texto integral indexado. Estudo incluído na síntese = extração "
        "aprovada ou corrigida por humano, com ao menos uma fonte literal validada."
    )

linhas_motivos = []
for etapa, motivos in fluxo_atual["exclusion_reasons"].items():
    for codigo, quantidade in motivos.items():
        linhas_motivos.append(
            {
                "Etapa": "Triagem" if etapa == "screening" else "Texto integral",
                "Motivo": EXCLUSION_REASON_LABELS.get(codigo, codigo),
                "Quantidade": quantidade,
            }
        )
if linhas_motivos:
    with st.expander("Ver motivos estruturados de exclusão"):
        st.dataframe(pd.DataFrame(linhas_motivos), use_container_width=True, hide_index=True)

if ultimo_snapshot:
    export_col1, export_col2, export_col3 = st.columns(3)
    nome_base = f"prisma_snapshot_v{ultimo_snapshot['snapshot_version']}"
    export_col1.download_button(
        "⬇️ Baixar JSON auditável",
        prisma_para_json(ultimo_snapshot).encode("utf-8"),
        file_name=f"{nome_base}.json",
        mime="application/json",
        use_container_width=True,
    )
    export_col2.download_button(
        "⬇️ Baixar dados CSV",
        prisma_para_csv(ultimo_snapshot).encode("utf-8"),
        file_name=f"{nome_base}.csv",
        mime="text/csv",
        use_container_width=True,
    )
    export_col3.download_button(
        "⬇️ Baixar diagrama SVG",
        gerar_prisma_svg(ultimo_snapshot).encode("utf-8"),
        file_name=f"{nome_base}.svg",
        mime="image/svg+xml",
        use_container_width=True,
    )

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
    snapshot_relatorio = relatorio_compilado.get("prisma_snapshot")
    if snapshot_relatorio:
        st.info(
            f"Relatório vinculado ao snapshot PRISMA v{snapshot_relatorio['snapshot_version']} "
            f"e ao protocolo v{snapshot_relatorio['protocol_version']}."
        )
    
    with st.container(height=500, border=True):
        st.markdown(texto_relatorio)
        
    st.download_button(
        label="📄 Baixar Relatório Completo (Markdown)",
        data=texto_relatorio.encode('utf-8'),
        file_name="Relatorio_Final_Revisao_Sistematica.md",
        mime="text/markdown",
        type="primary"
    )
