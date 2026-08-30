import os
import json
import psycopg2
import uuid
import time
from dotenv import load_dotenv
from google.genai.errors import APIError
from backend.app.ai_config import TASK_SCREENING, get_generation_config
from backend.app.ai_service import generate_content
from backend.app.database import obter_projeto, resolver_project_id
from backend.app.protocol_service import normalize_protocol, protocol_fingerprint
from backend.app.screening_service import UNUSABLE_ABSTRACTS

# ==========================================
# CONFIGURAÇÃO DE AMBIENTE E CONEXÃO
# ==========================================
load_dotenv()

def get_conexao():
    """Estabelece a conexão estritamente via variáveis de ambiente."""
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "rag_systematic_review"),
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"]
    )

def buscar_artigos_sem_analise(project_id, connection_factory=None):
    connection_factory = connection_factory or get_conexao
    with connection_factory() as connection, connection.cursor() as cursor:
        cursor.execute("""
            SELECT d.id, d.title, d.abstract
            FROM deduplicated_papers d
            WHERE d.project_id = %s
              AND NOT EXISTS (
                  SELECT 1 FROM screening_decisions s WHERE s.paper_id = d.id
              )
              AND NULLIF(BTRIM(d.abstract), '') IS NOT NULL
              AND BTRIM(d.abstract) NOT IN (%s, %s, %s)
            ORDER BY d.created_at, d.id;
        """, (project_id, *UNUSABLE_ABSTRACTS))
        return cursor.fetchall()

def carregar_criterios_dinamicos(project_id, protocol=None):
    """Lê os critérios versionados do projeto no PostgreSQL."""
    dados = normalize_protocol(
        protocol or obter_projeto(project_id).get("criteria_jsonb") or {}
    )
    pico = dados["pico"]
    eligibility = dados["eligibility"]
    scope_items = []
    for field, label in (
        ("population", "População ou problema"),
        ("intervention", "Intervenção, exposição ou método"),
        ("comparison", "Comparação"),
        ("outcome", "Desfechos"),
        ("study_design", "Desenhos de estudo esperados"),
    ):
        if pico.get(field):
            scope_items.append(f"{label}: {pico[field]}")
    if eligibility.get("year_from") or eligibility.get("year_to"):
        scope_items.append(
            "Período de publicação: "
            f"{eligibility.get('year_from') or 'sem limite inicial'} a "
            f"{eligibility.get('year_to') or 'sem limite final'}"
        )
    for field, label in (
        ("languages", "Idiomas aceitos"),
        ("publication_types", "Tipos de publicação aceitos"),
        ("study_designs", "Desenhos de estudo aceitos"),
    ):
        if eligibility.get(field):
            scope_items.append(f"{label}: {', '.join(eligibility[field])}")

    escopo = "\n".join(f"- {item}" for item in scope_items) or "- Não estruturado"
    inclusao = "\n".join([f"- {c}" for c in dados.get("inclusion_criteria", [])])
    exclusao = "\n".join([f"- {c}" for c in dados.get("exclusion_criteria", [])])

    return escopo, inclusao, exclusao

