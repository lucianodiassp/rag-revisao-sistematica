import os
from unittest.mock import Mock, patch

import pytest

from backend.app.ai_admin_service import inspect_openai_key
from backend.app.ai_config import (
    PROVIDER_OPENAI,
    TASK_REPORT,
    clear_ai_settings_cache,
    get_generation_config,
)
from backend.app.ai_service import generate_content
from backend.app.openai_client import OpenAIResponsesClient


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def test_responses_api_preserva_json_privacidade_e_rastreabilidade():
    session = Mock()
    session.request.return_value = FakeResponse(
        200,
        {
            "id": "resp_123",
            "model": "modelo-openai-efetivo",
            "output": [
                {
                    "content": [
                        {"type": "output_text", "text": '{"resultado": "ok"}'}
                    ]
                }
            ],
            "usage": {"input_tokens": 12, "output_tokens": 5},
        },
    )
    client = OpenAIResponsesClient("segredo", session=session, timeout=30)

    response = client.generate_content(
        model="modelo-openai",
        contents="Responda em JSON",
        response_mime_type="application/json",
        system_instruction="Use apenas as evidências fornecidas.",
        temperature=0.2,
    )

    assert response.text == '{"resultado": "ok"}'
    assert response.model == "modelo-openai-efetivo"
    assert response.request_id == "resp_123"
    assert response.usage["input_tokens"] == 12
    call = session.request.call_args
    assert call.args == ("POST", "https://api.openai.com/v1/responses")
    assert call.kwargs["json"]["store"] is False
    assert call.kwargs["json"]["text"] == {"format": {"type": "json_object"}}
    assert call.kwargs["json"]["instructions"].startswith("Use apenas")
    assert call.kwargs["headers"]["Authorization"] == "Bearer segredo"


def test_erro_openai_remove_credencial_da_mensagem():
    segredo = "chave-que-nao-pode-vazar"
    session = Mock()
    session.request.return_value = FakeResponse(
        401,
        {"error": {"message": f"Credencial inválida: {segredo}"}},
    )
    client = OpenAIResponsesClient(segredo, session=session)

    with pytest.raises(RuntimeError) as context:
        client.list_models()

    assert segredo not in str(context.value)
    assert "[REDACTED]" in str(context.value)


@patch("backend.app.ai_admin_service.OpenAIResponsesClient")
def test_validacao_openai_lista_modelos_sem_gerar_conteudo(client_class):
    client = Mock()
    client.list_models.return_value = [
        "modelo-geracao",
        "text-embedding-modelo",
        "omni-moderation-modelo",
    ]
    client_class.return_value = client

    catalog = inspect_openai_key("chave-openai")

    assert catalog["generative"] == ["modelo-geracao"]
    assert catalog["embedding"] == []
    client.list_models.assert_called_once_with()
    assert not hasattr(client, "generate_content") or not client.generate_content.called


@patch("backend.app.ai_service.get_openai_client")
def test_servico_despacha_tarefa_para_openai(openai_client):
    client = Mock()
    client.generate_content.return_value = Mock(text="resposta OpenAI")
    openai_client.return_value = client
    environment = {
        "AI_CONFIG_DATABASE_ENABLED": "false",
        "AI_PROVIDER": "openai",
        "AI_DEFAULT_GENERATION_MODEL": "modelo-openai",
        "AI_REPORT_TEMPERATURE": "0.4",
        "GEMINI_API_KEY": "embedding-key",
        "OPENAI_API_KEY": "generation-key",
    }
    with patch.dict(os.environ, environment, clear=True):
        clear_ai_settings_cache()
        try:
            response = generate_content(
                TASK_REPORT,
                "conteúdo",
                system_instruction="instrução",
            )
            config = get_generation_config(TASK_REPORT)
        finally:
            clear_ai_settings_cache()

    assert response.text == "resposta OpenAI"
    assert config.provider == PROVIDER_OPENAI
    client.generate_content.assert_called_once_with(
        model="modelo-openai",
        contents="conteúdo",
        response_mime_type=None,
        system_instruction="instrução",
        temperature=0.4,
    )


def test_modelo_openai_de_raciocinio_omite_temperatura():
    environment = {
        "AI_CONFIG_DATABASE_ENABLED": "false",
        "AI_PROVIDER": "openai",
        "AI_DEFAULT_GENERATION_MODEL": "gpt-5-modelo",
        "AI_REPORT_TEMPERATURE": "0.7",
    }
    with patch.dict(os.environ, environment, clear=True):
        clear_ai_settings_cache()
        try:
            assert get_generation_config(TASK_REPORT).effective_temperature is None
        finally:
            clear_ai_settings_cache()
