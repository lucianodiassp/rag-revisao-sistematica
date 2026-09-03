"""Detecção e revisão humana de tabelas e figuras dos PDFs."""

import os
import sys

import pandas as pd
import streamlit as st

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from backend.app.ai_config import TASK_VISUAL_INTERPRETATION, get_generation_config
from backend.app.background_jobs import (
    JOB_VISUAL_CATALOGING,
    JOB_VISUAL_INTERPRETATION,
    get_latest_job,
)
from backend.app.visual_catalog import (
    list_visual_artifacts,
    render_visual_artifact_preview,
    review_visual_artifact,
    summarize_visual_artifacts,
)
from backend.app.visual_interpretation import (
    get_current_visual_interpretation,
    review_visual_interpretation,
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

st.divider()
st.header("3. Interpretar candidato aprovado")
st.info(
    "A interpretação é opcional e feita para um único recorte por vez. O recorte será "
    "enviado ao provedor externo configurado somente após sua confirmação. A resposta "
    "só poderá ser usada no Assistente com o uso visual habilitado explicitamente no projeto. "
    "Permanece fora do relatório final."
)

if artifact["review_status"] not in {"approved", "corrected"}:
    st.warning(
        "Aprove ou corrija o candidato visual na etapa 2 antes de solicitar uma "
        "interpretação por IA."
    )
    st.stop()

try:
    interpretation_config = get_generation_config(TASK_VISUAL_INTERPRETATION)
    current_interpretation = get_current_visual_interpretation(project_id, artifact_id)
except Exception as error:
    st.error(f"Não foi possível carregar a configuração de interpretação: {error}")
    st.stop()

provider_labels = {"google_gemini": "Google Gemini", "openai": "OpenAI"}
config_col, model_col = st.columns(2)
config_col.metric(
    "Provedor",
    provider_labels.get(interpretation_config.provider, interpretation_config.provider),
)
model_col.metric("Modelo", interpretation_config.model)

interpret_job = render_job_status(
    project_id,
    JOB_VISUAL_INTERPRETATION,
    key="visual_interpretation",
    title="Interpretação visual",
    parameters={"artifact_id": artifact_id},
)
global_interpret_job = get_latest_job(project_id, JOB_VISUAL_INTERPRETATION)
another_interpretation_active = (
    job_is_active(global_interpret_job)
    and (global_interpret_job.get("parameters_jsonb") or {}).get("artifact_id")
    != artifact_id
)
if another_interpretation_active:
    st.info("Outro candidato visual deste projeto está sendo interpretado no momento.")
external_confirmation = st.checkbox(
    "Autorizo o envio deste recorte aprovado ao provedor de IA configurado.",
    key=f"visual_external_confirmation_{artifact_id}",
)
if st.button(
    "✨ Solicitar interpretação visual",
    type="primary",
    width="stretch",
    disabled=(
        job_is_active(interpret_job)
        or another_interpretation_active
        or not external_confirmation
    ),
):
    try:
        start_job(
            project_id,
            JOB_VISUAL_INTERPRETATION,
            {"artifact_id": artifact_id},
        )
        st.rerun()
    except Exception as error:
        st.error(f"Não foi possível solicitar a interpretação visual: {error}")

if not current_interpretation:
    st.caption("Este candidato ainda não possui interpretação multimodal registrada.")
    st.stop()

st.subheader("Interpretação registrada")
interpretation = current_interpretation.get("interpretation_jsonb") or {}
status = current_interpretation.get("review_status", "pending")
st.markdown(f"**Estado da segunda revisão:** {STATUS_LABELS.get(status, status)}")
st.markdown(f"**Resumo da IA:** {interpretation.get('summary') or 'Não disponível'}")
if interpretation.get("observations"):
    st.markdown("**Observações verificáveis propostas:**")
    for observation in interpretation["observations"]:
        st.markdown(f"- {observation}")
if interpretation.get("limitations"):
    st.markdown("**Limitações declaradas:**")
    for limitation in interpretation["limitations"]:
        st.markdown(f"- {limitation}")
st.caption(
    f"Confiança declarada: {interpretation.get('confidence', 'não informada')} · "
    f"prompt: {current_interpretation.get('prompt_version')} · "
    f"hash do recorte: {current_interpretation.get('image_sha256')}"
)
if interpretation.get("structured_data") is not None:
    with st.expander("Dados estruturados propostos pela IA"):
        st.json(interpretation["structured_data"])

SECOND_DECISIONS = {
    "Aprovar interpretação": "approved",
    "Corrigir resumo": "corrected",
    "Rejeitar interpretação": "rejected",
}
second_review_success_key = (
    f"visual_second_review_success_{project_id}_{current_interpretation['id']}"
)
with st.form(f"visual_interpretation_review_{current_interpretation['id']}"):
    second_label = st.radio(
        "Segunda decisão humana",
        list(SECOND_DECISIONS),
        horizontal=True,
    )
    second_action = SECOND_DECISIONS[second_label]
    corrected_summary = st.text_area(
        "Resumo humano corrigido",
        value=(current_interpretation.get("human_interpretation_jsonb") or {}).get(
            "summary", interpretation.get("summary") or ""
        ),
        help="Usado somente quando a decisão for Corrigir resumo.",
    )
    interpretation_notes = st.text_area(
        "Justificativa ou notas da segunda revisão",
        value=current_interpretation.get("human_notes") or "",
        help="Obrigatória para corrigir ou rejeitar.",
    )
    interpretation_reviewer = st.text_input(
        "Responsável pela segunda revisão",
        value=current_interpretation.get("reviewer_name") or "",
    )
    second_confirmation = st.checkbox(
        "Confirmo que comparei a interpretação com o recorte e o PDF original."
    )
    second_submitted = st.form_submit_button(
        "Registrar segunda revisão",
        type="primary",
    )

# Exibe o aviso após o rerun que recarrega a decisão salva, junto ao formulário.
second_review_success = st.session_state.pop(second_review_success_key, None)
if second_review_success:
    st.success(second_review_success)

if second_submitted:
    if not second_confirmation:
        st.warning("Confirme a conferência humana antes de registrar a decisão.")
    else:
        try:
            review_visual_interpretation(
                project_id,
                str(current_interpretation["id"]),
                second_action,
                interpretation_reviewer,
                corrected_summary=corrected_summary,
                human_notes=interpretation_notes,
            )
        except ValueError as error:
            st.warning(str(error))
        except Exception as error:
            st.error(f"Não foi possível registrar a segunda revisão: {error}")
        else:
            st.session_state[second_review_success_key] = (
                "Segunda revisão salva com sucesso. "
                f"Estado: {STATUS_LABELS[second_action]}. Histórico preservado."
            )
            st.rerun()
