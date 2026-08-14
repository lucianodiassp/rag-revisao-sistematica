import os
import json
import time
import pandas as pd
from backend.app.ai_config import TASK_EVALUATION, get_generation_config
from backend.app.ai_service import generate_content

# 1. Ajuste de Caminho para importar o nosso Agente RAG
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from backend.agentes.agente_rag import responder_com_rag
from backend.app.database import (
    log_interacao_agente,
    obter_projeto,
    resolver_project_id,
    salvar_execucao_avaliacao,
)

# ==========================================
# CONJUNTO DE TESTES (GROUND TRUTH / FALLBACK)
# ==========================================
PERGUNTAS_PADRAO = [
    "Quais as metodologias principais utilizadas para avaliação do modelo?",
    "Quais são as principais limitações apontadas pelos autores?",
    "Que tipos de algoritmos de Machine Learning são mencionados nos textos?",
    "Qual é a capital do Brasil?" # Pergunta rasteira fora do escopo para testar a recusa
]

def carregar_perguntas_auditoria(project_id):
    """Lê as perguntas de auditoria do protocolo versionado do projeto."""
    protocolo = obter_projeto(project_id).get("criteria_jsonb") or {}
    return protocolo.get("audit_questions") or PERGUNTAS_PADRAO

def obter_resposta_rag_segura(project_id, pergunta, tentativa=1):
    """Envolve a chamada do RAG num mecanismo de tolerância a falhas (Rate Limit)."""
    try:
        return responder_com_rag(pergunta, project_id, return_details=True)
    except Exception as e:
        if "429" in str(e) and tentativa <= 3:
            print(f"   ⏳ Rate limit do RAG atingido. A aguardar 45s (Tentativa {tentativa}/3)...")
            time.sleep(45)
            return obter_resposta_rag_segura(project_id, pergunta, tentativa + 1)
        print(f"❌ Erro fatal no RAG: {e}")
        return {
            "answer": "Erro ao gerar resposta devido a falha na API.",
            "evidence": [],
            "reranking": {"status": "error"},
        }

def avaliar_resposta(pergunta, resposta_rag, contexto_recuperado, tentativa=1):
    """O LLM atua como Juiz, avaliando a resposta gerada contra o contexto original."""
    prompt_juiz = f"""
    És um Juiz Académico rigoroso a avaliar um sistema de Inteligência Artificial.
    Vou fornecer-te uma Pergunta, o Contexto Científico que o sistema encontrou, e a Resposta que o sistema gerou.
    
    A tua tarefa é avaliar a Resposta atribuindo duas notas de 1 a 10 e justificando brevemente.
    
    [DADOS DA AVALIAÇÃO]
    Pergunta: {pergunta}
    Contexto Recuperado: {contexto_recuperado}
    Resposta do Sistema: {resposta_rag}
    
    [MÉTRICAS DE AVALIAÇÃO]
    1. Fidelidade (1-10): A resposta deriva EXCLUSIVAMENTE do Contexto? (Se admitiu não ter dados, é alta fidelidade).
    2. Relevância (1-10): A resposta responde diretamente à Pergunta? (Se recusou com razão, é alta relevância).
    
    REGRA DE PONTUAÇÃO (MUITO IMPORTANTE):
    - Seja conservador nas notas. Comprima os extremos para o centro.
    - O que seria um 10 perfeito, mapeie para 7.
    - O que seria um 1 péssimo, mapeie para 3.
    - Notas médias (5-6) permanecem inalteradas.
    
    Responde OBRIGATORIAMENTE no formato JSON:
    {{
        "fidelidade_score": 7,
        "relevancia_score": 5,
        "justificativa": "Justificativa resumida (máximo 1 frase)."
    }}
    """
    
    try:
        resposta_avaliacao = generate_content(
            TASK_EVALUATION,
            contents=prompt_juiz,
            response_mime_type="application/json",
        )
        return json.loads(resposta_avaliacao.text)
    except Exception as e:
        if "429" in str(e) and tentativa <= 3:
            print(f"   ⏳ Rate limit do Juiz atingido. A aguardar 45s (Tentativa {tentativa}/3)...")
            time.sleep(45)
            return avaliar_resposta(pergunta, resposta_rag, contexto_recuperado, tentativa + 1)
        return {"fidelidade_score": 0, "relevancia_score": 0, "justificativa": f"Erro: {e}"}

