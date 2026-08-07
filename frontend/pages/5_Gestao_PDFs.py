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

# ==========================================
# INTERFACE VISUAL
# ==========================================
st.title("📂 Gestão de arquivos e Vetorização")
projeto = selecionar_projeto_ativo()
project_id = str(projeto["id"])
st.caption(f"Projeto ativo: **{projeto['title']}**")
st.markdown("""
Faça o upload dos documentos na íntegra para os artigos aprovados e acione a indexação 
vetorial para alimentar o cérebro do motor RAG.
""")
st.divider()

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
            titulo_selecionado = st.selectbox(
                "1. Selecione o artigo aprovado:",
                options=df_pendentes['title'].tolist(),
                help="Apenas artigos marcados como 'Incluir' que ainda não possuem PDF aparecem aqui."
            )
            
            uuid_alvo = df_pendentes[
                df_pendentes['title'] == titulo_selecionado
            ]['paper_id'].values[0]
            st.caption(f"**UUID de Vínculo:** `{uuid_alvo}`")
            
            arquivo_upload = st.file_uploader("2. Envie o ficheiro PDF do artigo", type=['pdf'])
            
            if arquivo_upload is not None:
                if st.button("💾 Salvar e Relacionar PDF", type="primary", use_container_width=True):
                    caminho_salvo = os.path.join(DIRETORIO_PDFS, f"{uuid_alvo}.pdf")
                    
                    with open(caminho_salvo, "wb") as f:
                        f.write(arquivo_upload.getbuffer())
                    
                    st.success(f"Ficheiro guardado e vinculado com sucesso!")
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
