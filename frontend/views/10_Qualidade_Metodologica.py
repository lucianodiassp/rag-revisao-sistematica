import os
import sys

import pandas as pd
import streamlit as st


sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from backend.app.methodological_quality import (  # noqa: E402
    RATINGS,
    RESPONSES,
    analyze_paper_with_ai,
    create_instrument_version,
    create_manual_assessment,
    ensure_default_instrument,
    list_eligible_assessments,
    list_instrument_versions,
    load_assessment_sources,
    methodological_summary,
    save_human_assessment,
)
from frontend.project_selector import selecionar_projeto_ativo  # noqa: E402


RESPONSE_LABELS = {
    "yes": "Sim — critério atendido",
    "no": "Não — possível problema metodológico",
    "uncertain": "Incerto — informação insuficiente",
    "not_applicable": "Não aplicável ao desenho do estudo",
}
RATING_LABELS = {
    "low": "Baixo risco / boa qualidade",
    "moderate": "Risco moderado",
    "high": "Alto risco / limitação importante",
    "uncertain": "Incerto por informação insuficiente",
}


st.set_page_config(page_title="Qualidade Metodológica", page_icon="🧭", layout="wide")
project = selecionar_projeto_ativo()
project_id = str(project["id"])

st.title("🧭 Qualidade Metodológica e Possíveis Vieses")
st.caption(f"Projeto ativo: **{project['title']}**")
st.info(
    "Este checklist é genérico e exploratório. Ele não substitui instrumentos oficiais "
    "específicos para cada desenho de estudo. A IA apenas sugere; a classificação válida "
    "é sempre a registrada pela revisão humana."
)

try:
    instrument = ensure_default_instrument(project_id)
except Exception as error:
    st.error(f"Não foi possível carregar o instrumento: {error}")
    st.stop()

st.header("1. Instrumento versionado")
col_name, col_version = st.columns([4, 1])
col_name.markdown(f"**{instrument['name']}**")
col_name.caption(instrument["description"])
col_version.metric("Versão ativa", instrument["version"])

with st.expander("Consultar domínios e criar uma nova versão"):
    st.warning(
        "Uma nova versão preserva as avaliações antigas como histórico. Os artigos precisarão "
        "ser avaliados novamente para que os resultados usem o instrumento atualizado."
    )
    with st.form(f"instrument_version_{instrument['version']}"):
        new_name = st.text_input("Nome do instrumento", value=instrument["name"])
        new_description = st.text_area("Descrição e escopo", value=instrument["description"])
        edited_domains = []
        for domain in instrument["domains_jsonb"]:
            st.markdown(f"**{domain['label']}** · código `{domain['code']}`")
            question = st.text_area(
                "Pergunta de avaliação",
                value=domain["question"],
                key=f"question_{instrument['version']}_{domain['code']}",
            )
            critical = st.checkbox(
                "Domínio crítico",
                value=bool(domain.get("critical")),
                key=f"critical_{instrument['version']}_{domain['code']}",
            )
            edited_domains.append({**domain, "question": question, "critical": critical})
        change_reason = st.text_input("Motivo da nova versão")
        create_version = st.form_submit_button("Criar e ativar nova versão")
    if create_version:
        try:
            result = create_instrument_version(
                project_id, new_name, new_description, edited_domains, change_reason
            )
            st.success(f"Instrumento v{result['version']} criado e ativado.")
            st.rerun()
        except Exception as error:
            st.error(f"Não foi possível criar a versão: {error}")

    versions = list_instrument_versions(project_id)
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Versão": item["version"],
                    "Nome": item["name"],
                    "Ativa": "Sim" if item["is_active"] else "Não",
                    "Motivo": item["change_reason"],
                    "Criada em": item["created_at"],
                }
                for item in versions
            ]
        ),
        hide_index=True,
        use_container_width=True,
    )

st.divider()
st.header("2. Avaliação dos estudos")
st.markdown(
    "São exibidos somente artigos **incluídos na triagem** e com texto integral indexado. "
    "Você pode começar manualmente ou solicitar uma sugestão rastreável da IA."
)

try:
    items = list_eligible_assessments(project_id, instrument["id"])
except Exception as error:
    st.error(f"Não foi possível carregar os artigos: {error}")
    st.stop()

if not items:
    st.warning(
        "Ainda não há artigos incluídos com PDF indexado. Conclua a Triagem e a Gestão de PDFs."
    )
    st.stop()

counts = {
    "eligible": len(items),
    "pending": sum(1 for item in items if item.get("assessment_id") and item.get("review_status") != "reviewed"),
    "reviewed": sum(1 for item in items if item.get("review_status") == "reviewed"),
    "not_started": sum(1 for item in items if not item.get("assessment_id")),
}
c1, c2, c3, c4 = st.columns(4)
c1.metric("Artigos elegíveis", counts["eligible"])
c2.metric("Não iniciados", counts["not_started"])
c3.metric("Aguardando revisão", counts["pending"])
c4.metric("Revisados", counts["reviewed"])

by_id = {str(item["paper_id"]): item for item in items}
paper_id = st.selectbox(
    "Artigo",
    options=list(by_id),
    format_func=lambda value: by_id[value]["title"],
)
selected = by_id[paper_id]

action1, action2 = st.columns(2)
with action1:
    if st.button("🧑 Iniciar avaliação manual", use_container_width=True):
        try:
            create_manual_assessment(project_id, paper_id)
            st.success("Avaliação aberta para preenchimento humano.")
            st.rerun()
        except Exception as error:
            st.error(f"Não foi possível iniciar a avaliação: {error}")
