from psycopg2.extras import Json

from backend.app.ai_config import GENERATION_TASKS
from backend.app.database import get_connection


SCOPE_INSTALLATION = "installation"
TASK_EMBEDDING = "embedding"
SUPPORTED_TASKS = set(GENERATION_TASKS) | {TASK_EMBEDDING}


def configuration_tables_available():
    try:
        with get_connection() as conexao, conexao.cursor() as cursor:
            cursor.execute("SELECT to_regclass('public.ai_model_settings') IS NOT NULL")
            return bool(cursor.fetchone()[0])
    except Exception:
        return False


def get_installation_credential(provider_code="google_gemini"):
    with get_connection() as conexao, conexao.cursor() as cursor:
        cursor.execute(
            """
            SELECT id, provider_code, label, encrypted_secret, secret_hint,
                   validation_status, last_validated_at, validation_error,
                   created_at, updated_at
            FROM ai_provider_credentials
            WHERE provider_code = %s
              AND scope_type = 'installation'
              AND scope_id IS NULL
              AND owner_user_id IS NULL
              AND is_active = TRUE
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (provider_code,),
        )
        linha = cursor.fetchone()
        if not linha:
            return None
        colunas = [item[0] for item in cursor.description]
        return dict(zip(colunas, linha))


def save_installation_credential(
    provider_code,
    label,
    encrypted_secret,
    secret_hint_value,
    validation_status="untested",
    validation_error=None,
):
    with get_connection() as conexao, conexao.cursor() as cursor:
        cursor.execute(
            """
            SELECT id
            FROM ai_provider_credentials
            WHERE provider_code = %s
              AND scope_type = 'installation'
              AND scope_id IS NULL
              AND owner_user_id IS NULL
              AND is_active = TRUE
            FOR UPDATE
            """,
            (provider_code,),
        )
        existente = cursor.fetchone()
        if existente:
            credential_id = str(existente[0])
            cursor.execute(
                """
                UPDATE ai_provider_credentials
                SET label = %s,
                    encrypted_secret = %s,
                    secret_hint = %s,
                    validation_status = %s,
                    last_validated_at = CASE
                        WHEN %s IN ('valid', 'invalid') THEN CURRENT_TIMESTAMP
                        ELSE last_validated_at
                    END,
                    validation_error = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (
                    label,
                    encrypted_secret,
                    secret_hint_value,
                    validation_status,
                    validation_status,
                    validation_error,
                    credential_id,
                ),
            )
            acao = "credential_replaced"
        else:
            cursor.execute(
                """
                INSERT INTO ai_provider_credentials
                    (provider_code, label, encrypted_secret, secret_hint,
                     validation_status, last_validated_at, validation_error)
                VALUES (%s, %s, %s, %s, %s,
                        CASE WHEN %s IN ('valid', 'invalid') THEN CURRENT_TIMESTAMP END,
                        %s)
                RETURNING id
                """,
                (
                    provider_code,
                    label,
                    encrypted_secret,
                    secret_hint_value,
                    validation_status,
                    validation_status,
                    validation_error,
                ),
            )
            credential_id = str(cursor.fetchone()[0])
            acao = "credential_created"

        cursor.execute(
            """
            INSERT INTO ai_configuration_audit (action, changes_jsonb)
            VALUES (%s, %s)
            """,
            (
                acao,
                Json({
                    "provider_code": provider_code,
                    "label": label,
                    "secret_hint": secret_hint_value,
                    "validation_status": validation_status,
                }),
            ),
        )
        return credential_id


def update_credential_validation(credential_id, status, error=None):
    if status not in {"valid", "invalid", "untested"}:
        raise ValueError("Status de validação inválido.")
    with get_connection() as conexao, conexao.cursor() as cursor:
        cursor.execute(
            """
            UPDATE ai_provider_credentials
            SET validation_status = %s,
                last_validated_at = CURRENT_TIMESTAMP,
                validation_error = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s AND scope_type = 'installation' AND is_active = TRUE
            RETURNING id
            """,
            (status, error, str(credential_id)),
        )
        if not cursor.fetchone():
            raise ValueError("Credencial ativa não encontrada.")
        cursor.execute(
            """
            INSERT INTO ai_configuration_audit (action, changes_jsonb)
            VALUES ('credential_validated', %s)
            """,
            (Json({"credential_id": str(credential_id), "status": status}),),
        )


def get_installation_model_settings():
    with get_connection() as conexao, conexao.cursor() as cursor:
        cursor.execute(
            """
            SELECT task_type, provider_code, credential_id, model_name,
                   parameters_jsonb, embedding_dimensions, updated_at
            FROM ai_model_settings
            WHERE scope_type = 'installation'
              AND scope_id IS NULL
              AND owner_user_id IS NULL
              AND is_active = TRUE
            ORDER BY task_type
            """
        )
        colunas = [item[0] for item in cursor.description]
        return {
            linha[0]: dict(zip(colunas, linha))
            for linha in cursor.fetchall()
        }


def save_installation_model_settings(provider_code, credential_id, settings):
    tarefas_recebidas = set(settings)
    if tarefas_recebidas != SUPPORTED_TASKS:
        faltantes = sorted(SUPPORTED_TASKS - tarefas_recebidas)
        extras = sorted(tarefas_recebidas - SUPPORTED_TASKS)
        raise ValueError(f"Configuração de tarefas incompleta. Faltantes={faltantes}; extras={extras}")

    with get_connection() as conexao, conexao.cursor() as cursor:
        for task_type, config in settings.items():
            model_name = str(config.get("model_name") or "").strip()
            if not model_name:
                raise ValueError(f"Modelo não informado para {task_type}.")
            parameters = config.get("parameters") or {}
            dimensions = config.get("embedding_dimensions")
            cursor.execute(
                """
                SELECT id FROM ai_model_settings
                WHERE task_type = %s
                  AND scope_type = 'installation'
                  AND scope_id IS NULL
                  AND owner_user_id IS NULL
                  AND is_active = TRUE
                FOR UPDATE
                """,
                (task_type,),
            )
            existente = cursor.fetchone()
            if existente:
                cursor.execute(
                    """
                    UPDATE ai_model_settings
                    SET provider_code = %s,
                        credential_id = %s,
                        model_name = %s,
                        parameters_jsonb = %s,
                        embedding_dimensions = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                    """,
                    (
                        provider_code,
                        credential_id,
                        model_name,
                        Json(parameters),
                        dimensions,
                        str(existente[0]),
                    ),
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO ai_model_settings
                        (task_type, provider_code, credential_id, model_name,
                         parameters_jsonb, embedding_dimensions)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        task_type,
                        provider_code,
                        credential_id,
                        model_name,
                        Json(parameters),
                        dimensions,
                    ),
                )

        cursor.execute(
            """
            INSERT INTO ai_configuration_audit (action, changes_jsonb)
            VALUES ('model_settings_saved', %s)
            """,
            (Json({
                "provider_code": provider_code,
                "credential_id": str(credential_id) if credential_id else None,
                "models": {
                    tarefa: {
                        "model_name": config["model_name"],
                        "parameters": config.get("parameters") or {},
                        "embedding_dimensions": config.get("embedding_dimensions"),
                    }
                    for tarefa, config in settings.items()
                },
            }),),
        )


def list_configuration_audit(limit=20):
    with get_connection() as conexao, conexao.cursor() as cursor:
        cursor.execute(
            """
            SELECT action, changes_jsonb, created_at
            FROM ai_configuration_audit
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (int(limit),),
        )
        return [
            {"action": linha[0], "changes": linha[1], "created_at": linha[2]}
            for linha in cursor.fetchall()
        ]
