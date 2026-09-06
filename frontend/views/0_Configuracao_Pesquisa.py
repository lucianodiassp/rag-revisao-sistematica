import os
import sys
import uuid

import pandas as pd
import streamlit as st


sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from backend.agentes.agente_formulador import estruturar_pergunta_pesquisa  # noqa: E402
from backend.app.bibliographic_config import get_bibliographic_settings  # noqa: E402
from backend.app.background_jobs import JOB_BIBLIOGRAPHIC_SEARCH  # noqa: E402
from backend.app.database import (  # noqa: E402
    criar_projeto,
    salvar_protocolo_projeto,
)
from backend.app.demo_project import ensure_demo_project  # noqa: E402
from backend.app.protocol_service import (  # noqa: E402
    compare_protocols,
    get_protocol_change_impact,
    get_protocol_history,
    normalize_protocol,
    protocol_fingerprint,
    validate_protocol,
)
from backend.app.reproducibility_import import (  # noqa: E402
    ReproducibilityImportError,
    import_reproducibility_package,
    validate_reproducibility_package,
)
from backend.app.user_identity import ensure_project_owner  # noqa: E402
from backend.coleta.importador_bibtex import (  # noqa: E402
    ErroBibTeX,
    analisar_bibtex,
    importar_bibtex,
)
from frontend.project_selector import (  # noqa: E402
    CHAVE_PROJETO_ATIVO,
    selecionar_projeto_ativo,
)
from frontend.background_jobs_ui import (  # noqa: E402
    job_is_active,
    render_job_status,
    start_job,
)


st.set_page_config(page_title="Configuração da Pesquisa", page_icon="⚙️", layout="wide")


with st.sidebar.expander("🧪 Projeto demonstrativo", expanded=False):
    st.caption(
        "Carrega um exemplo auditável com artigos reais, deduplicação, triagem, "
        "cartões PDF, matriz de evidências, qualidade metodológica, PRISMA e Golden Set. "
        "Não utiliza chaves de IA."
    )
    abrir_demo = st.button(
        "Criar / abrir demonstração",
        use_container_width=True,
        key="open_demo_project",
    )
    confirmar_restauracao = st.checkbox(
        "Confirmo que desejo descartar alterações feitas somente na demonstração",
        key="confirm_demo_reset",
    )
    restaurar_demo = st.button(
        "Restaurar dados originais",
        use_container_width=True,
        disabled=not confirmar_restauracao,
        key="reset_demo_project",
    )

    if abrir_demo or restaurar_demo:
        try:
            resultado_demo = ensure_demo_project(reset=bool(restaurar_demo))
        except Exception as erro:
            st.error(f"Não foi possível preparar a demonstração: {erro}")
        else:
            demo_id = str(resultado_demo["project_id"])
            ensure_project_owner(demo_id)
            st.session_state[CHAVE_PROJETO_ATIVO] = demo_id
            st.session_state["project_selector_widget"] = demo_id
            if resultado_demo.get("restored"):
                mensagem = "Demonstração restaurada com os dados originais."
            elif resultado_demo.get("outdated"):
                mensagem = (
                    "Uma versão anterior da demonstração foi aberta. Para incluir os "
                    "novos exemplos metodológicos, use Restaurar dados originais."
                )
            else:
                mensagem = "Projeto demonstrativo pronto para exploração."
            st.session_state["demo_project_message"] = mensagem
            st.rerun()


with st.sidebar.expander("➕ Novo projeto", expanded=False):
    with st.form("form_novo_projeto"):
        novo_titulo = st.text_input("Título do projeto")
        nova_pergunta = st.text_area("Pergunta inicial")
        criar = st.form_submit_button("Criar projeto", type="primary")
        if criar:
            if not novo_titulo.strip() or not nova_pergunta.strip():
                st.warning("Informe o título e a pergunta inicial.")
            else:
                novo_id = criar_projeto(novo_titulo, nova_pergunta)
                st.session_state[CHAVE_PROJETO_ATIVO] = novo_id
                st.session_state["project_selector_widget"] = novo_id
                st.rerun()


