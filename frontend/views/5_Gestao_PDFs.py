import os
import sys
import pandas as pd
import streamlit as st

# Ajuste de Caminho para podermos importar funções do backend
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from backend.processamento.leitor_pdf import (
    carregar_status_pdfs,
    resumir_status_fluxo,
)
from backend.app.background_jobs import JOB_PDF_INDEXING
from backend.processamento.ocr_pdf import get_pdf_ocr_config
from backend.app.screening_reassessment import (
    ACTION_EXCLUDE,
    ACTION_RETURN_TO_SCREENING,
    reassess_included_paper,
)
from backend.app.storage_service import (
    StorageCapacityError,
    inspect_storage,
    pdf_directory,
    save_upload_atomic,
    storage_limits,
)
from frontend.project_selector import selecionar_projeto_ativo
from frontend.background_jobs_ui import job_is_active, render_job_status, start_job

# ==========================================
# CONFIGURAÇÃO DA PÁGINA
# ==========================================
st.set_page_config(page_title="Gestão de PDFs", page_icon="📂", layout="wide")

DIRETORIO_PDFS = str(pdf_directory())

# Garante que a pasta física existe no ambiente
if not os.path.exists(DIRETORIO_PDFS):
    os.makedirs(DIRETORIO_PDFS)


ROTULOS_INDEXACAO = {
    "awaiting_pdf": "Aguardando PDF",
    "awaiting_index": "PDF associado — aguardando indexação",
    "needs_reindex": "Reindexação necessária",
    "indexed": "Indexado",
}

ROTULOS_RESULTADO = {
    "indexed": "Indexado agora",
    "already_indexed": "Já estava indexado",
    "failed": "Falhou",
}

MOTIVOS_REAVALIACAO = {
    "Acesso restrito ou pago": "restricted_access",
    "PDF não localizado": "pdf_not_found",
    "Artigo/PDF não corresponde aos metadados": "metadata_mismatch",
    "Outro motivo": "other",
}

# ==========================================
# INTERFACE VISUAL
# ==========================================
st.title("📂 Gestão de arquivos e Vetorização")
projeto = selecionar_projeto_ativo()
project_id = str(projeto["id"])
st.caption(f"Projeto ativo: **{projeto['title']}**")
if (((projeto.get("criteria_jsonb") or {}).get("_demo") or {}).get("seed_id")):
    st.info(
        "Os arquivos deste projeto são cartões PDF demonstrativos, não os artigos "
        "integrais. Eles são carregados sem embeddings para não consumir sua API; "
        "por isso aparecem como aguardando reindexação até o processamento opcional."
    )
st.markdown("""
Faça o upload dos documentos na íntegra para os artigos aprovados e acione a indexação 
vetorial para alimentar o cérebro do motor RAG.
""")
limites_armazenamento = storage_limits()
status_armazenamento = inspect_storage("PDFs", DIRETORIO_PDFS)
st.caption(
    f"Limite por PDF: **{limites_armazenamento.pdf_upload_mb} MB** · "
    f"Espaço livre no armazenamento persistente: "
    f"**{status_armazenamento.free_bytes / (1024 ** 3):.1f} GB**."
)
if not status_armazenamento.healthy:
    st.error(
        "O armazenamento de PDFs não possui escrita ou reserva livre suficiente. "
        "Novos uploads devem aguardar a liberação de espaço."
    )
st.divider()

ultima_reavaliacao = st.session_state.pop("ultima_reavaliacao_pdf", None)
if ultima_reavaliacao and ultima_reavaliacao.get("project_id") == project_id:
    if ultima_reavaliacao["action"] == ACTION_RETURN_TO_SCREENING:
        st.success(
            "Artigo devolvido à Triagem. A decisão anterior e a justificativa "
            "foram preservadas no histórico."
        )
    else:
        st.success(
            "Artigo excluído da revisão com justificativa registrada no histórico."
        )

# Carrega o estado completo: arquivo físico, chunks, embeddings e extração.
status_artigos = carregar_status_pdfs(project_id)
funil = resumir_status_fluxo(status_artigos)
df_aprovados = pd.DataFrame(status_artigos)

if df_aprovados.empty:
    st.info("Nenhum artigo aprovado encontrado. Realize a triagem de artigos primeiro.")
