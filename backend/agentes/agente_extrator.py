import json
import os
import time
import uuid

import psycopg2
from dotenv import find_dotenv, load_dotenv
from google.genai import types
from google.genai.errors import APIError
from psycopg2.extras import Json

from backend.app.database import resolver_project_id
from backend.app.evidence_utils import (
    FIELD_TYPES,
    SCHEMA_VERSION,
    achatar_extracao,
    listar_fontes_extracao,
    validar_extracao_rastreavel,
)
from backend.app.gemini_client import get_gemini_client


load_dotenv(find_dotenv())
NOME_MODELO = "gemini-2.5-flash"
MAXIMO_CARACTERES_CONTEXTO = 100_000


def get_conexao():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "rag_systematic_review"),
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
    )


def buscar_artigos_aprovados(project_id):
    """Seleciona artigos incluídos com PDF rastreável e extração ausente/legada."""
    with get_conexao() as conexao, conexao.cursor() as cursor:
        cursor.execute(
            """
            SELECT DISTINCT p.id, p.title
            FROM deduplicated_papers p
            JOIN screening_decisions s ON p.id = s.paper_id
            WHERE p.project_id = %s
              AND s.human_decision = 'Incluir'
              AND EXISTS (
                  SELECT 1
                  FROM paper_chunks pc
                  WHERE pc.paper_id = p.id
                    AND pc.chunk_type LIKE 'full_text_part_%%'
                    AND pc.metadata_jsonb->>'source_type' = 'pdf'
                    AND pc.metadata_jsonb ? 'page_start'
              )
              AND NOT EXISTS (
                  SELECT 1
                  FROM extracted_evidence e
                  WHERE e.paper_id = p.id AND e.schema_version = %s
              )
            ORDER BY p.title
            """,
            (project_id, SCHEMA_VERSION),
        )
        return cursor.fetchall()


def contar_aprovados_sem_pdf_rastreavel(project_id):
    with get_conexao() as conexao, conexao.cursor() as cursor:
        cursor.execute(
            """
            SELECT COUNT(DISTINCT p.id)
            FROM deduplicated_papers p
            JOIN screening_decisions s ON p.id = s.paper_id
            WHERE p.project_id = %s
              AND s.human_decision = 'Incluir'
              AND NOT EXISTS (
                  SELECT 1 FROM paper_chunks pc
                  WHERE pc.paper_id = p.id
                    AND pc.chunk_type LIKE 'full_text_part_%%'
                    AND pc.metadata_jsonb->>'source_type' = 'pdf'
                    AND pc.metadata_jsonb ? 'page_start'
              )
            """,
            (project_id,),
        )
        return cursor.fetchone()[0]


def buscar_chunks_pdf(paper_id, maximo_caracteres=MAXIMO_CARACTERES_CONTEXTO):
    with get_conexao() as conexao, conexao.cursor() as cursor:
        cursor.execute(
            """
            SELECT id, chunk_text, (metadata_jsonb->>'page_start')::INTEGER AS page_number
            FROM paper_chunks
            WHERE paper_id = %s
              AND chunk_type LIKE 'full_text_part_%%'
              AND metadata_jsonb->>'source_type' = 'pdf'
              AND metadata_jsonb ? 'page_start'
            ORDER BY (metadata_jsonb->>'page_start')::INTEGER,
                     COALESCE((metadata_jsonb->>'page_chunk_index')::INTEGER, 1),
                     id
            """,
            (paper_id,),
        )
        todos = [
            {"id": str(linha[0]), "chunk_text": linha[1], "page_number": linha[2]}
            for linha in cursor.fetchall()
        ]

    selecionados = []
    caracteres = 0
    for chunk in todos:
        tamanho = len(chunk["chunk_text"])
        if selecionados and caracteres + tamanho > maximo_caracteres:
            break
        selecionados.append(chunk)
        caracteres += tamanho
    return selecionados, len(selecionados) < len(todos)


def _montar_contexto(chunks):
    return "\n\n".join(
        f"[chunk_id={chunk['id']} | página={chunk['page_number']}]\n{chunk['chunk_text']}"
        for chunk in chunks
    )


