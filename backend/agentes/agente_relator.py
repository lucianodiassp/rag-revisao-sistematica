import os
import json
import psycopg2
from dotenv import load_dotenv, find_dotenv
from google import genai
from google.genai import types

# ==========================================
# CONFIGURAÇÃO DE AMBIENTE E CONEXÃO
# ==========================================
load_dotenv(find_dotenv())
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
NOME_MODELO = "gemini-2.5-flash"

def get_conexao():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "rag_systematic_review"),
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"]
    )

def coletar_metricas_prisma():
    """Recolhe os números para o fluxograma de auditoria."""
    conexao = get_conexao()
    cursor = conexao.cursor()
    
    metricas = {}
    
    # 1. Total de artigos únicos na base
    cursor.execute("SELECT COUNT(*) FROM deduplicated_papers;")
    metricas['total_unicos'] = cursor.fetchone()[0]
    
    # 2. Total processado pela IA (Triagem)
    cursor.execute("SELECT COUNT(*) FROM screening_decisions;")
    metricas['triados_ia'] = cursor.fetchone()[0]
    
    # 3. Total aprovado pelo Humano
    cursor.execute("SELECT COUNT(*) FROM screening_decisions WHERE human_decision = 'Incluir';")
    metricas['aprovados_humano'] = cursor.fetchone()[0]
    
    # 4. Total de evidências extraídas
    cursor.execute("SELECT COUNT(*) FROM extracted_evidence;")
    metricas['evidencias_extraidas'] = cursor.fetchone()[0]
    
    cursor.close()
    conexao.close()
    return metricas

def coletar_evidencias():
    """Recolhe os dados JSON estruturados para enviar ao LLM."""
    conexao = get_conexao()
    cursor = conexao.cursor()
    
    cursor.execute("""
        SELECT p.title, e.extraction_jsonb 
        FROM extracted_evidence e
        JOIN deduplicated_papers p ON p.id = e.paper_id;
    """)
    resultados = cursor.fetchall()
    conexao.close()
    
    evidencias = []
    for titulo, jsonb_data in resultados:
        if isinstance(jsonb_data, str):
            jsonb_data = json.loads(jsonb_data)
        
        evidencias.append({
            "titulo": titulo,
            "dados": jsonb_data
        })
    return evidencias

def gerar_relatorio_final():
    """Orquestra a coleta de dados e a geração do texto pelo Gemini."""
    print("📊 A recolher métricas PRISMA...")
    metricas = coletar_metricas_prisma()
    
    print("📚 A recolher evidências extraídas...")
    evidencias = coletar_evidencias()
    
    if not evidencias:
        return {"metricas": metricas, "relatorio_md": "Não há evidências suficientes para gerar o relatório. Por favor, extraia evidências primeiro na Matriz."}
    
    print("🧠 A solicitar síntese ao Gemini...")
    
    # Preparar o prompt com rigor académico
    prompt = f"""
    Atue como um investigador sénior a redigir a secção de 'Resultados e Discussão' de uma Revisão Sistemática da Literatura.
    
    Aqui estão as métricas do fluxo de trabalho (PRISMA):
    - Artigos únicos analisados: {metricas['total_unicos']}
    - Artigos aprovados para extração: {metricas['aprovados_humano']}
    
    Abaixo estão os dados estruturados extraídos dos artigos aprovados:
    {json.dumps(evidencias, indent=2, ensure_ascii=False)}
    
    Sua tarefa:
    1. Escreva um resumo executivo formal e coeso (formato Markdown).
    2. Sintetize os principais 'Objetivos' e 'Métodos' encontrados.
    3. Destaque os 'Principais Resultados' de forma agregada (quais são as tendências ou consensos?).
    4. Identifique as 'Limitações' mais comuns relatadas pelos autores.
    5. Mantenha um tom estritamente académico, imparcial e científico. Não invente dados, baseie-se APENAS no JSON fornecido.
    """
    
    try:
        resposta = client.models.generate_content(
            model=NOME_MODELO,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.2, # Baixa temperatura para manter o rigor factual
            ),
        )
        texto_relatorio = resposta.text
    except Exception as e:
        texto_relatorio = f"Erro ao contactar a API do Gemini: {e}"
        
    return {
        "metricas": metricas,
        "relatorio_md": texto_relatorio
    }

if __name__ == "__main__":
    resultado = gerar_relatorio_final()
    print("\n✅ Relatório Gerado com Sucesso!\n")
    print(resultado['relatorio_md'][:500] + "...\n")