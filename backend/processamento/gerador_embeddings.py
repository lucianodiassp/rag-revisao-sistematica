import os
import psycopg2
from dotenv import load_dotenv
from google.genai import types
from backend.app.database import resolver_project_id
from backend.app.gemini_client import get_gemini_client

# ==========================================
# CONFIGURAÇÃO DE AMBIENTE
# ==========================================
load_dotenv()
NOME_MODELO_EMBEDDING = "gemini-embedding-001"
DIMENSOES = 768

def get_conexao():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "rag_systematic_review"),
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"]
    )

def criar_chunks(texto, max_palavras=150):
    """
    Divide o texto em pedaços menores (chunks) para melhorar a precisão da busca vetorial.
    """
    if not texto:
        return []
    
    palavras = texto.split()
    chunks = []
    for i in range(0, len(palavras), max_palavras):
        chunk = " ".join(palavras[i:i + max_palavras])
        chunks.append(chunk)
    return chunks

def processar_indexacao_vetorial(project_id=None):
    """Lê os artigos aprovados e converte-os em vetores matemáticos no pgvector."""
    project_id = resolver_project_id(project_id)
    conexao = get_conexao()
    cursor = conexao.cursor()
    
    print("🔍 A procurar artigos aprovados pendentes de indexação...")
    
    # Busca artigos que foram aprovados pelo humano, mas que ainda não estão na tabela paper_chunks
    cursor.execute("""
        SELECT d.id, d.title, d.abstract 
        FROM deduplicated_papers d
        JOIN screening_decisions s ON d.id = s.paper_id
        WHERE d.project_id = %s
        AND s.human_decision = 'Incluir'
        AND d.id NOT IN (SELECT paper_id FROM paper_chunks)
    """, (project_id,))
    artigos = cursor.fetchall()
    
    if not artigos:
        print("✅ Não há novos artigos aprovados para indexar.")
        cursor.close()
        conexao.close()
        return

    for paper_id, titulo, abstract in artigos:
        print(f"🧠 A processar vetorização para: '{titulo[:50]}...'")
        
        # Junta o título e o resumo para garantir que o contexto é rico
        texto_completo = f"Título: {titulo}. Resumo: {abstract}"
        chunks = criar_chunks(texto_completo)
        
        for index, chunk_text in enumerate(chunks):
            # 1. Gera o Embedding (Vetor) usando a API do Gemini com compressão Matryoshka
            resposta = get_gemini_client().models.embed_content(
                model=NOME_MODELO_EMBEDDING,
                contents=chunk_text,
                config=types.EmbedContentConfig(output_dimensionality=DIMENSOES)
            )
            vetor = resposta.embeddings[0].values
            
            # 2. Insere o Chunk textual na base de dados
            cursor.execute("""
                INSERT INTO paper_chunks (paper_id, chunk_type, chunk_text)
                VALUES (%s, %s, %s) RETURNING id
            """, (paper_id, f"abstract_part_{index+1}", chunk_text))
            chunk_id = cursor.fetchone()[0]
            
            # 3. Insere o vetor matemático associado a esse Chunk
            cursor.execute("""
                INSERT INTO embeddings_metadata (chunk_id, model_name, dimensions, embedding)
                VALUES (%s, %s, %s, %s)
            """, (chunk_id, NOME_MODELO_EMBEDDING, DIMENSOES, str(vetor)))
            
        conexao.commit()
        print("   💾 Embeddings guardados com sucesso!")

    cursor.close()
    conexao.close()
    print("\n🎉 Indexação de todos os artigos concluída!")

if __name__ == "__main__":
    processar_indexacao_vetorial(resolver_project_id())
