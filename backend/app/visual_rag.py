"""Recuperação de interpretações revisadas, sem novas chamadas multimodais.

O PDF é conferido no disco em cada recuperação e antes de entregar a resposta.
Não há cache de elegibilidade. Histórico e importações não concedem autorização.
"""

import hashlib
import json
import re
import unicodedata
from uuid import UUID

from psycopg2.extras import Json, RealDictCursor

from backend.app.database import get_connection
from backend.app.storage_service import pdf_directory


SOURCE_TYPE = "visual_interpretation"
POLICY_VERSION = "reviewed-visual-rag-v1"
MAX_VISUAL_CANDIDATES = 6
MAX_ELIGIBLE_ROWS = 2000
AUDIT_FIELDS = (
    "source_type", "artifact_id", "interpretation_id", "artifact_type",
    "caption", "source_file_sha256", "evidence_revision", "setting_revision",
    "review_status", "reviewer_name", "reviewed_at", "provider_code", "model_name",
)
STOP_WORDS = set("""a o os as um uma uns umas de da do das dos em no na nos nas
por para com sem e ou que qual quais como onde quando porque se ao aos the a an
of in on for to from with without and or what which how where when is are does
this these esse essa esses essas esta este isto artigo artigos paper papers
figura figuras tabela tabelas figure figures table tables mostre descreva""".split())


def get_visual_rag_setting(project_id):
    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT visual_enabled, revision FROM project_rag_settings WHERE project_id = %s",
            (str(project_id),),
        )
        row = cursor.fetchone()
    return {"enabled": bool(row[0]), "revision": int(row[1])} if row else {
        "enabled": False, "revision": 0,
    }


def set_visual_rag_setting(project_id, enabled):
    if not isinstance(enabled, bool):
        raise ValueError("A opção visual deve ser verdadeira ou falsa.")
    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT id FROM review_projects WHERE id = %s FOR UPDATE", (str(project_id),))
        if not cursor.fetchone():
            raise ValueError("Projeto não encontrado.")
        cursor.execute(
            """INSERT INTO project_rag_settings (project_id, visual_enabled)
               VALUES (%s, %s) ON CONFLICT (project_id) DO UPDATE
               SET visual_enabled = EXCLUDED.visual_enabled,
                   revision = project_rag_settings.revision + 1,
                   updated_at = CURRENT_TIMESTAMP
               RETURNING revision""",
            (str(project_id), enabled),
        )
        revision = cursor.fetchone()[0]
        cursor.execute(
            """INSERT INTO agent_interactions (project_id, agent_name, input_jsonb, output_jsonb, model_jsonb)
               VALUES (%s, 'visual_rag_configuration', %s, %s, '{}'::jsonb)""",
            (str(project_id), Json({"action": "human_opt_in"}),
             Json({"enabled": enabled, "revision": revision, "policy": POLICY_VERSION})),
        )
    return {"enabled": enabled, "revision": revision}


def evidence_metadata(item):
    return {key: item[key] for key in AUDIT_FIELDS if key in item}


def _reviewed_text(row):
    # A correção atual é um resumo substitutivo, não aprovação dos dados brutos.
    corrected = row["review_status"] == "corrected"
    payload = (row.get("human_interpretation_jsonb") if corrected else row.get("interpretation_jsonb")) or {}
    summary = str(payload.get("summary") or "").strip()
    if len(summary) < 10:
        return None
    parts = ["INTERPRETAÇÃO VISUAL REVISADA — não é transcrição literal do artigo.",
             f"Legenda: {row.get('caption') or 'não identificada'}",
             f"Descrição humana: {row.get('human_description') or ''}",
             f"Resumo revisado: {summary}"]
    if not corrected:
        for key, label in (("observations", "Observações"), ("structured_data", "Dados"),
                           ("limitations", "Limitações"), ("confidence", "Confiança declarada pela IA")):
            if payload.get(key):
                parts.append(f"{label}: {json.dumps(payload[key], ensure_ascii=False)}")
    else:
        parts.append("Somente o resumo humano corrigido substitui a interpretação original; não inferir valores ausentes.")
    if row.get("human_notes"):
        parts.append(f"Notas da segunda revisão: {row['human_notes']}")
    return "\n".join(parts)


def _pdf_hash(paper_id):
    # UUID validado + confinamento de symlink: nunca usar caminho fornecido pelo documento.
    root = pdf_directory().resolve()
    path = (root / f"{UUID(str(paper_id))}.pdf").resolve()
    if not path.is_relative_to(root) or not path.is_file():
        return None
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except OSError:
        return None
    return digest.hexdigest()


