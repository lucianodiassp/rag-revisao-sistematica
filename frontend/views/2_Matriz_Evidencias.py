import os
import sys

import pandas as pd
import streamlit as st


sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from backend.agentes.agente_extrator import (  # noqa: E402
    carregar_extracoes_projeto,
    executar_pipeline_extracao,
    salvar_revisao_humana,
)
from backend.app.evidence_utils import FIELD_TYPES, achatar_extracao  # noqa: E402
from backend.processamento.leitor_pdf import (  # noqa: E402
    carregar_status_pdfs,
    resumir_status_fluxo,
)
from frontend.project_selector import selecionar_projeto_ativo  # noqa: E402


ROTULOS = {
    "objective": "Objetivo",
    "method": "Método",
    "dataset": "Dataset / amostra",
    "metrics": "Métricas",
    "main_results": "Principais resultados",
    "limitations": "Limitações",
}
STATUS = {
    "pending": "Pendente",
    "approved": "Aprovada",
    "corrected": "Corrigida e aprovada",
    "rejected": "Rejeitada",
}


def _fontes_por_campo(extracao):
    fontes = {}
    for campo in FIELD_TYPES:
        bloco = extracao.get(campo) or {}
        fontes[campo] = bloco.get("evidence", []) if isinstance(bloco, dict) else []
    return fontes


def _texto_lista(valor):
    return "\n".join(valor or []) if isinstance(valor, list) else str(valor or "")


def _montar_dataframe(extracoes):
    linhas = []
    for item in extracoes:
        dados = item.get("human_review_jsonb") or achatar_extracao(item["extraction_jsonb"])
        fontes = _fontes_por_campo(item["extraction_jsonb"])
        status_exibicao = (
            STATUS.get(item["human_review_status"], item["human_review_status"])
            if item.get("schema_version") == "traceable-v1"
            else "Legada — reindexar PDF"
        )
        linhas.append(
            {
                "Título do Artigo": item["title"],
                "Objetivo": dados.get("objective", "Não reportado"),
                "Método": dados.get("method", "Não reportado"),
                "Dataset": dados.get("dataset", "Não reportado"),
                "Métricas": "; ".join(dados.get("metrics", [])),
                "Principais Resultados": dados.get("main_results", "Não reportado"),
                "Limitações": "; ".join(dados.get("limitations", [])),
                "Fontes validadas": sum(len(itens) for itens in fontes.values()),
                "Status": status_exibicao,
            }
        )
    return pd.DataFrame(linhas)


st.set_page_config(page_title="Matriz de Evidências", page_icon="📊", layout="wide")
projeto = selecionar_projeto_ativo()
project_id = str(projeto["id"])

st.title("📊 Matriz de Evidências Rastreáveis")
st.caption(f"Projeto ativo: **{projeto['title']}**")

if (((projeto.get("criteria_jsonb") or {}).get("_demo") or {}).get("seed_id")):
    st.info(
        "As extrações desta demonstração foram pré-carregadas a partir de cartões PDF "
        "atribuídos, sem executar IA. Como não há embeddings artificiais, o contador de "
        "PDFs indexados permanece zerado até que você processe os cartões com o modelo "
        "configurado. Isso não impede a inspeção das fontes e da revisão humana."
    )

col_texto, col_acao = st.columns([3, 1])
with col_texto:
    if (((projeto.get("criteria_jsonb") or {}).get("_demo") or {}).get("seed_id")):
        st.markdown(
            "No fluxo real, a extração usa o **texto integral dos PDFs**. Neste exemplo, "
            "ela usa os cartões claramente identificados como demonstração. Em ambos os "
            "casos, cada informação permanece ligada a trecho e página antes da revisão."
        )
    else:
        st.markdown(
            "A extração usa o **texto integral dos PDFs**. Cada informação precisa estar "
            "ligada a um trecho literal e à página de origem antes de aparecer para revisão. "
            "Somente itens aprovados nesta tela serão usados no relatório final."
        )