with action2:
    if st.button(
        "🤖 Gerar / atualizar sugestão da IA",
        type="primary",
        use_container_width=True,
        disabled=selected.get("review_status") == "reviewed",
        help=(
            "Uma revisão humana concluída é preservada. Crie uma nova versão do "
            "instrumento se for necessário reavaliar o artigo."
            if selected.get("review_status") == "reviewed"
            else None
        ),
    ):
        try:
            with st.spinner("Lendo o PDF e validando as citações literais..."):
                analyze_paper_with_ai(project_id, paper_id)
            st.success("Sugestão gerada. Revise todos os domínios antes de salvar.")
            st.rerun()
        except Exception as error:
            st.error(f"Não foi possível gerar a sugestão: {error}")

if not selected.get("assessment_id"):
    st.caption("Inicie a avaliação manualmente ou gere uma sugestão da IA.")
else:
    assessment_id = str(selected["assessment_id"])
    suggestion = selected.get("ai_suggestion_jsonb") or {}
    human = selected.get("human_assessment_jsonb") or {}
    suggested_by_domain = {
        item["domain_code"]: item for item in suggestion.get("domains", [])
    }
    human_by_domain = {
        item["domain_code"]: item for item in human.get("domains", [])
    }
    sources = load_assessment_sources(assessment_id, project_id)

    if suggestion:
        st.caption(
            f"Sugestão geral da IA: **{RATING_LABELS.get(suggestion.get('suggested_overall_rating'), 'Incerta')}** · "
            f"{suggestion.get('document_scope', {}).get('chunks_used', 0)} trecho(s) analisado(s)."
        )
        if suggestion.get("document_scope", {}).get("truncated"):
            st.warning("O PDF ultrapassou o limite de contexto; a sugestão não cobriu todo o documento.")
        for warning in suggestion.get("validation_warnings", []):
            st.warning(warning)
    else:
        st.caption("Avaliação iniciada sem IA; as justificativas serão exclusivamente humanas.")

    with st.form(f"assessment_{assessment_id}"):
        answers = {}
        confirmed_source_ids = []
        for domain in instrument["domains_jsonb"]:
            code = domain["code"]
            ai_domain = suggested_by_domain.get(code, {})
            human_domain = human_by_domain.get(code, {})
            st.subheader(domain["label"])
            st.caption(domain["question"] + (" · domínio crítico" if domain.get("critical") else ""))
            initial_response = human_domain.get("response") or ai_domain.get("response") or "uncertain"
            response = st.selectbox(
                "Decisão humana",
                options=list(RESPONSES),
                index=list(RESPONSES).index(initial_response),
                format_func=lambda value: RESPONSE_LABELS[value],
                key=f"response_{assessment_id}_{code}",
            )
            initial_justification = human_domain.get("justification") or ai_domain.get("rationale") or ""
            justification = st.text_area(
                "Justificativa humana",
                value=initial_justification,
                key=f"justification_{assessment_id}_{code}",
            )
            domain_sources = [item for item in sources if item["domain_code"] == code]
            if domain_sources:
                st.markdown("Fontes literais sugeridas pela IA:")
                for source in domain_sources:
                    checked = st.checkbox(
                        f"Confirmar p. {source['page_number']}: “{source['quote']}”",
                        value=bool(source["human_validated"]),
                        key=f"source_{source['id']}",
                    )
                    if checked:
                        confirmed_source_ids.append(str(source["id"]))
            answers[code] = {"response": response, "justification": justification}
            st.divider()

        suggested_rating = suggestion.get("suggested_overall_rating", "uncertain")
        initial_rating = selected.get("overall_rating") or suggested_rating
        overall_rating = st.selectbox(
            "Classificação final humana",
            options=list(RATINGS),
            index=list(RATINGS).index(initial_rating),
            format_func=lambda value: RATING_LABELS[value],
        )
        review_notes = st.text_area(
            "Síntese e justificativa geral",
            value=selected.get("review_notes") or suggestion.get("overall_rationale") or "",
        )
        acknowledge = st.checkbox(
            "Confirmo que revisei as respostas e que a classificação final é uma decisão humana."
        )
        save = st.form_submit_button("💾 Registrar revisão metodológica", type="primary")
    if save:
        if not acknowledge:
            st.error("Confirme a responsabilidade pela revisão humana antes de registrar.")
        else:
            try:
                save_human_assessment(
                    project_id,
                    assessment_id,
                    answers,
                    overall_rating,
                    review_notes,
                    confirmed_source_ids,
                )
                st.success("Avaliação humana registrada com rastreabilidade.")
                st.rerun()
            except Exception as error:
                st.error(f"Não foi possível registrar a avaliação: {error}")

st.divider()
st.header("3. Síntese das avaliações revisadas")
summary = methodological_summary(project_id)
if summary:
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Artigo": item["title"],
                    "Instrumento": f"{item['instrument_name']} v{item['instrument_version']}",
                    "Classificação humana": RATING_LABELS[item["overall_rating"]],
                    "Fontes confirmadas": item["confirmed_sources"],
                    "Revisado em": item["reviewed_at"],
                }
                for item in summary
            ]
        ),
        hide_index=True,
        use_container_width=True,
    )
else:
    st.caption("Nenhuma avaliação da versão ativa foi revisada por humano.")
