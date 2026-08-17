"""Exportação auditável e sem segredos de um projeto de revisão sistemática."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import unicodedata
import uuid
import zipfile
from datetime import date, datetime, timezone
from decimal import Decimal


PACKAGE_FORMAT = "rag-systematic-review-reproducibility-package"
PACKAGE_VERSION = 1
SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "contact_email",
    "email",
    "encrypted_secret",
    "password",
    "refresh_token",
    "secret",
    "token",
}


class ReproducibilityPackageError(RuntimeError):
    """Falha segura ao montar o pacote científico de um projeto."""


def _is_sensitive_key(value) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")
    return normalized in SENSITIVE_KEYS or normalized.endswith(
        ("_api_key", "_email", "_password", "_secret", "_token")
    )


def _json_safe(value):
    if isinstance(value, dict):
        sanitized = {}
        for key, item in value.items():
            sanitized[str(key)] = (
                "[REMOVIDO DO PACOTE]"
                if _is_sensitive_key(key)
                else _json_safe(item)
            )
        return sanitized
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _json_bytes(value) -> bytes:
    return json.dumps(
        _json_safe(value),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ).encode("utf-8")


def _csv_value(value):
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    if value is None:
        return ""
    if isinstance(value, str) and re.match(r"^[\s]*[=+\-@]", value):
        return "'" + value
    return value


def _csv_bytes(rows: list[dict], columns: list[str] | None = None) -> bytes:
    safe_rows = [_json_safe(row) for row in rows]
    if columns is None:
        columns = []
        for row in safe_rows:
            for key in row:
                if key not in columns:
                    columns.append(key)
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=columns, delimiter=";", extrasaction="ignore")
    writer.writeheader()
    for row in safe_rows:
        writer.writerow(
            {column: _csv_value(value) for column, value in row.items()}
        )
    return ("\ufeff" + output.getvalue()).encode("utf-8")


def _fetch_all(cursor, query: str, params=()) -> list[dict]:
    cursor.execute(query, params)
    columns = [description[0] for description in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _fetch_one(cursor, query: str, params=()) -> dict | None:
    rows = _fetch_all(cursor, query, params)
    return rows[0] if rows else None


def _collect_project_data(project_id, connection_factory=None) -> dict:
    if connection_factory is None:
        from backend.app.database import get_connection

        connection_factory = get_connection

    project_id = str(project_id or "").strip()
    if not project_id:
        raise ValueError("O projeto é obrigatório para gerar o pacote.")

    connection = connection_factory()
    try:
        if hasattr(connection, "set_session"):
            connection.set_session(readonly=True, isolation_level="REPEATABLE READ")
        with connection.cursor() as cursor:
            project = _fetch_one(
                cursor,
                """
                SELECT id, title, question, criteria_jsonb, status,
                       protocol_version, created_at, updated_at
                FROM review_projects
                WHERE id = %s
                """,
                (project_id,),
            )
            if not project:
                raise ValueError("Projeto não encontrado.")

            protocol_versions = _fetch_all(
                cursor,
                """
                SELECT id, project_id, version, question, criteria_jsonb,
                       change_reason, created_at
                FROM review_protocol_versions
                WHERE project_id = %s
                ORDER BY version
                """,
                (project_id,),
            )
            searches = _fetch_all(
                cursor,
                """
                SELECT id, project_id, source, query_text, query_jsonb, executed_at
                FROM search_queries
                WHERE project_id = %s
                ORDER BY executed_at, id
                """,
                (project_id,),
            )
            retrieved_records = _fetch_all(
                cursor,
                """
                SELECT id, project_id, search_query_id, source, external_id, doi,
                       metadata_jsonb, raw_jsonb, created_at
                FROM retrieved_records
                WHERE project_id = %s
                ORDER BY created_at, id
                """,
                (project_id,),
            )
            papers = _fetch_all(
                cursor,
                """
                SELECT id, project_id, canonical_doi, title, abstract,
                       merged_sources_jsonb, created_at
                FROM deduplicated_papers
                WHERE project_id = %s
                ORDER BY title, id
                """,
                (project_id,),
            )
            deduplication = _fetch_all(
                cursor,
                """
                SELECT id, project_id, retrieved_record_id, candidate_paper_id,
                       result_paper_id, rule_code, similarity_score, system_action,
                       explanation, evidence_jsonb, incoming_record_jsonb,
                       review_status, human_decision, review_justification,
                       created_at, reviewed_at
                FROM deduplication_decisions
                WHERE project_id = %s
                ORDER BY created_at, id
                """,
                (project_id,),
            )
            screening = _fetch_all(
                cursor,
                """
                SELECT s.id, p.id AS paper_id, p.title AS paper_title,
                       s.suggested_decision, s.human_decision, s.rationale_jsonb,
                       s.justification, s.exclusion_reason_code, s.reviewed_at
                FROM screening_decisions s
                JOIN deduplicated_papers p ON p.id = s.paper_id
                WHERE p.project_id = %s
                ORDER BY p.title, s.reviewed_at, s.id
                """,
                (project_id,),
            )
            reassessments = _fetch_all(
                cursor,
                """
                SELECT sr.id, sr.project_id, sr.screening_decision_id, sr.paper_id,
                       p.title AS paper_title, sr.action, sr.reason_code, sr.reason,
                       sr.previous_human_decision, sr.previous_justification,
                       sr.resulting_human_decision, sr.origin, sr.created_at
                FROM screening_reassessments sr
                JOIN deduplicated_papers p ON p.id = sr.paper_id
                WHERE sr.project_id = %s
                ORDER BY sr.created_at, sr.id
                """,
                (project_id,),
            )
            extractions = _fetch_all(
                cursor,
                """
                SELECT e.id, e.paper_id, p.title AS paper_title,
                       e.extraction_jsonb, e.schema_version, e.human_review_status,
                       e.human_review_jsonb, e.review_notes, e.extracted_at, e.reviewed_at
                FROM extracted_evidence e
                JOIN deduplicated_papers p ON p.id = e.paper_id
                WHERE p.project_id = %s
                ORDER BY p.title, e.id
                """,
                (project_id,),
            )
            evidence_sources = _fetch_all(
                cursor,
                """
                SELECT efs.id, efs.extraction_id, e.paper_id,
                       p.title AS paper_title, efs.field_name, efs.evidence_order,
                       efs.chunk_id, efs.page_number, efs.quote,
                       efs.quote_validated, efs.created_at
                FROM evidence_field_sources efs
                JOIN extracted_evidence e ON e.id = efs.extraction_id
                JOIN deduplicated_papers p ON p.id = e.paper_id
                WHERE p.project_id = %s
                ORDER BY p.title, efs.field_name, efs.evidence_order, efs.id
                """,
                (project_id,),
            )
            document_index = _fetch_all(
                cursor,
                """
                SELECT p.id AS paper_id, p.title AS paper_title,
                       COUNT(DISTINCT pc.id) FILTER (
                           WHERE pc.chunk_type LIKE 'full_text_part_%%'
                       ) AS full_text_chunks,
                       COUNT(DISTINCT em.id) AS embedding_records,
                       COALESCE(
                           array_remove(array_agg(DISTINCT em.model_name), NULL),
                           ARRAY[]::varchar[]
                       ) AS embedding_models,
                       COALESCE(
                           array_remove(array_agg(DISTINCT em.dimensions), NULL),
                           ARRAY[]::integer[]
                       ) AS embedding_dimensions
                FROM deduplicated_papers p
                LEFT JOIN paper_chunks pc ON pc.paper_id = p.id
                LEFT JOIN embeddings_metadata em ON em.chunk_id = pc.id
                WHERE p.project_id = %s
                GROUP BY p.id, p.title
                ORDER BY p.title, p.id
                """,
                (project_id,),
            )
            interactions = _fetch_all(
                cursor,
                """
                SELECT id, project_id, agent_name, input_jsonb, output_jsonb,
                       model_jsonb, created_at
                FROM agent_interactions
                WHERE project_id = %s
                ORDER BY created_at, id
                """,
                (project_id,),
            )
            evaluations = _fetch_all(
                cursor,
                """
                SELECT id, project_id, run_type, metrics_jsonb, params_jsonb, created_at
                FROM evaluation_runs
                WHERE project_id = %s
                ORDER BY created_at, id
                """,
                (project_id,),
            )
            golden_queries = _fetch_all(
                cursor,
                """
                SELECT id, project_id, question, expected_refusal, notes,
                       created_at, updated_at
                FROM rag_golden_queries
                WHERE project_id = %s
                ORDER BY created_at, id
                """,
                (project_id,),
            )
            golden_relevances = _fetch_all(
                cursor,
                """
                SELECT r.id, r.golden_query_id, r.paper_id, p.title AS paper_title,
                       r.page_number, r.relevance_grade, r.notes, r.created_at
                FROM rag_golden_relevances r
                JOIN rag_golden_queries q ON q.id = r.golden_query_id
                JOIN deduplicated_papers p ON p.id = r.paper_id
                WHERE q.project_id = %s AND p.project_id = %s
                ORDER BY r.golden_query_id, r.relevance_grade DESC, r.id
                """,
                (project_id, project_id),
            )
            golden_versions = _fetch_all(
                cursor,
                """
                SELECT id, project_id, version, set_jsonb, change_reason, created_at
                FROM rag_golden_set_versions
                WHERE project_id = %s
                ORDER BY version
                """,
                (project_id,),
            )
            prisma_snapshots = _fetch_all(
                cursor,
                """
                SELECT id, project_id, snapshot_version, protocol_version,
                       metrics_jsonb, source_counts_jsonb,
                       exclusion_reasons_jsonb, interpretation_jsonb, created_at
                FROM prisma_flow_snapshots
                WHERE project_id = %s
                ORDER BY snapshot_version
                """,
                (project_id,),
            )
        if hasattr(connection, "rollback"):
            connection.rollback()
    finally:
        connection.close()

    sources_by_extraction = {}
    for source in evidence_sources:
        sources_by_extraction.setdefault(str(source["extraction_id"]), []).append(source)
    for extraction in extractions:
        extraction["validated_sources"] = sources_by_extraction.get(str(extraction["id"]), [])

    relevances_by_query = {}
    for relevance in golden_relevances:
        relevances_by_query.setdefault(str(relevance["golden_query_id"]), []).append(relevance)
    for query in golden_queries:
        query["relevances"] = relevances_by_query.get(str(query["id"]), [])

    return _json_safe(
        {
            "project": project,
            "protocol_versions": protocol_versions,
            "searches": searches,
            "retrieved_records": retrieved_records,
            "papers": papers,
            "deduplication": deduplication,
            "screening": screening,
            "reassessments": reassessments,
            "extractions": extractions,
            "evidence_sources": evidence_sources,
            "document_index": document_index,
            "interactions": interactions,
            "evaluations": evaluations,
            "golden_queries": golden_queries,
            "golden_versions": golden_versions,
            "prisma_snapshots": prisma_snapshots,
        }
    )


def _matrix_rows(extractions: list[dict]) -> list[dict]:
    from backend.app.evidence_utils import achatar_extracao

    rows = []
    for extraction in extractions:
        reviewed = extraction.get("human_review_jsonb")
        values = reviewed or achatar_extracao(extraction.get("extraction_jsonb") or {})
        rows.append(
            {
                "paper_id": extraction.get("paper_id"),
                "titulo": extraction.get("paper_title"),
                "objetivo": values.get("objective", "Não reportado"),
                "metodo": values.get("method", "Não reportado"),
                "dataset_amostra": values.get("dataset", "Não reportado"),
                "metricas": values.get("metrics", []),
                "principais_resultados": values.get("main_results", "Não reportado"),
                "limitacoes": values.get("limitations", []),
                "status_revisao": extraction.get("human_review_status"),
                "fontes_literais": len(extraction.get("validated_sources") or []),
                "schema_version": extraction.get("schema_version"),
                "extraido_em": extraction.get("extracted_at"),
                "revisado_em": extraction.get("reviewed_at"),
            }
        )
    return rows


def _model_usage(interactions: list[dict]) -> list[dict]:
    groups = {}
    for interaction in interactions:
        model = interaction.get("model_jsonb") or {}
        canonical = json.dumps(_json_safe(model), ensure_ascii=False, sort_keys=True)
        key = (interaction.get("agent_name"), canonical)
        group = groups.setdefault(
            key,
            {
                "agent_name": interaction.get("agent_name"),
                "model_configuration": _json_safe(model),
                "interaction_count": 0,
                "first_used_at": interaction.get("created_at"),
                "last_used_at": interaction.get("created_at"),
            },
        )
        group["interaction_count"] += 1
        group["last_used_at"] = interaction.get("created_at")
    return list(groups.values())


def _latest_report(interactions: list[dict]) -> str | None:
    for interaction in reversed(interactions):
        if interaction.get("agent_name") != "report_agent":
            continue
        output = interaction.get("output_jsonb") or {}
        report = output.get("report_markdown")
        if report:
            return str(report)
    return None


def _counts(dataset: dict) -> dict:
    return {
        "protocol_versions": len(dataset.get("protocol_versions") or []),
        "search_executions": len(dataset.get("searches") or []),
        "retrieved_records": len(dataset.get("retrieved_records") or []),
        "unique_papers": len(dataset.get("papers") or []),
        "deduplication_decisions": len(dataset.get("deduplication") or []),
        "screening_decisions": len(dataset.get("screening") or []),
        "screening_reassessments": len(dataset.get("reassessments") or []),
        "evidence_extractions": len(dataset.get("extractions") or []),
        "literal_evidence_sources": len(dataset.get("evidence_sources") or []),
        "indexed_papers": sum(
            1
            for item in dataset.get("document_index") or []
            if int(item.get("full_text_chunks") or 0) > 0
        ),
        "agent_interactions": len(dataset.get("interactions") or []),
        "evaluation_runs": len(dataset.get("evaluations") or []),
        "golden_set_queries": len(dataset.get("golden_queries") or []),
        "prisma_snapshots": len(dataset.get("prisma_snapshots") or []),
    }


def _package_readme(dataset: dict, generated_at: str, counts: dict) -> bytes:
    project = dataset["project"]
    text = f"""# Pacote de reprodutibilidade da revisão sistemática

