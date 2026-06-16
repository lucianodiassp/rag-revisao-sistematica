import os
import psycopg2
from dotenv import load_dotenv
from google import genai
from google.genai import types

# ==========================================
# CONFIGURAÇÃO DE AMBIENTE
# ==========================================
load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
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

def processar_indexacao_vetorial():
    """Lê os artigos aprovados e converte-os em vetores matemáticos no pgvector."""
    conexao = get_conexao()
    cursor = conexao.cursor()
    
    print("🔍 A procurar artigos aprovados pendentes de indexação...")
    
    # Busca artigos que foram aprovados pelo humano, mas que ainda não estão na tabela paper_chunks
    cursor.execute("""
        SELECT d.id, d.title, d.abstract 
        FROM deduplicated_papers d
        JOIN screening_decisions s ON d.id = s.paper_id
        WHERE s.human_decision = 'Incluir'
        AND d.id NOT IN (SELECT paper_id FROM paper_chunks)
    """)
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
            resposta = client.models.embed_content(
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
    processar_indexacao_vetorial()