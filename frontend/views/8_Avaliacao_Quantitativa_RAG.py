import os
import sys

import pandas as pd
import streamlit as st

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from backend.app.golden_set import (
    add_golden_query,
    add_golden_relevance,
    delete_golden_query,
    delete_golden_relevance,
    list_golden_queries,
    list_indexed_papers,
)
from backend.app.rag_benchmark import (
    benchmark_to_csv,
    benchmark_to_json,
    get_latest_rag_benchmark,
    validate_golden_set,
)
from backend.app.background_jobs import JOB_RAG_BENCHMARK
from frontend.project_selector import selecionar_projeto_ativo
from frontend.background_jobs_ui import job_is_active, render_job_status, start_job


st.set_page_config(page_title="Avaliação Quantitativa do RAG", page_icon="🧪", layout="wide")
project = selecionar_projeto_ativo()
project_id = str(project["id"])

st.title("🧪 Avaliação Quantitativa do RAG")
st.caption(f"Projeto ativo: **{project['title']}**")
st.markdown(
    "Crie um gabarito humano e meça objetivamente se a busca híbrida e o "
    "reranking recuperam os artigos e páginas corretos."
)

try:
    golden = list_golden_queries(project_id)
    indexed_papers = list_indexed_papers(project_id)
except Exception as exc:
    st.error(f"Não foi possível carregar a avaliação quantitativa: {exc}")
    st.stop()

golden_tab, benchmark_tab, guide_tab = st.tabs(
    ["1. Golden Set", "2. Executar e comparar", "Como interpretar"]
)

with golden_tab:
    metric_col1, metric_col2, metric_col3 = st.columns(3)
    metric_col1.metric("Versão do Golden Set", golden["version"])
    metric_col2.metric("Perguntas", len(golden["queries"]))
    metric_col3.metric(
        "Julgamentos humanos",
        sum(len(item["relevances"]) for item in golden["queries"]),
    )

    with st.expander("➕ Adicionar pergunta ao Golden Set", expanded=not golden["queries"]):
        with st.form("add_golden_query", clear_on_submit=True):
            question = st.text_area(
                "Pergunta de referência",
                placeholder="Ex.: Quais métodos foram utilizados para otimizar as rotas?",
            )
            expected_refusal = st.checkbox(
                "O sistema deve recusar esta pergunta",
                help="Use para perguntas fora do escopo dos PDFs do projeto.",
            )
            notes = st.text_input("Observação metodológica (opcional)")
            if st.form_submit_button("Adicionar pergunta", type="primary"):
                try:
                    add_golden_query(
                        project_id,
                        question,
                        expected_refusal=expected_refusal,
                        notes=notes,
                    )
                    st.success("Pergunta adicionada e Golden Set versionado.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Não foi possível adicionar a pergunta: {exc}")

    if not indexed_papers:
        st.warning(
            "Nenhum PDF está indexado neste projeto. Indexe os textos integrais antes "
            "de cadastrar fontes relevantes."
        )

    grade_labels = {
        1: "1 — Marginalmente relevante",
        2: "2 — Relevante",
        3: "3 — Altamente relevante",
    }
    papers_by_id = {item["id"]: item for item in indexed_papers}

    for number, query in enumerate(golden["queries"], 1):
        label = "Deve recusar" if query["expected_refusal"] else "Deve responder"
        with st.expander(f"{number}. {query['question']} · {label}", expanded=False):
            if query.get("notes"):
                st.caption(query["notes"])
            if query["expected_refusal"]:
                st.info("Esta pergunta avalia a capacidade de recusar conteúdo fora do corpus.")
            else:
                if query["relevances"]:
                    st.dataframe(
                        pd.DataFrame(
                            [
                                {
                                    "Artigo": item["paper_title"],
                                    "Página": item["page_number"] or "Qualquer página",
                                    "Grau": grade_labels[item["relevance_grade"]],
                                    "Observação": item.get("notes") or "",
                                }
                                for item in query["relevances"]
                            ]
                        ),
                        use_container_width=True,
                        hide_index=True,
                    )
                    relevance_to_delete = st.selectbox(
                        "Julgamento a remover",
                        options=[item["id"] for item in query["relevances"]],
                        format_func=lambda relevance_id, items=query["relevances"]: next(
                            (
                                f"{item['paper_title']} · p. {item['page_number'] or 'qualquer'}"
                                for item in items
                                if item["id"] == relevance_id
                            ),
                            relevance_id,
                        ),
                        key=f"delete_relevance_select_{query['id']}",
                    )
                    if st.button(
                        "Remover julgamento selecionado",
                        key=f"delete_relevance_{query['id']}",
                    ):
                        try:
                            delete_golden_relevance(project_id, relevance_to_delete)
                            st.success("Julgamento removido e nova versão registrada.")
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Não foi possível remover o julgamento: {exc}")
                else:
                    st.warning("Adicione ao menos uma fonte relevante antes do benchmark.")

                if indexed_papers:
                    st.markdown("**Adicionar fonte relevante**")
                    selected_paper = st.selectbox(
                        "Artigo indexado",
                        options=list(papers_by_id),
                        format_func=lambda paper_id: papers_by_id[paper_id]["title"],
                        key=f"paper_{query['id']}",
                    )
                    page_options = [None] + papers_by_id[selected_paper]["pages"]
                    selected_page = st.selectbox(
                        "Página relevante",
                        options=page_options,
                        format_func=lambda page: "Qualquer página do artigo" if page is None else f"Página {page}",
                        key=f"page_{query['id']}",
                    )
                    selected_grade = st.selectbox(
                        "Grau de relevância",
                        options=[3, 2, 1],
                        format_func=lambda grade: grade_labels[grade],
                        key=f"grade_{query['id']}",
                    )
                    relevance_notes = st.text_input(
                        "Por que esta fonte é relevante? (opcional)",
                        key=f"notes_{query['id']}",
                    )
                    if st.button(
                        "Adicionar fonte ao gabarito",
                        type="primary",
                        key=f"add_relevance_{query['id']}",
                    ):
                        try:
                            add_golden_relevance(
                                project_id,
                                query["id"],
                                selected_paper,
                                selected_page,
                                selected_grade,
                                relevance_notes,
                            )
                            st.success("Fonte adicionada e nova versão registrada.")
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Não foi possível adicionar a fonte: {exc}")

            confirm_delete = st.checkbox(
                "Confirmo a remoção desta pergunta e de seus julgamentos",
                key=f"confirm_delete_query_{query['id']}",
            )
            if st.button(
                "Excluir pergunta",
                disabled=not confirm_delete,
                key=f"delete_query_{query['id']}",
            ):
                try:
                    delete_golden_query(project_id, query["id"])
                    st.success("Pergunta removida e nova versão registrada.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Não foi possível excluir a pergunta: {exc}")

