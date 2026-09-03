"""Detecção e revisão humana de tabelas e figuras dos PDFs."""

import os
import sys

import pandas as pd
import streamlit as st

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from backend.app.background_jobs import JOB_VISUAL_CATALOGING
from backend.app.visual_catalog import (
    list_visual_artifacts,
    render_visual_artifact_preview,
    review_visual_artifact,
    summarize_visual_artifacts,
)
from frontend.background_jobs_ui import job_is_active, render_job_status, start_job
from frontend.project_selector import selecionar_projeto_ativo


st.set_page_config(page_title="Catálogo Visual", page_icon="🖼️", layout="wide")

TYPE_LABELS = {"figure": "Figura", "table": "Tabela"}
STATUS_LABELS = {
    "pending": "Pendente",
    "approved": "Aprovado",
    "corrected": "Corrigido",
    "rejected": "Rejeitado",
}
METHOD_LABELS = {
    "embedded_image": "Imagem incorporada ao PDF",
    "table_structure": "Estrutura tabular",
    "caption_only": "Legenda sem região isolada",
}
DECISION_LABELS = {
    "Aprovar candidato": "approved",
    "Corrigir classificação/legenda": "corrected",
    "Rejeitar falso positivo": "rejected",
}


st.title("🖼️ Catálogo Visual Rastreável")
project = selecionar_projeto_ativo()
project_id = str(project["id"])
st.caption(f"Projeto ativo: **{project['title']}**")
st.info(
    "Esta etapa apenas detecta e organiza candidatos. Nenhuma imagem ou tabela é "
    "interpretada por IA nem incorporada ao RAG antes de uma etapa posterior e "
    "explicitamente revisada."
)

st.header("1. Detectar tabelas e figuras")
st.write(
    "O sistema examina os PDFs dos artigos incluídos, identifica imagens, estruturas "
    "tabulares e legendas, e registra página e região de origem. O processamento "
    "continua mesmo que o navegador seja fechado."
)

catalog_job = render_job_status(
    project_id,
    JOB_VISUAL_CATALOGING,
    key="visual_cataloging",
    title="Catalogação visual",
)
if st.button(
    "🔎 Atualizar catálogo visual",
    type="primary",
    width="stretch",
    disabled=job_is_active(catalog_job),
):
    try:
        start_job(project_id, JOB_VISUAL_CATALOGING)
        st.rerun()
    except Exception as error:
        st.error(f"Não foi possível iniciar a catalogação: {error}")

if catalog_job and catalog_job.get("status") == "succeeded":
    result = catalog_job.get("result_jsonb") or {}
    if result.get("papers_failed"):
        st.warning(
            f"Catálogo atualizado parcialmente: {result.get('papers_processed', 0)} PDF(s) "
            f"processado(s) e {result.get('papers_failed', 0)} falha(s)."
        )
    else:
        st.success(
            f"Catálogo atualizado: {result.get('figures', 0)} figura(s) e "
            f"{result.get('tables', 0)} tabela(s) em "
            f"{result.get('papers_processed', 0)} PDF(s)."
        )
    if result.get("warnings"):
        st.caption(
            f"{result['warnings']} página(s)/etapa(s) exigiram tolerância do detector. "
            "Os demais candidatos foram preservados para revisão."
        )

st.divider()
st.header("2. Revisar candidatos")

try:
    artifacts = list_visual_artifacts(project_id)
except Exception as error:
    st.error(f"Não foi possível carregar o catálogo visual: {error}")
    st.stop()

summary = summarize_visual_artifacts(artifacts)
col_total, col_figures, col_tables, col_pending, col_reviewed = st.columns(5)
col_total.metric("Candidatos atuais", summary["total"])
col_figures.metric("Figuras", summary["figures"])
col_tables.metric("Tabelas", summary["tables"])
col_pending.metric("Pendentes", summary["pending"])
col_reviewed.metric("Revisados", summary["reviewed"])

if not artifacts:
    st.info("Execute a catalogação para localizar tabelas e figuras nos PDFs associados.")
    st.stop()

filter_label = st.selectbox(
    "Estado exibido",
    ["Todos", "Pendente", "Aprovado", "Corrigido", "Rejeitado"],
)
reverse_status = {label: code for code, label in STATUS_LABELS.items()}
visible = (
    artifacts
    if filter_label == "Todos"
    else [item for item in artifacts if item["review_status"] == reverse_status[filter_label]]
)
if not visible:
    st.info("Nenhum candidato visual corresponde ao filtro selecionado.")
    st.stop()

