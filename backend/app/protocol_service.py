"""Validação, comparação e rastreabilidade do protocolo de pesquisa."""

from copy import deepcopy
import hashlib
import json


PICO_FIELDS = ("population", "intervention", "comparison", "outcome", "study_design")
SOURCE_CODES = ("openalex", "pubmed", "semantic_scholar")


def _clean_text(value):
    return " ".join(str(value or "").split()).strip()


def _clean_multiline_item(value):
    return " ".join(str(value or "").split()).strip()


def _normalize_list(value):
    if isinstance(value, str):
        value = value.splitlines()
    result = []
    seen = set()
    for item in value or []:
        cleaned = _clean_multiline_item(item)
        key = cleaned.casefold()
        if cleaned and key not in seen:
            result.append(cleaned)
            seen.add(key)
    return result


def _normalize_year(value):
    cleaned = _clean_text(value)
    if not cleaned:
        return None
    try:
        return int(cleaned)
    except ValueError as exc:
        raise ValueError("Os anos dos critérios de elegibilidade devem ser numéricos.") from exc


def normalize_protocol(protocol):
    """Normaliza o formato atual e mantém metadados legados do projeto."""
    source = deepcopy(protocol or {})
    pico_source = source.get("pico") or {}
    eligibility_source = source.get("eligibility") or {}
    source_queries = source.get("source_search_strings") or {}

    normalized = {
        key: value for key, value in source.items() if str(key).startswith("_")
    }
    normalized.update(
        {
            "pico": {
                field: _clean_text(pico_source.get(field))
                for field in PICO_FIELDS
            },
            "eligibility": {
                "year_from": _normalize_year(eligibility_source.get("year_from")),
                "year_to": _normalize_year(eligibility_source.get("year_to")),
                "languages": _normalize_list(eligibility_source.get("languages")),
                "publication_types": _normalize_list(
                    eligibility_source.get("publication_types")
                ),
                "study_designs": _normalize_list(
                    eligibility_source.get("study_designs")
                ),
            },
            "inclusion_criteria": _normalize_list(source.get("inclusion_criteria")),
            "exclusion_criteria": _normalize_list(source.get("exclusion_criteria")),
            "search_concepts": [],
            "search_string": str(source.get("search_string") or "").strip(),
            "source_search_strings": {
                code: str(source_queries.get(code) or "").strip()
                for code in SOURCE_CODES
            },
            "audit_questions": _normalize_list(source.get("audit_questions")),
        }
    )

    for row in source.get("search_concepts") or []:
        if not isinstance(row, dict):
            continue
        concept = _clean_text(row.get("concept"))
        terms = row.get("terms") or []
        if isinstance(terms, str):
            terms = [item.strip() for item in terms.split(";")]
        terms = _normalize_list(terms)
        if concept or terms:
            normalized["search_concepts"].append(
                {"concept": concept, "terms": terms}
            )
    return normalized


def _validate_boolean_query(query, label):
    if len(query) < 3:
        raise ValueError(f"{label} não pode estar vazia.")
    depth = 0
    quoted = False
    escaped = False
    for char in query:
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
        elif char == '"':
            quoted = not quoted
        elif not quoted and char == "(":
            depth += 1
        elif not quoted and char == ")":
            depth -= 1
            if depth < 0:
                break
    if depth != 0:
        raise ValueError(f"{label} possui parênteses não balanceados.")
    if quoted:
        raise ValueError(f"{label} possui aspas não fechadas.")