## Identificação

- Projeto: {project.get('title')}
- Identificador: `{project.get('id')}`
- Pergunta atual: {project.get('question')}
- Versão atual do protocolo: {project.get('protocol_version')}
- Gerado em: {generated_at}

## Escopo

Este ZIP é um retrato somente leitura das trilhas científicas e de auditoria do
projeto. Os arquivos JSON preservam estruturas completas; os CSV usam ponto e
vírgula e UTF-8 com BOM para facilitar a abertura no Excel.

O pacote não contém PDFs, texto integral dos chunks, vetores de embedding, chaves de
API, senhas, e-mails de contato da instalação ou a chave-mestra local. Trechos
literais já usados como evidência permanecem presentes para permitir a auditoria.

## Contagens

- Versões do protocolo: {counts['protocol_versions']}
- Execuções de busca/importação: {counts['search_executions']}
- Registros recuperados: {counts['retrieved_records']}
- Artigos únicos: {counts['unique_papers']}
- Decisões de triagem: {counts['screening_decisions']}
- Extrações de evidências: {counts['evidence_extractions']}
- Fontes literais: {counts['literal_evidence_sources']}
- Interações de agentes: {counts['agent_interactions']}
- Execuções de avaliação: {counts['evaluation_runs']}
- Snapshots PRISMA: {counts['prisma_snapshots']}

