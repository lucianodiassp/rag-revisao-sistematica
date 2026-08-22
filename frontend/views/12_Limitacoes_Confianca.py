import os
import sys

import pandas as pd
import streamlit as st


sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from backend.app.synthesis_confidence import (  # noqa: E402
    CATEGORIES,
    CONFIDENCE_DOMAINS,
    CONFIDENCE_LEVELS,
    confidence_snapshot_json,
    confidence_summary,
    create_manual_limitation,
    list_confidence_snapshots,
    list_limitations,
    review_limitation,
    save_confidence_snapshot,
    suggest_confidence,
    synchronize_limitations,
)
from frontend.project_selector import selecionar_projeto_ativo  # noqa: E402


STATUS_LABELS = {
    "pending": "Pendente de revisão",
    "confirmed": "Confirmada",
    "dismissed": "Descartada com justificativa",
    "mitigated": "Mitigada",
    "resolved": "Resolvida",
}
IMPACT_LABELS = {"low": "Baixo", "moderate": "Moderado", "high": "Alto"}
CONFIDENCE_LABELS = {
    "high": "Alta",
    "moderate": "Moderada",
    "low": "Baixa",
    "very_low": "Muito baixa",
}
SOURCE_LABELS = {
    "automatic": "Sinal determinístico do sistema",
    "study_reported": "Relatada pelo próprio estudo",
    "manual": "Registrada pelo pesquisador",
}


st.set_page_config(page_title="Limitações e Confiança", page_icon="⚖️", layout="wide")
project = selecionar_projeto_ativo()
project_id = str(project["id"])

st.title("⚖️ Limitações e Confiança na Síntese")
st.caption(
    f"Projeto ativo: **{project['title']}** · protocolo v{project.get('protocol_version', 1)}"
)
st.info(
    "O sistema detecta sinais objetivos, mas não os transforma automaticamente em conclusões. "
    "Você confirma, descarta, mitiga ou resolve cada alerta. Somente um snapshot registrado "
    "por uma pessoa representa a confiança válida da síntese. Este painel não aplica GRADE."
)

st.header("1. Sinais de limitação revisáveis")
col_update, col_explanation = st.columns([1, 2])
with col_update:
    if st.button("🔄 Atualizar sinais do projeto", type="primary", width="stretch"):
        try:
            result = synchronize_limitations(project_id)
            st.success(f"Atualização concluída: {result['signals_detected']} sinal(is) atual(is).")
            st.rerun()
        except Exception as error:
            st.error(f"Não foi possível atualizar os sinais: {error}")
with col_explanation:
    st.caption(
        "Atualize após mudanças na busca, triagem, PDFs, matriz, qualidade metodológica ou benchmark. "
        "Decisões humanas anteriores são preservadas; sinais que reaparecem voltam para revisão."
    )

try:
    limitations = list_limitations(project_id, include_historical=True)
except Exception as error:
    st.error(f"Não foi possível carregar as limitações: {error}")
    st.stop()

current = [item for item in limitations if item["is_current"]]
metrics = {
    status: sum(1 for item in current if item["status"] == status)
    for status in STATUS_LABELS
}
m1, m2, m3, m4 = st.columns(4)
m1.metric("Sinais atuais", len(current))
m2.metric("Aguardando revisão", metrics["pending"])
m3.metric("Confirmados", metrics["confirmed"])
m4.metric("Mitigados", metrics["mitigated"])

filter_col1, filter_col2, filter_col3 = st.columns(3)
category_filter = filter_col1.selectbox(
    "Categoria",
    options=["all", *CATEGORIES],
    format_func=lambda value: "Todas" if value == "all" else CATEGORIES[value],
)
status_filter = filter_col2.selectbox(
    "Situação",
    options=["all", *STATUS_LABELS],
    format_func=lambda value: "Todas" if value == "all" else STATUS_LABELS[value],
)
scope_filter = filter_col3.selectbox(
    "Histórico",
    options=["current", "all"],
    format_func=lambda value: "Somente sinais atuais" if value == "current" else "Incluir histórico",
)

filtered = [
    item for item in limitations
    if (category_filter == "all" or item["category"] == category_filter)
    and (status_filter == "all" or item["status"] == status_filter)
    and (scope_filter == "all" or item["is_current"])
]