with st.sidebar.expander("📦 Importar projeto", expanded=False):
    st.caption(
        "Cria um novo projeto a partir de um pacote de reprodutibilidade. "
        "A instalação atual e os demais projetos não são substituídos."
    )
    arquivo_pacote = st.file_uploader(
        "Pacote de reprodutibilidade (.zip)",
        type=["zip"],
        key="reproducibility_package_uploader",
    )
    if arquivo_pacote is not None:
        conteudo_pacote = arquivo_pacote.getvalue()
        try:
            previa_pacote = validate_reproducibility_package(conteudo_pacote)
        except ReproducibilityImportError as erro:
            st.error(f"Pacote inválido: {erro}")
        except Exception as erro:
            st.error(f"Não foi possível validar o pacote: {erro}")
        else:
            manifesto = previa_pacote["manifest"]
            projeto_origem = manifesto["project"]
            contagens = manifesto.get("counts") or {}
            st.success("Integridade e formato validados.")
            st.caption(
                f"Origem: **{projeto_origem['title']}** · "
                f"{contagens.get('unique_papers', 0)} artigo(s) · "
                f"{contagens.get('screening_decisions', 0)} decisão(ões) de triagem · "
                f"SHA-256 `{previa_pacote['sha256'][:16]}…`"
            )
            titulo_importado = st.text_input(
                "Título do novo projeto",
                value=f"{projeto_origem['title']} — importado",
                key=f"import_title_{previa_pacote['sha256'][:12]}",
            )
            for aviso in previa_pacote["warnings"]:
                st.warning(aviso)
            confirmar_importacao = st.checkbox(
                "Entendo que PDFs e embeddings deverão ser adicionados novamente.",
                key=f"confirm_import_{previa_pacote['sha256'][:12]}",
            )
            if st.button(
                "Importar como novo projeto",
                type="primary",
                width="stretch",
                disabled=not confirmar_importacao,
                key=f"run_import_{previa_pacote['sha256'][:12]}",
            ):
                try:
                    with st.spinner("A reconstruir o projeto e suas trilhas de auditoria..."):
                        resultado_importacao = import_reproducibility_package(
                            conteudo_pacote,
                            title=titulo_importado,
                        )
                except ReproducibilityImportError as erro:
                    st.error(str(erro))
                except Exception as erro:
                    st.error(f"Não foi possível importar o projeto: {erro}")
                else:
                    novo_id = str(resultado_importacao["project_id"])
                    ensure_project_owner(novo_id)
                    st.session_state[CHAVE_PROJETO_ATIVO] = novo_id
                    st.session_state["project_selector_widget"] = novo_id
                    st.session_state["imported_project_message"] = (
                        "Projeto importado com integridade validada. Adicione os PDFs dos "
                        "artigos incluídos antes de reativar o RAG."
                    )
                    st.rerun()


projeto = selecionar_projeto_ativo(obrigatorio=False)

st.title("⚙️ Formulação da Pergunta de Pesquisa")

mensagem_demo = st.session_state.pop("demo_project_message", None)
if mensagem_demo:
    st.success(mensagem_demo)
mensagem_importacao = st.session_state.pop("imported_project_message", None)
if mensagem_importacao:
    st.success(mensagem_importacao)

if projeto is None:
    st.info("Crie o primeiro projeto no painel lateral para iniciar a revisão.")
    st.stop()

project_id = str(projeto["id"])
protocolo_atual = projeto.get("criteria_jsonb") or {}

if (protocolo_atual.get("_demo") or {}).get("seed_id"):
    st.info(
        "Esta demonstração usa metadados de publicações reais e cartões de evidência "
        "gerados localmente. Ela permite percorrer o fluxo sem consumir APIs; os cartões "
        "não substituem a leitura dos artigos integrais."
    )

st.caption(f"Projeto ativo: **{projeto['title']}** · protocolo v{projeto['protocol_version']}")
st.markdown(
    "Defina e confirme o escopo da revisão antes da coleta. A IA pode propor um "
    "rascunho PICO/PICOS, critérios e strings, mas somente a confirmação humana cria "
    "uma nova versão do protocolo."
)
st.divider()

draft_key = f"protocol_draft_{project_id}"
pergunta_para_ia = st.text_area(
    "Pergunta de pesquisa usada para gerar um rascunho",
    value=projeto.get("question") or "",
    height=100,
    help="A geração pela IA não altera a versão confirmada do protocolo.",
)

