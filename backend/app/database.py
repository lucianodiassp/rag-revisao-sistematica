import json
import os
import uuid

import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import Json
from backend.app.deduplication import (
    ACTION_AUTO_CREATE,
    ACTION_AUTO_MERGE,
    ACTION_PENDING_REVIEW,
    avaliar_duplicidade,
)
from backend.app.project_utils import (
    mesclar_proveniencia,
    normalizar_doi,
    normalizar_titulo,
)


load_dotenv()


def get_connection():
    """Cria uma conexão usando apenas a configuração do ambiente."""
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        database=os.getenv("DB_NAME", "rag_systematic_review"),
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
    )


def listar_projetos():
    with get_connection() as conexao, conexao.cursor() as cursor:
        cursor.execute(
            """
            SELECT id, title, question, criteria_jsonb, status,
                   protocol_version, created_at, updated_at
            FROM review_projects
            ORDER BY updated_at DESC, created_at DESC
            """
        )
        colunas = [descricao[0] for descricao in cursor.description]
        return [dict(zip(colunas, linha)) for linha in cursor.fetchall()]


def obter_projeto(project_id):
    with get_connection() as conexao, conexao.cursor() as cursor:
        cursor.execute(
            """
            SELECT id, title, question, criteria_jsonb, status,
                   protocol_version, created_at, updated_at
            FROM review_projects
            WHERE id = %s
            """,
            (project_id,),
        )
        linha = cursor.fetchone()
        if not linha:
            raise ValueError(f"Projeto não encontrado: {project_id}")
        colunas = [descricao[0] for descricao in cursor.description]
        return dict(zip(colunas, linha))


def criar_projeto(titulo, pergunta):
    projeto_id = str(uuid.uuid4())
    protocolo_inicial = {
        "pico": {},
        "inclusion_criteria": [],
        "exclusion_criteria": [],
        "search_string": "",
        "audit_questions": [],
    }
    with get_connection() as conexao, conexao.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO review_projects
                (id, title, question, criteria_jsonb, status, protocol_version)
            VALUES (%s, %s, %s, %s, 'draft_protocol', 1)
            """,
            (projeto_id, titulo.strip(), pergunta.strip(), Json(protocolo_inicial)),
        )
        cursor.execute(
            """
            INSERT INTO review_protocol_versions
                (project_id, version, question, criteria_jsonb, change_reason)
            VALUES (%s, 1, %s, %s, 'Criação do projeto')
            """,
            (projeto_id, pergunta.strip(), Json(protocolo_inicial)),
        )
    return projeto_id


def salvar_protocolo_projeto(project_id, pergunta, protocolo, motivo="Atualização do protocolo"):
    with get_connection() as conexao, conexao.cursor() as cursor:
        cursor.execute(
            "SELECT protocol_version FROM review_projects WHERE id = %s FOR UPDATE",
            (project_id,),
        )
        linha = cursor.fetchone()
        if not linha:
            raise ValueError(f"Projeto não encontrado: {project_id}")

        nova_versao = linha[0] + 1
        cursor.execute(
            """
            UPDATE review_projects
            SET question = %s,
                criteria_jsonb = %s,
                status = 'search_ready',
                protocol_version = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (pergunta.strip(), Json(protocolo), nova_versao, project_id),
        )
        cursor.execute(
            """
            INSERT INTO review_protocol_versions
                (project_id, version, question, criteria_jsonb, change_reason)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (project_id, nova_versao, pergunta.strip(), Json(protocolo), motivo),
        )
    return nova_versao


def resolver_project_id(project_id=None):
    """Resolve o projeto para scripts CLI sem permitir mistura silenciosa."""
    if project_id:
        return str(project_id)

    project_id_ambiente = os.getenv("PROJECT_ID")
    if project_id_ambiente:
        return project_id_ambiente

    projetos = listar_projetos()
    if len(projetos) == 1:
        return str(projetos[0]["id"])
    if not projetos:
        raise RuntimeError("Nenhum projeto cadastrado. Crie um projeto pela interface.")
    raise RuntimeError("Há vários projetos. Defina PROJECT_ID ou selecione um projeto na interface.")


def registrar_busca(project_id, fonte, query_text, parametros=None):
    with get_connection() as conexao, conexao.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO search_queries (project_id, source, query_text, query_jsonb)
            VALUES (%s, %s, %s, %s)
            RETURNING id
            """,
            (project_id, fonte, query_text, Json(parametros or {})),
        )
        return cursor.fetchone()[0]


def atualizar_metadados_busca(project_id, search_query_id, parametros):
    """Atualiza o relatório auditável de uma execução de coleta/importação."""
    with get_connection() as conexao, conexao.cursor() as cursor:
        cursor.execute(
            """
            UPDATE search_queries
            SET query_jsonb = %s
            WHERE id = %s AND project_id = %s
            """,
            (Json(parametros or {}), search_query_id, project_id),
        )
        if cursor.rowcount != 1:
            raise ValueError("Execução de coleta não encontrada no projeto ativo.")


