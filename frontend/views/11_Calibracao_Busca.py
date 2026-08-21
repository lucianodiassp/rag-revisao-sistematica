import os
import sys

import pandas as pd
import streamlit as st


sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from backend.app.search_calibration import (  # noqa: E402
    PRESS_DOMAINS,
    SOURCE_LABELS,
    calibration_export_json,
    calibration_matches_csv,
    list_calibration_runs,
    list_press_reviews,
    list_sentinels,
    run_calibration,
    save_press_review,
    save_sentinel,
    set_sentinel_active,
)
from frontend.project_selector import selecionar_projeto_ativo  # noqa: E402


RESPONSE_LABELS = {
    "yes": "Sim — atendido",
    "no": "Não — requer correção",
    "uncertain": "Incerto — revisar",
    "not_applicable": "Não aplicável",
}
DECISION_LABELS = {
    "approved": "Aprovada para execução",
    "changes_requested": "Alterações necessárias",
}
MATCH_LABELS = {
    "doi_exact": "DOI exato",
    "title_exact": "Título exato",
    "title_similar": "Título muito semelhante",
}


st.set_page_config(page_title="Calibração da Busca", page_icon="🎯", layout="wide")
project = selecionar_projeto_ativo()
project_id = str(project["id"])

st.title("🎯 Calibração da Estratégia de Busca")
st.caption(
    f"Projeto ativo: **{project['title']}** · protocolo v{project['protocol_version']}"
)
st.info(
    "Use artigos cuja relevância já é conhecida para testar a estratégia antes da coleta "
    "definitiva. O piloto é isolado: seus resultados não entram no corpus nem na triagem."
)

st.header("1. Artigos sentinela")
st.markdown(
    "Cadastre estudos relevantes conhecidos previamente. O DOI aumenta a segurança da "
    "correspondência; quando ele não existe, o sistema usa título exato ou muito semelhante."
)

try:
    sentinels = list_sentinels(project_id)
except Exception as error:
    st.error(f"Não foi possível carregar os artigos sentinela: {error}")
    st.stop()

sentinel_by_id = {str(item["id"]): item for item in sentinels}
edit_options = [""] + list(sentinel_by_id)
selected_id = st.selectbox(
    "Adicionar ou editar",
    options=edit_options,
    format_func=lambda value: "Novo artigo sentinela" if not value else sentinel_by_id[value]["title"],
)
selected = sentinel_by_id.get(selected_id, {})
with st.form(f"sentinel_form_{selected_id or 'new'}"):
    title = st.text_input("Título do artigo *", value=selected.get("title", ""))
    doi = st.text_input(
        "DOI (recomendado)",
        value=selected.get("canonical_doi") or "",
        placeholder="10.xxxx/identificador",
    )
    notes = st.text_area(
        "Como a relevância deste artigo foi confirmada?",
        value=selected.get("notes") or "",
        height=90,
    )
    save = st.form_submit_button(
        "Salvar artigo sentinela", type="primary", use_container_width=True
    )
if save:
    try:
        save_sentinel(project_id, title, doi, notes, sentinel_id=selected_id or None)
    except Exception as error:
        st.error(f"Não foi possível salvar: {error}")
    else:
        st.success("Artigo sentinela salvo.")
        st.rerun()

if sentinels:
    active_count = sum(bool(item["is_active"]) for item in sentinels)
    st.caption(f"{active_count} ativo(s) de {len(sentinels)} cadastrado(s).")
    for sentinel in sentinels:
        c1, c2, c3 = st.columns([6, 2, 1])
        c1.markdown(f"**{sentinel['title']}**")
        c1.caption(
            f"DOI: {sentinel.get('canonical_doi') or 'não informado'}"
            + (f" · {sentinel['notes']}" if sentinel.get("notes") else "")
        )
        c2.markdown("🟢 Ativo" if sentinel["is_active"] else "⚪ Inativo")
        action_label = "Desativar" if sentinel["is_active"] else "Reativar"
        if c3.button(action_label, key=f"sentinel_active_{sentinel['id']}"):
            try:
                set_sentinel_active(project_id, sentinel["id"], not sentinel["is_active"])
            except Exception as error:
                st.error(f"Não foi possível atualizar: {error}")
            else:
                st.rerun()
else:
    st.warning("Nenhum artigo sentinela cadastrado.")

