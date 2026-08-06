import os
import fitz  # PyMuPDF
import psycopg2
from dotenv import load_dotenv, find_dotenv
from psycopg2.extras import Json
from backend.app.ai_config import get_embedding_config
from backend.app.ai_service import generate_embedding
from backend.app.database import resolver_project_id

# ==========================================
# CONFIGURAÇÃO DE AMBIENTE
# ==========================================
load_dotenv(find_dotenv())
DIRETORIO_PDFS = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../data/pdfs'))

def get_conexao():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "rag_systematic_review"),
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"]
    )

def extrair_paginas_pdf(caminho_pdf):
    """Extrai o texto sem perder o número da página de origem."""
    try:
        paginas = []
        with fitz.open(caminho_pdf) as documento:
            for numero, pagina in enumerate(documento, start=1):
                texto = pagina.get_text("text").strip()
                if texto:
                    paginas.append({"page_number": numero, "text": texto})
        return paginas
    except Exception as e:
        print(f"❌ Erro ao ler {caminho_pdf}: {e}")
        return None


def extrair_texto_pdf(caminho_pdf):
    """Mantém compatibilidade com chamadas antigas que esperam texto contínuo."""
    paginas = extrair_paginas_pdf(caminho_pdf)
    if paginas is None:
        return None
    return "\n".join(pagina["text"] for pagina in paginas).strip()

def criar_chunks(texto, max_palavras=250, overlap=50):
    """
    Divide o texto em pedaços com uma janela deslizante (overlap),
    garantindo que nenhuma frase importante seja cortada ao meio na transição.
    """
    if not texto:
        return []
    
    palavras = texto.split()
    chunks = []
    
    i = 0
    while i < len(palavras):
        # Garante que o fim não ultrapasse o tamanho total do texto
        fim = min(i + max_palavras, len(palavras))
        chunk = " ".join(palavras[i:fim])
        chunks.append(chunk)
        
        # Avança o índice mitigando o corte pelo tamanho do overlap
        i += (max_palavras - overlap)
        
        if fim == len(palavras):
            break
            
    return chunks


def criar_chunks_por_pagina(paginas, max_palavras=250, overlap=50):
    """Cria chunks que nunca atravessam páginas e anexa sua proveniência."""
    resultado = []
    for pagina in paginas or []:
        for indice_pagina, texto in enumerate(
            criar_chunks(pagina["text"], max_palavras=max_palavras, overlap=overlap),
            start=1,
        ):
            resultado.append(
                {
                    "chunk_text": texto,
                    "page_number": pagina["page_number"],
                    "page_chunk_index": indice_pagina,
                }
            )
    return resultado

