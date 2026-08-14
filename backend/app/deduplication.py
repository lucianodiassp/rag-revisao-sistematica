"""Deduplicação bibliográfica explicável e revisão humana de candidatos."""

from difflib import SequenceMatcher
import re
import unicodedata
import uuid

from psycopg2.extras import Json

from backend.app.project_utils import mesclar_proveniencia, normalizar_doi, normalizar_titulo


RULE_DOI_EXACT = "doi_exact"
RULE_TITLE_EXACT = "title_exact"
RULE_TITLE_SIMILAR = "title_similar"
RULE_NO_CANDIDATE = "no_candidate"

ACTION_AUTO_CREATE = "auto_create"
ACTION_AUTO_MERGE = "auto_merge"
ACTION_PENDING_REVIEW = "pending_review"

HUMAN_MERGE = "merge"
HUMAN_KEEP_SEPARATE = "keep_separate"

TITLE_SIMILARITY_THRESHOLD = 0.82
COMBINED_SCORE_THRESHOLD = 0.78
SCORE_WEIGHTS = {"title": 0.80, "authors": 0.15, "year": 0.05}


def _normalizar_texto(valor):
    texto = unicodedata.normalize("NFKD", str(valor or ""))
    texto = "".join(char for char in texto if not unicodedata.combining(char))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", texto.lower()).split())


def _jaccard(valores_a, valores_b):
    conjunto_a, conjunto_b = set(valores_a), set(valores_b)
    if not conjunto_a or not conjunto_b:
        return 0.0
    return len(conjunto_a & conjunto_b) / len(conjunto_a | conjunto_b)


def _similaridade_titulo(titulo_a, titulo_b):
    normalizado_a = normalizar_titulo(titulo_a)
    normalizado_b = normalizar_titulo(titulo_b)
    if not normalizado_a or not normalizado_b:
        return 0.0
    sequencia = SequenceMatcher(None, normalizado_a, normalizado_b).ratio()
    tokens = _jaccard(normalizado_a.split(), normalizado_b.split())
    return round((0.70 * sequencia) + (0.30 * tokens), 4)


def _sobrenomes(autores):
    resultado = set()
    for autor in autores or []:
        autor_original = str(autor or "").strip()
        autor_normalizado = _normalizar_texto(autor_original)
        if not autor_normalizado:
            continue
        tokens = autor_normalizado.split()
        if "," in autor_original:
            sobrenome = _normalizar_texto(autor_original.split(",", 1)[0]).split()[-1]
        elif len(tokens) > 1 and len(tokens[-1]) <= 2:
            # PubMed frequentemente devolve "Sobrenome A".
            sobrenome = tokens[0]
        else:
            # OpenAlex e Semantic Scholar normalmente usam "Nome Sobrenome".
            sobrenome = tokens[-1]
        resultado.add(sobrenome)
    return resultado


def _metadados(fontes):
    return (fontes or {}).get("metadata", {}) or {}


def _evidencias(entrada, candidato):
    fontes_entrada = entrada.get("fontes_dict") or {}
    fontes_candidato = candidato.get("merged_sources_jsonb") or {}
    doi_entrada = normalizar_doi(
        fontes_entrada.get("external_ids", {}).get("doi") or entrada.get("canonical_doi")
    )
    doi_candidato = normalizar_doi(candidato.get("canonical_doi"))
    titulo_entrada = normalizar_titulo(entrada.get("title"))
    titulo_candidato = normalizar_titulo(candidato.get("title"))
    metadados_entrada = _metadados(fontes_entrada)
    metadados_candidato = _metadados(fontes_candidato)
    autores_entrada = _sobrenomes(metadados_entrada.get("authors"))
    autores_candidato = _sobrenomes(metadados_candidato.get("authors"))
    ano_entrada = metadados_entrada.get("publication_year")
    ano_candidato = metadados_candidato.get("publication_year")
    similaridade_titulo = _similaridade_titulo(entrada.get("title"), candidato.get("title"))
    sobreposicao_autores = round(_jaccard(autores_entrada, autores_candidato), 4)
    ano_comparavel = ano_entrada is not None and ano_candidato is not None
    ano_igual = bool(ano_comparavel and str(ano_entrada) == str(ano_candidato))

    return {
        "incoming_doi": doi_entrada,
        "candidate_doi": doi_candidato,
        "doi_match": bool(doi_entrada and doi_candidato and doi_entrada == doi_candidato),
        "doi_conflict": bool(doi_entrada and doi_candidato and doi_entrada != doi_candidato),
        "incoming_normalized_title": titulo_entrada,
        "candidate_normalized_title": titulo_candidato,
        "title_exact": bool(titulo_entrada and titulo_entrada == titulo_candidato),
        "title_similarity": similaridade_titulo,
        "author_overlap": sobreposicao_autores,
        "incoming_year": ano_entrada,
        "candidate_year": ano_candidato,
        "year_comparable": ano_comparavel,
        "year_match": ano_igual,
        "weights": SCORE_WEIGHTS,
        "thresholds": {
            "title_similarity": TITLE_SIMILARITY_THRESHOLD,
            "combined_score": COMBINED_SCORE_THRESHOLD,
        },
    }


