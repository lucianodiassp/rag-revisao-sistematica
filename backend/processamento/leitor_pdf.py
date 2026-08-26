import os
import psycopg2
from dotenv import load_dotenv, find_dotenv
from psycopg2.extras import Json
from backend.app.ai_config import get_embedding_config
from backend.app.ai_service import generate_embedding
from backend.app.database import resolver_project_id
from backend.processamento.ocr_pdf import (
    extract_pdf_document,
    get_pdf_ocr_config,
    sanitize_pdf_text,
)
from backend.app.storage_service import pdf_directory

# ==========================================
# CONFIGURAÇÃO DE AMBIENTE
# ==========================================
load_dotenv(find_dotenv())
DIRETORIO_PDFS = str(pdf_directory())

def get_conexao():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "rag_systematic_review"),
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"]
    )


def carregar_status_pdfs(project_id=None):
    """Retorna o estágio real de cada artigo incluído no fluxo de evidências."""
    project_id = resolver_project_id(project_id)
    embedding_config = get_embedding_config()

    with get_conexao() as conexao, conexao.cursor() as cursor:
        cursor.execute(
            """
            SELECT d.id, d.title,
                   COUNT(pc.id) FILTER (
                       WHERE pc.chunk_type LIKE 'full_text_part_%%'
                   ) AS total_chunks,
                   COUNT(pc.id) FILTER (
                       WHERE pc.chunk_type LIKE 'full_text_part_%%'
                         AND pc.metadata_jsonb->>'source_type' = 'pdf'
                         AND pc.metadata_jsonb ? 'page_start'
                   ) AS chunks_rastreaveis,
                   COUNT(pc.id) FILTER (
                       WHERE pc.chunk_type LIKE 'full_text_part_%%'
                         AND EXISTS (
                             SELECT 1
                             FROM embeddings_metadata em
                             WHERE em.chunk_id = pc.id
                               AND em.model_name = %s
                               AND em.dimensions = %s
                         )
                   ) AS chunks_compativeis,
                   COUNT(pc.id) FILTER (
                       WHERE pc.chunk_type LIKE 'full_text_part_%%'
                         AND pc.metadata_jsonb->>'traceability_version' = '2'
                   ) AS chunks_extracao_v2,
                   COUNT(DISTINCT (pc.metadata_jsonb->>'page_start')::INTEGER) FILTER (
                       WHERE pc.chunk_type LIKE 'full_text_part_%%'
                         AND pc.metadata_jsonb->>'text_extraction_method' = 'ocr'
                   ) AS paginas_ocr,
                   e.schema_version,
                   e.human_review_status
            FROM deduplicated_papers d
            LEFT JOIN paper_chunks pc ON pc.paper_id = d.id
            LEFT JOIN extracted_evidence e ON e.paper_id = d.id
            WHERE d.project_id = %s
              AND EXISTS (
                  SELECT 1
                  FROM screening_decisions s
                  WHERE s.paper_id = d.id
                    AND s.human_decision = 'Incluir'
              )
            GROUP BY d.id, d.title, e.schema_version, e.human_review_status
            ORDER BY d.title
            """,
            (embedding_config.model, embedding_config.dimensions, project_id),
        )
        linhas = cursor.fetchall()

    arquivos = set()
    if os.path.exists(DIRETORIO_PDFS):
        arquivos = {
            arquivo[:-4]
            for arquivo in os.listdir(DIRETORIO_PDFS)
            if arquivo.lower().endswith(".pdf")
        }

    resultado = []
    for (
        paper_id,
        titulo,
        total_chunks,
        chunks_rastreaveis,
        chunks_compativeis,
        chunks_extracao_v2,
        paginas_ocr,
        schema_version,
        human_review_status,
    ) in linhas:
        paper_id = str(paper_id)
        pdf_associado = paper_id in arquivos
        indexado = (
            total_chunks > 0
            and total_chunks == chunks_rastreaveis
            and total_chunks == chunks_compativeis
            and total_chunks == chunks_extracao_v2
        )
        if not pdf_associado:
            situacao = "awaiting_pdf"
        elif indexado:
            situacao = "indexed"
        elif total_chunks:
            situacao = "needs_reindex"
        else:
            situacao = "awaiting_index"

        resultado.append(
            {
                "paper_id": paper_id,
                "title": titulo,
                "pdf_associado": pdf_associado,
                "indexado": indexado,
                "situacao": situacao,
                "total_chunks": total_chunks,
                "chunks_rastreaveis": chunks_rastreaveis,
                "chunks_compativeis": chunks_compativeis,
                "paginas_ocr": paginas_ocr,
                "schema_version": schema_version,
                "human_review_status": human_review_status,
            }
        )
    return resultado


