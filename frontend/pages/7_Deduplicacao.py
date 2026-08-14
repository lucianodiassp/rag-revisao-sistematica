import os
import sys

import pandas as pd
import streamlit as st


sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from backend.app.deduplication import (  # noqa: E402
    HUMAN_KEEP_SEPARATE,
    HUMAN_MERGE,
    listar_decisoes_deduplicacao,
    listar_resumo_deduplicacao,
    revisar_decisao_deduplicacao,
)
from frontend.project_selector import selecionar_projeto_ativo  # noqa: E402


ROTULOS_REGRAS = {
    "doi_exact": "DOI idêntico",
    "title_exact": "Título idêntico",
    "title_similar": "Título semelhante",
    "no_candidate": "Sem candidato suficiente",
}
ROTULOS_ACOES = {
    "auto_create": "Novo artigo",
    "auto_merge": "Mesclado automaticamente",
    "pending_review": "Revisão humana",
}
ROTULOS_REVISAO = {
    "automatic": "Automática",
    "pending": "Pendente",
    "reviewed": "Revisada",
}
ROTULOS_DECISAO_HUMANA = {
    "merge": "Mesclar registros",
    "keep_separate": "Manter separados",
}


def _metadados(fontes):
    return (fontes or {}).get("metadata", {}) or {}


def _valor(valor, padrao="Não informado"):
    return valor if valor not in (None, "", [], {}) else padrao


def _fontes(fontes):
    valores = (fontes or {}).get("sources", []) or []
    return ", ".join(valores) if valores else "Não informada"


st.set_page_config(page_title="Deduplicação", page_icon="🔎", layout="wide")
projeto = selecionar_projeto_ativo()
project_id = str(projeto["id"])

st.title("🔎 Deduplicação explicável")
st.caption(f"Projeto ativo: **{projeto['title']}**")
st.markdown(
    "Cada registro recuperado recebe uma regra, uma pontuação e uma justificativa. "
    "DOIs idênticos são consolidados automaticamente; correspondências por título "
    "só entram na triagem depois da sua validação."
)

mensagem = st.session_state.pop("deduplication_review_result", None)
if mensagem and mensagem.get("project_id") == project_id:
    if mensagem["human_decision"] == HUMAN_MERGE:
        st.success("Registros mesclados. A decisão e a justificativa foram preservadas.")
    else:
        st.success("Registros mantidos separados. O novo artigo foi liberado para a Triagem.")

try:
    resumo = listar_resumo_deduplicacao(project_id)
    pendentes = listar_decisoes_deduplicacao(project_id, apenas_pendentes=True)
    historico = listar_decisoes_deduplicacao(project_id, apenas_pendentes=False)
except Exception as erro:
    st.error(f"Não foi possível carregar a deduplicação: {erro}")
    st.info("Se a aplicação foi atualizada agora, aplique a migração 007 no PostgreSQL.")
    st.stop()

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Registros avaliados", resumo["total"])
col2.metric("Novos artigos", resumo["new"])
col3.metric("Mesclados por DOI", resumo["auto_merged"])
col4.metric("Pendentes", resumo["pending"])
col5.metric("Revisados", resumo["reviewed"])

st.divider()
st.subheader("Revisão humana de candidatos")

if not pendentes:
    st.success("Não há candidatos de duplicação aguardando revisão neste projeto.")
