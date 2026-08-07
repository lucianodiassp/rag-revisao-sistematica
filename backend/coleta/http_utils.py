import time

import requests


def safe_request_error(erro, segredo=None):
    mensagem = str(erro).strip() or erro.__class__.__name__
    if segredo:
        mensagem = mensagem.replace(str(segredo), "[REDACTED]")
    return mensagem[:500]


def get_with_retry(url, config, **kwargs):
    """Executa GET com timeout e repetição limitada para falhas transitórias."""
    ultimo_erro = None
    for tentativa in range(1, config.max_retries + 1):
        try:
            resposta = requests.get(
                url,
                timeout=config.timeout_seconds,
                **kwargs,
            )
            if resposta.status_code == 429 or resposta.status_code >= 500:
                resposta.raise_for_status()
            return resposta
        except requests.exceptions.RequestException as erro:
            ultimo_erro = erro
            if tentativa == config.max_retries:
                raise
            time.sleep(min(2 ** (tentativa - 1), 5))
    raise ultimo_erro