def list_eligible_visual_evidence(project_id, *, setting=None):
    """Também usado na seleção humana do Golden Set; não ativa o recurso."""
    with get_connection() as connection, connection.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """SELECT i.*, a.paper_id, a.page_number, a.artifact_type, a.caption,
                      a.human_description, a.updated_at AS artifact_updated_at,
                      p.title AS paper_title
               FROM visual_interpretations i
               JOIN visual_artifacts a ON a.id = i.artifact_id AND a.project_id = i.project_id
               JOIN deduplicated_papers p ON p.id = a.paper_id AND p.project_id = a.project_id
               WHERE i.project_id = %s AND i.is_current AND a.is_current
                 AND i.review_status IN ('approved', 'corrected')
                 AND a.review_status IN ('approved', 'corrected')
                 AND length(btrim(a.human_description)) >= 10
                 AND i.source_file_sha256 = a.file_sha256
                 AND EXISTS (SELECT 1 FROM screening_decisions s
                             WHERE s.paper_id = p.id AND s.human_decision = 'Incluir')
               ORDER BY a.paper_id, a.page_number, a.id
               LIMIT %s""", (str(project_id), MAX_ELIGIBLE_ROWS + 1),
        )
        rows = cursor.fetchall()
    if len(rows) > MAX_ELIGIBLE_ROWS:
        raise ValueError("O catálogo excede o limite de 2000 interpretações elegíveis por consulta.")
    hashes, evidence = {}, []
    for row in rows:
        paper_id = str(row["paper_id"])
        if paper_id not in hashes:
            hashes[paper_id] = _pdf_hash(paper_id)
        if not hashes[paper_id] or hashes[paper_id] != row["source_file_sha256"]:
            continue
        text = _reviewed_text(row)
        if not text:
            continue
        payload = (row.get("human_interpretation_jsonb") if row["review_status"] == "corrected"
                   else row.get("interpretation_jsonb")) or {}
        search_text = " ".join([
            str(row.get("caption") or ""), str(row.get("human_description") or ""),
            str(payload.get("summary") or ""),
            json.dumps(payload.get("observations") or [], ensure_ascii=False),
            json.dumps(payload.get("structured_data") or {}, ensure_ascii=False),
        ])
        revision = hashlib.sha256(json.dumps({
            "artifact_updated_at": str(row["artifact_updated_at"]),
            "interpretation_updated_at": str(row["updated_at"]), "text": text,
        }, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        evidence.append({
            "source_type": SOURCE_TYPE, "chunk_id": None, "paper_id": paper_id,
            "paper_title": row["paper_title"], "page_number": int(row["page_number"]),
            "artifact_id": str(row["artifact_id"]), "interpretation_id": str(row["id"]),
            "artifact_type": row["artifact_type"], "caption": row.get("caption"),
            "source_file_sha256": row["source_file_sha256"], "evidence_revision": revision,
            "setting_revision": (setting or {}).get("revision"), "text": text,
            "search_text": search_text,
            "review_status": row["review_status"], "reviewer_name": row.get("reviewer_name"),
            "reviewed_at": str(row.get("reviewed_at")), "provider_code": row["provider_code"],
            "model_name": row["model_name"],
        })
    return evidence


def _terms(text):
    normalized = "".join(c for c in unicodedata.normalize("NFKD", str(text).lower()) if not unicodedata.combining(c))
    return set(re.findall(r"[a-z0-9]{2,}", normalized)) - STOP_WORDS


def retrieve_visual_evidence(question, project_id, setting):
    terms = _terms(question)
    if not setting["enabled"] or not terms:
        return []
    scored = []
    for item in list_eligible_visual_evidence(project_id, setting=setting):
        overlap = len(terms & _terms(item.get("search_text", item["text"])))
        if overlap:
            scored.append((overlap, item))
    scored.sort(key=lambda pair: (-pair[0], pair[1]["artifact_id"]))
    return [item for _, item in scored[:MAX_VISUAL_CANDIDATES]]


def combine_candidates(textual, visual):
    """Intercala os dois canais, sem alterar a busca textual quando não há visual."""
    if not visual:
        return textual
    merged = []
    for index in range(max(len(textual), len(visual))):
        for channel in (textual, visual):
            if index < len(channel):
                item = dict(channel[index])
                item["channel_rank"] = index + 1
                item["channel_rrf_score"] = 1.0 / (61 + index)
                item.setdefault("rrf_score", item["channel_rrf_score"])
                item.update(candidate_id=f"c{len(merged) + 1}", original_rank=len(merged) + 1)
                merged.append(item)
    return merged


def ensure_visual_evidence_current(project_id, evidence):
    visual = [item for item in evidence if item.get("source_type") == SOURCE_TYPE]
    if not visual:
        return
    setting = get_visual_rag_setting(project_id)
    if not setting["enabled"] or any(item.get("setting_revision") != setting["revision"] for item in visual):
        raise ValueError("A autorização visual mudou. Faça uma nova pergunta para recuperar evidências atuais.")
    current = {item["interpretation_id"]: item for item in list_eligible_visual_evidence(project_id, setting=setting)}
    if any(item["interpretation_id"] not in current or
           item["evidence_revision"] != current[item["interpretation_id"]]["evidence_revision"] for item in visual):
        raise ValueError("O PDF ou a revisão visual mudou. A resposta não foi entregue; consulte o catálogo e tente novamente.")
