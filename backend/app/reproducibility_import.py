"""Validação e importação transacional de pacotes de reprodutibilidade."""

from __future__ import annotations

import hashlib
import io
import json
import re
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import PurePosixPath

from psycopg2.extras import Json

from backend.app.reproducibility_package import (
    PACKAGE_FORMAT,
    PACKAGE_VERSION,
    ReproducibilityPackageError,
    _counts,
)


MAX_PACKAGE_BYTES = 100 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 300 * 1024 * 1024
MAX_MEMBER_BYTES = 100 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 100

REQUIRED_JSON_FILES = {
    "01_projeto/projeto.json": "project",
    "01_projeto/historico_protocolos.json": "protocol_versions",
    "02_buscas/execucoes.json": "searches",
    "02_buscas/registros_recuperados.json": "retrieved_records",
    "03_selecao/artigos_unicos.json": "papers",
    "03_selecao/deduplicacao.json": "deduplication",
    "03_selecao/triagem.json": "screening",
    "03_selecao/reavaliacoes.json": "reassessments",
    "04_documentos/inventario_indexacao.json": "document_index",
    "05_evidencias/extracoes_rastreaveis.json": "extractions",
    "06_avaliacao/instrumentos_metodologicos.json": "methodological_instruments",
    "06_avaliacao/avaliacoes_metodologicas.json": "methodological_assessments",
    "06_avaliacao/prisma_snapshots.json": "prisma_snapshots",
    "06_avaliacao/golden_set_atual.json": "golden_queries",
    "06_avaliacao/golden_set_versoes.json": "golden_versions",
    "06_avaliacao/execucoes.json": "evaluations",
    "07_agentes/interacoes.json": "interactions",
}

OPTIONAL_JSON_FILES = {
    "02_buscas/artigos_sentinela.json": "calibration_sentinels",
    "02_buscas/calibracoes.json": "calibration_runs",
    "02_buscas/calibracao_correspondencias.json": "calibration_matches",
    "02_buscas/revisoes_press.json": "press_reviews",
}

LIST_DATASETS = (set(REQUIRED_JSON_FILES.values()) | set(OPTIONAL_JSON_FILES.values())) - {"project"}
UUID_PATTERN = re.compile(
    r"(?i)\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b"
)


class ReproducibilityImportError(ReproducibilityPackageError):
    """Pacote inválido ou falha atômica durante sua importação."""


def _safe_member_name(name: str) -> str:
    if not name or "\\" in name:
        raise ReproducibilityImportError("O ZIP contém um caminho de arquivo inválido.")
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or ":" in path.parts[0]:
        raise ReproducibilityImportError("O ZIP contém um caminho de arquivo inseguro.")
    normalized = str(path)
    if normalized != name or name.endswith("/"):
        raise ReproducibilityImportError("O ZIP contém uma entrada não suportada.")
    return normalized