def resumir_status_fluxo(status_artigos):
    """Consolida o funil sem confundir indexação, extração e revisão humana."""
    status_artigos = list(status_artigos)
    extraidos = [
        item for item in status_artigos
        if item.get("schema_version") == "traceable-v1"
    ]
    return {
        "incluidos": len(status_artigos),
        "pdfs_associados": sum(bool(item.get("pdf_associado")) for item in status_artigos),
        "sem_pdf": sum(not item.get("pdf_associado") for item in status_artigos),
        "indexados": sum(bool(item.get("indexado")) for item in status_artigos),
        "aguardando_indexacao": sum(
            bool(item.get("pdf_associado")) and not item.get("indexado")
            for item in status_artigos
        ),
        "extraidos": len(extraidos),
        "aguardando_extracao": sum(
            bool(item.get("indexado"))
            and item.get("schema_version") != "traceable-v1"
            for item in status_artigos
        ),
        "revisados": sum(
            item.get("human_review_status") in {"approved", "corrected", "rejected"}
            for item in extraidos
        ),
    }


def sanitizar_texto_pdf(texto):
    """Remove caracteres NUL que o PostgreSQL não aceita em campos textuais."""
    return sanitize_pdf_text(texto)


def extrair_documento_pdf(caminho_pdf, ocr_config=None):
    """Extrai texto e diagnóstico por página, incluindo o fallback OCR."""
    try:
        resultado = extract_pdf_document(
            caminho_pdf,
            config=ocr_config or get_pdf_ocr_config(),
        )
        if resultado["null_characters_removed"]:
            print(
                f"🧹 {resultado['null_characters_removed']} caractere(s) NUL inválido(s) "
                "removido(s) do texto extraído."
            )
        if resultado["ocr_pages"]:
            print(
                f"🔎 OCR aplicado em {resultado['ocr_pages']} de "
                f"{resultado['total_pages']} página(s)."
            )
        for warning in resultado["warnings"]:
            print(
                f"⚠️ OCR da página {warning['page_number']}: {warning['message']}"
            )
        return resultado
    except Exception as error:
        print(f"❌ Erro ao ler {caminho_pdf}: {error}")
        return None

def extrair_paginas_pdf(caminho_pdf):
    """Compatibilidade para consumidores que esperam somente a lista de páginas."""
    resultado = extrair_documento_pdf(caminho_pdf)
    return None if resultado is None else resultado["pages"]


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
                    "text_extraction_method": pagina.get(
                        "text_extraction_method", "native"
                    ),
                    "native_character_count": pagina.get("native_character_count"),
                    "ocr_attempted": bool(pagina.get("ocr_attempted")),
                    "ocr_languages": pagina.get("ocr_languages"),
                    "ocr_dpi": pagina.get("ocr_dpi"),
                }
            )
    return resultado

