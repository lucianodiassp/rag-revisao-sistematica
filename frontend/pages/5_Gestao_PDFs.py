import os
import sys
import pandas as pd
import streamlit as st

# Ajuste de Caminho para podermos importar funções do backend
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from backend.processamento.leitor_pdf import (
    carregar_status_pdfs,
    processar_pdfs,
    resumir_status_fluxo,
)
from backend.app.screening_reassessment import (
    ACTION_EXCLUDE,
    ACTION_RETURN_TO_SCREENING,
    reassess_included_paper,
)
from frontend.project_selector import selecionar_projeto_ativo

# ==========================================
# CONFIGURAÇÃO DA PÁGINA
# ==========================================
st.set_page_config(page_title="Gestão de PDFs", page_icon="📂", layout="wide")

DIRETORIO_PDFS = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../data/pdfs'))

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
                if st.button("💾 Salvar e Relacionar PDF", type="primary", use_container_width=True):
                    caminho_salvo = os.path.join(DIRETORIO_PDFS, f"{uuid_alvo}.pdf")
                    
                    with open(caminho_salvo, "wb") as f:
                        f.write(arquivo_upload.getbuffer())
                    
                    st.success(f"Ficheiro guardado e vinculado com sucesso!")
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
                        use_container_width=True,
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
                df_concluidos[['title', 'paper_id', 'Situação', 'chunks_rastreaveis']],
                column_config={
                    "title": "Artigo",
                    "paper_id": "UUID",
                    "chunks_rastreaveis": "Trechos rastreáveis",
                },
                hide_index=True, 
                use_container_width=True
            )
        else:
            st.info("Ainda não há arquivos PDF armazenados no sistema.")

    st.divider()

    # --- NOVA SECÇÃO: ENGENHARIA VETORIAL AUTOMÁTICA ---
    st.header("🧠 Central de Indexação Vetorial Avançada")
    st.markdown("""
    Clique no botão abaixo para acionar o processador do sistema. O motor irá abrir cada PDF armazenado, 
    extrair o texto completo, dividi-lo em blocos lógicos, registrar a página de cada trecho e gerar os
    *embeddings* com o provedor configurado. Índices antigos sem página serão atualizados
    automaticamente; PDFs que já possuem rastreabilidade serão ignorados para evitar custo duplicado.
    """)

    # Botão de ignição do backend
    if st.button("⚡ Executar Processamento e Vetorização de PDFs", type="secondary", use_container_width=True):
        with st.spinner("O sistema está a ler, fatiar e vetorizar os documentos na íntegra... Isto pode demorar alguns minutos consoante o tamanho dos artigos."):
            try:
                # Invoca a função do leitor_pdf.py diretamente
                resumo = processar_pdfs(project_id)
                st.session_state["ultimo_relatorio_indexacao"] = {
                    "project_id": project_id,
                    "resumo": resumo,
                }
                st.rerun()
            except Exception as e:
                st.error(f"⚠️ Ocorreu um erro durante a vetorização: {e}")

    relatorio_salvo = st.session_state.get("ultimo_relatorio_indexacao")
    if relatorio_salvo and relatorio_salvo.get("project_id") == project_id:
        resumo = relatorio_salvo["resumo"]
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

        if resumo["resultados"]:
            resultados = pd.DataFrame(resumo["resultados"])
            resultados["Resultado"] = resultados["status"].map(ROTULOS_RESULTADO)
            st.dataframe(
                resultados[["title", "Resultado", "chunks", "error"]],
                column_config={
                    "title": "Artigo",
                    "chunks": "Trechos processados",
                    "error": "Motivo da falha",
                },
                hide_index=True,
                use_container_width=True,
            )
