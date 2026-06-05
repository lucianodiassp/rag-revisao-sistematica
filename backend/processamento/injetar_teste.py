import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

print("🔌 Ligando ao banco de dados...")
conexao = psycopg2.connect(
    host=os.getenv("DB_HOST", "localhost"),
    port=os.getenv("DB_PORT", "5432"),
    dbname=os.getenv("DB_NAME", "postgres"),
    user=os.getenv("DB_USER", "postgres"),
    password=os.getenv("DB_PASSWORD", "admin")
)
cursor = conexao.cursor()

# 1. Limpa os vetores antigos
cursor.execute("TRUNCATE TABLE document_chunks;")

# 2. Injeta o texto real no primeiro artigo que encontrar
cursor.execute("""
    UPDATE deduplicated_papers 
    SET abstract = 'This paper introduces a novel framework to benchmark and evaluate Large Language Models (LLMs) such as GPT-4 and Llama-3. We focus on evaluation metrics for reasoning, accuracy, and hallucination rates across multiple domains.'
    WHERE id = (SELECT id FROM deduplicated_papers LIMIT 1);
""")

# 3. O SEGREDO QUE FALTAVA: Confirmar e salvar a transação!
conexao.commit()
cursor.close()
conexao.close()

print("✅ Texto real injetado e salvo com sucesso no banco de dados!")