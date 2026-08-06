import os
import sys
import psycopg2
import pandas as pd
import streamlit as st
from dotenv import load_dotenv, find_dotenv

# Ajuste de Caminho para podermos importar funções do backend
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from backend.processamento.leitor_pdf import processar_pdfs
from frontend.project_selector import selecionar_projeto_ativo

# ==========================================
# CONFIGURAÇÃO DA PÁGINA
# ==========================================
st.set_page_config(page_title="Gestão de PDFs", page_icon="📂", layout="wide")
load_dotenv(find_dotenv())

DIRETORIO_PDFS = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../data/pdfs'))

# Garante que a pasta física existe no ambiente
if not os.path.exists(DIRETORIO_PDFS):
    os.makedirs(DIRETORIO_PDFS)

def get_conexao():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "rag_systematic_review"),
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"]
    )

def carregar_artigos_aprovados(project_id):
    """Busca apenas os artigos que o humano decidiu 'Incluir'"""
    conexao = get_conexao()
    query = """
        SELECT d.id, d.title
        FROM deduplicated_papers d
        JOIN screening_decisions s ON d.id = s.paper_id
        WHERE d.project_id = %s
          AND s.human_decision = 'Incluir'
        ORDER BY d.title ASC
    """
    df = pd.read_sql(query, conexao, params=(project_id,))
    conexao.close()
    return df

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

# Carrega os dados reais do banco
df_aprovados = carregar_artigos_aprovados(project_id)

if df_aprovados.empty:
    st.info("Nenhum artigo aprovado encontrado. Realize a triagem de artigos primeiro.")
else:
    # Verifica quais PDFs já existem fisicamente na pasta
    pdfs_existentes = [f.replace(".pdf", "") for f in os.listdir(DIRETORIO_PDFS) if f.endswith('.pdf')]
    
    # Identifica a presença do ficheiro físico
    df_aprovados['Possui PDF'] = df_aprovados['id'].isin(pdfs_existentes)
    
    df_pendentes = df_aprovados[~df_aprovados['Possui PDF']]
    df_concluidos = df_aprovados[df_aprovados['Possui PDF']]

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
            
            uuid_alvo = df_pendentes[df_pendentes['title'] == titulo_selecionado]['id'].values[0]
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
                df_concluidos[['title', 'id']], 
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
    *embeddings* de 768 dimensões com a IA do Google. Índices antigos sem página serão atualizados
    automaticamente; PDFs que já possuem rastreabilidade serão ignorados para evitar custo duplicado.
    """)

    # Botão de ignição do backend
    if st.button("⚡ Executar Processamento e Vetorização de PDFs", type="secondary", use_container_width=True):
        with st.spinner("O sistema está a ler, fatiar e vetorizar os documentos na íntegra... Isto pode demorar alguns minutos consoante o tamanho dos artigos."):
            try:
                # Invoca a função do leitor_pdf.py diretamente
                processar_pdfs(project_id)
                st.success("🎉 Processamento concluído! Os textos estão indexados com a página de origem de cada trecho.")
            except Exception as e:
                st.error(f"⚠️ Ocorreu um erro durante a vetorização: {e}")