def processar_pdfs(project_id=None):
    project_id = resolver_project_id(project_id)
    embedding_config = get_embedding_config()
    print(f"📂 A verificar diretório: {DIRETORIO_PDFS}")
    if not os.path.exists(DIRETORIO_PDFS):
        os.makedirs(DIRETORIO_PDFS)
        print("📁 Pasta criada. Por favor, adicione os ficheiros PDF lá dentro.")
        return

    conexao = get_conexao()
    cursor = conexao.cursor()
    cursor.execute("""
        SELECT d.id
        FROM deduplicated_papers d
        JOIN screening_decisions s ON s.paper_id = d.id
        WHERE d.project_id = %s AND s.human_decision = 'Incluir'
    """, (project_id,))
    ids_aprovados = {str(linha[0]) for linha in cursor.fetchall()}

    arquivos_pdf = [
        arquivo for arquivo in os.listdir(DIRETORIO_PDFS)
        if arquivo.lower().endswith('.pdf')
        and arquivo[:-4] in ids_aprovados
    ]
    if not arquivos_pdf:
        cursor.close()
        conexao.close()
        print("✅ Nenhum PDF aprovado deste projeto está pendente de processamento.")
        return

    for arquivo in arquivos_pdf:
        # O nome do arquivo deve ser o UUID exato da tabela deduplicated_papers
        paper_id = arquivo.replace(".pdf", "")
        caminho_completo = os.path.join(DIRETORIO_PDFS, arquivo)

        # Um índice antigo sem página precisa ser reconstruído uma única vez.
        cursor.execute("""
            SELECT COUNT(*), COUNT(*) FILTER (
                WHERE metadata_jsonb->>'source_type' = 'pdf'
                  AND metadata_jsonb ? 'page_start'
            ), COUNT(*) FILTER (
                WHERE EXISTS (
                    SELECT 1 FROM embeddings_metadata em
                    WHERE em.chunk_id = paper_chunks.id
                      AND em.model_name = %s
                      AND em.dimensions = %s
                )
            )
            FROM paper_chunks
            WHERE paper_id = %s AND chunk_type LIKE 'full_text_part_%%'
        """, (
            embedding_config.model,
            embedding_config.dimensions,
            paper_id,
        ))
        total_chunks, chunks_rastreaveis, chunks_compativeis = cursor.fetchone()
        ja_processado = (
            total_chunks > 0
            and total_chunks == chunks_rastreaveis
            and total_chunks == chunks_compativeis
        )

        if ja_processado:
            print(f"⏩ PDF {paper_id[:8]}... já possui índice com páginas. Saltando.")
            continue


        if total_chunks:
            motivo = (
                "modelo de embedding diferente"
                if chunks_rastreaveis == total_chunks and chunks_compativeis != total_chunks
                else "índice legado sem páginas"
            )
            print(f"♻️ PDF {paper_id[:8]}... possui {motivo}; reconstruindo.")
            cursor.execute("""
                UPDATE extracted_evidence
                SET schema_version = 'legacy-v0',
                    human_review_status = 'pending',
                    human_review_jsonb = NULL,
                    review_notes = 'Revisão invalidada por reindexação do PDF',
                    reviewed_at = NULL
                WHERE paper_id = %s
            """, (paper_id,))
            cursor.execute("""
                DELETE FROM paper_chunks
                WHERE paper_id = %s AND chunk_type LIKE 'full_text_part_%%'
            """, (paper_id,))

        print(f"📖 A ler e extrair texto de: {arquivo}...")
        paginas = extrair_paginas_pdf(caminho_completo)
        
        if not paginas:
            conexao.rollback()
            continue

        print(f"🔪 A fatiar {len(paginas)} páginas de {paper_id[:8]} sem perder a origem...")
        chunks = criar_chunks_por_pagina(paginas, max_palavras=250)
        
        print(f"🧠 A gerar embeddings para {len(chunks)} chunks com a IA do Google...")
        chunks_inseridos = 0
        
        for index, chunk in enumerate(chunks):
            try:
                chunk_text = chunk["chunk_text"]
                # 1. Gera a coordenada matemática do trecho
                vetor = generate_embedding(chunk_text)
                
                # 2. Insere o pedaço de texto na base
                cursor.execute("""
                    INSERT INTO paper_chunks
                        (paper_id, chunk_type, chunk_text, metadata_jsonb)
                    VALUES (%s, %s, %s, %s) RETURNING id
                """, (
                    paper_id,
                    f"full_text_part_{index+1}",
                    chunk_text,
                    Json({
                        "source_type": "pdf",
                        "file_name": arquivo,
                        "page_start": chunk["page_number"],
                        "page_end": chunk["page_number"],
                        "page_chunk_index": chunk["page_chunk_index"],
                        "document_chunk_index": index + 1,
                        "traceability_version": 1,
                    }),
                ))
                chunk_id = cursor.fetchone()[0]
                
                # 3. Insere a matemática no pgvector
                cursor.execute("""
                    INSERT INTO embeddings_metadata (chunk_id, model_name, dimensions, embedding)
                    VALUES (%s, %s, %s, %s)
                """, (
                    chunk_id,
                    embedding_config.model,
                    embedding_config.dimensions,
                    str(vetor),
                ))
                
                chunks_inseridos += 1
            except Exception as e:
                print(f"⚠️ Erro ao vetorizar chunk {index}: {e}")

        if chunks_inseridos != len(chunks):
            conexao.rollback()
            print(
                f"   ❌ Indexação incompleta ({chunks_inseridos}/{len(chunks)}). "
                "As alterações deste PDF foram desfeitas para preservar o índice anterior."
            )
            continue

        conexao.commit()
        print(f"   💾 Sucesso! {chunks_inseridos} trechos indexados para o artigo {paper_id[:8]}.\n")

    cursor.close()
    conexao.close()
    print("🎉 Processamento de PDFs concluído!")

if __name__ == "__main__":
    processar_pdfs(resolver_project_id())
