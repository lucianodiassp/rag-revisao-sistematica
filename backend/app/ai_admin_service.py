import os

from google import genai

from backend.app.ai_config import (
    GENERATION_TASKS,
    PROVIDER_GOOGLE_GEMINI,
    PROVIDER_OPENAI,
    PROVIDER_ENV_KEYS,
    SUPPORTED_GENERATION_PROVIDERS,
    TASK_RERANKING,
    get_environment_ai_settings,
    get_ai_settings,
)
from backend.app.ai_config_repository import (
    get_installation_credential,
    get_installation_model_settings,
    list_installation_credentials,
    save_installation_credential,
    save_installation_model_settings,
    update_credential_validation,
)
from backend.app.ai_service import reload_ai_runtime
from backend.app.openai_client import OpenAIResponsesClient
from backend.app.secret_store import decrypt_secret, encrypt_secret, secret_hint


def _safe_error(erro, segredo=None):
    mensagem = str(erro).strip() or erro.__class__.__name__
    if segredo:
        mensagem = mensagem.replace(str(segredo), "[REDACTED]")
    return mensagem[:500]


def _normalizar_nome_modelo(nome):
    nome = str(nome or "").strip()
    return nome.removeprefix("models/")


def inspect_gemini_key(api_key):
    """Valida uma chave por listagem de modelos, sem gerar conteúdo faturável."""
    api_key = str(api_key or "").strip()
    if not api_key:
        raise ValueError("Informe uma chave de API para executar o teste.")

    try:
        cliente = genai.Client(api_key=api_key)
        modelos = list(cliente.models.list())
    except Exception as erro:
        raise RuntimeError(_safe_error(erro, api_key)) from erro

    generativos = set()
    embeddings = set()
    todos = set()
    for modelo in modelos:
        nome = _normalizar_nome_modelo(getattr(modelo, "name", ""))
        if not nome:
            continue
        todos.add(nome)
        acoes = {
            str(acao).replace("_", "").lower()
            for acao in (getattr(modelo, "supported_actions", None) or [])
        }
        if "generatecontent" in acoes:
            generativos.add(nome)
        if "embedcontent" in acoes or "embedding" in nome.lower():
            embeddings.add(nome)

    if not todos:
        raise RuntimeError("A credencial respondeu, mas não retornou modelos disponíveis.")
    return {
        "generative": sorted(generativos),
        "embedding": sorted(embeddings),
        "all": sorted(todos),
    }


def _openai_generation_model(model_name):
    nome = str(model_name or "").lower()
    marcadores_nao_generativos = (
        "embedding",
        "moderation",
        "whisper",
        "tts",
        "transcribe",
        "dall-e",
        "image",
        "realtime",
        "audio",
    )
    return bool(nome) and not any(item in nome for item in marcadores_nao_generativos)


def inspect_openai_key(api_key):
    """Valida uma chave OpenAI pela listagem de modelos, sem gerar conteúdo."""
    api_key = str(api_key or "").strip()
    if not api_key:
        raise ValueError("Informe uma chave de API para executar o teste.")
    try:
        todos = OpenAIResponsesClient(api_key).list_models()
    except Exception as erro:
        raise RuntimeError(_safe_error(erro, api_key)) from erro
    if not todos:
        raise RuntimeError("A credencial respondeu, mas não retornou modelos disponíveis.")
    return {
        "generative": sorted(item for item in todos if _openai_generation_model(item)),
        "embedding": [],
        "all": sorted(todos),
    }


def inspect_provider_key(provider_code, api_key):
    if provider_code == PROVIDER_GOOGLE_GEMINI:
        return inspect_gemini_key(api_key)
    if provider_code == PROVIDER_OPENAI:
        return inspect_openai_key(api_key)
    raise ValueError(f"Provedor de IA não suportado: {provider_code}.")


def save_validated_gemini_key(api_key, label="Chave Gemini local"):
    modelos = inspect_gemini_key(api_key)
    credential_id = save_installation_credential(
        PROVIDER_GOOGLE_GEMINI,
        label.strip() or "Chave Gemini local",
        encrypt_secret(api_key),
        secret_hint(api_key),
        validation_status="valid",
    )
    reload_ai_runtime()
    return credential_id, modelos


def save_validated_provider_key(provider_code, api_key, label=None):
    if provider_code not in SUPPORTED_GENERATION_PROVIDERS:
        raise ValueError(f"Provedor de IA não suportado: {provider_code}.")
    modelos = inspect_provider_key(provider_code, api_key)
    rotulo_padrao = (
        "Chave Gemini local"
        if provider_code == PROVIDER_GOOGLE_GEMINI
        else "Chave OpenAI local"
    )
    credential_id = save_installation_credential(
        provider_code,
        str(label or rotulo_padrao).strip() or rotulo_padrao,
        encrypt_secret(api_key),
        secret_hint(api_key),
        validation_status="valid",
    )
    reload_ai_runtime()
    return credential_id, modelos


def import_environment_gemini_key(label="Chave importada do ambiente"):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY não está disponível no ambiente atual.")
    return save_validated_gemini_key(api_key, label)


