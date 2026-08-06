import os
import psycopg2
from dotenv import load_dotenv, find_dotenv
from backend.app.ai_config import (
    TASK_RAG,
    get_embedding_config,
    get_generation_config,
)
from backend.app.ai_service import generate_content, generate_embedding
from backend.app.database import log_interacao_agente, resolver_project_id

# ==========================================
# CONFIGURAÇÃO DE AMBIENTE E MODELOS
# ==========================================
load_dotenv(find_dotenv())

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
def buscar_contexto_hibrido(pergunta, project_id=None, limite=3):
    """
    Combina a busca semântica (pgvector) com a busca por palavras-chave (Full-Text Search)
    utilizando a fusão matemática RRF para mitigar falhas de recall.
    """
    project_id = resolver_project_id(project_id)
    print("   [1/2] A converter pergunta em matemática...")
    # Transforma a pergunta num vetor usando o Gemini com compressão Matryoshka (768d)
    embedding_config = get_embedding_config()
    vetor_pergunta = generate_embedding(pergunta)

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
        JOIN deduplicated_papers dp ON dp.id = pc.paper_id
        WHERE dp.project_id = %s
          AND em.model_name = %s
          AND em.dimensions = %s
        ORDER BY em.embedding <=> %s::vector
        LIMIT 20
    ),
    keyword_search AS (
        SELECT pc.id, pc.paper_id, pc.chunk_text,
               RANK() OVER (ORDER BY ts_rank_cd(to_tsvector('english', pc.chunk_text), plainto_tsquery('english', %s)) DESC) AS keyword_rank
        FROM paper_chunks pc
        JOIN deduplicated_papers dp ON dp.id = pc.paper_id
        WHERE dp.project_id = %s
          AND to_tsvector('english', pc.chunk_text) @@ plainto_tsquery('english', %s)
        ORDER BY ts_rank_cd(to_tsvector('english', pc.chunk_text), plainto_tsquery('english', %s)) DESC
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
        str(vetor_pergunta), project_id,
        embedding_config.model, embedding_config.dimensions, str(vetor_pergunta),
        pergunta, project_id, pergunta, pergunta,
        limite                                     # Limite de RRF
    ))
    
    resultados = cursor.fetchall()
    cursor.close()
    conexao.close()
    
    return resultados

# ==========================================
# 2. O AGENTE INTELIGENTE (Orquestrador RAG)
# ==========================================
def responder_com_rag(pergunta, project_id=None):
    project_id = resolver_project_id(project_id)
    print("\n🔍 INÍCIO DA RECUPERAÇÃO DE EVIDÊNCIAS")
    evidencias = buscar_contexto_hibrido(pergunta, project_id=project_id, limite=4)
    
    if not evidencias:
        resposta_sem_contexto = "Não tenho dados suficientes nos artigos recolhidos para responder."
        log_interacao_agente(
            project_id,
            "rag_agent",
            {"question": pergunta},
            {"answer": resposta_sem_contexto, "supporting_evidence": []},
            get_generation_config(TASK_RAG).metadata(),
        )
        return resposta_sem_contexto

    contexto_formatado = ""
    print("\n📑 EVIDÊNCIAS RECUPERADAS (TOP SCORE RRF):")
    for paper_id, texto_chunk, score in evidencias:
        paper_id_texto = str(paper_id)
        print(f" -> Artigo ID: {paper_id_texto[:8]}... | Score Híbrido: {score:.4f}")
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

    resposta = generate_content(
        TASK_RAG,
        contents=pergunta,
        system_instruction=prompt_sistema,
    )
    
    resposta_texto = resposta.text
    log_interacao_agente(
        project_id,
        "rag_agent",
        {"question": pergunta},
        {
            "answer": resposta_texto,
            "supporting_evidence": [
                {
                    "paper_id": str(paper_id),
                    "snippet": texto_chunk,
                    "retrieval_score": float(score),
                }
                for paper_id, texto_chunk, score in evidencias
            ],
        },
        get_generation_config(TASK_RAG).metadata(),
    )
    return resposta_texto

# ==========================================
# 3. O TESTE FINAL LOCAL
# ==========================================
if __name__ == "__main__":
    # Pergunta genérica focada na estrutura acadêmica (agnóstica ao tema da pesquisa)
    pergunta_teste = "Quais são os principais desafios, limitações ou lacunas de pesquisa apontados pelos autores nestes artigos?"
    
    print("=" * 70)
    print(f"PERGUNTA: {pergunta_teste}")
    print("=" * 70)
    
    resposta_final = responder_com_rag(pergunta_teste, resolver_project_id())
    
    print("\n======================================================================")
    print("🤖 RESPOSTA DO AGENTE RAG AVANÇADO (HÍBRIDO):")
    print("======================================================================")
    print(resposta_final)
