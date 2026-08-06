import os
from functools import lru_cache

from dotenv import find_dotenv, load_dotenv
from google import genai


@lru_cache(maxsize=1)
def get_gemini_client():
    """Cria o cliente somente quando uma operação de IA for executada."""
    load_dotenv(find_dotenv())
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY não configurada. Defina a chave no arquivo .env da raiz do projeto."
        )
    return genai.Client(api_key=api_key)
