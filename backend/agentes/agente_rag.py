import os
import psycopg2
from dotenv import load_dotenv, find_dotenv
from backend.app.ai_config import (
    TASK_RAG,
    get_embedding_config,
    get_generation_config,
    get_reranking_config,
)
from backend.app.ai_service import generate_content, generate_embedding
from backend.app.database import log_interacao_agente, resolver_project_id
from backend.app.rag_citations import (
    RESPOSTA_SEM_CONTEXTO,
    formatar_citacao,
    validar_citacoes_rag,
)
from backend.app.reranking import reranquear_candidatos

# ==========================================
# CONFIGURAÇÃO DE AMBIENTE E MODELOS
# ==========================================
load_dotenv(find_dotenv())

RERANK_SCORE_RECONSIDERACAO = 60.0


def _resposta_recusada(texto):
    return RESPOSTA_SEM_CONTEXTO.lower() in str(texto or "").lower()


def _motivo_reavaliacao_recusa(evidencias):
    """Reavalia somente quando há sinal de suporte ou fallback sem score da IA."""
    if not evidencias:
        return None
    scores = [
        float(item["rerank_score"])
        for item in evidencias
        if item.get("rerank_score") is not None
    ]
    if scores and max(scores) >= RERANK_SCORE_RECONSIDERACAO:
        return "high_rerank_score"
    if not scores:
        return "unscored_ranking"
    return None

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
def _buscar_contexto_hibrido_detalhado(pergunta, project_id=None, limite=3):
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
               (pc.metadata_jsonb->>'page_start')::INTEGER AS page_number,
               RANK() OVER (ORDER BY em.embedding <=> %s::vector) AS vector_rank
        FROM embeddings_metadata em
        JOIN paper_chunks pc ON em.chunk_id = pc.id
        JOIN deduplicated_papers dp ON dp.id = pc.paper_id
        WHERE dp.project_id = %s
          AND em.model_name = %s
          AND em.dimensions = %s
          AND pc.metadata_jsonb->>'source_type' = 'pdf'
          AND pc.metadata_jsonb ? 'page_start'
        ORDER BY em.embedding <=> %s::vector
        LIMIT 20
    ),
    keyword_search AS (
        SELECT pc.id, pc.paper_id, pc.chunk_text,
               (pc.metadata_jsonb->>'page_start')::INTEGER AS page_number,
               RANK() OVER (ORDER BY ts_rank_cd(to_tsvector('english', pc.chunk_text), plainto_tsquery('english', %s)) DESC) AS keyword_rank
        FROM paper_chunks pc
        JOIN deduplicated_papers dp ON dp.id = pc.paper_id
        WHERE dp.project_id = %s
          AND pc.metadata_jsonb->>'source_type' = 'pdf'
          AND pc.metadata_jsonb ? 'page_start'
          AND to_tsvector('english', pc.chunk_text) @@ plainto_tsquery('english', %s)
        ORDER BY ts_rank_cd(to_tsvector('english', pc.chunk_text), plainto_tsquery('english', %s)) DESC
        LIMIT 20
    )
    SELECT
        COALESCE(v.id, k.id) AS chunk_id,
        COALESCE(v.paper_id, k.paper_id) AS paper_id,
        dp.title AS paper_title,
        COALESCE(v.chunk_text, k.chunk_text) AS text,
        COALESCE(v.page_number, k.page_number) AS page_number,
        COALESCE(1.0 / (60 + v.vector_rank), 0.0) + COALESCE(1.0 / (60 + k.keyword_rank), 0.0) AS rrf_score
    FROM vector_search v
    FULL OUTER JOIN keyword_search k ON v.id = k.id
    JOIN deduplicated_papers dp ON dp.id = COALESCE(v.paper_id, k.paper_id)
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
    
    return [
        {
            "candidate_id": f"c{indice}",
            "chunk_id": str(chunk_id),
            "paper_id": str(paper_id),
            "paper_title": paper_title,
            "text": texto,
            "page_number": int(page_number),
            "rrf_score": float(score),
            "original_rank": indice,
        }
        for indice, (chunk_id, paper_id, paper_title, texto, page_number, score)
        in enumerate(resultados, 1)
    ]