def avaliar_duplicidade(entrada, candidatos):
    """Retorna a melhor decisão, sua pontuação e as evidências calculadas."""
    avaliacoes = []
    for candidato in candidatos or []:
        evidencias = _evidencias(entrada, candidato)
        if evidencias["doi_match"]:
            score = 1.0
            regra = RULE_DOI_EXACT
        elif evidencias["title_exact"]:
            score = 0.90 if evidencias["doi_conflict"] else 0.95
            regra = RULE_TITLE_EXACT
        else:
            score = round(
                (SCORE_WEIGHTS["title"] * evidencias["title_similarity"])
                + (SCORE_WEIGHTS["authors"] * evidencias["author_overlap"])
                + (SCORE_WEIGHTS["year"] * (1.0 if evidencias["year_match"] else 0.0)),
                4,
            )
            regra = RULE_TITLE_SIMILAR
        avaliacoes.append((score, regra, candidato, evidencias))

    if not avaliacoes:
        return {
            "rule_code": RULE_NO_CANDIDATE,
            "score": 0.0,
            "system_action": ACTION_AUTO_CREATE,
            "candidate": None,
            "evidence": {
                "weights": SCORE_WEIGHTS,
                "thresholds": {
                    "title_similarity": TITLE_SIMILARITY_THRESHOLD,
                    "combined_score": COMBINED_SCORE_THRESHOLD,
                },
            },
            "explanation": "Nenhum artigo do projeto estava suficientemente próximo; novo registro canônico criado.",
        }

    score, regra, candidato, evidencias = max(
        avaliacoes,
        key=lambda item: (
            item[1] == RULE_DOI_EXACT,
            item[1] == RULE_TITLE_EXACT,
            item[0],
        ),
    )

    if regra == RULE_DOI_EXACT:
        return {
            "rule_code": regra,
            "score": score,
            "system_action": ACTION_AUTO_MERGE,
            "candidate": candidato,
            "evidence": evidencias,
            "explanation": "DOI normalizado idêntico; os registros foram consolidados automaticamente.",
        }

    if regra == RULE_TITLE_EXACT:
        conflito = " Há DOIs divergentes, o que exige atenção adicional." if evidencias["doi_conflict"] else ""
        return {
            "rule_code": regra,
            "score": score,
            "system_action": ACTION_PENDING_REVIEW,
            "candidate": candidato,
            "evidence": evidencias,
            "explanation": "Título normalizado idêntico; a consolidação aguarda validação humana." + conflito,
        }

    if (
        evidencias["title_similarity"] >= TITLE_SIMILARITY_THRESHOLD
        and score >= COMBINED_SCORE_THRESHOLD
    ):
        return {
            "rule_code": regra,
            "score": score,
            "system_action": ACTION_PENDING_REVIEW,
            "candidate": candidato,
            "evidence": evidencias,
            "explanation": (
                "Similaridade combinada de título, autores e ano acima dos limites; "
                "a consolidação aguarda validação humana."
            ),
        }

    return {
        "rule_code": RULE_NO_CANDIDATE,
        "score": round(score, 4),
        "system_action": ACTION_AUTO_CREATE,
        "candidate": candidato,
        "evidence": evidencias,
        "explanation": "O candidato mais próximo ficou abaixo dos limites; novo registro canônico criado.",
    }


def listar_resumo_deduplicacao(project_id, connection_factory=None):
    if connection_factory is None:
        from backend.app.database import get_connection

        connection_factory = get_connection

    with connection_factory() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE system_action = 'auto_create') AS novos,
                   COUNT(*) FILTER (WHERE system_action = 'auto_merge') AS mesclados_automaticamente,
                   COUNT(*) FILTER (WHERE review_status = 'pending') AS pendentes,
                   COUNT(*) FILTER (WHERE review_status = 'reviewed') AS revisados
            FROM deduplication_decisions
            WHERE project_id = %s
            """,
            (str(project_id),),
        )
        linha = cursor.fetchone()
    return dict(zip(("total", "new", "auto_merged", "pending", "reviewed"), linha))


def listar_decisoes_deduplicacao(project_id, apenas_pendentes=False, limite=250, connection_factory=None):
    if connection_factory is None:
        from backend.app.database import get_connection

        connection_factory = get_connection

    filtro = "AND dd.review_status = 'pending'" if apenas_pendentes else ""
    with connection_factory() as connection, connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT dd.id, dd.retrieved_record_id, dd.candidate_paper_id,
                   dd.result_paper_id, dd.rule_code, dd.similarity_score,
                   dd.system_action, dd.explanation, dd.evidence_jsonb,
                   dd.incoming_record_jsonb, dd.review_status,
                   dd.human_decision, dd.review_justification,
                   dd.created_at, dd.reviewed_at,
                   candidato.title AS candidate_title,
                   candidato.abstract AS candidate_abstract,
                   candidato.canonical_doi AS candidate_doi,
                   candidato.merged_sources_jsonb AS candidate_sources
            FROM deduplication_decisions dd
            LEFT JOIN deduplicated_papers candidato ON candidato.id = dd.candidate_paper_id
            WHERE dd.project_id = %s
              {filtro}
            ORDER BY (dd.review_status = 'pending') DESC, dd.created_at DESC
            LIMIT %s
            """,
            (str(project_id), int(limite)),
        )
        colunas = [descricao[0] for descricao in cursor.description]
        return [dict(zip(colunas, linha)) for linha in cursor.fetchall()]


