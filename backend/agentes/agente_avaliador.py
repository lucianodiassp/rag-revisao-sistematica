import os
import json
import time
import pandas as pd
from dotenv import load_dotenv, find_dotenv
from google import genai
from google.genai import types

# 1. Ajuste de Caminho para importar o nosso Agente RAG
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from backend.agentes.agente_rag import responder_com_rag, buscar_contexto_hibrido

# ==========================================
# CONFIGURAÇÃO DE AMBIENTE DO JUIZ
# ==========================================
load_dotenv(find_dotenv())
cliente_juiz = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
NOME_MODELO_JUIZ = 'gemini-2.5-flash'

CAMINHO_JSON_AUDITORIA = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../audit_questions.json'))

# ==========================================
# CONJUNTO DE TESTES (GROUND TRUTH / FALLBACK)
# ==========================================
PERGUNTAS_PADRAO = [
    "Quais as metodologias principais utilizadas para avaliação do modelo?",
    "Quais são as principais limitações apontadas pelos autores?",
    "Que tipos de algoritmos de Machine Learning são mencionados nos textos?",
    "Qual é a capital do Brasil?" # Pergunta rasteira fora do escopo para testar a recusa
]

def carregar_perguntas_auditoria():
    """Lê as perguntas do ficheiro JSON; se não existir, devolve as padrão."""
    if os.path.exists(CAMINHO_JSON_AUDITORIA):
        try:
            with open(CAMINHO_JSON_AUDITORIA, 'r', encoding='utf-8') as f:
                dados = json.load(f)
                perguntas = dados.get("questions", [])
                if perguntas: # Só usa se a lista não estiver vazia
                    return perguntas
        except Exception as e:
            print(f"⚠️ Erro ao ler {CAMINHO_JSON_AUDITORIA}: {e}. A usar fallback.")
            
    return PERGUNTAS_PADRAO

def obter_resposta_rag_segura(pergunta, tentativa=1):
    """Envolve a chamada do RAG num mecanismo de tolerância a falhas (Rate Limit)."""
    try:
        return responder_com_rag(pergunta)
    except Exception as e:
        if "429" in str(e) and tentativa <= 3:
            print(f"   ⏳ Rate limit do RAG atingido. A aguardar 45s (Tentativa {tentativa}/3)...")
            time.sleep(45)
            return obter_resposta_rag_segura(pergunta, tentativa + 1)
        print(f"❌ Erro fatal no RAG: {e}")
        return "Erro ao gerar resposta devido a falha na API."

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
        resposta_avaliacao = cliente_juiz.models.generate_content(
            model=NOME_MODELO_JUIZ,
            contents=prompt_juiz,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.0,
            ),
        )
        return json.loads(resposta_avaliacao.text)
    except Exception as e:
        if "429" in str(e) and tentativa <= 3:
            print(f"   ⏳ Rate limit do Juiz atingido. A aguardar 45s (Tentativa {tentativa}/3)...")
            time.sleep(45)
            return avaliar_resposta(pergunta, resposta_rag, contexto_recuperado, tentativa + 1)
        return {"fidelidade_score": 0, "relevancia_score": 0, "justificativa": f"Erro: {e}"}

def executar_auditoria():
    print("⚖️ A iniciar a Auditoria Quantitativa do Sistema RAG...\n")
    
    # --- NOVO: CARREGAR PERGUNTAS DINAMICAMENTE ---
    perguntas_ativas = carregar_perguntas_auditoria()
    resultados_auditoria = []
    
    for i, pergunta in enumerate(perguntas_ativas, 1):
        print(f"[{i}/{len(perguntas_ativas)}] Testando: '{pergunta}'")
        
        # 1. Pede ao motor RAG para buscar as evidências textuais puras (para o Juiz ler)
        evidencias_brutas = buscar_contexto_hibrido(pergunta, limite=3)
        contexto_texto = " ".join([chunk for _, chunk, _ in evidencias_brutas]) if evidencias_brutas else "Nenhum contexto encontrado."
        
        # 2. Pede ao RAG para gerar a resposta oficial final
        resposta_gerada = obter_resposta_rag_segura(pergunta)
        
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
        
        # Pausa generosa para não estourar os limites gratuitos da Google
        time.sleep(25) 
        
    df_resultados = pd.DataFrame(resultados_auditoria)
    caminho_csv = os.path.join(os.path.dirname(__file__), '..', '..', 'metricas_rag_auditoria.csv')
    df_resultados.to_csv(caminho_csv, index=False, encoding='utf-8')
    
    print("=" * 60)
    print("🎉 AUDITORIA CONCLUÍDA COM SUCESSO!")
    print(f"📈 Média de Fidelidade Conservadora: {df_resultados['Fidelidade (0-10)'].mean():.1f}/10")
    print(f"🎯 Média de Relevância Conservadora: {df_resultados['Relevância (0-10)'].mean():.1f}/10")
    print(f"💾 Relatório guardado em: metricas_rag_auditoria.csv")
    print("=" * 60)

if __name__ == "__main__":
    executar_auditoria()