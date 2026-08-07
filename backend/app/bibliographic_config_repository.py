from psycopg2.extras import Json

from backend.app.bibliographic_config import SUPPORTED_SOURCES
from backend.app.database import get_connection


def _validar_fonte(source_code):
    if source_code not in SUPPORTED_SOURCES:
        raise ValueError(f"Fonte bibliográfica desconhecida: {source_code}")


def bibliographic_tables_available():
    try:
        with get_connection() as conexao, conexao.cursor() as cursor:
            cursor.execute(
                """
                SELECT to_regclass('public.bibliographic_source_settings') IS NOT NULL
                   AND to_regclass('public.bibliographic_source_credentials') IS NOT NULL
                """
            )
            return bool(cursor.fetchone()[0])
    except Exception:
        return False


def get_installation_source_settings():
    with get_connection() as conexao, conexao.cursor() as cursor:
        cursor.execute(
            """
            SELECT source_code, is_enabled, contact_email, tool_name,
                   request_timeout_seconds, max_retries, created_at, updated_at
            FROM bibliographic_source_settings
            WHERE scope_type = 'installation'
              AND scope_id IS NULL
              AND owner_user_id IS NULL
            ORDER BY source_code
            """
        )
        colunas = [item[0] for item in cursor.description]
        return {linha[0]: dict(zip(colunas, linha)) for linha in cursor.fetchall()}


def save_installation_source_setting(
    source_code,
    is_enabled,
    contact_email,
    tool_name,
    request_timeout_seconds,
    max_retries,
):
    _validar_fonte(source_code)
    with get_connection() as conexao, conexao.cursor() as cursor:
        cursor.execute(
            """
            SELECT id
            FROM bibliographic_source_settings
            WHERE source_code = %s
              AND scope_type = 'installation'
              AND scope_id IS NULL
              AND owner_user_id IS NULL
            FOR UPDATE
            """,
            (source_code,),
        )
        existente = cursor.fetchone()
        valores = (
            bool(is_enabled),
            contact_email,
            tool_name,
            int(request_timeout_seconds),
            int(max_retries),
        )
        if existente:
            cursor.execute(
                """
                UPDATE bibliographic_source_settings
                SET is_enabled = %s,
                    contact_email = %s,
                    tool_name = %s,
                    request_timeout_seconds = %s,
                    max_retries = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (*valores, str(existente[0])),
            )
        else:
            cursor.execute(
                """
                INSERT INTO bibliographic_source_settings
                    (source_code, is_enabled, contact_email, tool_name,
                     request_timeout_seconds, max_retries)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (source_code, *valores),
            )
        cursor.execute(
            """
            INSERT INTO bibliographic_configuration_audit
                (action, source_code, changes_jsonb)
            VALUES ('source_settings_saved', %s, %s)
            """,
            (
                source_code,
                Json({
                    "is_enabled": bool(is_enabled),
                    "contact_email": contact_email,
                    "tool_name": tool_name,
                    "request_timeout_seconds": int(request_timeout_seconds),
                    "max_retries": int(max_retries),
                }),
            ),
        )


def get_installation_credentials():
    with get_connection() as conexao, conexao.cursor() as cursor:
        cursor.execute(
            """
            SELECT id, source_code, label, encrypted_secret, secret_hint,
                   validation_status, last_validated_at, validation_error,
                   created_at, updated_at
            FROM bibliographic_source_credentials
            WHERE scope_type = 'installation'
              AND scope_id IS NULL
              AND owner_user_id IS NULL
              AND is_active = TRUE
            ORDER BY source_code, updated_at DESC
            """
        )
        colunas = [item[0] for item in cursor.description]
        return {linha[1]: dict(zip(colunas, linha)) for linha in cursor.fetchall()}


def get_installation_credential(source_code):
    _validar_fonte(source_code)
    return get_installation_credentials().get(source_code)


def save_installation_credential(
    source_code,
    label,
    encrypted_secret,
    secret_hint_value,
    validation_status="untested",
    validation_error=None,
):
    _validar_fonte(source_code)
    with get_connection() as conexao, conexao.cursor() as cursor:
        cursor.execute(
            """
            SELECT id
            FROM bibliographic_source_credentials
            WHERE source_code = %s
              AND scope_type = 'installation'
              AND scope_id IS NULL
              AND owner_user_id IS NULL
              AND is_active = TRUE
            FOR UPDATE
            """,
            (source_code,),
        )
        existente = cursor.fetchone()
        if existente:
            credential_id = str(existente[0])
            cursor.execute(
                """
                UPDATE bibliographic_source_credentials
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
            action = "credential_replaced"
        else:
            cursor.execute(
                """
                INSERT INTO bibliographic_source_credentials
                    (source_code, label, encrypted_secret, secret_hint,
                     validation_status, last_validated_at, validation_error)
                VALUES (%s, %s, %s, %s, %s,
                        CASE WHEN %s IN ('valid', 'invalid') THEN CURRENT_TIMESTAMP END,
                        %s)
                RETURNING id
                """,
                (
                    source_code,
                    label,
                    encrypted_secret,
                    secret_hint_value,
                    validation_status,
                    validation_status,
                    validation_error,
                ),
            )
            credential_id = str(cursor.fetchone()[0])
            action = "credential_created"

        cursor.execute(
            """
            INSERT INTO bibliographic_configuration_audit
                (action, source_code, changes_jsonb)
            VALUES (%s, %s, %s)
            """,
            (
                action,
                source_code,
                Json({
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
            UPDATE bibliographic_source_credentials
            SET validation_status = %s,
                last_validated_at = CURRENT_TIMESTAMP,
                validation_error = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s AND scope_type = 'installation' AND is_active = TRUE
            RETURNING source_code
            """,
            (status, error, str(credential_id)),
        )
        linha = cursor.fetchone()
        if not linha:
            raise ValueError("Credencial ativa não encontrada.")
        cursor.execute(
            """
            INSERT INTO bibliographic_configuration_audit
                (action, source_code, changes_jsonb)
            VALUES ('credential_validated', %s, %s)
            """,
            (linha[0], Json({"credential_id": str(credential_id), "status": status})),
        )


def deactivate_installation_credential(source_code):
    _validar_fonte(source_code)
    with get_connection() as conexao, conexao.cursor() as cursor:
        cursor.execute(
            """
            UPDATE bibliographic_source_credentials
            SET is_active = FALSE, updated_at = CURRENT_TIMESTAMP
            WHERE source_code = %s
              AND scope_type = 'installation'
              AND scope_id IS NULL
              AND owner_user_id IS NULL
              AND is_active = TRUE
            RETURNING id
            """,
            (source_code,),
        )
        removida = cursor.fetchone()
        if removida:
            cursor.execute(
                """
                INSERT INTO bibliographic_configuration_audit
                    (action, source_code, changes_jsonb)
                VALUES ('credential_deactivated', %s, %s)
                """,
                (source_code, Json({"credential_id": str(removida[0])})),
            )
        return bool(removida)


def list_configuration_audit(limit=30):
    with get_connection() as conexao, conexao.cursor() as cursor:
        cursor.execute(
            """
            SELECT action, source_code, changes_jsonb, created_at
            FROM bibliographic_configuration_audit
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (int(limit),),
        )
        return [
            {
                "action": linha[0],
                "source_code": linha[1],
                "changes": linha[2],
                "created_at": linha[3],
            }
            for linha in cursor.fetchall()
        ]