if not filtered:
    st.caption("Nenhum sinal corresponde aos filtros. Atualize os sinais se este projeto ainda não foi analisado.")

for item in filtered:
    current_marker = "atual" if item["is_current"] else "histórico"
    label = (
        f"{IMPACT_LABELS[item['impact']]} · {STATUS_LABELS[item['status']]} · "
        f"{item['title']} ({current_marker})"
    )
    with st.expander(label, expanded=item["status"] == "pending" and item["is_current"]):
        c1, c2, c3 = st.columns(3)
        c1.write(f"**Categoria:** {CATEGORIES[item['category']]}")
        c2.write(f"**Origem:** {SOURCE_LABELS[item['source_kind']]}")
        c3.write(f"**Protocolo detectado:** v{item['detected_protocol_version']}")
        st.write(item["description"])
        with st.expander("Ver evidência objetiva do sinal"):
            st.json(item.get("evidence_jsonb") or {})

        if not item["is_current"]:
            st.caption("Este sinal não representa mais o estado atual e foi preservado para auditoria.")
            continue

        with st.form(f"review_limitation_{item['id']}"):
            decisions = ["confirmed", "mitigated", "dismissed", "resolved"]
            current_status = item["status"] if item["status"] in decisions else "confirmed"
            decision = st.selectbox(
                "Decisão humana",
                options=decisions,
                index=decisions.index(current_status),
                format_func=lambda value: STATUS_LABELS[value],
            )
            impact = st.selectbox(
                "Impacto na interpretação da síntese",
                options=["low", "moderate", "high"],
                index=["low", "moderate", "high"].index(item["impact"]),
                format_func=lambda value: IMPACT_LABELS[value],
            )
            mitigation = st.text_area(
                "Medida de mitigação",
                value=item.get("mitigation") or "",
                help="Obrigatória quando a decisão for Mitigada.",
            )
            notes = st.text_area(
                "Justificativa ou observação humana",
                value=item.get("human_notes") or "",
                help="Obrigatória para descartar ou declarar o sinal resolvido.",
            )
            submitted = st.form_submit_button("Registrar revisão humana", type="primary")
        if submitted:
            try:
                review_limitation(
                    project_id, item["id"], decision, impact,
                    mitigation=mitigation, human_notes=notes,
                )
                st.success("Revisão registrada com rastreabilidade.")
                st.rerun()
            except Exception as error:
                st.error(f"Não foi possível registrar a revisão: {error}")

with st.expander("➕ Registrar uma limitação identificada pelo pesquisador"):
    with st.form("manual_limitation"):
        manual_category = st.selectbox(
            "Categoria", options=list(CATEGORIES), format_func=lambda value: CATEGORIES[value]
        )
        manual_title = st.text_input("Título")
        manual_description = st.text_area("Descrição e efeito possível na interpretação")
        manual_impact = st.selectbox(
            "Impacto", options=["low", "moderate", "high"], index=1,
            format_func=lambda value: IMPACT_LABELS[value],
        )
        manual_mitigation = st.text_area("Mitigação adotada ou planejada")
        manual_notes = st.text_area("Observações do pesquisador")
        manual_submit = st.form_submit_button("Registrar limitação manual")
    if manual_submit:
        try:
            create_manual_limitation(
                project_id, manual_category, manual_title, manual_description,
                manual_impact, manual_mitigation, manual_notes,
            )
            st.success("Limitação manual confirmada e registrada.")
            st.rerun()
        except Exception as error:
            st.error(f"Não foi possível registrar a limitação: {error}")

st.divider()
st.header("2. Classificação humana da confiança")
st.caption(
    "A sugestão abaixo deriva apenas dos impactos confirmados e mitigados. Ela serve como apoio "
    "à revisão e nunca substitui a classificação e a justificativa do pesquisador."
)

current_limitations = [item for item in limitations if item["is_current"]]
suggestion = suggest_confidence(current_limitations)
try:
    snapshots = list_confidence_snapshots(project_id)
except Exception as error:
    st.error(f"Não foi possível carregar os snapshots de confiança: {error}")
    st.stop()
