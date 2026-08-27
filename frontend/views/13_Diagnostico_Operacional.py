import json
import os
import sys

import pandas as pd
import streamlit as st


sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from backend.app.operational_health import build_health_report  # noqa: E402
from backend.app.version import application_caption  # noqa: E402


STATUS_LABELS = {
    "ok": "Operacional",
    "warning": "Atenção",
    "error": "Indisponível",
}
STATUS_ICONS = {"ok": "✅", "warning": "⚠️", "error": "❌"}
CATEGORY_LABELS = {
    "configuration": "Configuração",
    "database": "Banco de dados",
    "storage": "Armazenamento",
    "ai_provider": "Provedor de IA",
    "bibliographic_source": "Fonte bibliográfica",
    "worker": "Processamento",
    "application": "Aplicação",
    "authentication": "Autenticação",
}
JOB_LABELS = {
    "bibliographic_search": "Coleta bibliográfica",
    "pdf_indexing": "Indexação de PDFs",
    "evidence_extraction": "Extração de evidências",
    "final_report": "Relatório final",
    "rag_benchmark": "Benchmark do RAG",
}


st.set_page_config(page_title="Diagnóstico Operacional", page_icon="🩺", layout="wide")
st.title("🩺 Diagnóstico Operacional")
st.caption(application_caption())
st.markdown(
    "Esta página verifica os componentes da instalação sem testar chamadas pagas, "
    "mostrar chaves de API ou expor conteúdo dos projetos."
)

if st.button("🔄 Atualizar diagnóstico", type="primary"):
    st.rerun()

report = build_health_report("full")
checks = report["checks"]
counts = {
    status: sum(1 for item in checks if item["status"] == status)
    for status in ("ok", "warning", "error")
}

overall_label = {
    "healthy": "Saudável",
    "degraded": "Requer atenção",
    "unhealthy": "Indisponibilidade detectada",
}.get(report["overall_status"], report["overall_status"])

c1, c2, c3, c4 = st.columns(4)
c1.metric("Estado geral", overall_label)
c2.metric("Operacionais", counts["ok"])
c3.metric("Atenção", counts["warning"])
c4.metric("Indisponíveis", counts["error"])

if report["overall_status"] == "healthy":
    st.success("Os componentes essenciais estão operacionais.")
elif report["overall_status"] == "degraded":
    st.warning("A instalação funciona, mas há configurações ou eventos que merecem atenção.")
else:
    st.error("Um componente essencial está indisponível. Consulte as ações abaixo.")

st.subheader("Componentes")
for item in checks:
    icon = STATUS_ICONS[item["status"]]
    label = STATUS_LABELS[item["status"]]
    with st.expander(
        f"{icon} {item['label']} · {label}",
        expanded=item["status"] != "ok",
    ):
        st.write(item["message"])
        details = item.get("details") or {}
        action = details.get("action")
        if action:
            st.info(f"Ação recomendada: {action}")

        if item["code"] == "storage" and details.get("areas"):
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "Área": area["label"],
                            "Gravável": area["writable"],
                            "Livre (MB)": area["free_mb"],
                            "Armazenado (MB)": area["stored_mb"],
                            "Reserva mínima (MB)": area["minimum_free_mb"],
                        }
                        for area in details["areas"]
                    ]
                ),
                hide_index=True,
                width="stretch",
            )
        elif item["code"] == "bibliographic_sources" and details.get("sources"):
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "Fonte": source["source_code"],
                            "Habilitada": source["enabled"],
                            "Autenticada": source["authenticated"],
                            "Origem da configuração": source["configuration_source"],
                        }
                        for source in details["sources"]
                    ]
                ),
                hide_index=True,
                width="stretch",
            )
        else:
            visible_details = {
                key: value
                for key, value in details.items()
                if key != "action" and value is not None
            }
            if visible_details:
                st.json(visible_details)

st.subheader("Falhas recentes de processamento")
failures = report.get("recent_job_failures") or []
if not failures:
    st.success("Nenhuma falha persistente foi encontrada no histórico recente da fila.")
else:
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Quando": item["finished_at"],
                    "Operação": JOB_LABELS.get(item["job_type"], item["job_type"]),
                    "Categoria": CATEGORY_LABELS.get(item["category"], item["category"]),
                    "Situação": item["message"],
                    "Ação recomendada": item["recommended_action"],
                    "Tentativas": item["attempts"],
                    "ID": item["job_id"],
                }
                for item in failures
            ]
        ),
        hide_index=True,
        width="stretch",
    )

st.download_button(
    "⬇️ Baixar diagnóstico seguro (JSON)",
    data=json.dumps(report, ensure_ascii=False, indent=2, default=str).encode("utf-8"),
    file_name="diagnostico_operacional.json",
    mime="application/json",
)
st.caption(
    "O arquivo contém estados técnicos, capacidade agregada e identificadores de "
    "processamento. Não inclui credenciais, e-mails, caminhos privados ou conteúdo científico."
)