else:
    df_aprovados["Situação"] = df_aprovados["situacao"].map(ROTULOS_INDEXACAO)
    df_pendentes = df_aprovados[~df_aprovados["pdf_associado"]]
    df_concluidos = df_aprovados[df_aprovados["pdf_associado"]]

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Artigos incluídos", funil["incluidos"])
    col2.metric("PDFs associados", funil["pdfs_associados"])
    col3.metric("Indexados", funil["indexados"])
    col4.metric("Aguardando indexação", funil["aguardando_indexacao"])
    st.caption(
        "PDF associado significa que o arquivo foi armazenado. Indexado significa que "
        "todos os trechos possuem página de origem e embedding compatível com o modelo ativo."
    )
    st.divider()

    # Distribuição da tela em duas colunas (Upload à esquerda, Lista à direita)
    col_upload, col_lista = st.columns([1, 1])

    with col_upload:
        st.subheader(f"⏳ Pendentes de Upload ({len(df_pendentes)})")
        
        if not df_pendentes.empty:
            uuid_alvo = st.selectbox(
                "1. Selecione o artigo aprovado:",
                options=df_pendentes['paper_id'].tolist(),
                format_func=lambda paper_id: df_pendentes.loc[
                    df_pendentes['paper_id'] == paper_id, 'title'
                ].iloc[0],
                help="Apenas artigos marcados como 'Incluir' que ainda não possuem PDF aparecem aqui."
            )
            st.caption(f"**UUID de Vínculo:** `{uuid_alvo}`")
            
            arquivo_upload = st.file_uploader("2. Envie o ficheiro PDF do artigo", type=['pdf'])
            
            if arquivo_upload is not None:
                if st.button("💾 Salvar e Relacionar PDF", type="primary", width="stretch"):
                    caminho_salvo = os.path.join(DIRETORIO_PDFS, f"{uuid_alvo}.pdf")
                    try:
                        save_upload_atomic(
                            arquivo_upload.getbuffer(),
                            caminho_salvo,
                            kind="pdf",
                        )
                    except StorageCapacityError as erro:
                        st.error(f"Não foi possível armazenar o PDF: {erro}")
                    except OSError as erro:
                        st.error(f"Falha ao gravar o PDF no armazenamento persistente: {erro}")
                    else:
                        st.success("Ficheiro guardado e vinculado com sucesso!")
                        st.rerun()

            with st.expander("Não consegui obter este PDF", expanded=False):
                st.write(
                    "Se o texto integral não estiver acessível, você pode devolver o "
                    "artigo para uma nova decisão ou excluí-lo da revisão. A justificativa "
                    "é obrigatória e a decisão anterior não será apagada do histórico."
                )
                with st.form(f"reavaliar_pdf_{uuid_alvo}", clear_on_submit=True):
                    acao_rotulo = st.radio(
                        "O que deseja fazer?",
                        ["Voltar para a Triagem", "Excluir da revisão"],
                        horizontal=True,
                    )
                    motivo_rotulo = st.selectbox(
                        "Categoria do motivo",
                        list(MOTIVOS_REAVALIACAO),
                    )
                    justificativa_reavaliacao = st.text_area(
                        "Justificativa obrigatória",
                        placeholder=(
                            "Ex.: o artigo está disponível apenas mediante pagamento e "
                            "não foi possível obter legalmente o texto integral."
                        ),
                        height=100,
                    )
                    confirmar_reavaliacao = st.form_submit_button(
                        "Registrar reavaliação",
                        width="stretch",
                    )

                if confirmar_reavaliacao:
                    acao = (
                        ACTION_RETURN_TO_SCREENING
                        if acao_rotulo == "Voltar para a Triagem"
                        else ACTION_EXCLUDE
                    )
                    try:
                        resultado = reassess_included_paper(
                            project_id=project_id,
                            paper_id=uuid_alvo,
                            action=acao,
                            reason_code=MOTIVOS_REAVALIACAO[motivo_rotulo],
                            reason=justificativa_reavaliacao,
                        )
                    except ValueError as erro:
                        st.warning(str(erro))
                    except Exception as erro:
                        st.error(f"Não foi possível reavaliar o artigo: {erro}")
                    else:
                        st.session_state["ultima_reavaliacao_pdf"] = resultado
                        st.rerun()
        else:
            st.success("🎉 Todos os artigos aprovados já possuem o respetivo PDF associado!")

    with col_lista:
        st.subheader(f"✅ PDFs Armazenados ({len(df_concluidos)})")
        if not df_concluidos.empty:
            st.dataframe(
                df_concluidos[
                    [
                        'title',
                        'paper_id',
                        'Situação',
                        'chunks_rastreaveis',
                        'paginas_ocr',
                    ]
                ],
                column_config={
                    "title": "Artigo",
                    "paper_id": "UUID",
                    "chunks_rastreaveis": "Trechos rastreáveis",
                    "paginas_ocr": "Páginas com OCR",
                },
                hide_index=True, 
                width="stretch"
            )
        else:
            st.info("Ainda não há arquivos PDF armazenados no sistema.")

    st.divider()

    # --- NOVA SECÇÃO: ENGENHARIA VETORIAL AUTOMÁTICA ---
    st.header("🧠 Central de Indexação Vetorial Avançada")
    ocr_config = get_pdf_ocr_config()
    st.markdown(
        "Clique no botão abaixo para extrair o texto, dividi-lo em blocos com "
        "página de origem e gerar os *embeddings*. Índices antigos sem página "
        "serão atualizados; PDFs já rastreáveis serão ignorados para evitar "
        "custo duplicado."
    )
    if ocr_config.enabled:
        st.info(
            "OCR local ativo para páginas digitalizadas: "
            f"idiomas **{ocr_config.languages}**, **{ocr_config.dpi} DPI**, "
            "acionado quando a camada nativa possui menos de "
            f"**{ocr_config.min_native_characters} caracteres alfanuméricos**. "
            "O método de extração fica registrado em cada trecho. Textos reconhecidos "
            "por OCR devem ser conferidos visualmente no PDF durante a revisão humana."
        )
    else:
        st.warning(
            "OCR local desativado. PDFs formados somente por imagens poderão não "
            "produzir texto para indexação."
        )

    index_job = render_job_status(
        project_id,
        JOB_PDF_INDEXING,
        key="pdf_indexing",
        title="Indexação vetorial",
    )

    # Botão de ignição do processo separado
    if st.button(
        "⚡ Executar Processamento e Vetorização de PDFs",
        type="secondary",
        width="stretch",
        disabled=job_is_active(index_job),
    ):
        try:
            start_job(project_id, JOB_PDF_INDEXING)
            st.rerun()
        except Exception as e:
            st.error(f"⚠️ Não foi possível iniciar a vetorização: {e}")

    if index_job and index_job.get("status") == "succeeded":
        resumo = index_job.get("result_jsonb") or {}
        if resumo["falhas"]:
            st.warning(
                "Processamento concluído parcialmente: "
                f"{resumo['processados']} indexado(s), "
                f"{resumo['ignorados']} já indexado(s) e "
                f"{resumo['falhas']} falha(s)."
            )
        elif resumo["processados"]:
            st.success(
                f"Processamento concluído: {resumo['processados']} PDF(s) indexado(s) "
                f"e {resumo['ignorados']} já indexado(s)."
            )
        else:
            st.info("Nenhum novo PDF precisou ser indexado.")

        if resumo.get("paginas_ocr"):
            st.caption(
                f"OCR aplicado com sucesso em {resumo['paginas_ocr']} página(s)."
            )
        if resumo.get("falhas_ocr"):
            st.warning(
                f"O OCR não produziu texto melhor em {resumo['falhas_ocr']} "
                "página(s). Consulte o resultado por artigo e confira o PDF."
            )

        if resumo["resultados"]:
            resultados = pd.DataFrame(resumo["resultados"])
            resultados["Resultado"] = resultados["status"].map(ROTULOS_RESULTADO)
            colunas_resultado = [
                "title",
                "Resultado",
                "chunks",
                "pages_total",
                "pages_ocr",
                "ocr_failures",
                "error",
            ]
            st.dataframe(
                resultados.reindex(columns=colunas_resultado),
                column_config={
                    "title": "Artigo",
                    "chunks": "Trechos processados",
                    "pages_total": "Páginas do PDF",
                    "pages_ocr": "Páginas com OCR",
                    "ocr_failures": "Avisos de OCR",
                    "error": "Motivo da falha",
                },
                hide_index=True,
                width="stretch",
            )
