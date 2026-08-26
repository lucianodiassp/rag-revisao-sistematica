import json

from backend.app.observability import (
    classify_error,
    log_event,
    sanitize_fields,
)


def test_structured_event_contains_identity_without_secrets(capsys, monkeypatch):
    monkeypatch.setenv("RAG_DEPLOYMENT_PROFILE", "web_private")
    monkeypatch.setenv("RAG_USER_MODE", "single_user")

    log_event(
        "provider_failed",
        component="worker",
        level="error",
        category="ai_provider",
        api_key="valor-secreto",
        nested={"password": "outra-senha", "attempt": 2},
        message="API_KEY=nao-pode-aparecer indisponível",
    )
    payload = json.loads(capsys.readouterr().out)

    assert payload["event"] == "provider_failed"
    assert payload["component"] == "worker"
    assert payload["deployment_profile"] == "web_private"
    assert payload["api_key"] == "[oculto]"
    assert payload["nested"]["password"] == "[oculto]"
    serialized = json.dumps(payload)
    assert "valor-secreto" not in serialized
    assert "outra-senha" not in serialized
    assert "nao-pode-aparecer" not in serialized


def test_sanitizer_hides_scientific_content_fields():
    sanitized = sanitize_fields(
        {
            "project_id": "project-1",
            "query_text": "string de busca sensível",
            "answer": "síntese científica",
            "result_count": 4,
        }
    )

    assert sanitized == {
        "project_id": "project-1",
        "query_text": "[oculto]",
        "answer": "[oculto]",
        "result_count": 4,
    }


def test_error_classifier_distinguishes_operational_categories():
    database = classify_error(RuntimeError("could not connect to server"))
    storage = classify_error(RuntimeError("No space left on device"))
    provider = classify_error(RuntimeError("503 UNAVAILABLE"), component_hint="ai_provider")
    source = classify_error(RuntimeError("timeout"), component_hint="bibliographic_source")
    configuration = classify_error(RuntimeError("chave-mestra não foi configurada"))

    assert database.category == "database"
    assert storage.category == "storage"
    assert provider.category == "ai_provider" and provider.retryable is True
    assert source.category == "bibliographic_source" and source.retryable is True
    assert configuration.category == "configuration"
