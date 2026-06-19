import os
import fitz  # PyMuPDF
import psycopg2
from dotenv import load_dotenv, find_dotenv
from google import genai
from google.genai import types

# ==========================================
# CONFIGURAÇÃO DE AMBIENTE
# ==========================================
load_dotenv(find_dotenv())
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

NOME_MODELO_EMBEDDING = "gemini-embedding-001"
DIMENSOES = 768
DIRETORIO_PDFS = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../data/pdfs'))

def get_conexao():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "rag_systematic_review"),
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"]
    )

def extrair_texto_pdf(caminho_pdf):
    """Extrai texto do PDF página a página usando PyMuPDF."""
    texto_completo = ""
    try:
        documento = fitz.open(caminho_pdf)
        for pagina in documento:
            texto_completo += pagina.get_text("text") + "\n"
        documento.close()
        return texto_completo.strip()
    except Exception as e:
        print(f"❌ Erro ao ler {caminho_pdf}: {e}")
        return None

def criar_chunks(texto, max_palavras=250):
    """
    Divide o texto em pedaços. Como os PDFs são muito grandes, 
    usamos chunks ligeiramente maiores (250 palavras) para capturar mais contexto por vetor.
    """
    if not texto:
        return []
    
    palavras = texto.split()
    chunks = []
    # Cria fatias de texto, avançando max_palavras de cada vez
    for i in range(0, len(palavras), max_palavras):
        chunk = " ".join(palavras[i:i + max_palavras])
        chunks.append(chunk)
    return chunks

def processar_pdfs():
    print(f"📂 A verificar diretório: {DIRETORIO_PDFS}")
    if not os.path.exists(DIRETORIO_PDFS):
        os.makedirs(DIRETORIO_PDFS)
        print("📁 Pasta criada. Por favor, adicione os ficheiros PDF lá dentro.")
        return

    arquivos_pdf = [f for f in os.listdir(DIRETORIO_PDFS) if f.endswith('.pdf')]
    if not arquivos_pdf:
        print("✅ Nenhum PDF encontrado na pasta para processar.")
        return

    conexao = get_conexao()
    cursor = conexao.cursor()

    for arquivo in arquivos_pdf:
        # O nome do arquivo deve ser o UUID exato da tabela deduplicated_papers
        paper_id = arquivo.replace(".pdf", "")
        caminho_completo = os.path.join(DIRETORIO_PDFS, arquivo)

        # Verifica se o PDF já foi vetorizado antes (evita duplicação cara)
        cursor.execute("SELECT COUNT(*) FROM paper_chunks WHERE paper_id = %s AND chunk_type LIKE 'full_text_part_%%'", (paper_id,))
        ja_processado = cursor.fetchone()[0] > 0

        if ja_processado:
            print(f"⏩ PDF {paper_id[:8]}... já processado anteriormente. Saltando.")
            continue

        print(f"📖 A ler e extrair texto de: {arquivo}...")
        texto_pdf = extrair_texto_pdf(caminho_completo)
        
        if not texto_pdf:
            continue

        print(f"🔪 A fatiar o texto completo de {paper_id[:8]}...")
        chunks = criar_chunks(texto_pdf, max_palavras=250)
        
        print(f"🧠 A gerar embeddings para {len(chunks)} chunks com a IA do Google...")
        chunks_inseridos = 0
        
        for index, chunk_text in enumerate(chunks):
            try:
                # 1. Gera a coordenada matemática do trecho
                resposta = client.models.embed_content(
                    model=NOME_MODELO_EMBEDDING,
                    contents=chunk_text,
                    config=types.EmbedContentConfig(output_dimensionality=DIMENSOES)
                )
                vetor = resposta.embeddings[0].values
                
                # 2. Insere o pedaço de texto na base
                cursor.execute("""
                    INSERT INTO paper_chunks (paper_id, chunk_type, chunk_text)
                    VALUES (%s, %s, %s) RETURNING id
                """, (paper_id, f"full_text_part_{index+1}", chunk_text))
                chunk_id = cursor.fetchone()[0]
                
                # 3. Insere a matemática no pgvector
                cursor.execute("""
                    INSERT INTO embeddings_metadata (chunk_id, model_name, dimensions, embedding)
                    VALUES (%s, %s, %s, %s)
                """, (chunk_id, NOME_MODELO_EMBEDDING, DIMENSOES, str(vetor)))
                
                chunks_inseridos += 1
            except Exception as e:
                print(f"⚠️ Erro ao vetorizar chunk {index}: {e}")
                
        conexao.commit()
        print(f"   💾 Sucesso! {chunks_inseridos} trechos indexados para o artigo {paper_id[:8]}.\n")

    cursor.close()
    conexao.close()
    print("🎉 Processamento de PDFs concluído!")

if __name__ == "__main__":
    processar_pdfs()