def buscar_contexto_hibrido(pergunta, project_id=None, limite=3):
    """Mantém a interface histórica: lista de (paper_id, texto, score RRF)."""
    resultados = _buscar_contexto_hibrido_detalhado(pergunta, project_id, limite)
    return [
        (item["paper_id"], item["text"], item["rrf_score"])
        for item in resultados
    ]


def buscar_contexto_reranqueado(pergunta, project_id=None):
    """Recupera candidatos pelo RRF e aplica o reranking configurado."""
    project_id = resolver_project_id(project_id)
    config = get_reranking_config()
    candidatos = _buscar_contexto_hibrido_detalhado(
        pergunta,
        project_id,
        limite=int(config.candidate_limit or 12),
    )
    if not candidatos:
        return [], {
            "status": "no_candidates",
            "initial_ranking": [],
            "reranked_ranking": [],
            "final_ranking": [],
            "error": None,
            "configuration": config.metadata(),
        }
    return reranquear_candidatos(pergunta, candidatos, project_id, config=config)

# ==========================================
# 2. O AGENTE INTELIGENTE (Orquestrador RAG)
# ==========================================
def responder_com_rag(pergunta, project_id=None, return_details=False):
    project_id = resolver_project_id(project_id)
    print("\n🔍 INÍCIO DA RECUPERAÇÃO DE EVIDÊNCIAS")
    evidencias, trace_reranking = buscar_contexto_reranqueado(
        pergunta,
        project_id=project_id,
    )
    
    if not evidencias:
        resposta_sem_contexto = f"{RESPOSTA_SEM_CONTEXTO} para responder."
        generation_trace = {
            "attempts": 0,
            "initial_refused": True,
            "final_refused": True,
            "refusal_reconsidered": False,
            "refusal_recovered": False,
            "reconsideration_reason": None,
            "reconsideration_error": None,
        }
        log_interacao_agente(
            project_id,
            "rag_agent",
            {"question": pergunta},
            {
                "answer": resposta_sem_contexto,
                "supporting_evidence": [],
                "generation": generation_trace,
            },
            get_generation_config(TASK_RAG).metadata(),
        )
        if return_details:
            return {
                "answer": resposta_sem_contexto,
                "reranking": trace_reranking,
                "evidence": [],
                "generation": generation_trace,
                "citation_validation": {
                    "valid_citations": [],
                    "invalid_citations_removed": [],
                    "internal_references_disambiguated": [],
                    "source_citations_appended": [],
                },
            }
        return resposta_sem_contexto

    contexto_formatado = ""
    print("\n📑 EVIDÊNCIAS SELECIONADAS APÓS RERANKING:")
    for evidencia in evidencias:
        paper_id = evidencia["paper_id"]
        paper_title = evidencia.get("paper_title") or "Título não informado"
        texto_chunk = evidencia["text"]
        score = evidencia["rrf_score"]
        pagina = evidencia["page_number"]
        score_reranking = evidencia.get("rerank_score")
        paper_id_texto = str(paper_id)
        score_exibido = f"{score_reranking:.1f}" if score_reranking is not None else "fallback RRF"
        print(
            f" -> Artigo ID: {paper_id_texto[:8]}... | "
            f"Página: {pagina} | RRF: {score:.4f} | Reranking: {score_exibido}"
        )
        contexto_formatado += (
            f"\n[FONTE RASTREÁVEL: {formatar_citacao(paper_id, pagina)} | "
            f"Artigo: {paper_title} | "
            f"Score RRF: {score:.4f} | Score reranking: {score_exibido}]"
            f"\nTrecho: {texto_chunk}\n"
        )

    print("\n🧠 A gerar síntese com IA baseada EXCLUSIVAMENTE no contexto...")
    
    prompt_sistema = f"""
    És um assistente de pesquisa académica rigoroso focado em Revisões Sistemáticas. 
    Vais receber uma Pergunta e um Contexto científico extraído de artigos através de busca híbrida.
    
    REGRA 1: Responde APENAS com base na informação fornecida no Contexto.
    REGRA 2: Se a resposta não estiver contida explicitamente no Contexto, diz estritamente "Não tenho dados suficientes nos artigos recolhidos".
    REGRA 3: Não inventes nem adiciones conhecimento externo (Zero Alucinação).
    REGRA 4: Toda afirmação factual deve terminar com uma ou mais citações no formato exato [paper_id, p. página], copiadas das FONTES RASTREÁVEIS.
    REGRA 5: Não use números bibliográficos internos como [5] ou [36] como fonte da resposta. Se precisar mencioná-los, escreva "referência 5 citada pelo artigo" e acrescente a fonte rastreável com UUID e página.
    REGRA 6: Nunca invente um UUID ou uma página e nunca cite uma fonte que não esteja no Contexto.
    
    CONTEXTO CIENTÍFICO RECUPERADO:
    {contexto_formatado}
    """

    resposta = generate_content(
        TASK_RAG,
        contents=pergunta,
        system_instruction=prompt_sistema,
    )

    resposta_inicial = resposta.text
    resposta_original = resposta_inicial
    recusou_inicialmente = _resposta_recusada(resposta_inicial)
    motivo_reavaliacao = (
        _motivo_reavaliacao_recusa(evidencias) if recusou_inicialmente else None
    )
    erro_reavaliacao = None
    tentativas_geracao = 1
    if motivo_reavaliacao:
        prompt_reavaliacao = f"""
        {prompt_sistema}

        REAVALIAÇÃO CONSERVADORA:
        Uma primeira leitura concluiu que não havia dados suficientes, mas a recuperação
        selecionou evidências potencialmente relevantes. Releia cuidadosamente os trechos.
        Se houver suporte explícito, responda à pergunta usando somente esse suporte e as
        citações rastreáveis fornecidas. Se o suporte continuar insuficiente, mantenha
        estritamente a frase de recusa definida na REGRA 2. Não complete lacunas por inferência.
        """
        try:
            resposta_reavaliada = generate_content(
                TASK_RAG,
                contents=pergunta,
                system_instruction=prompt_reavaliacao,
            )
            resposta_original = resposta_reavaliada.text
            tentativas_geracao += 1
        except Exception as excecao:
            erro_reavaliacao = (
                f"{excecao.__class__.__name__}: reavaliação indisponível; "
                "a recusa inicial foi preservada."
            )

    generation_trace = {
        "attempts": tentativas_geracao,
        "initial_refused": recusou_inicialmente,
        "final_refused": _resposta_recusada(resposta_original),
        "refusal_reconsidered": bool(motivo_reavaliacao),
        "refusal_recovered": (
            recusou_inicialmente and not _resposta_recusada(resposta_original)
        ),
        "reconsideration_reason": motivo_reavaliacao,
        "reconsideration_error": erro_reavaliacao,
    }
    resposta_texto, validacao_citacoes = validar_citacoes_rag(
        resposta_original,
        evidencias,
    )
    log_interacao_agente(
        project_id,
        "rag_agent",
        {"question": pergunta},
        {
            "answer": resposta_texto,
            "raw_answer": resposta_original,
            "initial_raw_answer": resposta_inicial,
            "supporting_evidence": [
                {
                    "paper_id": str(evidencia["paper_id"]),
                    "paper_title": evidencia.get("paper_title"),
                    "chunk_id": str(evidencia["chunk_id"]),
                    "page_number": int(evidencia["page_number"]),
                    "snippet": evidencia["text"],
                    "rrf_score": float(evidencia["rrf_score"]),
                    "original_rank": int(evidencia["original_rank"]),
                    "rerank_rank": int(evidencia["rerank_rank"]),
                    "model_rank": evidencia.get("model_rank"),
                    "rerank_score": evidencia.get("rerank_score"),
                    "fusion_score": evidencia.get("fusion_score"),
                    "rerank_reason": evidencia.get("rerank_reason"),
                }
                for evidencia in evidencias
            ],
            "reranking_status": trace_reranking["status"],
            "generation": generation_trace,
            "citation_validation": validacao_citacoes,
        },
        get_generation_config(TASK_RAG).metadata(),
    )
    if return_details:
        return {
            "answer": resposta_texto,
            "reranking": trace_reranking,
            "evidence": evidencias,
            "generation": generation_trace,
            "citation_validation": validacao_citacoes,
        }
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
