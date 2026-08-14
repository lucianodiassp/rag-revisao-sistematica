import os

from google import genai

from backend.app.ai_config import (
    GENERATION_TASKS,
    PROVIDER_GOOGLE_GEMINI,
    TASK_RERANKING,
    get_environment_ai_settings,
    get_ai_settings,
)
from backend.app.ai_config_repository import (
    get_installation_credential,
    get_installation_model_settings,
    save_installation_credential,
    save_installation_model_settings,
    update_credential_validation,
)
from backend.app.ai_service import reload_ai_runtime
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


def import_environment_gemini_key(label="Chave importada do ambiente"):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY não está disponível no ambiente atual.")
    return save_validated_gemini_key(api_key, label)


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


def get_ai_admin_state():
    credential = get_installation_credential(PROVIDER_GOOGLE_GEMINI)
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
        "credential_source": settings.credential_source,
        "environment_key_available": bool(os.getenv("GEMINI_API_KEY")),
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
    except (TypeError, ValueError) as erro:
        raise ValueError("Informe limites inteiros para o reranking.") from erro
    if not 4 <= candidate_limit <= 30:
        raise ValueError("Os candidatos do reranking devem ficar entre 4 e 30.")
    if not 2 <= final_limit <= 10:
        raise ValueError("Os trechos finais do reranking devem ficar entre 2 e 10.")
    if final_limit > candidate_limit:
        raise ValueError("O limite final do reranking não pode superar os candidatos.")

    credential = get_installation_credential(PROVIDER_GOOGLE_GEMINI)
    credential_id = str(credential["id"]) if credential else None
    configuracoes = {}
    for task in GENERATION_TASKS:
        item = generation[task]
        parameters = {
            chave: valor
            for chave, valor in item.items()
            if chave != "model_name" and valor is not None
        }
        configuracoes[task] = {
            "model_name": str(item["model_name"]).strip(),
            "parameters": parameters,
            "embedding_dimensions": None,
        }
    configuracoes["embedding"] = {
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
