"""Eventos operacionais estruturados e classificação segura de falhas."""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from backend.app.version import APP_VERSION


SENSITIVE_KEY_PARTS = (
    "api_key",
    "apikey",
    "token",
    "secret",
    "password",
    "authorization",
    "cookie",
    "credential",
    "email",
    "query",
    "prompt",
    "content",
    "answer",
    "abstract",
    "quote",
)
SECRET_ASSIGNMENT = re.compile(
    r"(?i)(api[_-]?key|token|secret|password|authorization|cookie)"
    r"(\s*[:=]\s*)[^\s,;]+"
)
BEARER_VALUE = re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+")


@dataclass(frozen=True)
class OperationalIssue:
    category: str
    code: str
    retryable: bool
    user_message: str
    recommended_action: str

    def as_dict(self):
        return asdict(self)


def _is_sensitive_key(key) -> bool:
    normalized = str(key or "").strip().lower()
    return any(part in normalized for part in SENSITIVE_KEY_PARTS)


def sanitize_text(value, *, maximum=500) -> str:
    text = str(value or "").replace("\x00", "")
    text = SECRET_ASSIGNMENT.sub(r"\1\2[oculto]", text)
    text = BEARER_VALUE.sub("Bearer [oculto]", text)
    return text[:maximum]


def sanitize_fields(value, *, depth=0):
    """Remove segredos e limita estruturas antes de enviá-las ao log."""
    if depth > 5:
        return "[limite de profundidade]"
    if isinstance(value, dict):
        result = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= 50:
                result["_truncated"] = True
                break
            result[str(key)] = (
                "[oculto]"
                if _is_sensitive_key(key)
                else sanitize_fields(item, depth=depth + 1)
            )
        return result
    if isinstance(value, (list, tuple, set)):
        items = list(value)
        return [sanitize_fields(item, depth=depth + 1) for item in items[:50]]
    if isinstance(value, (str, bytes)):
        return sanitize_text(value.decode(errors="replace") if isinstance(value, bytes) else value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return sanitize_text(value)


def log_event(
    event,
    *,
    component,
    level="info",
    category="application",
    message=None,
    **fields,
):
    """Escreve uma linha JSON sem dados científicos ou credenciais."""
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": str(level).lower(),
        "event": str(event),
        "component": str(component),
        "category": str(category),
        "app_version": APP_VERSION,
        "deployment_profile": os.getenv("RAG_DEPLOYMENT_PROFILE", "local"),
        "user_mode": os.getenv("RAG_USER_MODE", "single_user"),
    }
    if message:
        payload["message"] = sanitize_text(message)
    payload.update(sanitize_fields(fields))
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True), flush=True)
    return payload


def classify_error(error, *, component_hint=None) -> OperationalIssue:
    """Converte detalhes técnicos em uma categoria e ação operacional segura."""
    message = str(error or "").lower()
    class_name = type(error).__name__.lower()
    module_name = type(error).__module__.lower()
    hint = str(component_hint or "").lower()

    if any(
        marker in message
        for marker in (
            "deve ser configur",
            "não foi configur",
            "configuração inválida",
            "environment variable",
            "master key",
            "chave-mestra",
            "credencial ausente",
        )
    ):
        return OperationalIssue(
            "configuration",
            "invalid_configuration",
            False,
            "Uma configuração obrigatória está ausente ou inválida.",
            "Revise o preflight e os arquivos de configuração sem publicar seus valores.",
        )

    if "psycopg" in module_name or "operationalerror" in class_name or any(
        marker in message
        for marker in (
            "could not connect to server",
            "connection to server",
            "database is starting",
            "the database system",
            "no route to host",
        )
    ):
        return OperationalIssue(
            "database",
            "database_unavailable",
            True,
            "O PostgreSQL não está disponível para a aplicação.",
            "Confira a saúde do serviço db e, depois, a execução das migrações.",
        )

    if "storage" in hint or any(
        marker in message
        for marker in (
            "no space left",
            "espaço insuficiente",
            "permission denied",
            "read-only file system",
            "não permite gravação",
        )
    ):
        return OperationalIssue(
            "storage",
            "storage_unavailable",
            False,
            "O armazenamento persistente requer atenção.",
            "Confira permissões, volumes montados, limites e espaço livre antes de repetir.",
        )

    rate_limited = any(
        marker in message
        for marker in ("429", "resource_exhausted", "rate limit", "too many requests")
    )
    unavailable = any(
        marker in message
        for marker in ("503", "unavailable", "temporarily", "timed out", "timeout")
    )
    if hint == "bibliographic_source":
        return OperationalIssue(
            "bibliographic_source",
            "source_rate_limited" if rate_limited else "source_unavailable",
            rate_limited or unavailable,
            "Uma fonte bibliográfica recusou ou não concluiu a consulta.",
            "Confira a fonte configurada e aguarde a nova tentativa quando a falha for temporária.",
        )
    if hint == "ai_provider" or rate_limited or unavailable:
        return OperationalIssue(
            "ai_provider",
            "provider_rate_limited" if rate_limited else "provider_unavailable",
            rate_limited or unavailable,
            "O provedor de IA não concluiu a solicitação.",
            "Confira a configuração do modelo e aguarde a nova tentativa em indisponibilidades temporárias.",
        )

    return OperationalIssue(
        "application",
        "processing_error",
        False,
        "A aplicação não concluiu o processamento solicitado.",
        "Consulte o identificador do evento nos logs e revise os dados de entrada antes de repetir.",
    )
