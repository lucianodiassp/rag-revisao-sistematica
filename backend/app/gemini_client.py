from functools import lru_cache

from google import genai

from backend.app.ai_config import PROVIDER_GOOGLE_GEMINI, get_provider_api_key
from backend.app.user_identity import current_configuration_cache_key


@lru_cache(maxsize=32)
def _get_gemini_client_for_scope(_scope_key):
    """Cria o cliente somente quando uma operação de IA for executada."""
    api_key = get_provider_api_key(PROVIDER_GOOGLE_GEMINI)
    if not api_key:
        raise RuntimeError(
            "Credencial Gemini não configurada para o usuário atual. "
            "Cadastre a chave na Configuração de IA."
        )
    return genai.Client(api_key=api_key)


def get_gemini_client():
    return _get_gemini_client_for_scope(current_configuration_cache_key())


def clear_ai_client_cache():
    """Será usado quando credenciais forem alteradas pela futura tela de configuração."""
    _get_gemini_client_for_scope.cache_clear()