def validate_protocol(question, protocol, change_reason):
    """Valida o rascunho antes de criar uma versão imutável."""
    question = _clean_text(question)
    reason = _clean_text(change_reason)
    if len(question) < 10:
        raise ValueError("Descreva a pergunta de pesquisa com pelo menos 10 caracteres.")
    if len(reason) < 5:
        raise ValueError("Informe o motivo da nova versão com pelo menos 5 caracteres.")

    normalized = normalize_protocol(protocol)
    pico = normalized["pico"]
    required_pico = {
        "population": "População ou problema",
        "intervention": "Intervenção, exposição ou método",
        "outcome": "Desfechos",
    }
    missing = [label for field, label in required_pico.items() if not pico[field]]
    if missing:
        raise ValueError("Preencha os campos PICO obrigatórios: " + ", ".join(missing) + ".")

    for key, label in (
        ("inclusion_criteria", "inclusão"),
        ("exclusion_criteria", "exclusão"),
    ):
        criteria = normalized[key]
        if not criteria:
            raise ValueError(f"Informe ao menos um critério de {label}.")
        if any(len(item) < 5 for item in criteria):
            raise ValueError(f"Cada critério de {label} deve ter pelo menos 5 caracteres.")

    eligibility = normalized["eligibility"]
    year_from = eligibility["year_from"]
    year_to = eligibility["year_to"]
    if year_from is not None and not 1800 <= year_from <= 2200:
        raise ValueError("O ano inicial deve estar entre 1800 e 2200.")
    if year_to is not None and not 1800 <= year_to <= 2200:
        raise ValueError("O ano final deve estar entre 1800 e 2200.")
    if year_from is not None and year_to is not None and year_from > year_to:
        raise ValueError("O ano inicial não pode ser posterior ao ano final.")

    _validate_boolean_query(normalized["search_string"], "A string de busca geral")
    for code, query in normalized["source_search_strings"].items():
        if query:
            _validate_boolean_query(query, f"A string de busca de {code}")

    return question, normalized, reason


def protocol_fingerprint(protocol):
    """Produz um identificador estável dos critérios efetivamente utilizados."""
    payload = json.dumps(
        normalize_protocol(protocol),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def compare_protocols(first_question, first_protocol, second_question, second_protocol):
    """Lista, em linguagem de interface, as seções alteradas entre duas versões."""
    first = normalize_protocol(first_protocol)
    second = normalize_protocol(second_protocol)
    changes = []
    if _clean_text(first_question) != _clean_text(second_question):
        changes.append("Pergunta de pesquisa")
    for key, label in (
        ("pico", "PICO/PICOS"),
        ("eligibility", "Elegibilidade estruturada"),
        ("inclusion_criteria", "Critérios de inclusão"),
        ("exclusion_criteria", "Critérios de exclusão"),
        ("search_concepts", "Conceitos e sinônimos"),
        ("search_string", "String geral"),
        ("source_search_strings", "Strings por fonte"),
        ("audit_questions", "Perguntas de auditoria"),
    ):
        if first.get(key) != second.get(key):
            changes.append(label)
    return changes


def get_protocol_history(project_id, connection_factory=None):
    if connection_factory is None:
        from backend.app.database import get_connection

        connection_factory = get_connection
    with connection_factory() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT version, question, criteria_jsonb, change_reason, created_at
            FROM review_protocol_versions
            WHERE project_id = %s
            ORDER BY version DESC
            """,
            (str(project_id),),
        )
        return [
            {
                "version": int(row[0]),
                "question": row[1],
                "criteria_jsonb": normalize_protocol(row[2]),
                "change_reason": row[3],
                "created_at": row[4],
            }
            for row in cursor.fetchall()
        ]


def get_protocol_change_impact(project_id, connection_factory=None):
    """Conta dados que permanecem ligados a versões anteriores após uma mudança."""
    if connection_factory is None:
        from backend.app.database import get_connection

        connection_factory = get_connection
    with connection_factory() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM search_queries WHERE project_id = %s),
                (SELECT COUNT(*) FROM deduplicated_papers WHERE project_id = %s),
                (SELECT COUNT(*)
                 FROM screening_decisions s
                 JOIN deduplicated_papers p ON p.id = s.paper_id
                 WHERE p.project_id = %s)
            """,
            (str(project_id), str(project_id), str(project_id)),
        )
        row = cursor.fetchone()
    return {
        "searches": int(row[0] or 0),
        "papers": int(row[1] or 0),
        "screening_decisions": int(row[2] or 0),
        "requires_attention": any(int(value or 0) for value in row),
    }
