from functools import lru_cache

from google import genai

from backend.app.ai_config import PROVIDER_GOOGLE_GEMINI, get_ai_settings


@lru_cache(maxsize=1)
def get_gemini_client():
    """Cria o cliente somente quando uma operação de IA for executada."""
    settings = get_ai_settings()
    if settings.provider != PROVIDER_GOOGLE_GEMINI:
        raise RuntimeError(
            f"O provedor '{settings.provider}' ainda não possui adaptador ativo. "
            "Use AI_PROVIDER=google_gemini nesta fase."
        )
    if not settings.api_key:
        raise RuntimeError(
            "GEMINI_API_KEY não configurada. Defina a chave em backend/.env "
            "ou no ambiente do sistema."
        )
    return genai.Client(api_key=settings.api_key)


def clear_ai_client_cache():
    """Será usado quando credenciais forem alteradas pela futura tela de configuração."""
    get_gemini_client.cache_clear()