def processar_pdfs(project_id=None):
    project_id = resolver_project_id(project_id)
    embedding_config = get_embedding_config()
    resumo = {
        "total_aprovados": 0,
        "pdfs_encontrados": 0,
        "processados": 0,
        "ignorados": 0,
        "falhas": 0,
        "paginas_ocr": 0,
        "falhas_ocr": 0,
        "resultados": [],
    }
    print(f"📂 A verificar diretório: {DIRETORIO_PDFS}")
    if not os.path.exists(DIRETORIO_PDFS):
        os.makedirs(DIRETORIO_PDFS)
        print("📁 Pasta criada. Por favor, adicione os ficheiros PDF lá dentro.")
        return resumo

    conexao = get_conexao()
    cursor = conexao.cursor()
    cursor.execute("""
        SELECT d.id, d.title
        FROM deduplicated_papers d
        WHERE d.project_id = %s
          AND EXISTS (
              SELECT 1
              FROM screening_decisions s
              WHERE s.paper_id = d.id
                AND s.human_decision = 'Incluir'
          )
    """, (project_id,))
    artigos_aprovados = {str(linha[0]): linha[1] for linha in cursor.fetchall()}
    ids_aprovados = set(artigos_aprovados)
    resumo["total_aprovados"] = len(ids_aprovados)

    arquivos_pdf = [
        arquivo for arquivo in os.listdir(DIRETORIO_PDFS)
        if arquivo.lower().endswith('.pdf')
        and arquivo[:-4] in ids_aprovados
    ]
    resumo["pdfs_encontrados"] = len(arquivos_pdf)
    if not arquivos_pdf:
        cursor.close()
        conexao.close()
        print("✅ Nenhum PDF aprovado deste projeto está pendente de processamento.")
        return resumo

    for arquivo in arquivos_pdf:
        # O nome do arquivo deve ser o UUID exato da tabela deduplicated_papers
        paper_id = arquivo.replace(".pdf", "")
        titulo = artigos_aprovados[paper_id]
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
            ), COUNT(*) FILTER (
                WHERE metadata_jsonb->>'traceability_version' = '2'
            )
            FROM paper_chunks
            WHERE paper_id = %s AND chunk_type LIKE 'full_text_part_%%'
        """, (
            embedding_config.model,
            embedding_config.dimensions,
            paper_id,
        ))
        (
            total_chunks,
            chunks_rastreaveis,
            chunks_compativeis,
            chunks_extracao_v2,
        ) = cursor.fetchone()
        ja_processado = (
            total_chunks > 0
            and total_chunks == chunks_rastreaveis
            and total_chunks == chunks_compativeis
            and total_chunks == chunks_extracao_v2
        )

        if ja_processado:
            print(f"⏩ PDF {paper_id[:8]}... já possui índice com páginas. Saltando.")
            resumo["ignorados"] += 1
            resumo["resultados"].append(
                {
                    "paper_id": paper_id,
                    "title": titulo,
                    "status": "already_indexed",
                    "chunks": total_chunks,
                    "pages_total": None,
                    "pages_ocr": None,
                    "ocr_failures": None,
                    "error": None,
                }
            )
            continue


        if total_chunks:
            if chunks_rastreaveis != total_chunks:
                motivo = "índice legado sem páginas"
            elif chunks_compativeis != total_chunks:
                motivo = "modelo de embedding diferente"
            else:
                motivo = "índice anterior sem proveniência do método de extração"
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
        documento_extraido = extrair_documento_pdf(caminho_completo)
        paginas = documento_extraido["pages"] if documento_extraido else None
        if documento_extraido:
            resumo["paginas_ocr"] += documento_extraido["ocr_pages"]
            resumo["falhas_ocr"] += documento_extraido["ocr_failed_pages"]
        
        if not paginas:
            conexao.rollback()
            resumo["falhas"] += 1
            resumo["resultados"].append(
                {
                    "paper_id": paper_id,
                    "title": titulo,
                    "status": "failed",
                    "chunks": 0,
                    "pages_total": (
                        documento_extraido.get("total_pages", 0)
                        if documento_extraido else 0
                    ),
                    "pages_ocr": 0,
                    "ocr_failures": (
                        documento_extraido.get("ocr_failed_pages", 0)
                        if documento_extraido else 0
                    ),
                    "error": (
                        "O PDF não possui texto extraível. O OCR também não produziu "
                        "texto utilizável; confira se o arquivo está legível e se os "
                        "idiomas do OCR estão instalados."
                        if documento_extraido and documento_extraido.get("ocr_attempted_pages")
                        else "O PDF não possui texto extraível ou não pôde ser lido."
                    ),
                }
            )
            continue

        print(f"🔪 A fatiar {len(paginas)} páginas de {paper_id[:8]} sem perder a origem...")
        chunks = criar_chunks_por_pagina(paginas, max_palavras=250)
        
        print(
            f"🧠 A gerar embeddings para {len(chunks)} chunks com "
            f"{embedding_config.provider}/{embedding_config.model}..."
        )
        chunks_inseridos = 0
        erro_indexacao = None
        
        for index, chunk in enumerate(chunks):
            try:
                # Defesa adicional para chunks produzidos por integrações futuras.
                chunk_text = sanitizar_texto_pdf(chunk["chunk_text"])
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
                        "traceability_version": 2,
                        "text_extraction_method": chunk["text_extraction_method"],
                        "native_character_count": chunk["native_character_count"],
                        "ocr_attempted": chunk["ocr_attempted"],
                        "ocr_engine": (
                            "tesseract"
                            if chunk["text_extraction_method"] == "ocr"
                            else None
                        ),
                        "ocr_languages": chunk["ocr_languages"],
                        "ocr_dpi": chunk["ocr_dpi"],
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
                erro_indexacao = str(e)
                # Uma falha torna a transação incompleta. Interromper evita chamadas
                # desnecessárias à API e o rollback preserva qualquer índice anterior.
                break

        if chunks_inseridos != len(chunks):
            conexao.rollback()
            print(
                f"   ❌ Indexação incompleta ({chunks_inseridos}/{len(chunks)}). "
                "As alterações deste PDF foram desfeitas para preservar o índice anterior."
            )
            resumo["falhas"] += 1
            resumo["resultados"].append(
                {
                    "paper_id": paper_id,
                    "title": titulo,
                    "status": "failed",
                    "chunks": chunks_inseridos,
                    "pages_total": documento_extraido["total_pages"],
                    "pages_ocr": documento_extraido["ocr_pages"],
                    "ocr_failures": documento_extraido["ocr_failed_pages"],
                    "error": erro_indexacao or "A indexação não processou todos os trechos.",
                }
            )
            continue

        conexao.commit()
        resumo["processados"] += 1
        resumo["resultados"].append(
            {
                "paper_id": paper_id,
                "title": titulo,
                "status": "indexed",
                "chunks": chunks_inseridos,
                "pages_total": documento_extraido["total_pages"],
                "pages_ocr": documento_extraido["ocr_pages"],
                "ocr_failures": documento_extraido["ocr_failed_pages"],
                "error": None,
            }
        )
        print(f"   💾 Sucesso! {chunks_inseridos} trechos indexados para o artigo {paper_id[:8]}.\n")

    cursor.close()
    conexao.close()
    print("🎉 Processamento de PDFs concluído!")
    return resumo

if __name__ == "__main__":
    processar_pdfs(resolver_project_id())
