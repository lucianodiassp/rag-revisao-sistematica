import os

import requests

from backend.app.bibliographic_config import (
    SOURCE_KEY_ENV,
    SOURCE_LABELS,
    SOURCE_OPENALEX,
    SOURCE_PUBMED,
    SOURCE_SEMANTIC_SCHOLAR,
    SUPPORTED_SOURCES,
    clear_bibliographic_settings_cache,
    get_bibliographic_settings,
    get_environment_bibliographic_settings,
    get_source_config,
)
from backend.app.bibliographic_config_repository import (
    deactivate_installation_credential,
    get_installation_credential,
    get_installation_credentials,
    get_installation_source_settings,
    save_installation_credential,
    save_installation_source_setting,
    update_credential_validation,
)
from backend.app.secret_store import decrypt_secret, encrypt_secret, secret_hint


def _safe_error(erro, segredo=None):
    mensagem = str(erro).strip() or erro.__class__.__name__
    if segredo:
        mensagem = mensagem.replace(str(segredo), "[REDACTED]")
    return mensagem[:500]


def _validar_fonte(source_code):
    if source_code not in SUPPORTED_SOURCES:
        raise ValueError(f"Fonte bibliográfica desconhecida: {source_code}")


def _validar_configuracao(email, tool_name, timeout_seconds, max_retries):
    email = str(email or "").strip() or None
    if email and ("@" not in email or email.startswith("@") or email.endswith("@")):
        raise ValueError("Informe um e-mail de contato válido ou deixe o campo vazio.")
    tool_name = str(tool_name or "").strip()
    if not tool_name:
        raise ValueError("A identificação da aplicação não pode ficar vazia.")
    timeout_seconds = int(timeout_seconds)
    max_retries = int(max_retries)
    if not 1 <= timeout_seconds <= 120:
        raise ValueError("O timeout deve estar entre 1 e 120 segundos.")
    if not 1 <= max_retries <= 10:
        raise ValueError("O número de tentativas deve estar entre 1 e 10.")
    return email, tool_name[:100], timeout_seconds, max_retries


def inspect_source_access(source_code, api_key=None, config=None):
    """Executa uma consulta mínima e não persiste resultados bibliográficos."""
    _validar_fonte(source_code)
    config = config or get_source_config(source_code)
    chave = config.api_key if api_key is None else str(api_key or "").strip() or None

    headers = {"User-Agent": config.tool_name}
    try:
        if source_code == SOURCE_OPENALEX:
            url = "https://api.openalex.org/works"
            params = {"search": "systematic review", "per-page": 1}
            if config.contact_email:
                params["mailto"] = config.contact_email
            if chave:
                params["api_key"] = chave
        elif source_code == SOURCE_SEMANTIC_SCHOLAR:
            url = "https://api.semanticscholar.org/graph/v1/paper/search"
            params = {"query": "systematic review", "limit": 1, "fields": "paperId,title"}
            if config.contact_email:
                headers["User-Agent"] = f"{config.tool_name} (mailto:{config.contact_email})"
            if chave:
                headers["x-api-key"] = chave
        else:
            url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
            params = {"db": "pubmed", "term": "systematic review", "retmax": 1, "retmode": "json"}
            if config.contact_email:
                params["email"] = config.contact_email
            if config.tool_name:
                params["tool"] = config.tool_name
            if chave:
                params["api_key"] = chave

        resposta = requests.get(
            url,
            params=params,
            headers=headers,
            timeout=config.timeout_seconds,
        )
        resposta.raise_for_status()
        dados = resposta.json()
        if not isinstance(dados, dict):
            raise RuntimeError("A fonte respondeu em um formato inesperado.")
        if source_code == SOURCE_OPENALEX and "results" not in dados:
            raise RuntimeError("A resposta do OpenAlex não contém o campo results.")
        if source_code == SOURCE_SEMANTIC_SCHOLAR and "data" not in dados:
            raise RuntimeError("A resposta do Semantic Scholar não contém o campo data.")
        if source_code == SOURCE_PUBMED and "esearchresult" not in dados:
            raise RuntimeError("A resposta do PubMed não contém o campo esearchresult.")
        return {
            "source_code": source_code,
            "label": SOURCE_LABELS[source_code],
            "authenticated": bool(chave),
            "status_code": resposta.status_code,
        }
    except Exception as erro:
        raise RuntimeError(_safe_error(erro, chave)) from erro


def save_source_settings(
    source_code,
    enabled,
    contact_email,
    tool_name,
    timeout_seconds,
    max_retries,
):
    _validar_fonte(source_code)
    valores = _validar_configuracao(
        contact_email,
        tool_name,
        timeout_seconds,
        max_retries,
    )
    save_installation_source_setting(source_code, bool(enabled), *valores)
    clear_bibliographic_settings_cache()


def save_validated_source_key(source_code, api_key, label=None):
    _validar_fonte(source_code)
    api_key = str(api_key or "").strip()
    if not api_key:
        raise ValueError("Informe uma chave de API para executar o teste.")
    resultado = inspect_source_access(source_code, api_key=api_key)
    label = str(label or "").strip() or f"Chave {SOURCE_LABELS[source_code]} local"
    credential_id = save_installation_credential(
        source_code,
        label,
        encrypt_secret(api_key),
        secret_hint(api_key),
        validation_status="valid",
    )
    clear_bibliographic_settings_cache()
    return credential_id, resultado


def import_environment_source_key(source_code):
    _validar_fonte(source_code)
    nome_variavel = SOURCE_KEY_ENV[source_code]
    api_key = os.getenv(nome_variavel)
    if not api_key:
        raise RuntimeError(f"{nome_variavel} não está disponível no ambiente atual.")
    return save_validated_source_key(
        source_code,
        api_key,
        f"Chave {SOURCE_LABELS[source_code]} importada do ambiente",
    )


def inspect_saved_source_key(source_code):
    credencial = get_installation_credential(source_code)
    if not credencial:
        raise RuntimeError("Nenhuma credencial cifrada foi salva para esta fonte.")
    segredo = decrypt_secret(credencial["encrypted_secret"])
    try:
        resultado = inspect_source_access(source_code, api_key=segredo)
        update_credential_validation(credencial["id"], "valid")
        return resultado
    except Exception as erro:
        update_credential_validation(
            credencial["id"],
            "invalid",
            _safe_error(erro, segredo),
        )
        raise
    finally:
        clear_bibliographic_settings_cache()


def inspect_effective_source_access(source_code):
    return inspect_source_access(source_code)


def remove_saved_source_key(source_code):
    removida = deactivate_installation_credential(source_code)
    clear_bibliographic_settings_cache()
    return removida


def get_bibliographic_admin_state():
    credentials = get_installation_credentials()
    saved_settings = get_installation_source_settings()
    configuration_error = None
    try:
        settings = get_bibliographic_settings()
    except RuntimeError as erro:
        settings = get_environment_bibliographic_settings()
        configuration_error = str(erro)

    fontes = {}
    for source_code, config in settings.items():
        credential = credentials.get(source_code)
        fontes[source_code] = {
            "config": config,
            "credential": (
                {
                    "id": str(credential["id"]),
                    "label": credential["label"],
                    "secret_hint": credential["secret_hint"],
                    "validation_status": credential["validation_status"],
                    "last_validated_at": credential["last_validated_at"],
                    "validation_error": credential["validation_error"],
                }
                if credential else None
            ),
            "environment_key_available": bool(os.getenv(SOURCE_KEY_ENV[source_code])),
            "saved_settings": saved_settings.get(source_code),
        }
    return {"sources": fontes, "configuration_error": configuration_error}
