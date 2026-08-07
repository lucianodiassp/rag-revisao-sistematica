import os
from dataclasses import dataclass, field, replace
from functools import lru_cache

from backend.app.ai_config import load_project_environment


SOURCE_OPENALEX = "openalex"
SOURCE_SEMANTIC_SCHOLAR = "semantic_scholar"
SOURCE_PUBMED = "pubmed"
SUPPORTED_SOURCES = (
    SOURCE_OPENALEX,
    SOURCE_SEMANTIC_SCHOLAR,
    SOURCE_PUBMED,
)
SOURCE_LABELS = {
    SOURCE_OPENALEX: "OpenAlex",
    SOURCE_SEMANTIC_SCHOLAR: "Semantic Scholar",
    SOURCE_PUBMED: "PubMed",
}
SOURCE_KEY_ENV = {
    SOURCE_OPENALEX: "OPENALEX_API_KEY",
    SOURCE_SEMANTIC_SCHOLAR: "SEMANTIC_SCHOLAR_API_KEY",
    SOURCE_PUBMED: "PUBMED_API_KEY",
}
SOURCE_EMAIL_ENV = {
    SOURCE_OPENALEX: "OPENALEX_EMAIL",
    SOURCE_SEMANTIC_SCHOLAR: "SEMANTIC_SCHOLAR_EMAIL",
    SOURCE_PUBMED: "PUBMED_EMAIL",
}
SOURCE_ENABLED_ENV = {
    SOURCE_OPENALEX: "OPENALEX_ENABLED",
    SOURCE_SEMANTIC_SCHOLAR: "SEMANTIC_SCHOLAR_ENABLED",
    SOURCE_PUBMED: "PUBMED_ENABLED",
}


load_project_environment()


def _ler_booleano(nome, padrao=True):
    valor = os.getenv(nome)
    if valor is None:
        return padrao
    return valor.strip().lower() not in {"0", "false", "no", "off"}


def _ler_inteiro(nome, padrao, minimo, maximo):
    try:
        valor = int(os.getenv(nome, str(padrao)))
    except ValueError as erro:
        raise RuntimeError(f"{nome} deve ser um número inteiro.") from erro
    if not minimo <= valor <= maximo:
        raise RuntimeError(f"{nome} deve estar entre {minimo} e {maximo}.")
    return valor


@dataclass(frozen=True)
class BibliographicSourceConfig:
    source_code: str
    label: str
    enabled: bool
    api_key: str | None = field(repr=False)
    contact_email: str | None
    tool_name: str
    timeout_seconds: int
    max_retries: int
    source: str = "environment"
    credential_source: str = "environment"

    def public_metadata(self):
        return {
            "source_code": self.source_code,
            "label": self.label,
            "enabled": self.enabled,
            "authenticated": bool(self.api_key),
            "contact_identification_configured": bool(self.contact_email),
            "tool_name": self.tool_name,
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
            "configuration_source": self.source,
            "credential_source": self.credential_source,
        }


def get_environment_bibliographic_settings():
    email_generico = os.getenv("BIBLIOGRAPHIC_CONTACT_EMAIL")
    tool_padrao = os.getenv("BIBLIOGRAPHIC_TOOL_NAME", "rag-revisao-sistematica").strip()
    timeout = _ler_inteiro("BIBLIOGRAPHIC_TIMEOUT_SECONDS", 30, 1, 120)
    tentativas = _ler_inteiro("BIBLIOGRAPHIC_MAX_RETRIES", 3, 1, 10)
    configuracoes = {}
    for source_code in SUPPORTED_SOURCES:
        email = os.getenv(SOURCE_EMAIL_ENV[source_code], email_generico or "").strip() or None
        configuracoes[source_code] = BibliographicSourceConfig(
            source_code=source_code,
            label=SOURCE_LABELS[source_code],
            enabled=_ler_booleano(SOURCE_ENABLED_ENV[source_code]),
            api_key=os.getenv(SOURCE_KEY_ENV[source_code]) or None,
            contact_email=email,
            tool_name=(
                os.getenv("PUBMED_TOOL", tool_padrao).strip()
                if source_code == SOURCE_PUBMED else tool_padrao
            ),
            timeout_seconds=timeout,
            max_retries=tentativas,
        )
    return configuracoes


def _apply_database_overrides(configuracoes):
    try:
        from backend.app.bibliographic_config_repository import (
            bibliographic_tables_available,
            get_installation_credentials,
            get_installation_source_settings,
        )

        if not bibliographic_tables_available():
            return configuracoes
        settings = get_installation_source_settings()
        credentials = get_installation_credentials()
    except Exception:
        return configuracoes

    from backend.app.secret_store import decrypt_secret

    resultado = {}
    for source_code, config in configuracoes.items():
        salvo = settings.get(source_code)
        if salvo:
            config = replace(
                config,
                enabled=salvo["is_enabled"],
                contact_email=salvo.get("contact_email") or None,
                tool_name=salvo["tool_name"],
                timeout_seconds=salvo["request_timeout_seconds"],
                max_retries=salvo["max_retries"],
                source="database",
            )
        credential = credentials.get(source_code)
        if credential:
            config = replace(
                config,
                api_key=decrypt_secret(credential["encrypted_secret"]),
                credential_source="encrypted_database",
            )
        resultado[source_code] = config
    return resultado


@lru_cache(maxsize=1)
def get_bibliographic_settings():
    return _apply_database_overrides(get_environment_bibliographic_settings())


def get_source_config(source_code):
    try:
        return get_bibliographic_settings()[source_code]
    except KeyError as erro:
        raise ValueError(f"Fonte bibliográfica desconhecida: {source_code}") from erro


def clear_bibliographic_settings_cache():
    get_bibliographic_settings.cache_clear()