with col_acao:
    if st.button("🔄 Extrair dos PDFs", type="primary", use_container_width=True):
        with st.spinner("Lendo os artigos e validando as citações literais..."):
            try:
                resumo = executar_pipeline_extracao(project_id)
                st.success(f"{resumo['extraidos']} artigo(s) extraído(s) com rastreabilidade.")
                if resumo["sem_pdf_rastreavel"]:
                    st.warning(
                        f"{resumo['sem_pdf_rastreavel']} artigo(s) aprovado(s) ainda não "
                        "possuem indexação rastreável. Confira a página Gestão de PDFs."
                    )
                if resumo["falhas"]:
                    st.warning(f"{resumo['falhas']} extração(ões) não puderam ser concluídas.")
            except Exception as erro:
                st.error(f"Não foi possível executar a extração: {erro}")

st.divider()
st.subheader("Andamento do fluxo de evidências")
status_artigos = carregar_status_pdfs(project_id)
funil = resumir_status_fluxo(status_artigos)

col1, col2, col3, col4 = st.columns(4)
col1.metric("Artigos incluídos", funil["incluidos"])
col2.metric("PDFs associados", funil["pdfs_associados"])
col3.metric("PDFs indexados", funil["indexados"])
col4.metric("Artigos extraídos", funil["extraidos"])

col5, col6, col7, col8 = st.columns(4)
col5.metric("Sem PDF", funil["sem_pdf"])
col6.metric("Aguardando indexação", funil["aguardando_indexacao"])
col7.metric("Aguardando extração", funil["aguardando_extracao"])
col8.metric("Revisados", funil["revisados"])
if (((projeto.get("criteria_jsonb") or {}).get("_demo") or {}).get("seed_id")):
    st.caption(
        "Os números representam etapas do mesmo fluxo e não categorias somáveis. "
        "Nesta demonstração, os cartões já possuem extrações revisadas, mas permanecem "
        "sem embeddings até a reindexação opcional."
    )
else:
    st.caption(
        "Os números representam etapas do mesmo fluxo e não categorias que precisam ser "
        "somadas. Um artigo extraído também está incluído, possui PDF e está indexado."
    )

st.divider()
extracoes = carregar_extracoes_projeto(project_id)

if not extracoes:
    st.info(
        "Ainda não há evidências. Aprove os artigos na Triagem, envie e indexe os PDFs "
        "na Gestão de PDFs e depois execute a extração nesta página."
    )
    st.stop()

contagens = {status: 0 for status in STATUS}
for item in extracoes:
    contagens[item["human_review_status"]] = contagens.get(item["human_review_status"], 0) + 1
st.subheader("Situação da revisão humana")
st.caption("Estes contadores consideram somente os artigos que já passaram pela extração.")
col1, col2, col3, col4 = st.columns(4)
col1.metric("Pendentes", contagens.get("pending", 0))
col2.metric("Aprovadas", contagens.get("approved", 0))
col3.metric("Corrigidas", contagens.get("corrected", 0))
col4.metric("Rejeitadas", contagens.get("rejected", 0))

st.dataframe(_montar_dataframe(extracoes), use_container_width=True, hide_index=True, height=320)

st.divider()
st.subheader("Revisão humana")
st.caption("Confira os valores e abra as fontes para comparar cada trecho com a página indicada.")