with benchmark_tab:
    errors = validate_golden_set(golden)
    if errors:
        st.warning("O Golden Set ainda não está pronto:")
        for error in errors:
            st.write(f"- {error}")

    benchmark_job = render_job_status(
        project_id,
        JOB_RAG_BENCHMARK,
        key="rag_benchmark",
        title="Benchmark quantitativo",
    )
    info_col, button_col = st.columns([2, 1])
    with info_col:
        st.write(
            "Cada pergunta executa o RAG completo uma vez. A mesma recuperação é usada "
            "para avaliar RRF, reranking, recusa e conformidade das citações."
        )
    with button_col:
        execute = st.button(
            "▶️ Executar benchmark",
            type="primary",
            use_container_width=True,
            disabled=bool(errors) or job_is_active(benchmark_job),
        )
    if execute:
        try:
            start_job(project_id, JOB_RAG_BENCHMARK)
            st.rerun()
        except Exception as exc:
            st.error(f"Não foi possível iniciar o benchmark: {exc}")

    latest = get_latest_rag_benchmark(project_id)
    if not latest:
        st.info("Ainda não há benchmark quantitativo registrado neste projeto.")
    else:
        summary = (latest.get("metrics") or {}).get("summary") or {}
        params = latest.get("params") or {}
        calibration = summary.get("reranking_calibration") or {}
        calibrated_result = bool(calibration)
        final_pipeline_label = "Fusão configurada" if calibrated_result else "Reranking"
        st.caption(
            f"Última execução: {latest['created_at']} · Golden Set v"
            f"{params.get('golden_set_version')} · hash {str(params.get('golden_set_hash'))[:12]}"
        )
        if params.get("golden_set_version") != golden["version"]:
            st.warning(
                "O Golden Set mudou após esta execução. Rode novamente o benchmark "
                "para avaliar a versão atual."
            )
        if summary.get("failed_query_count"):
            st.error(
                f"{summary['failed_query_count']} pergunta(s) não foram concluídas após "
                "as tentativas automáticas. Os demais resultados permanecem válidos."
            )
        elif summary.get("retried_query_count"):
            st.info(
                f"{summary['retried_query_count']} pergunta(s) precisaram de novas "
                f"tentativas ({summary.get('total_retry_count', 0)} no total)."
            )
        kpi1, kpi2, kpi3, kpi4 = st.columns(4)
        kpi1.metric(f"Recall@5 · {final_pipeline_label}", f"{(summary.get('reranked') or {}).get('recall_at_5', 0):.3f}")
        kpi2.metric(f"nDCG@5 · {final_pipeline_label}", f"{(summary.get('reranked') or {}).get('ndcg_at_5', 0):.3f}")
        kpi3.metric(
            "Recusas corretas",
            "N/A" if summary.get("correct_refusal_rate") is None else f"{summary['correct_refusal_rate'] * 100:.1f}%",
        )
        kpi4.metric(
            "Citações conformes",
            "N/A" if summary.get("citation_compliance_rate") is None else f"{summary['citation_compliance_rate'] * 100:.1f}%",
        )
        quality1, quality2, quality3, quality4 = st.columns(4)
        quality1.metric(
            f"Precision@5 · {final_pipeline_label}",
            f"{(summary.get('reranked') or {}).get('precision_at_5', 0):.3f}",
        )
        quality2.metric(
            f"MRR · {final_pipeline_label}",
            f"{(summary.get('reranked') or {}).get('reciprocal_rank', 0):.3f}",
        )
        quality3.metric(
            "Validade das citações",
            "N/A" if summary.get("citation_validity") is None else f"{summary['citation_validity'] * 100:.1f}%",
        )
        quality4.metric(
            "Recusas indevidas",
            "N/A" if summary.get("false_refusal_rate") is None else f"{summary['false_refusal_rate'] * 100:.1f}%",
        )

        comparison_rows = []
        comparison = summary.get("comparison_cohort") or {}
        has_comparison_control = "comparison_cohort" in summary
        comparison_count = int(comparison.get("query_count") or 0)
        if has_comparison_control:
            comparison_rrf = comparison.get("rrf") or {}
            comparison_model = comparison.get("model_reranked") or {}
            comparison_fused = comparison.get("reranked") or {}
        else:
            comparison_rrf = summary.get("rrf") or {}
            comparison_model = summary.get("model_reranked") or {}
            comparison_fused = summary.get("reranked") or {}
        for key, label in (
            ("precision_at_5", "Precision@5"),
            ("recall_at_5", "Recall@5"),
            ("hit_rate_at_5", "Hit Rate@5"),
            ("reciprocal_rank", "MRR"),
            ("ndcg_at_5", "nDCG@5"),
        ):
            row = {
                "Métrica": label,
                "RRF": comparison_rrf.get(key, 0),
                final_pipeline_label: comparison_fused.get(key, 0),
            }
            if comparison_model:
                row["Reranking IA"] = comparison_model.get(key, 0)
            comparison_rows.append(row)
        comparison_df = pd.DataFrame(comparison_rows).set_index("Métrica")
        st.subheader("Comparação do ranking")
        if comparison_count:
            excluded = int(comparison.get("excluded_answerable_query_count") or 0)
            st.caption(
                f"Comparação justa: {comparison_count} pergunta(s) com os três pipelines "
                f"disponíveis. Excluídas por fallback/ausência do ranking da IA: {excluded}."
            )
        elif has_comparison_control:
            st.warning(
                "Nenhuma pergunta possui os três rankings nesta execução. "
                "A comparação foi omitida para evitar denominadores incompatíveis."
            )
        else:
            st.caption(
                "Execução anterior ao controle de amostra comparável; os denominadores "
                "podem diferir entre os pipelines."
            )
        if comparison_count or not has_comparison_control:
            st.bar_chart(comparison_df)
            st.dataframe(comparison_df, use_container_width=True)

        interpretation = summary.get("interpretation") or {}
        with st.expander("Interpretação automática das métricas", expanded=True):
            for statement in interpretation.get("statements") or []:
                st.write(f"- {statement}")
            for warning in interpretation.get("warnings") or []:
                st.warning(warning)

        st.subheader("Calibração do reranking")
        if not calibration or calibration.get("status") == "unavailable":
            st.info(
                "A calibração não está disponível porque não houve ranking da IA "
                "em perguntas respondíveis nesta execução. Execute novamente o benchmark "
                "se este resultado foi criado numa versão anterior."
            )
        else:
            calibration_col1, calibration_col2, calibration_col3 = st.columns(3)
            calibration_col1.metric(
                "Peso RRF configurado",
                f"{calibration.get('configured_rrf_weight', 0):.2f}",
            )
            calibration_col2.metric(
                "Peso sugerido pelo Golden Set",
                f"{calibration.get('recommended_rrf_weight', 0):.2f}",
            )
            calibration_col3.metric(
                "Amostra comparável",
                (
                    f"{calibration.get('answerable_query_count', 0)}/"
                    f"{calibration.get('total_answerable_query_count', calibration.get('answerable_query_count', 0))}"
                ),
            )
            if calibration.get("status") == "exploratory":
                st.warning(
                    "Esta recomendação é exploratória. Cadastre pelo menos "
                    f"{calibration.get('minimum_recommended_queries', 10)} perguntas "
                    "respondíveis e diversificadas antes de adotar o peso como estável."
                )
            if calibration.get("coverage_status") == "partial":
                st.warning(
                    "A sugestão de peso usa somente perguntas com ranking da IA. "
                    "Repita a execução até eliminar os fallbacks antes de alterar a configuração."
                )
            st.caption(
                "Peso 0 usa somente a ordem da IA; peso 1 preserva somente a ordem RRF. "
                "A sugestão prioriza Recall@5, depois nDCG@5 e MRR. Para aplicá-la, "
                "use o campo Peso RRF em Configuração de IA."
            )
            calibration_rows = [
                {
                    "Peso RRF": item.get("rrf_weight"),
                    "Recall@5": item.get("recall_at_5"),
                    "nDCG@5": item.get("ndcg_at_5"),
                    "MRR": item.get("reciprocal_rank"),
                }
                for item in calibration.get("candidate_weights") or []
            ]
            if calibration_rows:
                calibration_df = pd.DataFrame(calibration_rows).set_index("Peso RRF")
                st.line_chart(calibration_df)
                with st.expander("Ver métricas de todos os pesos testados"):
                    st.dataframe(calibration_df, use_container_width=True)

        result_rows = []
        for item in (latest.get("metrics") or {}).get("results") or []:
            result_rows.append(
                {
                    "Pergunta": item["question"],
                    "Esperava recusa": item["expected_refusal"],
                    "Recusou": item["response_refused"],
                    "Recall@5 RRF": (item.get("rrf_metrics") or {}).get("recall_at_5"),
                    "Recall@5 IA": (item.get("model_reranked_metrics") or {}).get("recall_at_5"),
                    "Recall@5 fusão": (item.get("reranked_metrics") or {}).get("recall_at_5"),
                    "MRR RRF": (item.get("rrf_metrics") or {}).get("reciprocal_rank"),
                    "MRR IA": (item.get("model_reranked_metrics") or {}).get("reciprocal_rank"),
                    "MRR fusão": (item.get("reranked_metrics") or {}).get("reciprocal_rank"),
                    "Status da execução": item.get("execution_status", "success"),
                    "Tentativas": item.get("execution_attempts", 1),
                    "Status do reranking": item.get("reranking_status"),
                    "Tentativas do reranking": item.get("reranking_attempts", 0),
                    "Recuperado no reranking": item.get(
                        "reranking_recovered_after_retry", False
                    ),
                    "Amostra comparável": item.get("comparison_eligible", False),
                    "Motivo do fallback": item.get("reranking_error"),
                    "Recusa reavaliada": (item.get("generation") or {}).get(
                        "refusal_reconsidered", False
                    ),
                    "Recusa recuperada": (item.get("generation") or {}).get(
                        "refusal_recovered", False
                    ),
                    "Erro da execução": item.get("execution_error"),
                }
            )
        st.subheader("Resultados por pergunta")
        st.dataframe(pd.DataFrame(result_rows), use_container_width=True, hide_index=True)

        export_json, export_csv = st.columns(2)
        export_json.download_button(
            "⬇️ Baixar benchmark JSON",
            benchmark_to_json(latest).encode("utf-8"),
            file_name="benchmark_rag.json",
            mime="application/json",
            use_container_width=True,
        )
        export_csv.download_button(
            "⬇️ Baixar benchmark CSV",
            benchmark_to_csv(latest).encode("utf-8"),
            file_name="benchmark_rag.csv",
            mime="text/csv",
            use_container_width=True,
        )

with guide_tab:
    st.markdown(
        """
### Leitura das métricas

- **Precision@k:** proporção dos primeiros `k` resultados que está correta.
- **Recall@k:** proporção das fontes relevantes do gabarito recuperada nos primeiros `k`.
- **Hit Rate@k:** indica se ao menos uma fonte relevante apareceu nos primeiros `k`.
- **MRR:** valoriza a posição do primeiro resultado relevante.
- **nDCG@k:** considera posição e grau de relevância de cada fonte.
- **Recusa correta:** pergunta fora do corpus que recebeu resposta de insuficiência de dados.
- **Conformidade de citação:** resposta que usou citações válidas sem correção automática.

As métricas variam de `0` a `1`; valores maiores representam melhor desempenho.
O Golden Set deve ser definido por julgamento humano antes da execução para evitar
que a própria IA produza e avalie o seu gabarito.
"""
    )
