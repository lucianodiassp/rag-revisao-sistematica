from backend.app.database import get_connection, resolver_project_id


project_id = resolver_project_id()
texto_teste = (
    "This paper introduces a framework to benchmark Large Language Models, "
    "focusing on reasoning, accuracy and hallucination rates."
)

with get_connection() as conexao, conexao.cursor() as cursor:
    cursor.execute(
        """
        UPDATE deduplicated_papers
        SET abstract = %s
        WHERE id = (
            SELECT id FROM deduplicated_papers
            WHERE project_id = %s
            ORDER BY created_at
            LIMIT 1
        )
        """,
        (texto_teste, project_id),
    )

print(f"✅ Texto de teste atualizado somente no projeto {project_id}.")