## Organização

- `01_projeto/`: projeto, protocolo atual e histórico imutável.
- `02_buscas/`: consultas, parâmetros públicos e registros recuperados.
- `03_selecao/`: artigos, deduplicação, triagem e reavaliações.
- `04_documentos/`: inventário de indexação, sem PDFs, chunks ou vetores.
- `05_evidencias/`: matriz, extrações e fontes literais rastreáveis.
- `06_avaliacao/`: PRISMA, Golden Set e execuções de avaliação/benchmark.
- `07_agentes/`: interações JSONB e configurações de modelos registradas.
- `08_relatorio/`: última síntese persistida, quando disponível.
- `manifest.json`: versão, escopo, contagens, tamanho e SHA-256 de cada arquivo.

## Verificação

Calcule o SHA-256 de cada arquivo e compare com `manifest.json`. O manifesto não
lista o próprio hash para evitar uma referência circular.

## Limitações

Este pacote documenta o estado do projeto no momento da exportação. Ele não substitui
o backup integral `.ragbackup`, não reinstala a aplicação e não transfere material
protegido por direitos autorais. A reprodução de chamadas externas também depende da
disponibilidade futura das APIs e dos modelos registrados.
"""
    return text.encode("utf-8")


def _slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or "projeto"))
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "-", ascii_value).strip("-")[:60] or "projeto"


def build_reproducibility_package(dataset: dict, generated_at: str | None = None) -> dict:
    """Monta o ZIP a partir de um snapshot já coletado, facilitando testes puros."""
    dataset = _json_safe(dataset)
    project = dataset.get("project") or {}
    if not project.get("id") or not project.get("title"):
        raise ReproducibilityPackageError("Snapshot do projeto está incompleto.")
    generated_at = generated_at or datetime.now(timezone.utc).isoformat()
    counts = _counts(dataset)
    matrix = _matrix_rows(dataset.get("extractions") or [])
    models = _model_usage(dataset.get("interactions") or [])
    latest_report = _latest_report(dataset.get("interactions") or [])

    files = {
        "README.md": _package_readme(dataset, generated_at, counts),
        "01_projeto/projeto.json": _json_bytes(project),
        "01_projeto/protocolo_atual.json": _json_bytes(
            {
                "project_id": project.get("id"),
                "version": project.get("protocol_version"),
                "question": project.get("question"),
                "criteria": project.get("criteria_jsonb") or {},
                "status": project.get("status"),
            }
        ),
        "01_projeto/historico_protocolos.json": _json_bytes(dataset.get("protocol_versions") or []),
        "01_projeto/historico_protocolos.csv": _csv_bytes(dataset.get("protocol_versions") or []),
        "02_buscas/execucoes.json": _json_bytes(dataset.get("searches") or []),
        "02_buscas/execucoes.csv": _csv_bytes(dataset.get("searches") or []),
        "02_buscas/registros_recuperados.json": _json_bytes(dataset.get("retrieved_records") or []),
        "03_selecao/artigos_unicos.json": _json_bytes(dataset.get("papers") or []),
        "03_selecao/artigos_unicos.csv": _csv_bytes(dataset.get("papers") or []),
        "03_selecao/deduplicacao.json": _json_bytes(dataset.get("deduplication") or []),
        "03_selecao/deduplicacao.csv": _csv_bytes(dataset.get("deduplication") or []),
        "03_selecao/triagem.json": _json_bytes(dataset.get("screening") or []),
        "03_selecao/triagem.csv": _csv_bytes(dataset.get("screening") or []),
        "03_selecao/reavaliacoes.json": _json_bytes(dataset.get("reassessments") or []),
        "03_selecao/reavaliacoes.csv": _csv_bytes(dataset.get("reassessments") or []),
        "04_documentos/inventario_indexacao.json": _json_bytes(dataset.get("document_index") or []),
        "04_documentos/inventario_indexacao.csv": _csv_bytes(dataset.get("document_index") or []),
        "05_evidencias/matriz_evidencias.csv": _csv_bytes(matrix),
        "05_evidencias/extracoes_rastreaveis.json": _json_bytes(dataset.get("extractions") or []),
        "05_evidencias/fontes_literais.csv": _csv_bytes(dataset.get("evidence_sources") or []),
        "06_avaliacao/prisma_snapshots.json": _json_bytes(dataset.get("prisma_snapshots") or []),
        "06_avaliacao/golden_set_atual.json": _json_bytes(dataset.get("golden_queries") or []),
        "06_avaliacao/golden_set_versoes.json": _json_bytes(dataset.get("golden_versions") or []),
        "06_avaliacao/execucoes.json": _json_bytes(dataset.get("evaluations") or []),
        "07_agentes/interacoes.json": _json_bytes(dataset.get("interactions") or []),
        "07_agentes/modelos_utilizados.json": _json_bytes(models),
    }
    if latest_report:
        files["08_relatorio/relatorio_final.md"] = latest_report.encode("utf-8")

    manifest_files = [
        {
            "path": path,
            "size": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        }
        for path, content in sorted(files.items())
    ]
    manifest = {
        "format": PACKAGE_FORMAT,
        "version": PACKAGE_VERSION,
        "generated_at": generated_at,
        "project": {
            "id": project.get("id"),
            "title": project.get("title"),
            "protocol_version": project.get("protocol_version"),
        },
        "scope": {
            "project_only": True,
            "read_only_snapshot": True,
            "secrets_excluded": True,
            "pdfs_excluded": True,
            "full_text_chunks_excluded": True,
            "embeddings_excluded": True,
        },
        "counts": counts,
        "integrity": {"algorithm": "SHA-256", "files": manifest_files},
    }
    files["manifest.json"] = _json_bytes(manifest)

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path, content in sorted(files.items()):
            archive.writestr(path, content)
    data = output.getvalue()
    timestamp = generated_at.replace("-", "").replace(":", "")[:15]
    filename = f"pacote-reprodutibilidade-{_slug(project['title'])}-{timestamp}.zip"
    return {
        "data": data,
        "filename": filename,
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "manifest": manifest,
    }


def generate_reproducibility_package(project_id, connection_factory=None) -> dict:
    dataset = _collect_project_data(project_id, connection_factory=connection_factory)
    return build_reproducibility_package(dataset)