def executar_auditoria(project_id=None):
    project_id = resolver_project_id(project_id)
    print("⚖️ A iniciar a Auditoria Quantitativa do Sistema RAG...\n")
    
    # --- NOVO: CARREGAR PERGUNTAS DINAMICAMENTE ---
    perguntas_ativas = carregar_perguntas_auditoria(project_id)
    resultados_auditoria = []
    
    for i, pergunta in enumerate(perguntas_ativas, 1):
        print(f"[{i}/{len(perguntas_ativas)}] Testando: '{pergunta}'")
        
        # 1. Executa uma única recuperação e reutiliza exatamente as evidências
        # selecionadas tanto na resposta quanto na avaliação do Juiz.
        resultado_rag = obter_resposta_rag_segura(project_id, pergunta)
        evidencias_brutas = resultado_rag.get("evidence") or []
        contexto_texto = (
            " ".join(item["text"] for item in evidencias_brutas)
            if evidencias_brutas
            else "Nenhum contexto encontrado."
        )
        
        # 2. Usa a resposta produzida a partir desse mesmo ranking final.
        resposta_gerada = resultado_rag["answer"]
        
        print("   -> 👨‍⚖️ O Juiz a avaliar a precisão...")
        avaliacao = avaliar_resposta(pergunta, resposta_gerada, contexto_texto)
        
        fidelidade = avaliacao.get("fidelidade_score", 0)
        relevancia = avaliacao.get("relevancia_score", 0)
        
        print(f"   📊 Notas (Conservadoras) -> Fidelidade: {fidelidade}/10 | Relevância: {relevancia}/10\n")
        
        resultados_auditoria.append({
            "Pergunta": pergunta,
            "Fidelidade (0-10)": fidelidade,
            "Relevância (0-10)": relevancia,
            "Justificativa do Juiz": avaliacao.get("justificativa", "")
        })

        log_interacao_agente(
            project_id,
            "evaluation_judge",
            {"question": pergunta, "rag_answer": resposta_gerada, "context": contexto_texto},
            avaliacao,
            get_generation_config(TASK_EVALUATION).metadata(),
        )
        
        # Pausa generosa para não estourar os limites gratuitos da Google
        time.sleep(25) 
        
    df_resultados = pd.DataFrame(resultados_auditoria)
    metricas = {
        "results": resultados_auditoria,
        "mean_faithfulness": float(df_resultados['Fidelidade (0-10)'].mean()),
        "mean_relevance": float(df_resultados['Relevância (0-10)'].mean()),
    }
    salvar_execucao_avaliacao(
        project_id,
        "rag_llm_judge",
        metricas,
        {
            "questions": perguntas_ativas,
            "judge_model": get_generation_config(TASK_EVALUATION).model,
            "retrieval_pipeline": "hybrid_rrf_plus_reranking",
        },
    )
    
    print("=" * 60)
    print("🎉 AUDITORIA CONCLUÍDA COM SUCESSO!")
    print(f"📈 Média de Fidelidade Conservadora: {df_resultados['Fidelidade (0-10)'].mean():.1f}/10")
    print(f"🎯 Média de Relevância Conservadora: {df_resultados['Relevância (0-10)'].mean():.1f}/10")
    print("💾 Resultado guardado em evaluation_runs para o projeto ativo.")
    print("=" * 60)
    return df_resultados

if __name__ == "__main__":
    executar_auditoria(resolver_project_id())