if st.button("🧠 Gerar rascunho com IA", type="primary"):
    if not pergunta_para_ia.strip():
        st.warning("Digite uma pergunta ou tema de pesquisa.")
    else:
        with st.spinner("A propor PICO/PICOS, critérios, conceitos e estratégias..."):
            resultado = estruturar_pergunta_pesquisa(pergunta_para_ia, project_id)

        if resultado:
            resultado["audit_questions"] = protocolo_atual.get("audit_questions", [])
            for key, value in protocolo_atual.items():
                if str(key).startswith("_"):
                    resultado[key] = value
            st.session_state[draft_key] = {
                "question": pergunta_para_ia.strip(),
                "protocol": normalize_protocol(resultado),
                "origin": "ai",
                "token": f"ai-{uuid.uuid4().hex}",
            }
            st.success("Rascunho gerado. Revise todos os campos antes de confirmar.")
            st.rerun()
        else:
            st.error("Não foi possível gerar o rascunho. Tente novamente.")

protocolo_normalizado = normalize_protocol(protocolo_atual)
protocol_is_confirmed = bool(
    projeto.get("status") == "search_ready" and protocolo_normalizado.get("search_string")
)
draft = st.session_state.get(draft_key) or {
    "question": projeto.get("question") or "",
    "protocol": protocolo_normalizado,
    "origin": "confirmed",
    "token": f"confirmed-{projeto['protocol_version']}",
}
draft_protocol = normalize_protocol(draft["protocol"])
impacto = get_protocol_change_impact(project_id)

st.subheader("1. Editor do protocolo")
if draft["origin"] == "ai":
    if protocol_is_confirmed:
        st.info(
            "Este conteúdo é somente um **rascunho proposto pela IA**. A versão "
            f"confirmada continua sendo a v{projeto['protocol_version']}."
        )
    else:
        st.info(
            "Este conteúdo é somente um **rascunho proposto pela IA**. O projeto "
            "ainda não possui uma versão metodológica confirmada."
        )
else:
    if protocol_is_confirmed:
        st.success(f"Editando uma cópia da versão confirmada v{projeto['protocol_version']}.")
    else:
        st.info("Prepare e confirme a primeira versão metodológica deste projeto.")

if impacto["requires_attention"]:
    st.warning(
        "Este projeto já possui "
        f"{impacto['searches']} busca(s), {impacto['papers']} artigo(s) e "
        f"{impacto['screening_decisions']} parecer(es) de triagem. Uma nova versão "
        "não altera registros anteriores; avalie se será necessário repetir buscas ou "
        "reavaliar artigos."
    )

token = draft["token"]
with st.form(f"protocol_editor_{project_id}_{token}"):
    pergunta_editada = st.text_area(
        "Pergunta de pesquisa confirmada",
        value=draft["question"],
        height=100,
    )

    st.markdown("#### Estrutura PICO/PICOS")
    pico = draft_protocol["pico"]
    p1, p2 = st.columns(2)
    population = p1.text_area("População ou problema (P) *", value=pico["population"])
    intervention = p2.text_area(
        "Intervenção, exposição ou método (I) *", value=pico["intervention"]
    )
    p3, p4 = st.columns(2)
    comparison = p3.text_area("Comparação (C)", value=pico["comparison"])
    outcome = p4.text_area("Desfechos ou métricas (O) *", value=pico["outcome"])
    study_design = st.text_area(
        "Desenhos de estudo esperados (S)", value=pico["study_design"]
    )

    st.markdown("#### Elegibilidade estruturada")
    eligibility = draft_protocol["eligibility"]
    e1, e2, e3 = st.columns([1, 1, 2])
    year_from = e1.text_input(
        "Ano inicial", value=str(eligibility["year_from"] or "")
    )
    year_to = e2.text_input("Ano final", value=str(eligibility["year_to"] or ""))
    languages = e3.text_input(
        "Idiomas (separados por vírgula)",
        value=", ".join(eligibility["languages"]),
    )
    e4, e5 = st.columns(2)
    publication_types = e4.text_area(
        "Tipos de publicação aceitos — um por linha",
        value="\n".join(eligibility["publication_types"]),
    )
    study_designs = e5.text_area(
        "Desenhos de estudo aceitos — um por linha",
        value="\n".join(eligibility["study_designs"]),
    )

    st.markdown("#### Critérios operacionais")
    c1, c2 = st.columns(2)
    inclusion_text = c1.text_area(
        "Critérios de inclusão — um por linha *",
        value="\n".join(draft_protocol["inclusion_criteria"]),
        height=180,
    )
    exclusion_text = c2.text_area(
        "Critérios de exclusão — um por linha *",
        value="\n".join(draft_protocol["exclusion_criteria"]),
        height=180,
    )

    st.markdown("#### Matriz de conceitos e sinônimos")
    concept_rows = [
        {
            "Conceito": item["concept"],
            "Termos e sinônimos (separados por ;)": "; ".join(item["terms"]),
        }
        for item in draft_protocol["search_concepts"]
    ]
    concept_table = st.data_editor(
        pd.DataFrame(concept_rows, columns=["Conceito", "Termos e sinônimos (separados por ;)"]),
        num_rows="dynamic",
        hide_index=True,
        use_container_width=True,
    )

    st.markdown("#### Estratégias de busca")
    general_query = st.text_area(
        "String booleana geral *",
        value=draft_protocol["search_string"],
        height=130,
    )
    st.caption(
        "As strings específicas são opcionais. Quando vazias, a fonte utiliza a string geral."
    )
    q1, q2, q3 = st.columns(3)
    openalex_query = q1.text_area(
        "OpenAlex", value=draft_protocol["source_search_strings"]["openalex"], height=120
    )
    pubmed_query = q2.text_area(
        "PubMed", value=draft_protocol["source_search_strings"]["pubmed"], height=120
    )
    semantic_query = q3.text_area(
        "Semantic Scholar",
        value=draft_protocol["source_search_strings"]["semantic_scholar"],
        height=120,
    )

    motivo_versao = st.text_input(
        "Motivo da nova versão *",
        placeholder="Ex.: refinamento dos sinônimos após busca piloto",
    )
    confirmar_protocolo = st.checkbox(
        "Revisei os campos e confirmo que esta versão representa as decisões metodológicas humanas."
    )
    salvar_versao = st.form_submit_button(
        "💾 Confirmar e criar nova versão", type="primary", use_container_width=True
    )