def _read_json(archive: zipfile.ZipFile, path: str):
    try:
        return json.loads(archive.read(path).decode("utf-8"))
    except (KeyError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ReproducibilityImportError(
            f"O arquivo obrigatório {path} está ausente ou não contém JSON válido."
        ) from error


def _flatten_embedded(dataset: dict) -> None:
    evidence_sources = []
    for extraction in dataset.get("extractions", []):
        normalized = []
        for source in extraction.get("validated_sources", []) or []:
            source = dict(source)
            source.setdefault("extraction_id", extraction.get("id"))
            source.setdefault("paper_id", extraction.get("paper_id"))
            if not source.get("chunk_id"):
                raise ReproducibilityImportError(
                    "Uma fonte literal não possui o identificador do trecho."
                )
            normalized.append(source)
        extraction["validated_sources"] = normalized
        evidence_sources.extend(normalized)
    dataset["evidence_sources"] = evidence_sources

    methodological_sources = []
    for assessment in dataset.get("methodological_assessments", []):
        normalized = []
        for source in assessment.get("sources", []) or []:
            source = dict(source)
            source.setdefault("assessment_id", assessment.get("id"))
            source.setdefault("paper_id", assessment.get("paper_id"))
            if not source.get("chunk_id"):
                raise ReproducibilityImportError(
                    "Uma fonte metodológica não possui o identificador do trecho."
                )
            normalized.append(source)
        assessment["sources"] = normalized
        methodological_sources.extend(normalized)
    dataset["methodological_sources"] = methodological_sources

    golden_relevances = []
    for query in dataset.get("golden_queries", []):
        normalized = []
        for relevance in query.get("relevances", []) or []:
            relevance = dict(relevance)
            relevance.setdefault("golden_query_id", query.get("id"))
            normalized.append(relevance)
        query["relevances"] = normalized
        golden_relevances.extend(normalized)
    dataset["golden_relevances"] = golden_relevances


def _validate_counts(dataset: dict, manifest: dict) -> None:
    calculated = _counts(dataset)
    declared = manifest.get("counts") or {}
    for key, value in calculated.items():
        if key in declared and int(declared[key] or 0) != int(value or 0):
            raise ReproducibilityImportError(
                f"A contagem '{key}' diverge entre o manifesto e os dados."
            )


def validate_reproducibility_package(data: bytes) -> dict:
    """Valida estrutura, formato, limites, hashes e coerência do pacote."""
    data = bytes(data or b"")
    if not data:
        raise ReproducibilityImportError("Selecione um pacote ZIP para validar.")
    if len(data) > MAX_PACKAGE_BYTES:
        raise ReproducibilityImportError("O pacote excede o limite de 100 MB.")

    try:
        archive = zipfile.ZipFile(io.BytesIO(data), "r")
    except zipfile.BadZipFile as error:
        raise ReproducibilityImportError("O arquivo não é um ZIP válido.") from error

    with archive:
        infos = archive.infolist()
        if not infos or len(infos) > MAX_ARCHIVE_MEMBERS:
            raise ReproducibilityImportError("O ZIP possui uma quantidade inválida de arquivos.")
        names = [_safe_member_name(info.filename) for info in infos]
        if len(names) != len(set(names)):
            raise ReproducibilityImportError("O ZIP contém nomes de arquivos duplicados.")
        if any(info.flag_bits & 0x1 for info in infos):
            raise ReproducibilityImportError("Arquivos ZIP criptografados não são aceitos.")
        if any(info.file_size > MAX_MEMBER_BYTES for info in infos):
            raise ReproducibilityImportError("Um arquivo interno excede o limite de 100 MB.")
        if sum(info.file_size for info in infos) > MAX_UNCOMPRESSED_BYTES:
            raise ReproducibilityImportError(
                "O conteúdo descompactado excede o limite de segurança de 300 MB."
            )
        if "manifest.json" not in names:
            raise ReproducibilityImportError("O pacote não contém manifest.json.")

        manifest = _read_json(archive, "manifest.json")
        if manifest.get("format") != PACKAGE_FORMAT:
            raise ReproducibilityImportError("O formato do pacote não é reconhecido.")
        if manifest.get("version") != PACKAGE_VERSION:
            raise ReproducibilityImportError(
                f"A versão {manifest.get('version')} do pacote não é suportada."
            )
        scope = manifest.get("scope") or {}
        required_scope = {
            "project_only",
            "read_only_snapshot",
            "secrets_excluded",
            "pdfs_excluded",
            "full_text_chunks_excluded",
            "embeddings_excluded",
        }
        if not all(scope.get(key) is True for key in required_scope):
            raise ReproducibilityImportError(
                "O escopo do pacote não garante uma importação seletiva e sem segredos."
            )

        if (manifest.get("integrity") or {}).get("algorithm") != "SHA-256":
            raise ReproducibilityImportError(
                "O algoritmo de integridade do pacote não é suportado."
            )
        integrity_entries = (manifest.get("integrity") or {}).get("files") or []
        expected = {}
        for entry in integrity_entries:
            path = _safe_member_name(str(entry.get("path") or ""))
            if path in expected or path == "manifest.json":
                raise ReproducibilityImportError("O manifesto contém entradas duplicadas.")
            expected[path] = entry
        actual = set(names) - {"manifest.json"}
        if actual != set(expected):
            raise ReproducibilityImportError(
                "Os arquivos do ZIP não correspondem exatamente ao manifesto."
            )
        if not set(REQUIRED_JSON_FILES).issubset(actual):
            raise ReproducibilityImportError("O pacote está incompleto para importação.")

        for path, entry in expected.items():
            content = archive.read(path)
            if len(content) != int(entry.get("size", -1)):
                raise ReproducibilityImportError(
                    f"O tamanho de {path} não corresponde ao manifesto."
                )
            if hashlib.sha256(content).hexdigest() != entry.get("sha256"):
                raise ReproducibilityImportError(
                    f"A integridade SHA-256 de {path} não foi confirmada."
                )

        dataset = {
            target: _read_json(archive, path)
            for path, target in REQUIRED_JSON_FILES.items()
        }
        for path, target in OPTIONAL_JSON_FILES.items():
            dataset[target] = _read_json(archive, path) if path in actual else []

    if not isinstance(dataset["project"], dict):
        raise ReproducibilityImportError("Os dados do projeto possuem formato inválido.")
    for name in LIST_DATASETS:
        if not isinstance(dataset[name], list):
            raise ReproducibilityImportError(f"O conjunto '{name}' deveria ser uma lista.")
        if any(not isinstance(row, dict) for row in dataset[name]):
            raise ReproducibilityImportError(
                f"O conjunto '{name}' contém um registro com formato inválido."
            )

    project = dataset["project"]
    manifest_project = manifest.get("project") or {}
    if not project.get("id") or not str(project.get("title") or "").strip():
        raise ReproducibilityImportError("A identificação do projeto está incompleta.")
    if str(project["id"]) != str(manifest_project.get("id")):
        raise ReproducibilityImportError(
            "O identificador do projeto diverge entre manifesto e conteúdo."
        )

    _flatten_embedded(dataset)
    _validate_counts(dataset, manifest)
    warnings = [
        "PDFs, texto integral e embeddings não fazem parte do pacote; os artigos incluídos voltarão a aguardar seus PDFs.",
        "Fontes literais serão preservadas como trechos de auditoria e não participarão da busca do RAG.",
        "Credenciais e configurações secretas permanecem as da instalação de destino.",
    ]
    return {
        "manifest": manifest,
        "dataset": dataset,
        "sha256": hashlib.sha256(data).hexdigest(),
        "size": len(data),
        "warnings": warnings,
    }


def _new_id_map(rows: list[dict], label: str, require_id: bool = True) -> dict[str, str]:
    result = {}
    for index, row in enumerate(rows):
        old_id = row.get("id")
        if old_id is None and not require_id:
            old_id = f"__{label}_{index}"
            row["_import_source_id"] = old_id
        if old_id is None:
            raise ReproducibilityImportError(f"Um registro de {label} não possui identificador.")
        key = str(old_id)
        if key in result:
            raise ReproducibilityImportError(f"Há identificadores duplicados em {label}.")
        result[key] = str(uuid.uuid4())
    return result


def _mapped(mapping: dict[str, str], value, label: str, required: bool = True):
    if value is None and not required:
        return None
    result = mapping.get(str(value))
    if result is None and required:
        raise ReproducibilityImportError(f"Referência ausente para {label}: {value}")
    return result


def _remap_json(value, mapping: dict[str, str]):
    if isinstance(value, dict):
        return {str(key): _remap_json(item, mapping) for key, item in value.items()}
    if isinstance(value, list):
        return [_remap_json(item, mapping) for item in value]
    if isinstance(value, str):
        if value in mapping:
            return mapping[value]
        return UUID_PATTERN.sub(lambda match: mapping.get(match.group(0), match.group(0)), value)
    return value


def _source_id(row: dict, label: str) -> str:
    return str(row.get("id") or row.get("_import_source_id") or label)


def _prepare_import(dataset: dict, title: str | None = None) -> dict:
    source_project = dataset["project"]
    source_project_id = str(source_project["id"])
    new_project_id = str(uuid.uuid4())
    final_title = str(title or f"{source_project['title']} — importado").strip()
    if len(final_title) < 3 or len(final_title) > 255:
        raise ReproducibilityImportError("O título deve possuir entre 3 e 255 caracteres.")

    maps = {
        "project": {source_project_id: new_project_id},
        "protocol": _new_id_map(dataset["protocol_versions"], "protocolos", False),
        "search": _new_id_map(dataset["searches"], "buscas", False),
        "calibration_sentinel": _new_id_map(
            dataset["calibration_sentinels"], "artigos sentinela", False
        ),
        "calibration_run": _new_id_map(
            dataset["calibration_runs"], "calibrações de busca", False
        ),
        "calibration_match": _new_id_map(
            dataset["calibration_matches"], "correspondências de calibração", False
        ),
        "press_review": _new_id_map(
            dataset["press_reviews"], "revisões PRESS", False
        ),
        "record": _new_id_map(dataset["retrieved_records"], "registros", False),
        "paper": _new_id_map(dataset["papers"], "artigos"),
        "dedup": _new_id_map(dataset["deduplication"], "deduplicações", False),
        "screening": _new_id_map(dataset["screening"], "triagens", False),
        "reassessment": _new_id_map(dataset["reassessments"], "reavaliações", False),
        "extraction": _new_id_map(dataset["extractions"], "extrações", False),
        "instrument": _new_id_map(dataset["methodological_instruments"], "instrumentos", False),
        "assessment": _new_id_map(dataset["methodological_assessments"], "avaliações", False),
        "interaction": _new_id_map(dataset["interactions"], "interações", False),
        "evaluation": _new_id_map(dataset["evaluations"], "execuções", False),
        "golden_query": _new_id_map(dataset["golden_queries"], "perguntas Golden Set", False),
        "golden_version": _new_id_map(dataset["golden_versions"], "versões Golden Set", False),
        "prisma": _new_id_map(dataset["prisma_snapshots"], "snapshots PRISMA", False),
    }

    chunk_map = {}
    chunk_details = {}
    all_sources = dataset["evidence_sources"] + dataset["methodological_sources"]
    for source in all_sources:
        old_chunk = str(source["chunk_id"])
        if old_chunk not in chunk_map:
            chunk_map[old_chunk] = str(uuid.uuid4())
        quote = str(source.get("quote") or "Trecho literal importado para auditoria.").strip()
        current = chunk_details.get(old_chunk)
        if current is None or len(quote) > len(current["quote"]):
            chunk_details[old_chunk] = {
                "quote": quote,
                "paper_id": source.get("paper_id"),
                "page_number": source.get("page_number"),
            }
    maps["chunk"] = chunk_map
    combined_map = {}
    for mapping in maps.values():
        combined_map.update(mapping)

    criteria = dict(source_project.get("criteria_jsonb") or {})
    criteria.pop("_demo", None)
    criteria = _remap_json(criteria, combined_map)
    criteria["_import"] = {
        "format": PACKAGE_FORMAT,
        "version": PACKAGE_VERSION,
        "source_project_id": source_project_id,
        "source_generated_at": dataset.get("_generated_at"),
        "package_sha256": dataset.get("_package_sha256"),
        "imported_at": datetime.now(timezone.utc).isoformat(),
    }
    return {
        "source_project_id": source_project_id,
        "project_id": new_project_id,
        "title": final_title,
        "criteria": criteria,
        "maps": maps,
        "combined_map": combined_map,
        "chunk_details": chunk_details,
    }


def _insert_import(cursor, dataset: dict, prepared: dict) -> None:
    maps = prepared["maps"]
    remap = prepared["combined_map"]
    project = dataset["project"]
    project_id = prepared["project_id"]

    cursor.execute(
        """
        INSERT INTO review_projects
            (id, title, question, criteria_jsonb, status, protocol_version)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (
            project_id,
            prepared["title"],
            project.get("question") or "Pergunta não informada no pacote",
            Json(prepared["criteria"]),
            project.get("status") or "search_ready",
            int(project.get("protocol_version") or 1),
        ),
    )

    protocols = dataset["protocol_versions"] or [
        {
            "_import_source_id": "__protocol_default",
            "version": int(project.get("protocol_version") or 1),
            "question": project.get("question") or "Pergunta não informada no pacote",
            "criteria_jsonb": prepared["criteria"],
            "change_reason": "Protocolo recuperado do pacote de reprodutibilidade",
        }
    ]
    if "__protocol_default" not in maps["protocol"] and not dataset["protocol_versions"]:
        maps["protocol"]["__protocol_default"] = str(uuid.uuid4())
    for row in protocols:
        cursor.execute(
            """
            INSERT INTO review_protocol_versions
                (id, project_id, version, question, criteria_jsonb, change_reason, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, COALESCE(%s::timestamptz, CURRENT_TIMESTAMP))
            """,
            (
                maps["protocol"][_source_id(row, "__protocol_default")],
                project_id,
                int(row.get("version") or 1),
                row.get("question") or project.get("question") or "Pergunta não informada",
                Json(_remap_json(row.get("criteria_jsonb") or {}, remap)),
                row.get("change_reason") or "Importado do pacote de reprodutibilidade",
                row.get("created_at"),
            ),
        )

    for row in dataset["searches"]:
        cursor.execute(
            """
            INSERT INTO search_queries
                (id, project_id, source, query_text, query_jsonb, executed_at)
            VALUES (%s, %s, %s, %s, %s, COALESCE(%s::timestamptz, CURRENT_TIMESTAMP))
            """,
            (
                maps["search"][_source_id(row, "search")], project_id,
                row.get("source") or "imported_package", row.get("query_text") or "",
                Json(_remap_json(row.get("query_jsonb") or {}, remap)), row.get("executed_at"),
            ),
        )

    for row in dataset["calibration_sentinels"]:
        cursor.execute(
            """
            INSERT INTO search_calibration_sentinels
                (id, project_id, title, canonical_doi, notes, is_active,
                 created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s,
                    COALESCE(%s::timestamptz, CURRENT_TIMESTAMP),
                    COALESCE(%s::timestamptz, CURRENT_TIMESTAMP))
            """,
            (
                maps["calibration_sentinel"][_source_id(row, "calibration_sentinel")],
                project_id, row.get("title") or "Artigo sentinela importado",
                row.get("canonical_doi"), row.get("notes"), bool(row.get("is_active", True)),
                row.get("created_at"), row.get("updated_at"),
            ),
        )

    for row in dataset["calibration_runs"]:
        cursor.execute(
            """
            INSERT INTO search_calibration_runs
                (id, project_id, protocol_version, protocol_fingerprint,
                 max_results_per_source, status, queries_jsonb,
                 sentinel_snapshot_jsonb, source_results_jsonb, summary_jsonb, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    COALESCE(%s::timestamptz, CURRENT_TIMESTAMP))
            """,
            (
                maps["calibration_run"][_source_id(row, "calibration_run")], project_id,
                int(row.get("protocol_version") or 1),
                row.get("protocol_fingerprint") or ("0" * 64),
                int(row.get("max_results_per_source") or 100),
                row.get("status") or "completed",
                Json(_remap_json(row.get("queries_jsonb") or {}, remap)),
                Json(_remap_json(row.get("sentinel_snapshot_jsonb") or [], remap)),
                Json(_remap_json(row.get("source_results_jsonb") or {}, remap)),
                Json(_remap_json(row.get("summary_jsonb") or {}, remap)),
                row.get("created_at"),
            ),
        )

    for row in dataset["calibration_matches"]:
        cursor.execute(
            """
            INSERT INTO search_calibration_matches
                (id, run_id, sentinel_id, source_code, result_rank, match_method,
                 similarity_score, matched_title, matched_doi, evidence_jsonb, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    COALESCE(%s::timestamptz, CURRENT_TIMESTAMP))
            """,
            (
                maps["calibration_match"][_source_id(row, "calibration_match")],
                _mapped(maps["calibration_run"], row.get("run_id"), "execução de calibração"),
                _mapped(
                    maps["calibration_sentinel"], row.get("sentinel_id"),
                    "artigo sentinela", False,
                ),
                row.get("source_code") or "openalex", int(row.get("result_rank") or 1),
                row.get("match_method") or "title_exact",
                row.get("similarity_score") or 0,
                row.get("matched_title") or "Título importado", row.get("matched_doi"),
                Json(_remap_json(row.get("evidence_jsonb") or {}, remap)),
                row.get("created_at"),
            ),
        )

    for row in dataset["press_reviews"]:
        cursor.execute(
            """
            INSERT INTO press_search_reviews
                (id, project_id, protocol_version, protocol_fingerprint,
                 checklist_jsonb, overall_decision, reviewer_name, review_notes,
                 reviewed_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s,
                    COALESCE(%s::timestamptz, CURRENT_TIMESTAMP),
                    COALESCE(%s::timestamptz, CURRENT_TIMESTAMP))
            """,
            (
                maps["press_review"][_source_id(row, "press_review")], project_id,
                int(row.get("protocol_version") or 1),
                row.get("protocol_fingerprint") or ("0" * 64),
                Json(_remap_json(row.get("checklist_jsonb") or [], remap)),
                row.get("overall_decision") or "changes_requested",
                row.get("reviewer_name"), row.get("review_notes"),
                row.get("reviewed_at"), row.get("updated_at"),
            ),
        )

    for row in dataset["retrieved_records"]:
        cursor.execute(
            """
            INSERT INTO retrieved_records
                (id, project_id, search_query_id, source, external_id, doi,
                 metadata_jsonb, raw_jsonb, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s,
                    COALESCE(%s::timestamptz, CURRENT_TIMESTAMP))
            """,
            (
                maps["record"][_source_id(row, "record")], project_id,
                _mapped(maps["search"], row.get("search_query_id"), "busca", False),
                row.get("source") or "imported_package", row.get("external_id"), row.get("doi"),
                Json(_remap_json(row.get("metadata_jsonb") or {}, remap)),
                Json(_remap_json(row.get("raw_jsonb") or {}, remap)), row.get("created_at"),
            ),
        )

    for row in dataset["papers"]:
        cursor.execute(
            """
            INSERT INTO deduplicated_papers
                (id, project_id, canonical_doi, title, abstract,
                 merged_sources_jsonb, created_at)
            VALUES (%s, %s, %s, %s, %s, %s,
                    COALESCE(%s::timestamptz, CURRENT_TIMESTAMP))
            """,
            (
                maps["paper"][_source_id(row, "paper")], project_id, row.get("canonical_doi"),
                row.get("title") or "Artigo sem título", row.get("abstract"),
                Json(_remap_json(row.get("merged_sources_jsonb") or {}, remap)), row.get("created_at"),
            ),
        )

    for row in dataset["deduplication"]:
        cursor.execute(
            """
            INSERT INTO deduplication_decisions
                (id, project_id, retrieved_record_id, candidate_paper_id, result_paper_id,
                 rule_code, similarity_score, system_action, explanation, evidence_jsonb,
                 incoming_record_jsonb, review_status, human_decision,
                 review_justification, created_at, reviewed_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    COALESCE(%s::timestamptz, CURRENT_TIMESTAMP), %s::timestamptz)
            """,
            (
                maps["dedup"][_source_id(row, "dedup")], project_id,
                _mapped(maps["record"], row.get("retrieved_record_id"), "registro recuperado"),
                _mapped(maps["paper"], row.get("candidate_paper_id"), "artigo candidato", False),
                _mapped(maps["paper"], row.get("result_paper_id"), "artigo resultante", False),
                row.get("rule_code") or "no_candidate", row.get("similarity_score") or 0,
                row.get("system_action") or "auto_create", row.get("explanation") or "Importado",
                Json(_remap_json(row.get("evidence_jsonb") or {}, remap)),
                Json(_remap_json(row.get("incoming_record_jsonb") or {}, remap)),
                row.get("review_status") or "automatic", row.get("human_decision"),
                row.get("review_justification"), row.get("created_at"), row.get("reviewed_at"),
            ),
        )

    for row in dataset["screening"]:
        cursor.execute(
            """
            INSERT INTO screening_decisions
                (id, paper_id, suggested_decision, human_decision, rationale_jsonb,
                 justification, exclusion_reason_code, reviewed_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s,
                    COALESCE(%s::timestamp, CURRENT_TIMESTAMP))
            """,
            (
                maps["screening"][_source_id(row, "screening")],
                _mapped(maps["paper"], row.get("paper_id"), "artigo da triagem"),
                row.get("suggested_decision"), row.get("human_decision"),
                Json(_remap_json(row.get("rationale_jsonb") or {}, remap)),
                row.get("justification"), row.get("exclusion_reason_code"), row.get("reviewed_at"),
            ),
        )

    for row in dataset["reassessments"]:
        cursor.execute(
            """
            INSERT INTO screening_reassessments
                (id, project_id, screening_decision_id, paper_id, action, reason_code,
                 reason, previous_human_decision, previous_justification,
                 resulting_human_decision, origin, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    COALESCE(%s::timestamptz, CURRENT_TIMESTAMP))
            """,
            (
                maps["reassessment"][_source_id(row, "reassessment")], project_id,
                _mapped(maps["screening"], row.get("screening_decision_id"), "decisão de triagem"),
                _mapped(maps["paper"], row.get("paper_id"), "artigo reavaliado"),
                row.get("action"), row.get("reason_code"), row.get("reason"),
                row.get("previous_human_decision"), row.get("previous_justification"),
                row.get("resulting_human_decision"), row.get("origin") or "pdf_management",
                row.get("created_at"),
            ),
        )

    for old_chunk, new_chunk in maps["chunk"].items():
        detail = prepared["chunk_details"][old_chunk]
        cursor.execute(
            """
            INSERT INTO paper_chunks (id, paper_id, chunk_type, chunk_text, metadata_jsonb)
            VALUES (%s, %s, 'imported_evidence_quote', %s, %s)
            """,
            (
                new_chunk, _mapped(maps["paper"], detail.get("paper_id"), "artigo da fonte"),
                detail["quote"], Json({
                    "source_type": "reproducibility_package", "audit_only": True,
                    "original_chunk_id": old_chunk, "page_start": detail.get("page_number"),
                    "page_end": detail.get("page_number"),
                    "source_project_id": prepared["source_project_id"],
                }),
            ),
        )

    for row in dataset["extractions"]:
        cursor.execute(
            """
            INSERT INTO extracted_evidence
                (id, paper_id, extraction_jsonb, schema_version, human_review_status,
                 human_review_jsonb, review_notes, extracted_at, reviewed_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s,
                    COALESCE(%s::timestamptz, CURRENT_TIMESTAMP), %s::timestamptz)
            """,
            (
                maps["extraction"][_source_id(row, "extraction")],
                _mapped(maps["paper"], row.get("paper_id"), "artigo da extração"),
                Json(_remap_json(row.get("extraction_jsonb") or {}, remap)),
                row.get("schema_version") or "traceable-v1",
                row.get("human_review_status") or "pending",
                Json(_remap_json(row.get("human_review_jsonb"), remap)) if row.get("human_review_jsonb") is not None else None,
                row.get("review_notes"), row.get("extracted_at"), row.get("reviewed_at"),
            ),
        )
        for order, source in enumerate(row.get("validated_sources") or []):
            cursor.execute(
                """
                INSERT INTO evidence_field_sources
                    (id, extraction_id, field_name, evidence_order, chunk_id,
                     page_number, quote, quote_validated, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s,
                        COALESCE(%s::timestamptz, CURRENT_TIMESTAMP))
                """,
                (
                    str(uuid.uuid4()), maps["extraction"][_source_id(row, "extraction")],
                    source.get("field_name") or "imported_evidence",
                    int(source.get("evidence_order", order)),
                    maps["chunk"][str(source["chunk_id"])],
                    source.get("page_number"), source.get("quote") or "Trecho importado",
                    bool(source.get("quote_validated", True)), source.get("created_at"),
                ),
            )

    for row in dataset["methodological_instruments"]:
        cursor.execute(
            """
            INSERT INTO methodological_assessment_instruments
                (id, project_id, version, name, description, schema_version,
                 domains_jsonb, change_reason, is_active, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s,
                    COALESCE(%s::timestamptz, CURRENT_TIMESTAMP))
            """,
            (
                maps["instrument"][_source_id(row, "instrument")], project_id,
                int(row.get("version") or 1), row.get("name") or "Instrumento importado",
                row.get("description") or "Instrumento recuperado do pacote de reprodutibilidade.",
                row.get("schema_version") or "generic-methodological-v1",
                Json(_remap_json(row.get("domains_jsonb") or [], remap)),
                row.get("change_reason") or "Importado do pacote de reprodutibilidade",
                bool(row.get("is_active")), row.get("created_at"),
            ),
        )

    for row in dataset["methodological_assessments"]:
        cursor.execute(
            """
            INSERT INTO methodological_assessments
                (id, project_id, paper_id, instrument_id, ai_suggestion_jsonb,
                 human_assessment_jsonb, overall_rating, review_status, review_notes,
                 created_at, updated_at, reviewed_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s,
                    COALESCE(%s::timestamptz, CURRENT_TIMESTAMP),
                    COALESCE(%s::timestamptz, CURRENT_TIMESTAMP), %s::timestamptz)
            """,
            (
                maps["assessment"][_source_id(row, "assessment")], project_id,
                _mapped(maps["paper"], row.get("paper_id"), "artigo da avaliação"),
                _mapped(maps["instrument"], row.get("instrument_id"), "instrumento"),
                Json(_remap_json(row.get("ai_suggestion_jsonb"), remap)) if row.get("ai_suggestion_jsonb") is not None else None,
                Json(_remap_json(row.get("human_assessment_jsonb"), remap)) if row.get("human_assessment_jsonb") is not None else None,
                row.get("overall_rating"), row.get("review_status") or "pending",
                row.get("review_notes"), row.get("created_at"), row.get("updated_at"),
                row.get("reviewed_at"),
            ),
        )
        for order, source in enumerate(row.get("sources") or []):
            cursor.execute(
                """
                INSERT INTO methodological_assessment_sources
                    (id, assessment_id, domain_code, evidence_order, chunk_id,
                     page_number, quote, quote_validated, human_validated, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s,
                        COALESCE(%s::timestamptz, CURRENT_TIMESTAMP))
                """,
                (
                    str(uuid.uuid4()), maps["assessment"][_source_id(row, "assessment")],
                    source.get("domain_code") or "imported_domain",
                    int(source.get("evidence_order", order)),
                    maps["chunk"][str(source["chunk_id"])],
                    source.get("page_number"), source.get("quote") or "Trecho importado",
                    bool(source.get("quote_validated", True)), bool(source.get("human_validated")),
                    source.get("created_at"),
                ),
            )

    for row in dataset["interactions"]:
        cursor.execute(
            """
            INSERT INTO agent_interactions
                (id, project_id, agent_name, input_jsonb, output_jsonb, model_jsonb, created_at)
            VALUES (%s, %s, %s, %s, %s, %s,
                    COALESCE(%s::timestamptz, CURRENT_TIMESTAMP))
            """,
            (
                maps["interaction"][_source_id(row, "interaction")], project_id,
                row.get("agent_name") or "imported_agent",
                Json(_remap_json(row.get("input_jsonb") or {}, remap)),
                Json(_remap_json(row.get("output_jsonb") or {}, remap)),
                Json(_remap_json(row.get("model_jsonb") or {}, remap)), row.get("created_at"),
            ),
        )

    for row in dataset["evaluations"]:
        cursor.execute(
            """
            INSERT INTO evaluation_runs
                (id, project_id, run_type, metrics_jsonb, params_jsonb, created_at)
            VALUES (%s, %s, %s, %s, %s, COALESCE(%s::timestamptz, CURRENT_TIMESTAMP))
            """,
            (
                maps["evaluation"][_source_id(row, "evaluation")], project_id,
                row.get("run_type") or "imported", Json(_remap_json(row.get("metrics_jsonb") or {}, remap)),
                Json(_remap_json(row.get("params_jsonb") or {}, remap)), row.get("created_at"),
            ),
        )

    for row in dataset["golden_queries"]:
        query_id = maps["golden_query"][_source_id(row, "golden_query")]
        cursor.execute(
            """
            INSERT INTO rag_golden_queries
                (id, project_id, question, expected_refusal, notes, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, COALESCE(%s::timestamptz, CURRENT_TIMESTAMP),
                    COALESCE(%s::timestamptz, CURRENT_TIMESTAMP))
            """,
            (
                query_id, project_id, row.get("question") or "Pergunta importada",
                bool(row.get("expected_refusal")), row.get("notes"),
                row.get("created_at"), row.get("updated_at"),
            ),
        )
        for relevance in row.get("relevances") or []:
            cursor.execute(
                """
                INSERT INTO rag_golden_relevances
                    (id, golden_query_id, paper_id, page_number,
                     relevance_grade, notes, created_at)
                VALUES (%s, %s, %s, %s, %s, %s,
                        COALESCE(%s::timestamptz, CURRENT_TIMESTAMP))
                """,
                (
                    str(uuid.uuid4()), query_id,
                    _mapped(maps["paper"], relevance.get("paper_id"), "artigo relevante"),
                    relevance.get("page_number"), int(relevance.get("relevance_grade") or 2),
                    relevance.get("notes"), relevance.get("created_at"),
                ),
            )

    for row in dataset["golden_versions"]:
        cursor.execute(
            """
            INSERT INTO rag_golden_set_versions
                (id, project_id, version, set_jsonb, change_reason, created_at)
            VALUES (%s, %s, %s, %s, %s, COALESCE(%s::timestamptz, CURRENT_TIMESTAMP))
            """,
            (
                maps["golden_version"][_source_id(row, "golden_version")], project_id,
                int(row.get("version") or 1), Json(_remap_json(row.get("set_jsonb") or {}, remap)),
                row.get("change_reason") or "Importado do pacote", row.get("created_at"),
            ),
        )

    for row in dataset["prisma_snapshots"]:
        cursor.execute(
            """
            INSERT INTO prisma_flow_snapshots
                (id, project_id, snapshot_version, protocol_version, metrics_jsonb,
                 source_counts_jsonb, exclusion_reasons_jsonb, interpretation_jsonb, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s,
                    COALESCE(%s::timestamptz, CURRENT_TIMESTAMP))
            """,
            (
                maps["prisma"][_source_id(row, "prisma")], project_id,
                int(row.get("snapshot_version") or 1), int(row.get("protocol_version") or 1),
                Json(_remap_json(row.get("metrics_jsonb") or {}, remap)),
                Json(_remap_json(row.get("source_counts_jsonb") or {}, remap)),
                Json(_remap_json(row.get("exclusion_reasons_jsonb") or {}, remap)),
                Json(_remap_json(row.get("interpretation_jsonb") or {}, remap)), row.get("created_at"),
            ),
        )


def import_reproducibility_package(
    data: bytes,
    title: str | None = None,
    connection_factory=None,
) -> dict:
    """Cria um projeto independente e preserva o pacote em uma única transação."""
    validated = validate_reproducibility_package(data)
    dataset = validated["dataset"]
    dataset["_generated_at"] = validated["manifest"].get("generated_at")
    dataset["_package_sha256"] = validated["sha256"]
    prepared = _prepare_import(dataset, title=title)

    if connection_factory is None:
        from backend.app.database import get_connection

        connection_factory = get_connection
    connection = connection_factory()
    try:
        with connection.cursor() as cursor:
            _insert_import(cursor, dataset, prepared)
        connection.commit()
    except ReproducibilityImportError:
        connection.rollback()
        raise
    except Exception as error:
        connection.rollback()
        raise ReproducibilityImportError(
            f"A importação foi cancelada e nenhuma alteração foi mantida: {error}"
        ) from error
    finally:
        connection.close()

    return {
        "project_id": prepared["project_id"],
        "title": prepared["title"],
        "source_project_id": prepared["source_project_id"],
        "sha256": validated["sha256"],
        "counts": validated["manifest"].get("counts") or {},
        "warnings": validated["warnings"],
    }
