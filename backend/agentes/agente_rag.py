import os
import psycopg2
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from google import genai
from google.genai import types

# Carregar variáveis de ambiente (banco de dados e API Key)
load_dotenv()

# ==========================================
# 1. O MOTOR DE BUSCA (A lógica da Pessoa 4)
# ==========================================
def buscar_contexto(pergunta, limite=2):
    """Transforma a pergunta num vetor e procura os melhores trechos no PostgreSQL."""
    modelo = SentenceTransformer('all-MiniLM-L6-v2')
    vetor_pergunta = modelo.encode(pergunta).tolist()

    conexao = psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "postgres"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", "admin")
    )
    cursor = conexao.cursor()

    cursor.execute(
        """
        SELECT chunk_text 
        FROM document_chunks
        ORDER BY embedding <=> %s::vector
        LIMIT %s;
        """,
        (str(vetor_pergunta), limite)
    )
    
    resultados = cursor.fetchall()
    conexao.close()
    
    contexto_unido = "\n\n".join([linha[0] for linha in resultados])
    return contexto_unido

# ==========================================
# 2. O AGENTE INTELIGENTE (Gemini - Nova API)
# ==========================================
def responder_com_rag(pergunta):
    print("🔍 1. A pesquisar na base de dados pelos artigos mais relevantes...")
    contexto_recuperado = buscar_contexto(pergunta)
    
    if not contexto_recuperado.strip():
        return "Não encontrei informação na base de dados para responder."

    print("🧠 2. A enviar o contexto para o Cérebro (Google Gemini)...")
    
    # Inicializar o cliente com a nova biblioteca
    cliente = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    # O "Prompt Engineering" Mestre
    prompt_sistema = f"""
    És um assistente de pesquisa académica rigoroso. 
    Vais receber uma Pergunta e um Contexto científico extraído de artigos.
    
    REGRA 1: Responde APENAS com base na informação fornecida no Contexto.
    REGRA 2: Se a resposta não estiver no Contexto, diz "Não tenho dados suficientes nos artigos recolhidos".
    REGRA 3: Não inventes nem adiciones conhecimento externo (Zero Alucinação).
    
    CONTEXTO:
    {contexto_recuperado}
    """

    # Chamada à API usando o novo padrão de configuração
    resposta = cliente.models.generate_content(
        model='gemini-2.5-flash', # <-- ATUALIZADO PARA O NOVO MODELO
        contents=pergunta,
        config=types.GenerateContentConfig(
            system_instruction=prompt_sistema,
            temperature=0.1
        )
    )
    
    return resposta.text

# ==========================================
# 3. O TESTE FINAL
# ==========================================
if __name__ == "__main__":
    pergunta_teste = "Which metrics are used to evaluate Large Language Models?"
    
    print("=" * 60)
    print(f"👤 PERGUNTA DO UTILIZADOR: {pergunta_teste}")
    print("=" * 60)
    
    resposta_final = responder_com_rag(pergunta_teste)
    
    print("\n🤖 RESPOSTA DO AGENTE RAG:")
    print("-" * 60)
    print(resposta_final)
    print("-" * 60)