import os
import json
import psycopg2
import uuid
import time # NOVO: Biblioteca para pausar a execução
from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.genai.errors import APIError # NOVO: Para capturar o erro específico

# ==========================================
# CONFIGURAÇÃO DE AMBIENTE E CONEXÃO
# ==========================================
load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
NOME_MODELO = "gemini-2.5-flash" 

def get_conexao():
    """Estabelece a conexão estritamente via variáveis de ambiente."""
    # Se DB_USER ou DB_PASSWORD não existirem no .env, o sistema falha com segurança
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"), # Host e Port podem ter fallback pois não são sensíveis
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "rag_systematic_review"),
        user=os.environ["DB_USER"],         # Usa os.environ para forçar erro se não existir
        password=os.environ["DB_PASSWORD"]  # Força a leitura exclusiva do .env
    )

def buscar_artigos_sem_analise():
    conexao = get_conexao()
    cursor = conexao.cursor()
    cursor.execute("""
        SELECT id, title, abstract 
        FROM deduplicated_papers 
        WHERE id NOT IN (SELECT paper_id FROM screening_decisions)
          AND abstract IS NOT NULL 
          AND abstract != ''
          AND abstract NOT IN (
              'Abstract indisponível.',
              'Abstract extraído do índice (simplificado para este exemplo).',
              'Abstract via PubMed E-Summary (Requer E-Fetch para texto completo).'
          );
    """)
    artigos = cursor.fetchall()
    conexao.close()
    return artigos

def triar_artigo_com_ia(titulo, resumo, tentativa=1):
    """Submete o artigo ao Gemini com tratamento de limite de cota (Rate Limit)."""
    prompt = f"""
    Você é um agente especialista em triagem de artigos científicos para uma Revisão Sistemática.
    Sua tarefa é avaliar o artigo abaixo com base estrita nos critérios fornecidos.

    [CRITÉRIOS DE INCLUSÃO]
    - O artigo deve abordar explicitamente abordagens de inteligência artificial, engenharia de software ou processamento de linguagem natural aplicados a revisões de literatura ou medicina.
    - Apresenta algum método computacional, experimental ou empírico claro.

    [CRITÉRIOS DE EXCLUSÃO]
    - Editoriais, revisões simples de literatura sem método computacional de suporte, opiniões ou comentários.
    - Artigos sem qualquer relação com automação, sistemas computacionais ou inteligência artificial.

    [DADOS DO ARTIGO]
    Título: {titulo}
    Resumo: {resumo}

    [REQUISITO DE SAÍDA]
    Você deve responder OBRIGATORIAMENTE no formato JSON abaixo, sem qualquer texto adicional antes ou depois:
    {{
        "suggested_decision": "Incluir" ou "Excluir" ou "Talvez",
        "confidence": 0.0 a 1.0,
        "justification": "Uma frase clara explicando qual critério foi ou não atendido baseado no resumo."
    }}
    """
    
    try:
        resposta = client.models.generate_content(
            model=NOME_MODELO,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.0,
            ),
        )
        return json.loads(resposta.text)
    
    except APIError as e:
        # Verifica se o erro é o código 429 (Resource Exhausted / Quota Exceeded)
        if e.code == 429 and tentativa <= 3:
            tempo_espera = 60 # Esperamos 1 minuto para a cota da Google "arrefecer"
            print(f"   ⏳ Limite atingido (429). A aguardar {tempo_espera}s antes da tentativa {tentativa + 1}/3...")
            time.sleep(tempo_espera)
            return triar_artigo_com_ia(titulo, resumo, tentativa + 1)
        else:
            print(f"❌ Falha persistente na API: {e}")
            return None
    except Exception as e:
        print(f"❌ Erro estrutural ao processar o artigo: {e}")
        return None

def executar_pipeline_triagem():
    print("🔍 A buscar artigos pendentes de análise pela IA...")
    artigos = buscar_artigos_sem_analise()
    
    if not artigos:
        print("🎉 Todos os artigos válidos já possuem análise da IA!")
        return

    print(f"📊 Encontrados {len(artigos)} artigos para triagem automática.\n")
    
    conexao = get_conexao()
    cursor = conexao.cursor()

    for paper_id, titulo, abstract in artigos:
        print(f"🧠 IA a analisar: '{titulo[:50]}...'")
        
        resultado_ia = triar_artigo_com_ia(titulo, abstract)
        
        if resultado_ia:
            decisao_id = str(uuid.uuid4())
            sugestao = resultado_ia.get("suggested_decision", "Talvez")
            justificativa_ia = resultado_ia.get("justification", "Sem justificativa fornecida.")
            
            rationale_dict = {
                "confidence": resultado_ia.get("confidence", 0.5),
                "justification": justificativa_ia,
                "agent_name": "screening_agent",
                "model_provider": "Google",
                "model_name": NOME_MODELO
            }
            
            cursor.execute("""
                INSERT INTO screening_decisions 
                (id, paper_id, suggested_decision, human_decision, rationale_jsonb, justification)
                VALUES (%s, %s, %s, NULL, %s, NULL)
            """, (decisao_id, paper_id, sugestao, json.dumps(rationale_dict)))
            
            cursor.execute("""
                INSERT INTO agent_interactions 
                (id, agent_name, input_jsonb, output_jsonb, model_jsonb)
                VALUES (%s, %s, %s, %s, %s)
            """, (
                str(uuid.uuid4()),
                "screening_agent",
                json.dumps({"paper_id": paper_id, "title": titulo}),
                json.dumps(resultado_ia),
                json.dumps({"provider": "Google", "model_name": NOME_MODELO})
            ))
            conexao.commit() # Commit iterativo para não perder o que já foi salvo
            print(f"   -> Veredicto IA: {sugestao} | Gravado com sucesso.")
            
            # Pausa proativa de 15 segundos entre cada artigo para evitar bater na cota de 5 req/min
            time.sleep(15) 
            
    cursor.close()
    conexao.close()
    print("\n🎉 Triagem automática concluída de forma auditável!")

if __name__ == "__main__":
    executar_pipeline_triagem()