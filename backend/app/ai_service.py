from google.genai import types

from backend.app.ai_config import (
    CURRENT_VECTOR_DIMENSIONS,
    clear_ai_settings_cache,
    get_embedding_config,
    get_generation_config,
)
from backend.app.gemini_client import clear_ai_client_cache, get_gemini_client


def generate_content(
    task,
    contents,
    *,
    response_mime_type=None,
    system_instruction=None,
):
    """Executa geração usando a configuração central da função solicitada."""
    config = get_generation_config(task)
    parametros = {}
    if response_mime_type:
        parametros["response_mime_type"] = response_mime_type
    if system_instruction:
        parametros["system_instruction"] = system_instruction
    if config.effective_temperature is not None:
        parametros["temperature"] = config.effective_temperature

    return get_gemini_client().models.generate_content(
        model=config.model,
        contents=contents,
        config=types.GenerateContentConfig(**parametros),
    )


def generate_embedding(contents):
    """Gera embedding com modelo e dimensão definidos em um único local."""
    config = get_embedding_config()
    if config.dimensions != CURRENT_VECTOR_DIMENSIONS:
        raise RuntimeError(
            "O schema atual usa vector(768). Altere AI_EMBEDDING_DIMENSIONS somente "
            "após uma migração e reindexação completa dos embeddings."
        )
    resposta = get_gemini_client().models.embed_content(
        model=config.model,
        contents=contents,
        config=types.EmbedContentConfig(output_dimensionality=config.dimensions),
    )
    return resposta.embeddings[0].values


def reload_ai_runtime():
    """Invalida configuração e cliente após uma futura alteração persistida."""
    clear_ai_client_cache()
    clear_ai_settings_cache()
