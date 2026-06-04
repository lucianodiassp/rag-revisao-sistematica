import os
import psycopg2
from psycopg2.extras import Json
from dotenv import load_dotenv

# Carrega as variáveis do .env
load_dotenv()

def get_connection():
    """Cria e retorna uma conexão com o banco de dados."""
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD")
    )

def salvar_artigo_coletado(id_artigo, titulo, abstract, fontes_dict):
    """
    Salva um artigo coletado no banco. 
    Ideal para a Pessoa 2 (Coleta de Dados).
    """
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            # O Json() converte o dicionário Python para o formato JSONB do Postgres
            cursor.execute("""
                INSERT INTO deduplicated_papers (id, title, abstract, merged_sources_jsonb)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (id) DO NOTHING;
            """, (id_artigo, titulo, abstract, Json(fontes_dict)))
            
            conn.commit()
            print(f"✅ Artigo '{titulo[:30]}...' salvo com sucesso!")
            
    except Exception as e:
        conn.rollback()
        print(f"❌ Erro ao salvar artigo: {e}")
    finally:
        conn.close()

def log_interacao_agente(nome_agente, input_dict, output_dict, modelo_dict=None):
    """
    Salva tudo o que o LLM leu e respondeu para fins de auditoria.
    Ideal para a Pessoa 5 (Agentes).
    """
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO agent_interactions (agent_name, input_jsonb, output_jsonb, model_jsonb)
                VALUES (%s, %s, %s, %s)
                RETURNING id;
            """, (
                nome_agente, 
                Json(input_dict), 
                Json(output_dict), 
                Json(modelo_dict) if modelo_dict else None
            ))
            
            interaction_id = cursor.fetchone()[0]
            conn.commit()
            print(f"✅ Log do agente '{nome_agente}' gravado. ID: {interaction_id}")
            return interaction_id
            
    except Exception as e:
        conn.rollback()
        print(f"❌ Erro ao gravar log do agente: {e}")
        return None
    finally:
        conn.close()