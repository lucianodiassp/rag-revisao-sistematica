import os
import json
import psycopg2
from dotenv import load_dotenv, find_dotenv
from backend.app.ai_config import TASK_REPORT, get_generation_config
from backend.app.ai_service import generate_content
from backend.app.database import log_interacao_agente, resolver_project_id
from backend.app.methodological_quality import methodological_summary
from backend.app.prisma import calcular_fluxo_prisma, salvar_snapshot_prisma
from backend.app.synthesis_confidence import confidence_summary

# ==========================================
# CONFIGURAÇÃO DE AMBIENTE E CONEXÃO
# ==========================================
load_dotenv(find_dotenv())

def get_conexao():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "rag_systematic_review"),
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"]
    )

def coletar_metricas_prisma(project_id):
    """Compatibilidade para consumidores antigos das métricas do fluxo."""
    return calcular_fluxo_prisma(project_id)["metrics"]

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

def gerar_relatorio_final(project_id=None, progress_callback=None):
    """Orquestra a coleta de dados e a geração do texto pelo Gemini."""
    project_id = resolver_project_id(project_id)
    if progress_callback:
        progress_callback(0, 4, "Calculando e registrando o fluxo PRISMA")
    print("📊 A recolher métricas PRISMA...")
    snapshot_prisma = salvar_snapshot_prisma(project_id)
    metricas = snapshot_prisma["metrics"]
    
    print("📚 A recolher evidências extraídas...")
    if progress_callback:
        progress_callback(1, 4, "Reunindo evidências revisadas")
    evidencias = coletar_evidencias(project_id)
    avaliacoes_metodologicas = methodological_summary(project_id)
    confianca = confidence_summary(project_id)
    if progress_callback:
        progress_callback(2, 4, "Preparando a síntese acadêmica")
    
    if not evidencias:
        if progress_callback:
            progress_callback(4, 4, "Relatório concluído sem evidências aprovadas")
        return {
            "metricas": metricas,
            "prisma_snapshot": snapshot_prisma,
            "synthesis_confidence": confianca,
            "relatorio_md": (
                "Não há evidências **aprovadas pela revisão humana** para gerar o relatório. "
                "Revise e aprove ao menos uma extração na Matriz de Evidências."
            ),
        }
    
    print("🧠 A solicitar síntese ao Gemini...")
    
    # Preparar o prompt com rigor académico
    prompt = f"""
    Atue como um investigador sénior a redigir a secção de 'Resultados e Discussão' de uma Revisão Sistemática da Literatura.
    
    Aqui está o snapshot determinístico e versionado do fluxo de trabalho PRISMA.
    Reproduza esses números exatamente; não estime nem recalcule valores:
    {json.dumps({
        'snapshot_version': snapshot_prisma['snapshot_version'],
        'protocol_version': snapshot_prisma['protocol_version'],
        'metrics': metricas,
        'source_counts': snapshot_prisma['source_counts'],
        'exclusion_reasons': snapshot_prisma['exclusion_reasons'],
        'interpretation': snapshot_prisma['interpretation'],
    }, indent=2, ensure_ascii=False)}
    
    Abaixo estão apenas os dados aprovados ou corrigidos por revisão humana, junto
    com as citações literais validadas contra o PDF:
    {json.dumps(evidencias, indent=2, ensure_ascii=False)}

    Avaliações metodológicas da versão ativa, registradas por revisão humana:
    {json.dumps(avaliacoes_metodologicas, indent=2, ensure_ascii=False, default=str)}

    Limitações do processo e confiança da síntese, revisadas por uma pessoa:
    {json.dumps({
        'latest_snapshot': confianca['latest_snapshot'],
        'snapshot_is_stale': confianca['is_stale'],
        'warnings': confianca['warnings'],
        'confirmed_or_mitigated_limitations': [
            item for item in confianca['current_limitations']
            if item['status'] in ('confirmed', 'mitigated')
        ],
    }, indent=2, ensure_ascii=False, default=str)}
    
    Sua tarefa:
    1. Abra com uma seção 'Fluxo PRISMA' e relate os números e motivos do snapshot exatamente como fornecidos.
    2. Escreva um resumo executivo formal e coeso (formato Markdown).
    3. Sintetize os principais 'Objetivos' e 'Métodos' encontrados.
    4. Destaque os 'Principais Resultados' de forma agregada (quais são as tendências ou consensos?).
    5. Identifique as 'Limitações' mais comuns relatadas pelos autores.
    6. Inclua uma seção 'Qualidade metodológica e possíveis vieses' somente quando
       houver avaliações humanas. Diferencie explicitamente a decisão humana da sugestão de IA.
    7. Inclua a seção 'Limitações metodológicas e confiança na síntese'. Diferencie
       limitações relatadas pelos estudos das limitações do processo de revisão. Use somente
       limitações confirmadas ou mitigadas. Informe a classificação humana geral e por dimensão
       apenas se houver snapshot atual; se estiver ausente ou desatualizado, declare isso explicitamente.
    8. Mantenha um tom estritamente académico, imparcial e científico. Não invente dados, baseie-se APENAS no JSON fornecido.
    9. Ao apresentar um achado, cite a fonte no formato [paper_id, p. página].
    10. Não apresente um achado quando não houver uma fonte literal compatível no campo correspondente.
    """
    
    try:
        if progress_callback:
            progress_callback(3, 4, "Gerando a síntese com o modelo de IA")
        resposta = generate_content(
            TASK_REPORT,
            contents=prompt,
        )
        texto_relatorio = resposta.text
    except Exception as e:
        raise RuntimeError(f"Não foi possível gerar a síntese com o provedor de IA: {e}") from e

    log_interacao_agente(
        project_id,
        "report_agent",
        {
            "prisma_snapshot_id": snapshot_prisma["id"],
            "metrics": metricas,
            "paper_ids": [item["paper_id"] for item in evidencias],
            "methodological_assessment_ids": [
                str(item["id"]) for item in avaliacoes_metodologicas
            ],
            "synthesis_confidence_snapshot_id": (
                str(confianca["latest_snapshot"]["id"])
                if confianca["latest_snapshot"] else None
            ),
            "synthesis_confidence_stale": confianca["is_stale"],
            "limitation_ids": [
                str(item["id"]) for item in confianca["current_limitations"]
                if item["status"] in ("confirmed", "mitigated")
            ],
        },
        {
            "report_markdown": texto_relatorio,
            "prisma_snapshot_version": snapshot_prisma["snapshot_version"],
        },
        get_generation_config(TASK_REPORT).metadata(),
    )
    if progress_callback:
        progress_callback(4, 4, "Relatório final registrado")
        
    return {
        "metricas": metricas,
        "prisma_snapshot": snapshot_prisma,
        "synthesis_confidence": confianca,
        "relatorio_md": texto_relatorio
    }

if __name__ == "__main__":
    resultado = gerar_relatorio_final(resolver_project_id())
    print("\n✅ Relatório Gerado com Sucesso!\n")
    print(resultado['relatorio_md'][:500] + "...\n")
