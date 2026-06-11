import os
import json
import psycopg2
import uuid
import time
from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.genai.errors import APIError

# ==========================================
# CONFIGURAÇÃO DE AMBIENTE E CONEXÃO
# ==========================================
load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
NOME_MODELO = "gemini-2.5-flash"

def get_conexao():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "rag_systematic_review"),
        user=os.getenv("DB_USER", "rag_user"),
        password=os.getenv("DB_PASSWORD", "rag_password")
    )

def criar_tabela_se_nao_existir():
    """Garante que a tabela de evidências existe (Requisito da Pessoa 3)."""
    conexao = get_conexao()
    cursor = conexao.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS extracted_evidence (
            id UUID PRIMARY KEY,
            paper_id VARCHAR(50) UNIQUE,
            extraction_jsonb JSONB,
            human_review_status VARCHAR(50) DEFAULT 'pending',
            extracted_at TIMESTAMP DEFAULT NOW()
        );
    """)
    conexao.commit()
    conexao.close()

def buscar_artigos_aprovados():
    """Busca apenas os artigos marcados como 'Incluir' pelo humano que ainda não foram extraídos."""
    conexao = get_conexao()
    cursor = conexao.cursor()
    cursor.execute("""
        SELECT p.id, p.title, p.abstract 
        FROM deduplicated_papers p
        JOIN screening_decisions s ON p.id = s.paper_id
        WHERE s.human_decision = 'Incluir'
          AND p.id NOT IN (SELECT paper_id FROM extracted_evidence);
    """)
    artigos = cursor.fetchall()
    conexao.close()
    return artigos

def extrair_evidencias_com_ia(titulo, resumo, tentativa=1):
    """Lê o artigo e extrai as informações estruturadas em formato JSON estrito."""
    prompt = f"""
    Você é um assistente de pesquisa científica. Sua tarefa é ler o título e resumo do artigo abaixo
    e extrair informações específicas para uma Revisão Sistemática (Matriz de Evidências).

    [DADOS DO ARTIGO]
    Título: {titulo}
    Resumo: {resumo}

    [REQUISITO DE SAÍDA - OBRIGATÓRIO JSON]
    Você deve extrair os dados e responder EXCLUSIVAMENTE neste formato JSON.
    Se uma informação não estiver explícita no texto, preencha com "Não reportado".
    {{
        "objective": "Qual o principal objetivo ou problema de pesquisa do artigo?",
        "method": "Qual a abordagem, arquitetura ou método proposto? (ex: CNN, RAG, Survey)",
        "dataset": "Qual a base de dados ou amostra utilizada? (ex: 50 pacientes, MIMIC-III, PubMed)",
        "metrics": ["Métrica 1", "Métrica 2"],
        "main_results": "Qual foi o principal resultado alcançado de forma resumida?",
        "limitations": ["Limitação 1", "Limitação 2"]
    }}
    """
    
    try:
        resposta = client.models.generate_content(
            model=NOME_MODELO,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.0, # Zero alucinação
            ),
        )
        return json.loads(resposta.text)
    
    except APIError as e:
        if e.code == 429 and tentativa <= 3:
            print(f"   ⏳ Cota da API atingida (429). A aguardar 60s antes de tentar novamente...")
            time.sleep(60)
            return extrair_evidencias_com_ia(titulo, resumo, tentativa + 1)
        print(f"❌ Falha na API: {e}")
        return None
    except Exception as e:
        print(f"❌ Erro estrutural: {e}")
        return None

def executar_pipeline_extracao():
    criar_tabela_se_nao_existir()
    
    print("🔍 A buscar artigos marcados como 'Incluir' pelo humano...")
    artigos = buscar_artigos_aprovados()
    
    if not artigos:
        print("🎉 Não há artigos aprovados pendentes de extração de evidências!")
        return

    print(f"📊 Encontrados {len(artigos)} artigos para montar a Matriz de Evidências.\n")
    
    conexao = get_conexao()
    cursor = conexao.cursor()

    for paper_id, titulo, abstract in artigos:
        print(f"🧠 IA a extrair dados de: '{titulo[:50]}...'")
        
        dados_extraidos = extrair_evidencias_com_ia(titulo, abstract)
        
        if dados_extraidos:
            extracao_id = str(uuid.uuid4())
            
            # Grava a matriz na tabela oficial de evidências
            cursor.execute("""
                INSERT INTO extracted_evidence (id, paper_id, extraction_jsonb, human_review_status)
                VALUES (%s, %s, %s, 'pending')
            """, (extracao_id, paper_id, json.dumps(dados_extraidos)))
            
            # Registo de auditoria (Log do Agente)
            cursor.execute("""
                INSERT INTO agent_interactions (id, agent_name, input_jsonb, output_jsonb, model_jsonb)
                VALUES (%s, %s, %s, %s, %s)
            """, (
                str(uuid.uuid4()),
                "extraction_agent",
                json.dumps({"paper_id": paper_id, "task": "evidence_extraction"}),
                json.dumps(dados_extraidos),
                json.dumps({"provider": "Google", "model_name": NOME_MODELO})
            ))
            
            conexao.commit()
            print(f"   ✅ Dados estruturados com sucesso!")
            
            # Pausa proativa para respeitar o Rate Limit do Free Tier
            time.sleep(15) 
            
    cursor.close()
    conexao.close()
    print("\n🎉 Matriz de Evidências construída com sucesso! Os dados estão salvos em JSONB.")

if __name__ == "__main__":
    executar_pipeline_extracao()