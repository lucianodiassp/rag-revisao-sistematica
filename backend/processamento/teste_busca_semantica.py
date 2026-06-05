import os
import psycopg2
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

# Carrega as credenciais do arquivo .env da raiz do projeto
load_dotenv()

def buscar_artigos_similares(pergunta, limite=3):
    print("🧠 Carregando modelo de IA...")
    modelo = SentenceTransformer('all-MiniLM-L6-v2')
    
    print(f"🔎 Transformando a sua pergunta em vetor: '{pergunta}'")
    vetor_pergunta = modelo.encode(pergunta).tolist()

    print("🗄️ Consultando o banco de dados via pgvector...")
    
    # Agora puxamos as credenciais corretas e seguras
    conexao = psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "postgres"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", "admin") # Tente alterar aqui manualmente se não tiver o .env
    )
    cursor = conexao.cursor()

    cursor.execute(
        """
        SELECT chunk_text, 1 - (embedding <=> %s::vector) AS similaridade
        FROM document_chunks
        ORDER BY embedding <=> %s::vector
        LIMIT %s;
        """,
        (str(vetor_pergunta), str(vetor_pergunta), limite)
    )
    
    resultados = cursor.fetchall()
    conexao.close()

    print("\n🏆 TOP 3 ARTIGOS MAIS RELEVANTES:")
    print("=" * 60)
    for i, (texto, similaridade) in enumerate(resultados, 1):
        porcentagem = round(similaridade * 100, 1)
        print(f"{i}º Lugar (Relevância: {porcentagem}%)")
        print(f"Trecho: {texto[:200]}...")
        print("-" * 60)

if __name__ == "__main__":
    minha_pergunta = "How to benchmark and evaluate large language models?"
    buscar_artigos_similares(minha_pergunta)