if salvar_versao:
    concepts = []
    for row in concept_table.to_dict("records"):
        concepts.append(
            {
                "concept": row.get("Conceito"),
                "terms": str(row.get("Termos e sinônimos (separados por ;)") or "").split(";"),
            }
        )
    protocol_candidate = {
        **{key: value for key, value in protocolo_atual.items() if str(key).startswith("_")},
        "pico": {
            "population": population,
            "intervention": intervention,
            "comparison": comparison,
            "outcome": outcome,
            "study_design": study_design,
        },
        "eligibility": {
            "year_from": year_from,
            "year_to": year_to,
            "languages": languages.replace(",", "\n").splitlines(),
            "publication_types": publication_types.splitlines(),
            "study_designs": study_designs.splitlines(),
        },
        "inclusion_criteria": inclusion_text.splitlines(),
        "exclusion_criteria": exclusion_text.splitlines(),
        "search_concepts": concepts,
        "search_string": general_query,
        "source_search_strings": {
            "openalex": openalex_query,
            "pubmed": pubmed_query,
            "semantic_scholar": semantic_query,
        },
        "audit_questions": protocolo_atual.get("audit_questions", []),
    }
    try:
        question, validated_protocol, reason = validate_protocol(
            pergunta_editada, protocol_candidate, motivo_versao
        )
        unchanged = (
            question == (projeto.get("question") or "").strip()
            and protocol_fingerprint(validated_protocol)
            == protocol_fingerprint(protocolo_atual)
        )
        if unchanged:
            raise ValueError("O rascunho não possui alterações em relação à versão confirmada.")
        if not confirmar_protocolo:
            raise ValueError("Confirme a revisão humana antes de criar a nova versão.")
        versao = salvar_protocolo_projeto(
            project_id, question, validated_protocol, motivo=reason
        )
    except ValueError as erro:
        st.warning(str(erro))
    except Exception as erro:
        st.error(f"Não foi possível salvar o protocolo: {erro}")
    else:
        st.session_state.pop(draft_key, None)
        st.success(f"Protocolo confirmado e salvo como versão {versao}.")
        st.rerun()

if draft["origin"] == "ai" and st.button("Descartar rascunho da IA"):
    st.session_state.pop(draft_key, None)
    st.rerun()

