import os
import psycopg2
from dotenv import load_dotenv

# Carrega as variáveis do arquivo .env
load_dotenv()

def test_database_connection():
    try:
        # Tenta estabelecer a conexão com o PostgreSQL
        print("Iniciando tentativa de conexão com o banco de dados...")
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST"),
            port=os.getenv("DB_PORT"),
            database=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD")
        )
        
        cursor = conn.cursor()
        
        # Executa uma query de sistema simples para listar nossas tabelas
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
            ORDER BY table_name;
        """)
        
        tables = cursor.fetchall()
        
        print("\n✅ Conexão bem-sucedida! O Python encontrou as seguintes tabelas:")
        for table in tables:
            print(f" - {table[0]}")

        cursor.close()
        conn.close()

    except Exception as e:
        print(f"\n❌ Erro ao conectar no banco de dados: {e}")

if __name__ == "__main__":
    test_database_connection()