by_id = {str(item["id"]): item for item in visible}
artifact_id = st.selectbox(
    "Candidato visual",
    list(by_id),
    format_func=lambda value: (
        f"{TYPE_LABELS[by_id[value]['artifact_type']]} · página "
        f"{by_id[value]['page_number']} · {by_id[value]['paper_title']}"
    ),
)
artifact = by_id[artifact_id]

left, right = st.columns([1.15, 1])
with left:
    try:
        preview = render_visual_artifact_preview(project_id, artifact_id)
        st.image(
            preview,
            caption=(
                f"{TYPE_LABELS[artifact['artifact_type']]} · página "
                f"{artifact['page_number']} · recorte gerado do PDF original"
            ),
            use_container_width=True,
        )
    except Exception as error:
        st.warning(f"A prévia não pôde ser renderizada: {error}")

with right:
    st.markdown(f"**Artigo:** {artifact['paper_title']}")
    st.markdown(f"**Paper ID:** `{artifact['paper_id']}`")
    st.markdown(f"**Página:** {artifact['page_number']}")
    st.markdown(f"**Estado:** {STATUS_LABELS[artifact['review_status']]}")
    st.markdown(
        f"**Método de detecção:** "
        f"{METHOD_LABELS.get(artifact['detection_method'], artifact['detection_method'])}"
    )
    st.markdown(f"**Legenda detectada:** {artifact.get('caption') or 'Não identificada'}")
    if artifact.get("human_description"):
        st.markdown(f"**Descrição humana:** {artifact['human_description']}")
    with st.expander("Contexto textual da página"):
        st.write(artifact.get("context_text") or "Contexto textual não disponível.")

    table_content = artifact.get("extracted_content_jsonb") or {}
    rows = table_content.get("rows") or []
    if rows:
        with st.expander("Estrutura tabular detectada", expanded=True):
            width = max(len(row) for row in rows)
            normalized = [list(row) + [""] * (width - len(row)) for row in rows]
            st.dataframe(pd.DataFrame(normalized), hide_index=True, width="stretch")
            if table_content.get("row_count_detected", len(rows)) > len(rows):
                st.caption("A prévia foi limitada; o total detectado permanece registrado.")

st.divider()
with st.form(f"visual_review_{artifact_id}"):
    decision_label = st.radio("Decisão humana", list(DECISION_LABELS), horizontal=True)
    decision = DECISION_LABELS[decision_label]
    corrected_type = st.selectbox(
        "Tipo correto",
        ["figure", "table"],
        index=0 if artifact["artifact_type"] == "figure" else 1,
        format_func=lambda value: TYPE_LABELS[value],
        help="Aplicado somente quando a decisão for corrigir a classificação/legenda.",
    )
    corrected_caption = st.text_area(
        "Legenda corrigida",
        value=artifact.get("caption") or "",
        help="Aplicada somente quando a decisão for corrigir a classificação/legenda.",
    )
    description = st.text_area(
        "Descrição humana do conteúdo visual",
        value=artifact.get("human_description") or "",
        help=(
            "Obrigatória para aprovação/correção. Descreva somente o que pode ser "
            "confirmado visualmente; a interpretação científica virá em etapa posterior."
        ),
    )
    notes = st.text_area(
        "Notas ou justificativa",
        value=artifact.get("human_notes") or "",
        help="Obrigatória para rejeitar um falso positivo.",
    )
    reviewer = st.text_input(
        "Responsável pela revisão",
        value=artifact.get("reviewer_name") or "",
    )
    confirmation = st.checkbox(
        "Confirmo que conferi este candidato no PDF e que a decisão é humana."
    )
    submitted = st.form_submit_button("Registrar revisão visual", type="primary")

if submitted:
    if not confirmation:
        st.warning("Confirme a conferência humana antes de registrar a revisão.")
    else:
        try:
            review_visual_artifact(
                project_id,
                artifact_id,
                decision,
                reviewer,
                artifact_type=corrected_type,
                caption=corrected_caption,
                human_description=description,
                human_notes=notes,
            )
        except ValueError as error:
            st.warning(str(error))
        except Exception as error:
            st.error(f"Não foi possível registrar a revisão visual: {error}")
        else:
            st.success("Revisão visual registrada com histórico rastreável.")
            st.rerun()
