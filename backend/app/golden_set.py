"""Golden Set humano, isolado por projeto e versionado para avaliação do RAG."""

from psycopg2.extras import Json


def _get_connection_factory(connection_factory=None):
    if connection_factory is not None:
        return connection_factory
    from backend.app.database import get_connection

    return get_connection


def _lock_project(cursor, project_id):
    cursor.execute(
        "SELECT id FROM review_projects WHERE id = %s FOR UPDATE",
        (str(project_id),),
    )
    if not cursor.fetchone():
        raise ValueError("Projeto não encontrado.")


def _snapshot_from_cursor(cursor, project_id):
    cursor.execute(
        """
        SELECT q.id, q.question, q.expected_refusal, q.notes,
               r.id, r.paper_id, p.title, r.page_number,
               r.relevance_grade, r.notes
        FROM rag_golden_queries q
        LEFT JOIN rag_golden_relevances r ON r.golden_query_id = q.id
        LEFT JOIN deduplicated_papers p ON p.id = r.paper_id
        WHERE q.project_id = %s
        ORDER BY q.created_at, q.id, r.relevance_grade DESC,
                 p.title NULLS LAST, r.page_number NULLS FIRST
        """,
        (str(project_id),),
    )
    queries = []
    by_id = {}
    for row in cursor.fetchall():
        query_id = str(row[0])
        if query_id not in by_id:
            item = {
                "id": query_id,
                "question": row[1],
                "expected_refusal": bool(row[2]),
                "notes": row[3],
                "relevances": [],
            }
            by_id[query_id] = item
            queries.append(item)
        if row[4] is not None:
            by_id[query_id]["relevances"].append(
                {
                    "id": str(row[4]),
                    "paper_id": str(row[5]),
                    "paper_title": row[6],
                    "page_number": int(row[7]) if row[7] is not None else None,
                    "relevance_grade": int(row[8]),
                    "notes": row[9],
                }
            )
    return {"project_id": str(project_id), "queries": queries}


def _record_version(cursor, project_id, reason):
    snapshot = _snapshot_from_cursor(cursor, project_id)
    cursor.execute(
        """
        SELECT COALESCE(MAX(version), 0) + 1
        FROM rag_golden_set_versions
        WHERE project_id = %s
        """,
        (str(project_id),),
    )
    version = int(cursor.fetchone()[0])
    snapshot["version"] = version
    cursor.execute(
        """
        INSERT INTO rag_golden_set_versions
            (project_id, version, set_jsonb, change_reason)
        VALUES (%s, %s, %s, %s)
        RETURNING id, created_at
        """,
        (str(project_id), version, Json(snapshot), str(reason)),
    )
    version_id, created_at = cursor.fetchone()
    snapshot.update(
        {
            "version_id": str(version_id),
            "change_reason": str(reason),
            "created_at": created_at,
        }
    )
    return snapshot


def list_golden_queries(project_id, connection_factory=None):
    factory = _get_connection_factory(connection_factory)
    with factory() as connection, connection.cursor() as cursor:
        snapshot = _snapshot_from_cursor(cursor, project_id)
        cursor.execute(
            """
            SELECT version, created_at, change_reason
            FROM rag_golden_set_versions
            WHERE project_id = %s
            ORDER BY version DESC
            LIMIT 1
            """,
            (str(project_id),),
        )
        latest = cursor.fetchone()
    snapshot["version"] = int(latest[0]) if latest else 0
    snapshot["version_created_at"] = latest[1] if latest else None
    snapshot["change_reason"] = latest[2] if latest else None
    return snapshot


def add_golden_query(
    project_id,
    question,
    expected_refusal=False,
    notes=None,
    connection_factory=None,
):
    question = " ".join(str(question or "").split()).strip()
    notes = " ".join(str(notes or "").split()).strip() or None
    if len(question) < 5:
        raise ValueError("A pergunta deve possuir pelo menos 5 caracteres.")
    factory = _get_connection_factory(connection_factory)
    with factory() as connection, connection.cursor() as cursor:
        _lock_project(cursor, project_id)
        cursor.execute(
            """
            SELECT 1 FROM rag_golden_queries
            WHERE project_id = %s AND lower(question) = lower(%s)
            """,
            (str(project_id), question),
        )
        if cursor.fetchone():
            raise ValueError("Esta pergunta já está cadastrada no Golden Set.")
        cursor.execute(
            """
            INSERT INTO rag_golden_queries
                (project_id, question, expected_refusal, notes)
            VALUES (%s, %s, %s, %s)
            RETURNING id
            """,
            (str(project_id), question, bool(expected_refusal), notes),
        )
        query_id = str(cursor.fetchone()[0])
        version = _record_version(cursor, project_id, "Pergunta adicionada ao Golden Set")
    return {"id": query_id, "version": version["version"]}


def delete_golden_query(project_id, query_id, connection_factory=None):
    factory = _get_connection_factory(connection_factory)
    with factory() as connection, connection.cursor() as cursor:
        _lock_project(cursor, project_id)
        cursor.execute(
            """
            DELETE FROM rag_golden_queries
            WHERE id = %s AND project_id = %s
            RETURNING id
            """,
            (str(query_id), str(project_id)),
        )
        if not cursor.fetchone():
            raise ValueError("Pergunta não encontrada no projeto ativo.")
        version = _record_version(cursor, project_id, "Pergunta removida do Golden Set")
    return version