with st.expander("📚 Histórico imutável do protocolo", expanded=False):
    history = get_protocol_history(project_id)
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Versão": item["version"],
                    "Data": item["created_at"],
                    "Motivo": item["change_reason"],
                    "Inclusão": len(item["criteria_jsonb"]["inclusion_criteria"]),
                    "Exclusão": len(item["criteria_jsonb"]["exclusion_criteria"]),
                    "Hash": protocol_fingerprint(item["criteria_jsonb"])[:12],
                }
                for item in history
            ]
        ),
        hide_index=True,
        use_container_width=True,
    )
    if history:
        version_by_number = {item["version"]: item for item in history}
        version_numbers = list(version_by_number)
        selector1, selector2 = st.columns(2)
        base_version = selector1.selectbox(
            "Versão de referência",
            options=version_numbers,
            index=min(1, len(version_numbers) - 1),
            key=f"protocol_base_{project_id}",
        )
        target_version = selector2.selectbox(
            "Comparar com",
            options=version_numbers,
            index=0,
            key=f"protocol_target_{project_id}",
        )
        base_item = version_by_number[base_version]
        target_item = version_by_number[target_version]
        changes = compare_protocols(
            base_item["question"],
            base_item["criteria_jsonb"],
            target_item["question"],
            target_item["criteria_jsonb"],
        )
        if changes:
            st.info("Seções alteradas: **" + " · ".join(changes) + "**")
        else:
            st.success("As versões selecionadas possuem o mesmo conteúdo metodológico.")

        for column, item in zip(st.columns(2), (base_item, target_item)):
            old_protocol = item["criteria_jsonb"]
            with column:
                st.markdown(f"#### Protocolo v{item['version']}")
                st.caption(
                    f"{item['change_reason'] or 'Sem motivo registrado'} · "
                    f"hash `{protocol_fingerprint(old_protocol)[:12]}`"
                )
                st.markdown("**Pergunta**")
                st.write(item["question"])
                st.markdown("**PICO/PICOS**")
                for field, label in (
                    ("population", "P"),
                    ("intervention", "I"),
                    ("comparison", "C"),
                    ("outcome", "O"),
                    ("study_design", "S"),
                ):
                    st.write(f"**{label}:** {old_protocol['pico'].get(field) or '—'}")
                st.markdown("**Inclusão**")
                st.write(
                    "\n".join(
                        f"- {criterion}"
                        for criterion in old_protocol["inclusion_criteria"]
                    )
                    or "—"
                )
                st.markdown("**Exclusão**")
                st.write(
                    "\n".join(
                        f"- {criterion}"
                        for criterion in old_protocol["exclusion_criteria"]
                    )
                    or "—"
                )
                st.markdown("**String geral**")
                st.code(old_protocol["search_string"] or "—", language=None)

st.divider()
st.subheader("2. Coleta com o protocolo confirmado")

termo_busca = protocolo_normalizado.get("search_string", "")
if not termo_busca:
    st.info("Confirme uma versão com estratégia de busca antes de iniciar a coleta.")
    st.stop()

st.code(termo_busca, language=None)
st.caption(
    f"As próximas buscas serão vinculadas ao protocolo v{projeto['protocol_version']} · "
    f"hash `{protocol_fingerprint(protocolo_normalizado)[:12]}…`"
)
with st.expander("Consultar strings confirmadas por fonte", expanded=False):
    for source_code, source_label in (
        ("openalex", "OpenAlex"),
        ("pubmed", "PubMed"),
        ("semantic_scholar", "Semantic Scholar"),
    ):
        source_query = protocolo_normalizado["source_search_strings"].get(source_code)
        st.markdown(f"**{source_label}**")
        st.code(source_query or termo_busca, language=None)
        if not source_query:
            st.caption("Usará a string geral.")
aba_apis, aba_bibtex = st.tabs(["Consultar APIs", "Importar BibTeX"])