def extrair_evidencias_com_ia(titulo, chunks, contexto_truncado=False, tentativa=1):
    """Extrai campos do texto integral e aceita apenas citações verificáveis."""
    prompt = f"""
Você é um extrator de evidências para uma Revisão Sistemática. Analise SOMENTE os
trechos do artigo fornecidos abaixo. Cada trecho tem um chunk_id e uma página.

Título do artigo: {titulo}

REGRAS OBRIGATÓRIAS:
1. Não use conhecimento externo, título ou inferência como evidência.
2. Para cada valor reportado, inclua ao menos uma citação copiada literalmente do trecho.
3. O chunk_id deve ser exatamente um dos identificadores fornecidos.
4. Se não houver evidência explícita, use "Não reportado" para texto, [] para listas,
   evidence=[] e confidence=0.
5. Responda exclusivamente em JSON no formato abaixo. Confidence varia de 0 a 1.

{{
  "objective": {{"value": "...", "evidence": [{{"chunk_id": "uuid", "quote": "trecho literal"}}], "confidence": 0.0}},
  "method": {{"value": "...", "evidence": [{{"chunk_id": "uuid", "quote": "trecho literal"}}], "confidence": 0.0}},
  "dataset": {{"value": "...", "evidence": [{{"chunk_id": "uuid", "quote": "trecho literal"}}], "confidence": 0.0}},
  "metrics": {{"value": ["..."], "evidence": [{{"chunk_id": "uuid", "quote": "trecho literal"}}], "confidence": 0.0}},
  "main_results": {{"value": "...", "evidence": [{{"chunk_id": "uuid", "quote": "trecho literal"}}], "confidence": 0.0}},
  "limitations": {{"value": ["..."], "evidence": [{{"chunk_id": "uuid", "quote": "trecho literal"}}], "confidence": 0.0}}
}}

TRECHOS DO PDF:
{_montar_contexto(chunks)}
"""
    try:
        resposta = get_gemini_client().models.generate_content(
            model=NOME_MODELO,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.0,
            ),
        )
        resposta_json = json.loads(resposta.text)
        resposta_json["document_scope"] = {"truncated": contexto_truncado}
        return validar_extracao_rastreavel(resposta_json, chunks)
    except APIError as erro:
        if erro.code == 429 and tentativa <= 3:
            print("   ⏳ Cota da API atingida. A aguardar antes de tentar novamente...")
            time.sleep(60)
            return extrair_evidencias_com_ia(titulo, chunks, contexto_truncado, tentativa + 1)
        print(f"❌ Falha na API: {erro}")
        return None
    except Exception as erro:
        print(f"❌ Erro estrutural na extração: {erro}")
        return None