else:
    ids = [str(item["id"]) for item in pendentes]
    por_id = {str(item["id"]): item for item in pendentes}
    decision_id = st.selectbox(
        "Selecione uma possível duplicata",
        ids,
        format_func=lambda item_id: (
            f"{por_id[item_id]['incoming_record_jsonb'].get('title', 'Sem título')} "
            f"↔ {por_id[item_id].get('candidate_title') or 'candidato indisponível'}"
        ),
    )
    decisao = por_id[decision_id]
    entrada = decisao["incoming_record_jsonb"] or {}
    fontes_entrada = entrada.get("fontes_dict") or {}
    metadados_entrada = _metadados(fontes_entrada)
    fontes_candidato = decisao.get("candidate_sources") or {}
    metadados_candidato = _metadados(fontes_candidato)
    evidencias = decisao.get("evidence_jsonb") or {}

    score = float(decisao["similarity_score"] or 0)
    titulo_score = float(evidencias.get("title_similarity") or 0)
    autores_score = float(evidencias.get("author_overlap") or 0)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Pontuação combinada", f"{score:.0%}")
    m2.metric("Similaridade do título", f"{titulo_score:.0%}")
    m3.metric("Sobreposição de autores", f"{autores_score:.0%}")
    m4.metric("Ano", "Igual" if evidencias.get("year_match") else "Diferente/ausente")

    if evidencias.get("doi_conflict"):
        st.warning("Os títulos coincidem, mas os dois registros apresentam DOIs diferentes.")
    st.info(
        f"**Regra:** {ROTULOS_REGRAS.get(decisao['rule_code'], decisao['rule_code'])}  \n"
        f"**Justificativa do sistema:** {decisao['explanation']}"
    )

    esquerda, direita = st.columns(2)
    with esquerda:
        st.markdown("#### Registro recebido")
        st.write(f"**Título:** {_valor(entrada.get('title'))}")
        st.write(f"**DOI:** {_valor(entrada.get('canonical_doi'))}")
        st.write(f"**Ano:** {_valor(metadados_entrada.get('publication_year'))}")
        st.write(f"**Autores:** {_valor('; '.join(metadados_entrada.get('authors', []) or []))}")
        st.write(f"**Fonte:** {_fontes(fontes_entrada)}")
        with st.expander("Ver resumo recebido"):
            st.write(_valor(entrada.get("abstract")))

    with direita:
        st.markdown("#### Artigo já existente")
        st.write(f"**Título:** {_valor(decisao.get('candidate_title'))}")
        st.write(f"**DOI:** {_valor(decisao.get('candidate_doi'))}")
        st.write(f"**Ano:** {_valor(metadados_candidato.get('publication_year'))}")
        st.write(f"**Autores:** {_valor('; '.join(metadados_candidato.get('authors', []) or []))}")
        st.write(f"**Fonte:** {_fontes(fontes_candidato)}")
        with st.expander("Ver resumo existente"):
            st.write(_valor(decisao.get("candidate_abstract")))

    with st.form(f"review_dedup_{decision_id}"):
        escolha = st.radio(
            "Decisão final",
            ["Mesclar: são o mesmo artigo", "Manter separados: são artigos diferentes"],
        )
        justificativa = st.text_area(
            "Justificativa obrigatória",
            placeholder="Ex.: mesmo título, autores, ano e objeto de estudo; trata-se do mesmo artigo.",
        )
        confirmar = st.form_submit_button(
            "Registrar decisão de deduplicação",
            type="primary",
            use_container_width=True,
        )

    if confirmar:
        human_decision = (
            HUMAN_MERGE if escolha.startswith("Mesclar") else HUMAN_KEEP_SEPARATE
        )
        try:
            resultado = revisar_decisao_deduplicacao(
                project_id,
                decision_id,
                human_decision,
                justificativa,
            )
        except ValueError as erro:
            st.warning(str(erro))
        except Exception as erro:
            st.error(f"Não foi possível registrar a decisão: {erro}")
        else:
            st.session_state["deduplication_review_result"] = resultado
            st.rerun()

st.divider()
st.subheader("Histórico e regras aplicadas")
st.caption(
    "O histórico inclui novos artigos, mesclagens automáticas por DOI e decisões humanas. "
    "Os registros anteriores à instalação desta melhoria não possuem evento retroativo."
)

if not historico:
    st.info("Ainda não há decisões registradas. Execute uma nova coleta ou importação BibTeX.")
else:
    linhas = []
    for item in historico:
        entrada = item.get("incoming_record_jsonb") or {}
        linhas.append(
            {
                "Data": item["created_at"],
                "Registro recebido": entrada.get("title"),
                "Candidato": item.get("candidate_title"),
                "Regra": ROTULOS_REGRAS.get(item["rule_code"], item["rule_code"]),
                "Pontuação": float(item["similarity_score"] or 0) * 100,
                "Ação do sistema": ROTULOS_ACOES.get(item["system_action"], item["system_action"]),
                "Revisão": ROTULOS_REVISAO.get(item["review_status"], item["review_status"]),
                "Decisão humana": ROTULOS_DECISAO_HUMANA.get(item.get("human_decision"), ""),
                "Justificativa humana": item.get("review_justification") or "",
            }
        )
    st.dataframe(
        pd.DataFrame(linhas),
        column_config={
            "Pontuação": st.column_config.ProgressColumn(
                "Pontuação", min_value=0.0, max_value=100.0, format="%.0f%%"
            ),
            "Data": st.column_config.DatetimeColumn("Data", format="DD/MM/YYYY HH:mm"),
        },
        hide_index=True,
        use_container_width=True,
    )