st.divider()
st.header("2. Busca piloto multifonte")
st.markdown(
    "O piloto usa as strings específicas da versão atual do protocolo. Quando uma string "
    "específica estiver vazia, será usada a string geral."
)
limit = st.slider(
    "Quantidade máxima de resultados examinados por fonte",
    min_value=10,
    max_value=100,
    value=100,
    step=10,
    help="Um limite maior permite encontrar sentinelas em posições mais baixas, mas aumenta o tempo das consultas.",
)
if st.button("▶️ Executar busca piloto", type="primary", use_container_width=True):
    try:
        with st.spinner("Consultando as fontes sem alterar o corpus do projeto..."):
            result = run_calibration(project_id, limit)
    except Exception as error:
        st.error(f"Não foi possível executar a calibração: {error}")
    else:
        if result["status"] == "completed":
            st.success("Busca piloto concluída e registrada.")
        else:
            st.warning("O piloto foi registrado, mas uma ou mais fontes falharam.")
        st.rerun()

try:
    runs = list_calibration_runs(project_id)
except Exception as error:
    st.error(f"Não foi possível carregar o histórico: {error}")
    runs = []

if not runs:
    st.caption("Ainda não há execuções piloto neste projeto.")
else:
    run_by_id = {str(item["id"]): item for item in runs}
    def format_run(value):
        item = run_by_id[value]
        return f"{item['created_at']} · protocolo v{item['protocol_version']} · {item['status']}"

    run_id = st.selectbox(
        "Execução analisada",
        options=list(run_by_id),
        format_func=format_run,
    )
    run = run_by_id[run_id]
    summary = run["summary_jsonb"]
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Sentinelas ativos", summary["active_sentinels"])
    m2.metric("Recuperados", summary["recovered_unique"])
    m3.metric("Sensibilidade conhecida", f"{summary['known_item_sensitivity']:.0%}")
    m4.metric("Protocolo", f"v{run['protocol_version']}")
    st.caption(summary["interpretation"])

    source_rows = []
    for code, source in summary["sources"].items():
        source_rows.append(
            {
                "Fonte": source["label"],
                "Resultados examinados": source["results_scanned"],
                "Sentinelas recuperados": source["sentinels_recovered"],
                "Sensibilidade conhecida": f"{source['known_item_sensitivity']:.0%}",
                "Situação": source.get("error") or "Concluída",
                "String executada": source["query"],
            }
        )
    st.dataframe(pd.DataFrame(source_rows), hide_index=True, use_container_width=True)

    if run["matches"]:
        snapshot = {item["id"]: item for item in run["sentinel_snapshot_jsonb"]}
        match_rows = []
        for match in run["matches"]:
            sentinel = snapshot.get(str(match["sentinel_id"]), {})
            match_rows.append(
                {
                    "Sentinela": sentinel.get("title", "Registro histórico"),
                    "Fonte": SOURCE_LABELS.get(match["source_code"], match["source_code"]),
                    "Posição": match["result_rank"],
                    "Regra": MATCH_LABELS.get(match["match_method"], match["match_method"]),
                    "Similaridade": f"{float(match['similarity_score']):.1%}",
                    "Título recuperado": match["matched_title"],
                    "DOI recuperado": match.get("matched_doi") or "",
                }
            )
        st.subheader("Correspondências explicáveis")
        st.dataframe(pd.DataFrame(match_rows), hide_index=True, use_container_width=True)
    if summary["missed_sentinels"]:
        st.warning(
            "Não recuperados: "
            + "; ".join(item["title"] for item in summary["missed_sentinels"])
        )
    else:
        st.success("Todos os artigos sentinela foram recuperados por pelo menos uma fonte.")

    d1, d2 = st.columns(2)
    d1.download_button(
        "Baixar execução em JSON",
        calibration_export_json(run),
        file_name=f"calibracao-busca-v{run['protocol_version']}.json",
        mime="application/json",
        use_container_width=True,
    )
    d2.download_button(
        "Baixar correspondências em CSV",
        calibration_matches_csv(run),
        file_name=f"calibracao-correspondencias-v{run['protocol_version']}.csv",
        mime="text/csv",
        use_container_width=True,
    )

    if len(runs) >= 2:
        with st.expander("Comparar execuções e versões"):
            col_a, col_b = st.columns(2)
            first_id = col_a.selectbox(
                "Execução anterior", list(run_by_id), index=min(1, len(runs) - 1),
                format_func=format_run, key="compare_first"
            )
            second_id = col_b.selectbox(
                "Execução mais recente", list(run_by_id), index=0,
                format_func=format_run, key="compare_second"
            )
            first, second = run_by_id[first_id], run_by_id[second_id]
            first_summary, second_summary = first["summary_jsonb"], second["summary_jsonb"]
            delta = second_summary["known_item_sensitivity"] - first_summary["known_item_sensitivity"]
            c1, c2, c3 = st.columns(3)
            c1.metric("Protocolo anterior", f"v{first['protocol_version']}")
            c2.metric("Protocolo comparado", f"v{second['protocol_version']}")
            c3.metric("Variação da sensibilidade", f"{delta:+.0%}")
            comparison_rows = []
            for code in sorted(set(first_summary["sources"]) | set(second_summary["sources"])):
                before = first_summary["sources"].get(code, {}).get("known_item_sensitivity", 0)
                after = second_summary["sources"].get(code, {}).get("known_item_sensitivity", 0)
                comparison_rows.append(
                    {
                        "Fonte": SOURCE_LABELS.get(code, code),
                        "Antes": f"{before:.0%}",
                        "Depois": f"{after:.0%}",
                        "Variação": f"{after - before:+.0%}",
                    }
                )
            st.dataframe(pd.DataFrame(comparison_rows), hide_index=True, use_container_width=True)