def _salvar_extracao(cursor, project_id, paper_id, dados_extraidos):
    # UUIDs retornados por diferentes configurações do psycopg2 podem chegar como
    # uuid.UUID ou texto. Padronizar na fronteira SQL evita "can't adapt type UUID".
    project_id = str(project_id)
    paper_id = str(paper_id)
    cursor.execute(
        """
        SELECT e.id
        FROM extracted_evidence e
        JOIN deduplicated_papers p ON p.id = e.paper_id
        WHERE e.paper_id = %s AND p.project_id = %s
        FOR UPDATE
        """,
        (paper_id, project_id),
    )
    existente = cursor.fetchone()
    if existente:
        extracao_id = str(existente[0])
        cursor.execute(
            """
            UPDATE extracted_evidence
            SET extraction_jsonb = %s,
                schema_version = %s,
                human_review_status = 'pending',
                human_review_jsonb = NULL,
                review_notes = NULL,
                reviewed_at = NULL,
                extracted_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (Json(dados_extraidos), SCHEMA_VERSION, extracao_id),
        )
        cursor.execute("DELETE FROM evidence_field_sources WHERE extraction_id = %s", (extracao_id,))
    else:
        extracao_id = str(uuid.uuid4())
        cursor.execute(
            """
            INSERT INTO extracted_evidence
                (id, paper_id, extraction_jsonb, schema_version, human_review_status)
            VALUES (%s, %s, %s, %s, 'pending')
            """,
            (extracao_id, paper_id, Json(dados_extraidos), SCHEMA_VERSION),
        )

    for fonte in listar_fontes_extracao(dados_extraidos):
        cursor.execute(
            """
            INSERT INTO evidence_field_sources
                (extraction_id, field_name, evidence_order, chunk_id,
                 page_number, quote, quote_validated)
            VALUES (%s, %s, %s, %s, %s, %s, TRUE)
            """,
            (
                extracao_id,
                fonte["field_name"],
                fonte["evidence_order"],
                fonte["chunk_id"],
                fonte["page_number"],
                fonte["quote"],
            ),
        )
    return str(extracao_id)


def carregar_extracoes_projeto(project_id):
    with get_conexao() as conexao, conexao.cursor() as cursor:
        cursor.execute(
            """
            SELECT e.id, e.paper_id, p.title, e.extraction_jsonb, e.schema_version,
                   e.human_review_status, e.human_review_jsonb,
                   e.review_notes, e.extracted_at, e.reviewed_at
            FROM extracted_evidence e
            JOIN deduplicated_papers p ON p.id = e.paper_id
            WHERE p.project_id = %s
            ORDER BY p.title
            """,
            (project_id,),
        )
        colunas = [item[0] for item in cursor.description]
        return [dict(zip(colunas, linha)) for linha in cursor.fetchall()]


def salvar_revisao_humana(project_id, extracao_id, dados_revisados, status, notas=""):
    if status not in {"approved", "corrected", "rejected"}:
        raise ValueError("Status de revisão inválido.")
    dados_finais = achatar_extracao(dados_revisados)
    with get_conexao() as conexao, conexao.cursor() as cursor:
        cursor.execute(
            """
            UPDATE extracted_evidence e
            SET human_review_status = %s,
                human_review_jsonb = %s,
                review_notes = %s,
                reviewed_at = CURRENT_TIMESTAMP
            FROM deduplicated_papers p
            WHERE e.id = %s AND p.id = e.paper_id AND p.project_id = %s
            RETURNING e.id
            """,
            (
                status,
                Json(dados_finais) if status != "rejected" else None,
                notas.strip() or None,
                extracao_id,
                project_id,
            ),
        )
        if not cursor.fetchone():
            raise ValueError("Extração não encontrada no projeto ativo.")


def executar_pipeline_extracao(project_id=None):
    project_id = resolver_project_id(project_id)
    artigos = buscar_artigos_aprovados(project_id)
    sem_pdf = contar_aprovados_sem_pdf_rastreavel(project_id)
    resumo = {"extraidos": 0, "falhas": 0, "sem_pdf_rastreavel": sem_pdf}

    if not artigos:
        print("🎉 Não há artigos com PDF rastreável pendentes de extração.")
        return resumo

    print(f"📊 Encontrados {len(artigos)} artigos para extração rastreável.\n")
    with get_conexao() as conexao, conexao.cursor() as cursor:
        for indice, (paper_id, titulo) in enumerate(artigos):
            print(f"🧠 IA a extrair evidências do PDF: '{titulo[:50]}...'")
            chunks, truncado = buscar_chunks_pdf(paper_id)
            dados_extraidos = extrair_evidencias_com_ia(titulo, chunks, truncado)
            if not dados_extraidos:
                resumo["falhas"] += 1
                continue

            extracao_id = _salvar_extracao(cursor, project_id, paper_id, dados_extraidos)
            cursor.execute(
                """
                INSERT INTO agent_interactions
                    (project_id, agent_name, input_jsonb, output_jsonb, model_jsonb)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    project_id,
                    "traceable_extraction_agent",
                    Json({
                        "project_id": str(project_id),
                        "paper_id": str(paper_id),
                        "chunk_ids": [chunk["id"] for chunk in chunks],
                        "context_truncated": truncado,
                    }),
                    Json({"extraction_id": extracao_id, "extraction": dados_extraidos}),
                    Json({"provider": "Google", "model_name": NOME_MODELO, "temperature": 0.0}),
                ),
            )
            conexao.commit()
            resumo["extraidos"] += 1
            print("   ✅ Evidências e fontes literais validadas e salvas.")
            if indice < len(artigos) - 1:
                time.sleep(15)

    return resumo


if __name__ == "__main__":
    executar_pipeline_extracao(resolver_project_id())