def triar_artigo_com_ia(project_id, titulo, resumo, tentativa=1, protocol=None):
    """Submete o artigo ao provedor configurado com critérios rastreáveis."""
    
    # Busca os critérios do JSON
    escopo_elegibilidade, criterios_inclusao, criterios_exclusao = carregar_criterios_dinamicos(
        project_id, protocol=protocol
    )
    
    prompt = f"""
    Você é um agente especialista em triagem de artigos científicos para uma Revisão Sistemática.
    Sua tarefa é avaliar o artigo abaixo com base estrita nos critérios fornecidos.

    [ESCOPO PICO/PICOS E ELEGIBILIDADE ESTRUTURADA]
    {escopo_elegibilidade}

    [CRITÉRIOS DE INCLUSÃO]
    {criterios_inclusao}

    [CRITÉRIOS DE EXCLUSÃO]
    {criterios_exclusao}

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
        resposta = generate_content(
            TASK_SCREENING,
            contents=prompt,
            response_mime_type="application/json",
        )
        return json.loads(resposta.text)
    
    except APIError as e:
        if e.code == 429 and tentativa <= 3:
            tempo_espera = 60
            print(f"   ⏳ Limite atingido (429). A aguardar {tempo_espera}s antes da tentativa {tentativa + 1}/3...")
            time.sleep(tempo_espera)
            return triar_artigo_com_ia(
                project_id,
                titulo,
                resumo,
                tentativa + 1,
                protocol=protocol,
            )
        else:
            print(f"❌ Falha persistente na API: {e}")
            return None
    except Exception as e:
        print(f"❌ Erro estrutural ao processar o artigo: {e}")
        return None

def executar_pipeline_triagem_ui(project_id=None):
    """Executa a triagem emitindo atualizações de estado (yield) para a interface gráfica."""
    project_id = resolver_project_id(project_id)
    project = obter_projeto(project_id)
    protocol = normalize_protocol(project.get("criteria_jsonb") or {})
    protocol_version = int(project.get("protocol_version") or 1)
    protocol_hash = protocol_fingerprint(protocol)
    artigos = buscar_artigos_sem_analise(project_id)
    
    if not artigos:
        yield {"status": "concluido", "atual": 0, "total": 0, "msg": "Nenhum artigo novo para analisar."}
        return

    total = len(artigos)
    conexao = get_conexao()
    cursor = conexao.cursor()

    for i, (paper_id, titulo, abstract) in enumerate(artigos, 1):
        yield {"status": "processando", "atual": i, "total": total, "msg": f"🧠 A analisar {i}/{total}: '{titulo[:40]}...'"}
        
        resultado_ia = triar_artigo_com_ia(
            project_id, titulo, abstract, protocol=protocol
        )
        
        if resultado_ia:
            decisao_id = str(uuid.uuid4())
            sugestao = resultado_ia.get("suggested_decision", "Talvez")
            justificativa_ia = resultado_ia.get("justification", "Sem justificativa fornecida.")
            
            rationale_dict = {
                "confidence": resultado_ia.get("confidence", 0.5),
                "justification": justificativa_ia,
                "agent_name": "screening_agent",
                "model_provider": get_generation_config(TASK_SCREENING).provider,
                "model_name": get_generation_config(TASK_SCREENING).model,
                "protocol_version": protocol_version,
                "protocol_fingerprint": protocol_hash,
            }
            
            cursor.execute("""
                INSERT INTO screening_decisions 
                (id, paper_id, suggested_decision, human_decision, rationale_jsonb, justification)
                VALUES (%s, %s, %s, NULL, %s, NULL)
            """, (decisao_id, paper_id, sugestao, json.dumps(rationale_dict)))
            
            cursor.execute("""
                INSERT INTO agent_interactions 
                (id, project_id, agent_name, input_jsonb, output_jsonb, model_jsonb)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                str(uuid.uuid4()),
                project_id,
                "screening_agent",
                json.dumps(
                    {
                        "project_id": project_id,
                        "paper_id": str(paper_id),
                        "title": titulo,
                        "protocol_version": protocol_version,
                        "protocol_fingerprint": protocol_hash,
                        "eligibility_snapshot": {
                            "pico": protocol.get("pico"),
                            "eligibility": protocol.get("eligibility"),
                            "inclusion_criteria": protocol.get("inclusion_criteria"),
                            "exclusion_criteria": protocol.get("exclusion_criteria"),
                        },
                    }
                ),
                json.dumps(resultado_ia),
                json.dumps(get_generation_config(TASK_SCREENING).metadata())
            ))
            conexao.commit()
            
            if i < total:
                yield {"status": "pausa", "atual": i, "total": total, "msg": f"⏳ Veredicto gravado ({sugestao}). Pausa de 15s para evitar bloqueio da API..."}
                time.sleep(15) 
            
    cursor.close()
    conexao.close()
    
    yield {"status": "concluido", "atual": total, "total": total, "msg": "🎉 Triagem automática concluída!"}

if __name__ == "__main__":
    for status in executar_pipeline_triagem_ui(resolver_project_id()):
        print(status["msg"])
