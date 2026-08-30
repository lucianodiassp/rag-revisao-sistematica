import os
from dataclasses import dataclass, field
from functools import lru_cache

import requests

from backend.app.ai_config import PROVIDER_OPENAI, get_provider_api_key


OPENAI_API_BASE = "https://api.openai.com/v1"


@dataclass(frozen=True)
class OpenAITextResponse:
    """Contrato mínimo compatível com as respostas usadas pelos agentes atuais."""

    text: str
    model: str
    request_id: str | None = None
    usage: dict = field(default_factory=dict)


class OpenAIResponsesClient:
    def __init__(self, api_key, *, session=None, timeout=None):
        self._api_key = str(api_key or "").strip()
        self._session = session or requests.Session()
        self._timeout = timeout or int(os.getenv("OPENAI_TIMEOUT_SECONDS", "120"))

    @property
    def _headers(self):
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def _safe_provider_error(self, response):
        try:
            payload = response.json()
            message = str((payload.get("error") or {}).get("message") or "").strip()
        except Exception:
            message = ""
        if not message:
            message = "O provedor recusou a solicitação sem fornecer detalhes."
        if self._api_key:
            message = message.replace(self._api_key, "[REDACTED]")
        return f"OpenAI API {response.status_code}: {message[:500]}"

    def _request(self, method, path, *, json_body=None):
        response = self._session.request(
            method,
            f"{OPENAI_API_BASE}{path}",
            headers=self._headers,
            json=json_body,
            timeout=self._timeout,
        )
        if not 200 <= response.status_code < 300:
            raise RuntimeError(self._safe_provider_error(response))
        try:
            return response.json()
        except ValueError as error:
            raise RuntimeError("A OpenAI retornou uma resposta inválida.") from error

    def list_models(self):
        payload = self._request("GET", "/models")
        return sorted(
            {
                str(item.get("id") or "").strip()
                for item in payload.get("data") or []
                if str(item.get("id") or "").strip()
            }
        )

    def generate_content(
        self,
        *,
        model,
        contents,
        response_mime_type=None,
        system_instruction=None,
        temperature=None,
    ):
        payload = {
            "model": str(model).strip(),
            "input": str(contents),
            # O conteúdo científico não deve ser mantido pelo provedor para
            # recuperação posterior da resposta.
            "store": False,
        }
        if system_instruction:
            payload["instructions"] = str(system_instruction)
        if temperature is not None:
            payload["temperature"] = float(temperature)
        if response_mime_type == "application/json":
            payload["text"] = {"format": {"type": "json_object"}}

        data = self._request("POST", "/responses", json_body=payload)
        textos = []
        recusas = []
        for output in data.get("output") or []:
            for content in output.get("content") or []:
                tipo = content.get("type")
                if tipo == "output_text" and content.get("text"):
                    textos.append(str(content["text"]))
                elif tipo == "refusal" and content.get("refusal"):
                    recusas.append(str(content["refusal"]))
        texto = "\n".join(textos).strip()
        if not texto:
            detalhe = recusas[0][:300] if recusas else "nenhum texto foi retornado"
            raise RuntimeError(f"A OpenAI não produziu conteúdo utilizável: {detalhe}.")
        return OpenAITextResponse(
            text=texto,
            model=str(data.get("model") or model),
            request_id=str(data.get("id")) if data.get("id") else None,
            usage=dict(data.get("usage") or {}),
        )


@lru_cache(maxsize=1)
def get_openai_client():
    api_key = get_provider_api_key(PROVIDER_OPENAI)
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY não configurada. Cadastre a chave na Configuração de IA "
            "ou defina-a no ambiente do sistema."
        )
    return OpenAIResponsesClient(api_key)


def clear_openai_client_cache():
    get_openai_client.cache_clear()