def salvar_artigo_coletado(
    project_id,
    id_artigo,
    titulo,
    abstract,
    fontes_dict,
    search_query_id=None,
    fonte=None,
    registro_bruto=None,
):
    """Registra a coleta e aplica uma decisão de deduplicação auditável."""
    doi = normalizar_doi((fontes_dict or {}).get("external_ids", {}).get("doi"))
    fonte_registro = fonte or next(iter((fontes_dict or {}).get("sources", [])), "desconhecida")
    ids_externos = (fontes_dict or {}).get("external_ids", {})
    external_id = next((str(valor) for valor in ids_externos.values() if valor), None)

    with get_connection() as conexao, conexao.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO retrieved_records
                (project_id, search_query_id, source, external_id, doi, metadata_jsonb, raw_jsonb)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                project_id,
                search_query_id,
                fonte_registro,
                external_id,
                doi,
                Json((fontes_dict or {}).get("metadata", {})),
                Json(registro_bruto if registro_bruto is not None else (fontes_dict or {})),
            ),
        )
        retrieved_record_id = cursor.fetchone()[0]

        cursor.execute(
            """
            SELECT id, canonical_doi, title, abstract, merged_sources_jsonb
            FROM deduplicated_papers
            WHERE project_id = %s
            FOR SHARE
            """,
            (project_id,),
        )
        candidatos = [
            {
                "id": linha[0],
                "canonical_doi": linha[1],
                "title": linha[2],
                "abstract": linha[3],
                "merged_sources_jsonb": linha[4],
            }
            for linha in cursor.fetchall()
        ]
        entrada = {
            "proposed_paper_id": str(id_artigo),
            "canonical_doi": doi,
            "title": titulo,
            "abstract": abstract,
            "fontes_dict": fontes_dict or {},
        }
        avaliacao = avaliar_duplicidade(entrada, candidatos)
        candidato = avaliacao["candidate"]
        candidate_paper_id = str(candidato["id"]) if candidato else None
        result_paper_id = None

        if avaliacao["system_action"] == ACTION_AUTO_MERGE:
            proveniencia = mesclar_proveniencia(candidato["merged_sources_jsonb"], fontes_dict)
            abstract_final = (
                abstract
                if abstract and "indispon" not in abstract.lower()
                else candidato["abstract"]
            )
            cursor.execute(
                """
                UPDATE deduplicated_papers
                SET title = %s,
                    abstract = %s,
                    canonical_doi = COALESCE(canonical_doi, %s),
                    merged_sources_jsonb = %s
                WHERE id = %s AND project_id = %s
                """,
                (
                    titulo or candidato["title"],
                    abstract_final,
                    doi,
                    Json(proveniencia),
                    candidate_paper_id,
                    project_id,
                ),
            )
            result_paper_id = candidate_paper_id
        elif avaliacao["system_action"] == ACTION_AUTO_CREATE:
            cursor.execute(
                """
                INSERT INTO deduplicated_papers
                    (id, project_id, canonical_doi, title, abstract, merged_sources_jsonb)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (id_artigo, project_id, doi, titulo, abstract, Json(fontes_dict or {})),
            )
            result_paper_id = str(id_artigo)

        review_status = "pending" if avaliacao["system_action"] == ACTION_PENDING_REVIEW else "automatic"
        cursor.execute(
            """
            INSERT INTO deduplication_decisions
                (project_id, retrieved_record_id, candidate_paper_id, result_paper_id,
                 rule_code, similarity_score, system_action, explanation,
                 evidence_jsonb, incoming_record_jsonb, review_status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                project_id,
                str(retrieved_record_id),
                candidate_paper_id,
                result_paper_id,
                avaliacao["rule_code"],
                avaliacao["score"],
                avaliacao["system_action"],
                avaliacao["explanation"],
                Json(avaliacao["evidence"]),
                Json(entrada),
                review_status,
            ),
        )
        decision_id = cursor.fetchone()[0]
        return {
            "status": avaliacao["system_action"],
            "decision_id": str(decision_id),
            "retrieved_record_id": str(retrieved_record_id),
            "candidate_paper_id": candidate_paper_id,
            "paper_id": result_paper_id,
            "rule_code": avaliacao["rule_code"],
            "score": float(avaliacao["score"]),
            "explanation": avaliacao["explanation"],
        }


def log_interacao_agente(project_id, nome_agente, input_dict, output_dict, modelo_dict):
    with get_connection() as conexao, conexao.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO agent_interactions
                (project_id, agent_name, input_jsonb, output_jsonb, model_jsonb)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                project_id,
                nome_agente,
                Json(input_dict),
                Json(output_dict),
                Json(modelo_dict),
            ),
        )
        return cursor.fetchone()[0]


def salvar_execucao_avaliacao(project_id, run_type, metricas, parametros):
    with get_connection() as conexao, conexao.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO evaluation_runs (project_id, run_type, metrics_jsonb, params_jsonb)
            VALUES (%s, %s, %s, %s)
            RETURNING id
            """,
            (project_id, run_type, Json(metricas), Json(parametros)),
        )
        return cursor.fetchone()[0]


def carregar_ultima_execucao_avaliacao(project_id, run_type="rag_llm_judge"):
    with get_connection() as conexao, conexao.cursor() as cursor:
        cursor.execute(
            """
            SELECT id, metrics_jsonb, params_jsonb, created_at
            FROM evaluation_runs
            WHERE project_id = %s AND run_type = %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (project_id, run_type),
        )
        linha = cursor.fetchone()
        if not linha:
            return None
        return {
            "id": linha[0],
            "metrics": linha[1],
            "params": linha[2],
            "created_at": linha[3],
        }