for item in extracoes:
    status_atual = item["human_review_status"]
    rastreavel = item.get("schema_version") == "traceable-v1"
    status_rotulo = STATUS.get(status_atual, status_atual) if rastreavel else "Legada — reindexar PDF"
    titulo_expansor = f"{status_rotulo} · {item['title']}"
    with st.expander(titulo_expansor, expanded=status_atual == "pending" and rastreavel):
        extracao_ia = item["extraction_jsonb"]
        valores_ia = achatar_extracao(extracao_ia)
        valores_atuais = item.get("human_review_jsonb") or valores_ia
        fontes = _fontes_por_campo(extracao_ia)

        if not rastreavel:
            st.warning(
                "Esta extração foi criada pelo fluxo antigo, sem PDF, página e trecho literal. "
                "Na página Gestão de PDFs, execute a indexação; depois volte e clique em "
                "Extrair dos PDFs. O registro será atualizado sem misturar projetos."
            )
            st.caption("O conteúdo legado permanece disponível abaixo apenas para consulta histórica.")
            st.json(valores_ia)
            continue

        for campo, rotulo in ROTULOS.items():
            bloco = extracao_ia.get(campo) or {}
            confianca = bloco.get("confidence", 0) if isinstance(bloco, dict) else 0
            with st.container(border=True):
                st.markdown(f"**{rotulo}** · confiança da IA: `{confianca:.0%}`")
                if fontes[campo]:
                    for fonte in fontes[campo]:
                        pagina = fonte.get("page") or "não identificada"
                        st.caption(f"Página {pagina} · chunk {fonte['chunk_id'][:8]}")
                        st.markdown(f"> {fonte['quote']}")
                else:
                    st.caption("Nenhuma fonte literal validada; o campo deve permanecer como não reportado.")

        with st.form(f"revisao_{item['id']}"):
            st.markdown("#### Valores finais da matriz")
            objetivo = st.text_area(
                "Objetivo", value=str(valores_atuais.get("objective", "")), key=f"obj_{item['id']}"
            )
            metodo = st.text_area(
                "Método", value=str(valores_atuais.get("method", "")), key=f"met_{item['id']}"
            )
            dataset = st.text_area(
                "Dataset / amostra", value=str(valores_atuais.get("dataset", "")), key=f"dat_{item['id']}"
            )
            metricas = st.text_area(
                "Métricas (uma por linha)",
                value=_texto_lista(valores_atuais.get("metrics", [])),
                key=f"metrics_{item['id']}",
            )
            resultados = st.text_area(
                "Principais resultados",
                value=str(valores_atuais.get("main_results", "")),
                key=f"res_{item['id']}",
            )
            limitacoes = st.text_area(
                "Limitações (uma por linha)",
                value=_texto_lista(valores_atuais.get("limitations", [])),
                key=f"lim_{item['id']}",
            )
            decisao_padrao = 1 if status_atual == "rejected" else 0
            decisao = st.radio(
                "Decisão",
                ["Aprovar para o relatório", "Rejeitar extração"],
                index=decisao_padrao,
                horizontal=True,
                key=f"dec_{item['id']}",
            )
            notas = st.text_area(
                "Notas da revisão (opcional)",
                value=item.get("review_notes") or "",
                key=f"notas_{item['id']}",
            )
            salvar = st.form_submit_button("💾 Registrar revisão", type="primary")

        if salvar:
            dados_revisados = {
                "objective": objetivo.strip() or "Não reportado",
                "method": metodo.strip() or "Não reportado",
                "dataset": dataset.strip() or "Não reportado",
                "metrics": [valor.strip() for valor in metricas.splitlines() if valor.strip()],
                "main_results": resultados.strip() or "Não reportado",
                "limitations": [valor.strip() for valor in limitacoes.splitlines() if valor.strip()],
            }
            if decisao == "Rejeitar extração":
                novo_status = "rejected"
            else:
                novo_status = "corrected" if dados_revisados != valores_ia else "approved"
            salvar_revisao_humana(project_id, item["id"], dados_revisados, novo_status, notas)
            st.success("Revisão registrada com data, status e versão humana.")
            st.rerun()

st.divider()
st.subheader("📥 Exportação de dados")
df_exportacao = _montar_dataframe(extracoes)
csv_exportacao = df_exportacao.to_csv(
    index=False,
    sep=";",
    lineterminator="\n",
).encode("utf-8-sig")
st.download_button(
    label="Download Matriz de Evidências (CSV)",
    data=csv_exportacao,
    file_name="matriz_evidencias_rastreaveis.csv",
    mime="text/csv; charset=utf-8",
    type="primary",
)