with aba_apis:
    qtd_artigos = st.slider(
        "Máximo de artigos por fonte",
        min_value=5,
        max_value=50,
        value=10,
        step=5,
    )

    fontes_ativas = [
        config.label
        for config in get_bibliographic_settings().values()
        if config.enabled
    ]
    if fontes_ativas:
        st.caption(f"Fontes habilitadas: **{', '.join(fontes_ativas)}**")
    else:
        st.warning(
            "Nenhuma fonte bibliográfica está habilitada. "
            "Configure as fontes antes de iniciar a coleta por API."
        )

    coleta_job = render_job_status(
        project_id,
        JOB_BIBLIOGRAPHIC_SEARCH,
        key="bibliographic_search",
        title="Coleta bibliográfica",
    )
    if st.button(
        "🚀 Iniciar coleta nas fontes habilitadas",
        type="primary",
        use_container_width=True,
        disabled=not fontes_ativas or job_is_active(coleta_job),
    ):
        try:
            start_job(
                project_id,
                JOB_BIBLIOGRAPHIC_SEARCH,
                {
                    "query": termo_busca,
                    "max_per_source": qtd_artigos,
                    "source_queries": protocolo_normalizado.get("source_search_strings") or {},
                },
            )
            st.rerun()
        except Exception as erro:
            st.error(f"Não foi possível iniciar a coleta: {erro}")

    if coleta_job and coleta_job.get("status") == "succeeded":
        resultado = coleta_job.get("result_jsonb") or {}
        encontrados = int(resultado.get("found") or 0)
        if encontrados == 0:
            st.warning("Nenhum artigo foi encontrado. Ajuste o rascunho do protocolo.")
        else:
            st.info(
                f"Última coleta: {resultado.get('saved', 0)} novo(s), "
                f"{resultado.get('merged', 0)} mesclado(s), "
                f"{resultado.get('pending_review', 0)} aguardando revisão, em "
                f"{encontrados} registro(s) recuperado(s)."
            )

with aba_bibtex:
    st.markdown(
        "Importe uma exportação `.bib` do Web of Science ou de outro gerenciador. "
        "Os registros entram na mesma triagem dos artigos coletados por API e são "
        "deduplicados por DOI ou título, sem aplicação automática dos critérios PICO."
    )
    arquivo_bibtex = st.file_uploader(
        "Arquivo BibTeX",
        type=["bib"],
        key=f"bibtex_uploader_{project_id}",
    )

    if arquivo_bibtex is not None:
        conteudo_bibtex = arquivo_bibtex.getvalue()
        try:
            analise = analisar_bibtex(conteudo_bibtex, arquivo_bibtex.name)
        except ErroBibTeX as erro:
            st.error(f"Arquivo BibTeX inválido: {erro}")
        except Exception as erro:
            st.error(f"Não foi possível analisar o arquivo: {erro}")
        else:
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Entradas", analise["total_entries"])
            col2.metric("Válidas", analise["valid_entries"])
            col3.metric("Sem abstract", analise["without_abstract"])
            col4.metric("Sem DOI", analise["without_doi"])
            st.caption(
                f"Codificação: {analise['encoding']} · "
                f"SHA-256: `{analise['file_sha256'][:16]}…`"
            )

            if analise["invalid_entries"]:
                st.warning(
                    f"{analise['invalid_entries']} entrada(s) sem título serão ignoradas."
                )
            if analise["duplicates_in_file"]:
                st.info(
                    f"O arquivo contém {analise['duplicates_in_file']} possível(is) "
                    "duplicata(s), que serão consolidadas pela proveniência."
                )

            st.write("**Prévia dos primeiros registros válidos**")
            st.dataframe(analise["preview"], use_container_width=True, hide_index=True)

            if st.button(
                "📥 Importar registros para o projeto ativo",
                type="primary",
                use_container_width=True,
                disabled=analise["valid_entries"] == 0,
            ):
                with st.spinner("A importar, deduplicar e registrar a proveniência..."):
                    try:
                        relatorio = importar_bibtex(
                            project_id,
                            conteudo_bibtex,
                            arquivo_bibtex.name,
                        )
                    except Exception as erro:
                        st.error(f"Erro durante a importação: {erro}")
                    else:
                        if relatorio["persistence_errors"]:
                            st.warning(
                                "Importação concluída com "
                                f"{relatorio['persistence_errors']} erro(s) de persistência."
                            )
                        else:
                            st.success("Importação BibTeX concluída e registrada.")
                        resultado1, resultado2, resultado3, resultado4 = st.columns(4)
                        resultado1.metric("Novos artigos", relatorio["new_papers"])
                        resultado2.metric("Mesclados por DOI", relatorio["merged_records"])
                        resultado3.metric(
                            "Revisão de duplicatas",
                            relatorio.get("pending_deduplication_review", 0),
                        )
                        resultado4.metric("Entradas inválidas", relatorio["invalid_entries"])
                        st.caption(
                            "Novos artigos já estão na Triagem; candidatos por título precisam "
                            "ser decididos na página Deduplicação. "
                            f"Execução: `{relatorio['search_query_id']}`"
                        )