def add_golden_relevance(
    project_id,
    query_id,
    paper_id,
    page_number=None,
    relevance_grade=2,
    notes=None,
    connection_factory=None,
):
    try:
        relevance_grade = int(relevance_grade)
    except (TypeError, ValueError) as exc:
        raise ValueError("O grau de relevância deve ser um número entre 1 e 3.") from exc
    if relevance_grade not in {1, 2, 3}:
        raise ValueError("O grau de relevância deve estar entre 1 e 3.")
    if page_number in (None, "", 0, "0"):
        page_number = None
    else:
        page_number = int(page_number)
        if page_number <= 0:
            raise ValueError("A página deve ser maior que zero.")
    notes = " ".join(str(notes or "").split()).strip() or None

    factory = _get_connection_factory(connection_factory)
    with factory() as connection, connection.cursor() as cursor:
        _lock_project(cursor, project_id)
        cursor.execute(
            """
            SELECT expected_refusal
            FROM rag_golden_queries
            WHERE id = %s AND project_id = %s
            """,
            (str(query_id), str(project_id)),
        )
        query = cursor.fetchone()
        if not query:
            raise ValueError("Pergunta não encontrada no projeto ativo.")
        if query[0]:
            raise ValueError("Perguntas de recusa não podem possuir fontes relevantes.")

        cursor.execute(
            """
            SELECT 1
            FROM deduplicated_papers p
            WHERE p.id = %s AND p.project_id = %s
              AND EXISTS (
                  SELECT 1 FROM paper_chunks pc
                  WHERE pc.paper_id = p.id
                    AND pc.metadata_jsonb->>'source_type' = 'pdf'
              )
            """,
            (str(paper_id), str(project_id)),
        )
        if not cursor.fetchone():
            raise ValueError("O artigo não possui PDF indexado no projeto ativo.")
        if page_number is not None:
            cursor.execute(
                """
                SELECT 1 FROM paper_chunks
                WHERE paper_id = %s
                  AND metadata_jsonb->>'source_type' = 'pdf'
                  AND (metadata_jsonb->>'page_start')::INTEGER = %s
                LIMIT 1
                """,
                (str(paper_id), page_number),
            )
            if not cursor.fetchone():
                raise ValueError("A página selecionada não está indexada para esse artigo.")

        cursor.execute(
            """
            SELECT page_number FROM rag_golden_relevances
            WHERE golden_query_id = %s
              AND paper_id = %s
            """,
            (str(query_id), str(paper_id)),
        )
        existing_pages = [row[0] for row in cursor.fetchall()]
        if page_number in existing_pages:
            raise ValueError("Esta fonte já está cadastrada para a pergunta.")
        if existing_pages and (page_number is None or None in existing_pages):
            raise ValueError(
                "Use relevância por artigo ou por páginas específicas, sem misturar os dois modos."
            )

        cursor.execute(
            """
            INSERT INTO rag_golden_relevances
                (golden_query_id, paper_id, page_number, relevance_grade, notes)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (str(query_id), str(paper_id), page_number, relevance_grade, notes),
        )
        relevance_id = str(cursor.fetchone()[0])
        version = _record_version(cursor, project_id, "Julgamento de relevância adicionado")
    return {"id": relevance_id, "version": version["version"]}


def delete_golden_relevance(project_id, relevance_id, connection_factory=None):
    factory = _get_connection_factory(connection_factory)
    with factory() as connection, connection.cursor() as cursor:
        _lock_project(cursor, project_id)
        cursor.execute(
            """
            DELETE FROM rag_golden_relevances r
            USING rag_golden_queries q
            WHERE r.golden_query_id = q.id
              AND r.id = %s
              AND q.project_id = %s
            RETURNING r.id
            """,
            (str(relevance_id), str(project_id)),
        )
        if not cursor.fetchone():
            raise ValueError("Julgamento não encontrado no projeto ativo.")
        version = _record_version(cursor, project_id, "Julgamento de relevância removido")
    return version


def list_indexed_papers(project_id, connection_factory=None):
    factory = _get_connection_factory(connection_factory)
    with factory() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT p.id, p.title,
                   ARRAY_AGG(DISTINCT (pc.metadata_jsonb->>'page_start')::INTEGER
                             ORDER BY (pc.metadata_jsonb->>'page_start')::INTEGER)
            FROM deduplicated_papers p
            JOIN paper_chunks pc ON pc.paper_id = p.id
            WHERE p.project_id = %s
              AND pc.metadata_jsonb->>'source_type' = 'pdf'
              AND pc.metadata_jsonb ? 'page_start'
            GROUP BY p.id, p.title
            ORDER BY p.title
            """,
            (str(project_id),),
        )
        return [
            {"id": str(row[0]), "title": row[1], "pages": [int(p) for p in row[2]]}
            for row in cursor.fetchall()
        ]