def import_environment_provider_key(provider_code, label="Chave importada do ambiente"):
    nome_variavel = PROVIDER_ENV_KEYS.get(provider_code)
    if not nome_variavel:
        raise ValueError(f"Provedor de IA não suportado: {provider_code}.")
    api_key = os.getenv(nome_variavel)
    if not api_key:
        raise RuntimeError(f"{nome_variavel} não está disponível no ambiente atual.")
    return save_validated_provider_key(provider_code, api_key, label)


def inspect_saved_gemini_key():
    credencial = get_installation_credential(PROVIDER_GOOGLE_GEMINI)
    if not credencial:
        raise RuntimeError("Nenhuma credencial cifrada foi salva para esta instalação.")
    segredo = decrypt_secret(credencial["encrypted_secret"])
    try:
        modelos = inspect_gemini_key(segredo)
        update_credential_validation(credencial["id"], "valid")
        return modelos
    except Exception as erro:
        update_credential_validation(
            credencial["id"],
            "invalid",
            _safe_error(erro, segredo),
        )
        raise
    finally:
        reload_ai_runtime()


def inspect_saved_provider_key(provider_code):
    credencial = get_installation_credential(provider_code)
    if not credencial:
        raise RuntimeError("Nenhuma credencial cifrada foi salva para este provedor.")
    segredo = decrypt_secret(credencial["encrypted_secret"])
    try:
        modelos = inspect_provider_key(provider_code, segredo)
        update_credential_validation(credencial["id"], "valid")
        return modelos
    except Exception as erro:
        update_credential_validation(
            credencial["id"],
            "invalid",
            _safe_error(erro, segredo),
        )
        raise
    finally:
        reload_ai_runtime()


def get_ai_admin_state():
    credentials = list_installation_credentials()
    credential = credentials.get(PROVIDER_GOOGLE_GEMINI)
    configuration_error = None
    try:
        settings = get_ai_settings()
    except RuntimeError as erro:
        # Mantém a tela utilizável para substituir uma credencial cujo arquivo-mestre
        # foi perdido durante uma restauração ou mudança de computador.
        settings = get_environment_ai_settings()
        configuration_error = str(erro)
    saved_models = get_installation_model_settings()
    return {
        "provider": settings.provider,
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
        "credentials": {
            provider_code: {
                "id": str(item["id"]),
                "provider_code": provider_code,
                "label": item["label"],
                "secret_hint": item["secret_hint"],
                "validation_status": item["validation_status"],
                "last_validated_at": item["last_validated_at"],
                "validation_error": item["validation_error"],
            }
            for provider_code, item in credentials.items()
        },
        "credential_source": settings.credential_source,
        "environment_key_available": bool(os.getenv("GEMINI_API_KEY")),
        "environment_keys_available": {
            provider_code: bool(os.getenv(nome_variavel))
            for provider_code, nome_variavel in PROVIDER_ENV_KEYS.items()
        },
        "generation": settings.generation,
        "embedding": settings.embedding,
        "saved_models": saved_models,
        "configuration_error": configuration_error,
    }


def save_ai_models(generation, embedding_model, embedding_dimensions=768):
    reranking = generation.get(TASK_RERANKING) or {}
    try:
        candidate_limit = int(reranking.get("candidate_limit"))
        final_limit = int(reranking.get("final_limit"))
        rrf_weight = float(reranking.get("rrf_weight", 0.0))
    except (TypeError, ValueError) as erro:
        raise ValueError("Informe limites válidos e um peso entre 0 e 1 para o reranking.") from erro
    if not 4 <= candidate_limit <= 30:
        raise ValueError("Os candidatos do reranking devem ficar entre 4 e 30.")
    if not 2 <= final_limit <= 10:
        raise ValueError("Os trechos finais do reranking devem ficar entre 2 e 10.")
    if final_limit > candidate_limit:
        raise ValueError("O limite final do reranking não pode superar os candidatos.")
    if not 0 <= rrf_weight <= 1:
        raise ValueError("O peso RRF do reranking deve estar entre 0 e 1.")

    credentials = {
        provider_code: get_installation_credential(provider_code)
        for provider_code in SUPPORTED_GENERATION_PROVIDERS
    }
    credential = credentials[PROVIDER_GOOGLE_GEMINI]
    credential_id = str(credential["id"]) if credential else None
    configuracoes = {}
    for task in GENERATION_TASKS:
        item = generation[task]
        provider_code = str(
            item.get("provider_code") or PROVIDER_GOOGLE_GEMINI
        ).strip()
        if provider_code not in SUPPORTED_GENERATION_PROVIDERS:
            raise ValueError(f"Provedor inválido para {task}: {provider_code}.")
        provider_credential = credentials.get(provider_code)
        parameters = {
            chave: valor
            for chave, valor in item.items()
            if chave not in {"model_name", "provider_code"} and valor is not None
        }
        configuracoes[task] = {
            "provider_code": provider_code,
            "credential_id": (
                str(provider_credential["id"]) if provider_credential else None
            ),
            "model_name": str(item["model_name"]).strip(),
            "parameters": parameters,
            "embedding_dimensions": None,
        }
    configuracoes["embedding"] = {
        "provider_code": PROVIDER_GOOGLE_GEMINI,
        "credential_id": credential_id,
        "model_name": str(embedding_model).strip(),
        "parameters": {},
        "embedding_dimensions": int(embedding_dimensions),
    }
    save_installation_model_settings(
        PROVIDER_GOOGLE_GEMINI,
        credential_id,
        configuracoes,
    )
    reload_ai_runtime()
