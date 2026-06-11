import os
import psycopg2
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from google import genai
from google.genai import types

# ==========================================
# CONFIGURAÇÃO DE AMBIENTE E MODELOS
# ==========================================
# Carregar variáveis de ambiente (banco de dados e API Key)
load_dotenv()

# Inicializar o cliente com a nova biblioteca oficial da Google
cliente = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
NOME_MODELO_LLM = 'gemini-2.5-flash'

# Carregar o modelo de processamento de embeddings
modelo_vetorial = SentenceTransformer('all-MiniLM-L6-v2')

def get_conexao():
    """Estabelece a conexão com o PostgreSQL utilizando variáveis de ambiente e fallbacks seguros."""
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "rag_systematic_review"),
        user=os.getenv("DB_USER", "rag_user"),
        password=os.getenv("DB_PASSWORD", "rag_password")
    )

# ==========================================
# 1. MOTOR DE BUSCA HÍBRIDA (BM25 + VETORES)
# ==========================================
def buscar_contexto_hibrido(pergunta, limite=3):
    """
    Combina a busca semântica (pgvector) com a busca por palavras-chave (Full-Text Search)
    utilizando a fusão matemática RRF (Reciprocal Rank Fusion) para mitigar falhas de recall.
    """
    # Transforma a pergunta num vetor de 384 dimensões
    vetor_pergunta = modelo_vetorial.encode(pergunta).tolist()

    conexao = get_conexao()
    cursor = conexao.cursor()

    # A Super Query Híbrida (Combinação exata exigida na Secção 5)
    query = """
    WITH vector_search AS (
        SELECT id, paper_id, chunk_text,
               RANK() OVER (ORDER BY embedding <=> %s::vector) AS vector_rank
        FROM document_chunks
        ORDER BY embedding <=> %s::vector
        LIMIT 20
    ),
    keyword_search AS (
        SELECT id, paper_id, chunk_text,
               RANK() OVER (ORDER BY ts_rank_cd(to_tsvector('english', chunk_text), plainto_tsquery('english', %s)) DESC) AS keyword_rank
        FROM document_chunks
        WHERE to_tsvector('english', chunk_text) @@ plainto_tsquery('english', %s)
        ORDER BY ts_rank_cd(to_tsvector('english', chunk_text), plainto_tsquery('english', %s)) DESC
        LIMIT 20
    )
    SELECT
        COALESCE(v.paper_id, k.paper_id) AS paper_id,
        COALESCE(v.chunk_text, k.chunk_text) AS text,
        COALESCE(1.0 / (60 + v.vector_rank), 0.0) + COALESCE(1.0 / (60 + k.keyword_rank), 0.0) AS rrf_score
    FROM vector_search v
    FULL OUTER JOIN keyword_search k ON v.id = k.id
    ORDER BY rrf_score DESC
    LIMIT %s;
    """

    cursor.execute(query, (
        str(vetor_pergunta), str(vetor_pergunta),  # Parâmetros da busca vetorial
        pergunta, pergunta, pergunta,              # Parâmetros da busca por palavras-chave
        limite                                     # Limite final de chunks combinados
    ))
    
    resultados = cursor.fetchall()
    conexao.close()
    
    return resultados

# ==========================================
# 2. O AGENTE INTELIGENTE (Orquestrador RAG)
# ==========================================
def responder_com_rag(pergunta):
    print("🔍 1. A executar Busca Híbrida (Vetor + BM25) para capturar contexto e termos exatos...")
    evidencias = buscar_contexto_hibrido(pergunta, limite=3)
    
    if not evidencias:
        return "Não tenho dados suficientes nos artigos recolhidos para responder."

    # Formatar o contexto incluindo o Score Híbrido para fins de auditoria
    contexto_formatado = ""
    for paper_id, texto_chunk, score in evidencias:
        contexto_formatado += f"\n[Artigo ID: {paper_id} | Score RRF: {score:.4f}]\nTrecho: {texto_chunk}\n"

    print("🧠 2. A injetar o contexto estruturado no Cérebro (Google Gemini)...")
    
    # O "Prompt Engineering" Mestre com regras de Grounding rigorosas
    prompt_sistema = f"""
    És um assistente de pesquisa académica rigoroso focado em Revisões Sistemáticas. 
    Vais receber uma Pergunta e um Contexto científico extraído de artigos através de busca híbrida.
    
    REGRA 1: Responde APENAS com base na informação fornecida no Contexto.
    REGRA 2: Se a resposta não estiver contida explicitamente no Contexto, diz estritamente "Não tenho dados suficientes nos artigos recolhidos".
    REGRA 3: Não inventes nem adiciones conhecimento externo (Zero Alucinação).
    REGRA 4: Sempre que fizeres uma afirmação baseada num artigo, cite o ID do Artigo correspondente.
    
    CONTEXTO CIENTÍFICO RECUPERADO:
    {contexto_formatado}
    """

    # Chamada à API usando o novo padrão de configuração oficial
    resposta = cliente.models.generate_content(
        model=NOME_MODELO_LLM,
        contents=pergunta,
        config=types.GenerateContentConfig(
            system_instruction=prompt_sistema,
            temperature=0.1 # Temperatura baixa para garantir determinismo científico
        )
    )
    
    return resposta.text

# ==========================================
# 3. O TESTE FINAL LOCAL
# ==========================================
if __name__ == "__main__":
    pergunta_teste = "Which metrics are used to evaluate Large Language Models?"
    
    print("=" * 60)
    print(f"👤 PERGUNTA DO UTILIZADOR: {pergunta_teste}")
    print("=" * 60)
    
    resposta_final = responder_com_rag(pergunta_teste)
    
    print("\n🤖 RESPOSTA DO AGENTE RAG AVANÇADO (HÍBRIDO):")
    print("-" * 60)
    print(resposta_final)
    print("-" * 60)