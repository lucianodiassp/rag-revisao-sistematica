import os

from google.genai import types

from backend.app.ai_config import (
    CURRENT_VECTOR_DIMENSIONS,
    PROVIDER_GOOGLE_GEMINI,
    PROVIDER_OPENAI,
    clear_ai_settings_cache,
    get_embedding_config,
    get_generation_config,
)
from backend.app.gemini_client import clear_ai_client_cache, get_gemini_client
from backend.app.openai_client import clear_openai_client_cache, get_openai_client


def generate_content(
    task,
    contents,
    *,
    response_mime_type=None,
    system_instruction=None,
):
    """Executa geração usando a configuração central da função solicitada."""
    config = get_generation_config(task)
    if config.provider == PROVIDER_OPENAI:
        return get_openai_client().generate_content(
            model=config.model,
            contents=contents,
            response_mime_type=response_mime_type,
            system_instruction=system_instruction,
            temperature=config.effective_temperature,
        )
    if config.provider != PROVIDER_GOOGLE_GEMINI:
        raise RuntimeError(f"Provedor de IA não suportado: {config.provider}.")

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


def generate_multimodal_content(
    task,
    prompt,
    image_bytes,
    *,
    mime_type="image/png",
    response_mime_type=None,
    system_instruction=None,
):
    """Envia um único recorte em memória, sem persistir a imagem ou seu base64."""
    if not isinstance(image_bytes, (bytes, bytearray)) or not image_bytes:
        raise ValueError("A imagem para interpretação está vazia.")
    maximum = max(1, int(os.getenv("AI_VISUAL_MAX_IMAGE_MB", "8"))) * 1024 * 1024
    if len(image_bytes) > maximum:
        raise ValueError("O recorte visual excede o limite seguro configurado.")
    config = get_generation_config(task)
    if config.provider == PROVIDER_OPENAI:
        return get_openai_client().generate_multimodal_content(
            model=config.model,
            prompt=prompt,
            image_bytes=bytes(image_bytes),
            mime_type=mime_type,
            response_mime_type=response_mime_type,
            system_instruction=system_instruction,
            temperature=config.effective_temperature,
        )
    if config.provider != PROVIDER_GOOGLE_GEMINI:
        raise RuntimeError(f"Provedor de IA não suportado: {config.provider}.")
    parametros = {}
    if response_mime_type:
        parametros["response_mime_type"] = response_mime_type
    if system_instruction:
        parametros["system_instruction"] = system_instruction
    if config.effective_temperature is not None:
        parametros["temperature"] = config.effective_temperature
    return get_gemini_client().models.generate_content(
        model=config.model,
        contents=[
            types.Part.from_bytes(data=bytes(image_bytes), mime_type=mime_type),
            str(prompt),
        ],
        config=types.GenerateContentConfig(**parametros),
    )


def generate_embedding(contents):
    """Gera embedding com modelo e dimensão definidos em um único local."""
    config = get_embedding_config()
    if config.provider != PROVIDER_GOOGLE_GEMINI:
        raise RuntimeError(
            "A versão 2.2 mantém embeddings no Google Gemini. "
            "Selecione google_gemini e reindexe somente após uma futura migração vetorial."
        )
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
    clear_openai_client_cache()
    clear_ai_settings_cache()