def revisar_decisao_deduplicacao(
    project_id,
    decision_id,
    human_decision,
    justification,
    connection_factory=None,
):
    """Consolida o candidato ou libera o registro como artigo distinto."""
    project_id = str(project_id or "").strip()
    decision_id = str(decision_id or "").strip()
    human_decision = str(human_decision or "").strip()
    justification = " ".join(str(justification or "").split()).strip()
    if human_decision not in {HUMAN_MERGE, HUMAN_KEEP_SEPARATE}:
        raise ValueError("Decisão humana de deduplicação inválida.")
    if len(justification) < 5:
        raise ValueError("Informe uma justificativa com pelo menos 5 caracteres.")

    if connection_factory is None:
        from backend.app.database import get_connection

        connection_factory = get_connection

    with connection_factory() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT candidate_paper_id, incoming_record_jsonb, review_status
            FROM deduplication_decisions
            WHERE id = %s AND project_id = %s
            FOR UPDATE
            """,
            (decision_id, project_id),
        )
        linha = cursor.fetchone()
        if not linha:
            raise ValueError("Candidato de deduplicação não encontrado no projeto ativo.")
        candidate_paper_id, incoming, review_status = linha
        if review_status != "pending":
            raise ValueError("Esta decisão de deduplicação já foi revisada.")

        if human_decision == HUMAN_MERGE:
            if not candidate_paper_id:
                raise ValueError("O artigo candidato não está mais disponível para consolidação.")
            cursor.execute(
                """
                SELECT title, abstract, canonical_doi, merged_sources_jsonb
                FROM deduplicated_papers
                WHERE id = %s AND project_id = %s
                FOR UPDATE
                """,
                (str(candidate_paper_id), project_id),
            )
            candidato = cursor.fetchone()
            if not candidato:
                raise ValueError("O artigo candidato não pertence ao projeto ativo.")
            titulo, abstract, doi, proveniencia = candidato
            nova_proveniencia = mesclar_proveniencia(proveniencia, incoming.get("fontes_dict"))
            abstract_entrada = incoming.get("abstract") or ""
            abstract_final = abstract_entrada if abstract_entrada and "indispon" not in abstract_entrada.lower() else abstract
            cursor.execute(
                """
                UPDATE deduplicated_papers
                SET title = %s, abstract = %s,
                    canonical_doi = COALESCE(canonical_doi, %s),
                    merged_sources_jsonb = %s
                WHERE id = %s AND project_id = %s
                """,
                (
                    incoming.get("title") or titulo,
                    abstract_final,
                    normalizar_doi(incoming.get("canonical_doi")),
                    Json(nova_proveniencia),
                    str(candidate_paper_id),
                    project_id,
                ),
            )
            result_paper_id = str(candidate_paper_id)
        else:
            proposed_id = str(incoming.get("proposed_paper_id") or "")
            cursor.execute("SELECT 1 FROM deduplicated_papers WHERE id = %s", (proposed_id,))
            if not proposed_id or cursor.fetchone():
                proposed_id = str(
                    uuid.uuid5(
                        uuid.NAMESPACE_URL,
                        f"project:{project_id}|dedup-decision:{decision_id}",
                    )
                )
            cursor.execute(
                """
                INSERT INTO deduplicated_papers
                    (id, project_id, canonical_doi, title, abstract, merged_sources_jsonb)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    proposed_id,
                    project_id,
                    normalizar_doi(incoming.get("canonical_doi")),
                    incoming.get("title"),
                    incoming.get("abstract"),
                    Json(incoming.get("fontes_dict") or {}),
                ),
            )
            result_paper_id = proposed_id

        cursor.execute(
            """
            UPDATE deduplication_decisions
            SET result_paper_id = %s,
                review_status = 'reviewed',
                human_decision = %s,
                review_justification = %s,
                reviewed_at = CURRENT_TIMESTAMP
            WHERE id = %s AND project_id = %s
            """,
            (result_paper_id, human_decision, justification, decision_id, project_id),
        )

    return {
        "decision_id": decision_id,
        "project_id": project_id,
        "human_decision": human_decision,
        "result_paper_id": result_paper_id,
        "justification": justification,
    }
