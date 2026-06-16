import os
import psycopg2
from dotenv import load_dotenv, find_dotenv
from google import genai
from google.genai import types

# ==========================================
# CONFIGURAÇÃO DE AMBIENTE E MODELOS
# ==========================================
load_dotenv(find_dotenv())

# Inicializar o cliente com a API oficial da Google
cliente = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
NOME_MODELO_LLM = 'gemini-2.5-flash'
NOME_MODELO_EMBEDDING = 'gemini-embedding-001'
DIMENSOES = 768

def get_conexao():
    """Estabelece a conexão estritamente via variáveis de ambiente."""
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "rag_systematic_review"),
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"]
    )

# ==========================================
# 1. MOTOR DE BUSCA HÍBRIDA (BM25 + VETORES RRF)
# ==========================================
def buscar_contexto_hibrido(pergunta, limite=3):
    """
    Combina a busca semântica (pgvector) com a busca por palavras-chave (Full-Text Search)
    utilizando a fusão matemática RRF para mitigar falhas de recall.
    """
    print("   [1/2] A converter pergunta em matemática...")
    # Transforma a pergunta num vetor usando o Gemini com compressão Matryoshka (768d)
    resposta_emb = cliente.models.embed_content(
        model=NOME_MODELO_EMBEDDING,
        contents=pergunta,
        config=types.EmbedContentConfig(output_dimensionality=DIMENSOES)
    )
    vetor_pergunta = resposta_emb.embeddings[0].values

    conexao = get_conexao()
    cursor = conexao.cursor()

    print("   [2/2] A executar Busca Híbrida (Vetor + BM25) no PostgreSQL...")
    # A Super Query Híbrida adaptada para as novas tabelas
    query = """
    WITH vector_search AS (
        SELECT pc.id, pc.paper_id, pc.chunk_text,
               RANK() OVER (ORDER BY em.embedding <=> %s::vector) AS vector_rank
        FROM embeddings_metadata em
        JOIN paper_chunks pc ON em.chunk_id = pc.id
        ORDER BY em.embedding <=> %s::vector
        LIMIT 20
    ),
    keyword_search AS (
        SELECT id, paper_id, chunk_text,
               RANK() OVER (ORDER BY ts_rank_cd(to_tsvector('english', chunk_text), plainto_tsquery('english', %s)) DESC) AS keyword_rank
        FROM paper_chunks
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
        str(vetor_pergunta), str(vetor_pergunta),  # Parâmetros vetoriais
        pergunta, pergunta, pergunta,              # Parâmetros de texto
        limite                                     # Limite de RRF
    ))
    
    resultados = cursor.fetchall()
    cursor.close()
    conexao.close()
    
    return resultados

# ==========================================
# 2. O AGENTE INTELIGENTE (Orquestrador RAG)
# ==========================================
def responder_com_rag(pergunta):
    print("\n🔍 INÍCIO DA RECUPERAÇÃO DE EVIDÊNCIAS")
    evidencias = buscar_contexto_hibrido(pergunta, limite=4) # Aumentado ligeiramente para mais contexto
    
    if not evidencias:
        return "Não tenho dados suficientes nos artigos recolhidos para responder."

    contexto_formatado = ""
    print("\n📑 EVIDÊNCIAS RECUPERADAS (TOP SCORE RRF):")
    for paper_id, texto_chunk, score in evidencias:
        print(f" -> Artigo ID: {paper_id[:8]}... | Score Híbrido: {score:.4f}")
        contexto_formatado += f"\n[Artigo ID: {paper_id} | Score RRF: {score:.4f}]\nTrecho: {texto_chunk}\n"

    print("\n🧠 A gerar síntese com IA baseada EXCLUSIVAMENTE no contexto...")
    
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

    resposta = cliente.models.generate_content(
        model=NOME_MODELO_LLM,
        contents=pergunta,
        config=types.GenerateContentConfig(
            system_instruction=prompt_sistema,
            temperature=0.1
        )
    )
    
    return resposta.text

# ==========================================
# 3. O TESTE FINAL LOCAL
# ==========================================
if __name__ == "__main__":
    pergunta_teste = "Como a inteligência artificial é utilizada na classificação de eletrocardiogramas (ECG) ou exames de imagem?"
    
    print("=" * 70)
    print(f"PERGUNTA: {pergunta_teste}")
    print("=" * 70)
    
    resposta_final = responder_com_rag(pergunta_teste)
    
    print("\n======================================================================")
    print("🤖 RESPOSTA DO AGENTE RAG AVANÇADO (HÍBRIDO):")
    print("======================================================================")
    print(resposta_final)