st.divider()
st.header("3. Revisão humana PRESS")
st.markdown(
    "Checklist adaptado dos seis domínios do PRESS 2015. Registre a avaliação humana "
    "da versão atual antes da busca definitiva."
)
try:
    press_reviews = list_press_reviews(project_id)
except Exception as error:
    st.error(f"Não foi possível carregar as revisões PRESS: {error}")
    press_reviews = []

current_review = next(
    (item for item in press_reviews if item["protocol_version"] == project["protocol_version"]),
    None,
)
existing_by_code = {
    item["code"]: item for item in (current_review or {}).get("checklist_jsonb", [])
}
with st.form(f"press_review_v{project['protocol_version']}"):
    checklist = []
    for domain in PRESS_DOMAINS:
        st.subheader(domain["label"])
        st.caption(domain["question"])
        existing = existing_by_code.get(domain["code"], {})
        response = st.selectbox(
            "Avaliação",
            options=list(RESPONSE_LABELS),
            index=list(RESPONSE_LABELS).index(existing.get("response", "uncertain")),
            format_func=lambda value: RESPONSE_LABELS[value],
            key=f"press_response_{domain['code']}",
        )
        comment = st.text_area(
            "Comentário ou correção proposta",
            value=existing.get("comment", ""),
            key=f"press_comment_{domain['code']}",
            height=70,
        )
        checklist.append({"code": domain["code"], "response": response, "comment": comment})

    reviewer = st.text_input(
        "Nome do revisor (opcional)", value=(current_review or {}).get("reviewer_name") or ""
    )
    decision_options = list(DECISION_LABELS)
    current_decision = (current_review or {}).get("overall_decision", "changes_requested")
    decision = st.selectbox(
        "Decisão geral",
        options=decision_options,
        index=decision_options.index(current_decision),
        format_func=lambda value: DECISION_LABELS[value],
    )
    review_notes = st.text_area(
        "Síntese da revisão",
        value=(current_review or {}).get("review_notes") or "",
        height=100,
    )
    confirm_press = st.checkbox(
        "Confirmo que esta avaliação foi revisada por uma pessoa e corresponde ao protocolo atual."
    )
    save_press = st.form_submit_button(
        "Registrar revisão PRESS",
        type="primary",
        use_container_width=True,
    )
if save_press:
    if not confirm_press:
        st.warning(
            "Marque a confirmação de revisão humana antes de registrar a avaliação PRESS."
        )
    else:
        try:
            save_press_review(
                project_id,
                project["protocol_version"],
                checklist,
                decision,
                reviewer,
                review_notes,
            )
        except Exception as error:
            st.error(f"Não foi possível registrar a revisão: {error}")
        else:
            st.success("Revisão PRESS registrada para a versão atual.")
            st.rerun()

if press_reviews:
    st.subheader("Histórico PRESS")
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Versão": item["protocol_version"],
                    "Decisão": DECISION_LABELS.get(item["overall_decision"], item["overall_decision"]),
                    "Revisor": item.get("reviewer_name") or "Não informado",
                    "Revisada em": item["reviewed_at"],
                }
                for item in press_reviews
            ]
        ),
        hide_index=True,
        use_container_width=True,
    )