latest = snapshots[0] if snapshots else None
latest_domains = {
    item["code"]: item for item in (latest or {}).get("domain_ratings_jsonb", [])
}

st.info(
    f"Sugestão determinística não vinculante: **{CONFIDENCE_LABELS[suggestion['overall_level']]}** · "
    f"baseada em {suggestion['basis_count']} limitação(ões) confirmada(s) ou mitigada(s)."
)
if metrics["pending"]:
    st.warning(
        f"Revise os {metrics['pending']} sinal(is) atual(is) pendente(s) antes de registrar um snapshot."
    )

with st.form("confidence_snapshot"):
    domain_ratings = []
    for domain in CONFIDENCE_DOMAINS:
        suggested_domain = next(
            item for item in suggestion["domains"] if item["code"] == domain["code"]
        )
        previous = latest_domains.get(domain["code"], {})
        initial_level = previous.get("level") or suggested_domain["suggested_level"]
        st.subheader(domain["label"])
        st.caption(domain["description"])
        domain_level = st.selectbox(
            "Confiança nesta dimensão",
            options=list(CONFIDENCE_LEVELS),
            index=list(CONFIDENCE_LEVELS).index(initial_level),
            format_func=lambda value: CONFIDENCE_LABELS[value],
            key=f"confidence_{domain['code']}",
        )
        domain_rationale = st.text_area(
            "Justificativa específica (opcional)",
            value=previous.get("rationale") or "",
            key=f"confidence_rationale_{domain['code']}",
        )
        domain_ratings.append(
            {"code": domain["code"], "level": domain_level, "rationale": domain_rationale}
        )

    initial_overall = (latest or {}).get("overall_level") or suggestion["overall_level"]
    overall = st.selectbox(
        "Confiança geral na síntese",
        options=list(CONFIDENCE_LEVELS),
        index=list(CONFIDENCE_LEVELS).index(initial_overall),
        format_func=lambda value: CONFIDENCE_LABELS[value],
    )
    rationale = st.text_area(
        "Justificativa integrada da classificação geral",
        value=(latest or {}).get("rationale") or "",
    )
    reviewer = st.text_input(
        "Nome ou identificação do revisor", value=(latest or {}).get("reviewer_name") or ""
    )
    acknowledged = st.checkbox(
        "Confirmo que revisei os sinais e que esta classificação representa minha avaliação humana."
    )
    save_snapshot = st.form_submit_button("📌 Registrar snapshot de confiança", type="primary")

if save_snapshot:
    if not acknowledged:
        st.error("Marque a confirmação de revisão humana antes de registrar o snapshot.")
    else:
        try:
            created = save_confidence_snapshot(
                project_id, domain_ratings, overall, rationale, reviewer_name=reviewer
            )
            st.success(f"Snapshot de confiança v{created['snapshot_version']} registrado.")
            st.rerun()
        except Exception as error:
            st.error(f"Não foi possível registrar o snapshot: {error}")

st.divider()
st.header("3. Histórico versionado")
try:
    summary = confidence_summary(project_id)
except Exception as error:
    st.error(f"Não foi possível calcular o estado da confiança: {error}")
    st.stop()

if summary["is_stale"]:
    st.warning("O último snapshot ficou desatualizado em relação ao protocolo ou às limitações atuais.")
for warning in summary["warnings"]:
    st.caption(f"• {warning}")

if snapshots:
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Versão": item["snapshot_version"],
                    "Protocolo": item["protocol_version"],
                    "Confiança geral": CONFIDENCE_LABELS[item["overall_level"]],
                    "Revisor": item.get("reviewer_name"),
                    "Registrado em": item["created_at"],
                }
                for item in snapshots
            ]
        ),
        hide_index=True,
        width="stretch",
    )
    chosen_version = st.selectbox(
        "Snapshot para exportação",
        options=[item["snapshot_version"] for item in snapshots],
    )
    chosen = next(item for item in snapshots if item["snapshot_version"] == chosen_version)
    st.download_button(
        "⬇️ Baixar snapshot de confiança (JSON)",
        confidence_snapshot_json(chosen),
        file_name=f"confianca_sintese_v{chosen_version}.json",
        mime="application/json",
    )
else:
    st.info("Ainda não há snapshot de confiança registrado para este projeto.")
