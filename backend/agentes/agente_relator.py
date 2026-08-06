import os
import json
import psycopg2
from dotenv import load_dotenv, find_dotenv
from google.genai import types
from backend.app.database import log_interacao_agente, resolver_project_id
from backend.app.gemini_client import get_gemini_client

# ==========================================
# CONFIGURAÇÃO DE AMBIENTE E CONEXÃO
# ==========================================
load_dotenv(find_dotenv())
NOME_MODELO = "gemini-2.5-flash"

def get_conexao():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "rag_systematic_review"),
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"]
    )

def coletar_metricas_prisma(project_id):
    """Recolhe os números para o fluxograma de auditoria."""
    conexao = get_conexao()
    cursor = conexao.cursor()
    
    metricas = {}
    
    # 1. Total de artigos únicos na base
    cursor.execute("SELECT COUNT(*) FROM deduplicated_papers WHERE project_id = %s;", (project_id,))
    metricas['total_unicos'] = cursor.fetchone()[0]
    
    # 2. Total processado pela IA (Triagem)
    cursor.execute("""
        SELECT COUNT(*)
        FROM screening_decisions s
        JOIN deduplicated_papers p ON p.id = s.paper_id
        WHERE p.project_id = %s
    """, (project_id,))
    metricas['triados_ia'] = cursor.fetchone()[0]
    
    # 3. Total aprovado pelo Humano
    cursor.execute("""
        SELECT COUNT(*)
        FROM screening_decisions s
        JOIN deduplicated_papers p ON p.id = s.paper_id
        WHERE p.project_id = %s AND s.human_decision = 'Incluir'
    """, (project_id,))
    metricas['aprovados_humano'] = cursor.fetchone()[0]
    
    # 4. Total de evidências extraídas
    cursor.execute("""
        SELECT COUNT(*)
        FROM extracted_evidence e
        JOIN deduplicated_papers p ON p.id = e.paper_id
        WHERE p.project_id = %s
    """, (project_id,))
    metricas['evidencias_extraidas'] = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*)
        FROM extracted_evidence e
        JOIN deduplicated_papers p ON p.id = e.paper_id
        WHERE p.project_id = %s
          AND e.human_review_status IN ('approved', 'corrected')
          AND e.schema_version = 'traceable-v1'
          AND EXISTS (
              SELECT 1 FROM evidence_field_sources efs
              WHERE efs.extraction_id = e.id AND efs.quote_validated = TRUE
          )
    """, (project_id,))
    metricas['evidencias_aprovadas'] = cursor.fetchone()[0]
    
    cursor.close()
    conexao.close()
    return metricas

def coletar_evidencias(project_id):
    """Recolhe somente a versão humana aprovada e suas fontes literais."""
    conexao = get_conexao()
    cursor = conexao.cursor()
    
    cursor.execute("""
        SELECT e.id, p.id, p.title, e.human_review_jsonb, e.human_review_status
        FROM extracted_evidence e
        JOIN deduplicated_papers p ON p.id = e.paper_id
        WHERE p.project_id = %s
          AND e.human_review_status IN ('approved', 'corrected')
          AND e.human_review_jsonb IS NOT NULL
          AND e.schema_version = 'traceable-v1'
          AND EXISTS (
              SELECT 1 FROM evidence_field_sources efs
              WHERE efs.extraction_id = e.id AND efs.quote_validated = TRUE
          )
        ORDER BY p.title;
    """, (project_id,))
    resultados = cursor.fetchall()

    ids_extracoes = [linha[0] for linha in resultados]
    fontes_por_extracao = {str(extracao_id): [] for extracao_id in ids_extracoes}
    if ids_extracoes:
        cursor.execute("""
            SELECT extraction_id, field_name, page_number, quote, chunk_id
            FROM evidence_field_sources
            WHERE extraction_id = ANY(%s::uuid[])
              AND quote_validated = TRUE
            ORDER BY extraction_id, field_name, evidence_order
        """, (ids_extracoes,))
        for extracao_id, campo, pagina, quote, chunk_id in cursor.fetchall():
            fontes_por_extracao[str(extracao_id)].append({
                "field": campo,
                "page": pagina,
                "quote": quote,
                "chunk_id": str(chunk_id),
            })
    conexao.close()
    
    evidencias = []
    for extracao_id, paper_id, titulo, jsonb_data, status in resultados:
        if isinstance(jsonb_data, str):
            jsonb_data = json.loads(jsonb_data)
        
        evidencias.append({
            "paper_id": str(paper_id),
            "titulo": titulo,
            "status_revisao": status,
            "dados_revisados": jsonb_data,
            "fontes_literais": fontes_por_extracao[str(extracao_id)],
        })
    return evidencias

def gerar_relatorio_final(project_id=None):
    """Orquestra a coleta de dados e a geração do texto pelo Gemini."""
    project_id = resolver_project_id(project_id)
    print("📊 A recolher métricas PRISMA...")
    metricas = coletar_metricas_prisma(project_id)
    
    print("📚 A recolher evidências extraídas...")
    evidencias = coletar_evidencias(project_id)
    
    if not evidencias:
        return {
            "metricas": metricas,
            "relatorio_md": (
                "Não há evidências **aprovadas pela revisão humana** para gerar o relatório. "
                "Revise e aprove ao menos uma extração na Matriz de Evidências."
            ),
        }
    
    print("🧠 A solicitar síntese ao Gemini...")
    
    # Preparar o prompt com rigor académico
    prompt = f"""
    Atue como um investigador sénior a redigir a secção de 'Resultados e Discussão' de uma Revisão Sistemática da Literatura.
    
    Aqui estão as métricas do fluxo de trabalho (PRISMA):
    - Artigos únicos analisados: {metricas['total_unicos']}
    - Artigos aprovados para extração: {metricas['aprovados_humano']}
    
    Abaixo estão apenas os dados aprovados ou corrigidos por revisão humana, junto
    com as citações literais validadas contra o PDF:
    {json.dumps(evidencias, indent=2, ensure_ascii=False)}
    
    Sua tarefa:
    1. Escreva um resumo executivo formal e coeso (formato Markdown).
    2. Sintetize os principais 'Objetivos' e 'Métodos' encontrados.
    3. Destaque os 'Principais Resultados' de forma agregada (quais são as tendências ou consensos?).
    4. Identifique as 'Limitações' mais comuns relatadas pelos autores.
    5. Mantenha um tom estritamente académico, imparcial e científico. Não invente dados, baseie-se APENAS no JSON fornecido.
    6. Ao apresentar um achado, cite a fonte no formato [paper_id, p. página].
    7. Não apresente um achado quando não houver uma fonte literal compatível no campo correspondente.
    """
    
    try:
        resposta = get_gemini_client().models.generate_content(
            model=NOME_MODELO,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.2, # Baixa temperatura para manter o rigor factual
            ),
        )
        texto_relatorio = resposta.text
    except Exception as e:
        texto_relatorio = f"Erro ao contactar a API do Gemini: {e}"

    log_interacao_agente(
        project_id,
        "report_agent",
        {"metrics": metricas, "paper_ids": [item["paper_id"] for item in evidencias]},
        {"report_markdown": texto_relatorio},
        {"provider": "Google", "model_name": NOME_MODELO, "temperature": 0.2},
    )
        
    return {
        "metricas": metricas,
        "relatorio_md": texto_relatorio
    }

if __name__ == "__main__":
    resultado = gerar_relatorio_final(resolver_project_id())
    print("\n✅ Relatório Gerado com Sucesso!\n")
    print(resultado['relatorio_md'][:500] + "...\n")
