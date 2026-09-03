from unittest.mock import MagicMock, Mock, patch

import pytest

from backend.app.visual_interpretation import (
    _normalize_interpretation,
    _parse_json_response,
    interpret_visual_artifact,
    review_visual_interpretation,
)


def test_normalizes_bounded_structured_visual_interpretation():
    result = _parse_json_response(
        """```json
        {
          "summary": "A figura mostra três etapas conectadas.",
          "observations": ["Há três caixas", "As setas seguem para a direita"],
          "structured_data": {"stages": ["A", "B", "C"]},
          "limitations": ["Rótulo inferior ilegível"],
          "confidence": "moderate",
          "supports_human_description": true
        }
        ```"""
    )

    assert result["confidence"] == "moderate"
    assert result["supports_human_description"] is True
    assert result["structured_data"]["stages"] == ["A", "B", "C"]


@pytest.mark.parametrize(
    "payload, message",
    [
        ({"summary": "curto", "confidence": "high"}, "resumo"),
        ({"summary": "Resumo suficientemente longo", "confidence": "absoluta"}, "confiança"),
        (
            {
                "summary": "Resumo suficientemente longo",
                "confidence": "high",
                "observations": "não é lista",
            },
            "observations",
        ),
    ],
)
def test_rejects_invalid_provider_contract(payload, message):
    with pytest.raises(RuntimeError, match=message):
        _normalize_interpretation(payload)


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"action": "invalid", "reviewer_name": "Pessoa"}, "Decisão"),
        ({"action": "approved", "reviewer_name": ""}, "responsável"),
        (
            {
                "action": "corrected",
                "reviewer_name": "Pessoa",
                "corrected_summary": "curto",
                "human_notes": "ajuste",
            },
            "10 caracteres",
        ),
        (
            {"action": "rejected", "reviewer_name": "Pessoa", "human_notes": "não"},
            "justificativa",
        ),
    ],
)
def test_rejects_invalid_second_review_before_database_access(kwargs, message):
    with pytest.raises(ValueError, match=message):
        review_visual_interpretation("project", "interpretation", **kwargs)


def test_migration_keeps_visual_interpretation_out_of_rag_schema():
    migration = open(
        "database/scripts/017_visual_interpretations.sql", encoding="utf-8"
    ).read()

    assert "CREATE TABLE IF NOT EXISTS visual_interpretations" in migration
    assert "visual_interpretation_review_events" in migration
    assert "paper_chunks" not in migration
    assert "embeddings_metadata" not in migration


@patch("backend.app.visual_interpretation.get_connection")
@patch("backend.app.visual_interpretation.generate_multimodal_content")
@patch("backend.app.visual_interpretation.get_generation_config")
@patch("backend.app.visual_interpretation.render_visual_artifact_preview")
@patch("backend.app.visual_interpretation._get_eligible_artifact")
def test_interprets_only_one_approved_crop_without_persisting_image(
    eligible, render, get_config, generate, get_connection
):
    eligible.return_value = {
        "id": "artifact",
        "paper_id": "paper",
        "file_sha256": "a" * 64,
        "artifact_type": "figure",
        "page_number": 2,
        "caption": "Figura 1",
        "context_text": "Contexto do artigo",
        "human_description": "Descrição humana previamente aprovada.",
    }
    render.return_value = b"imagem-png-nao-persistida"
    config = Mock(provider="openai", model="gpt-visual")
    config.metadata.return_value = {"provider": "openai", "model_name": "gpt-visual"}
    get_config.return_value = config
    generate.return_value = Mock(
        text=(
            '{"summary":"Diagrama com duas etapas conectadas.",'
            '"observations":["Duas caixas"],"structured_data":null,'
            '"limitations":[],"confidence":"high",'
            '"supports_human_description":true}'
        ),
        model="gpt-visual",
        request_id="resp-safe",
        usage={"input_tokens": 10},
    )
    connection = MagicMock()
    cursor = MagicMock()
    connection.__enter__.return_value = connection
    connection.cursor.return_value.__enter__.return_value = cursor
    cursor.fetchone.return_value = ["interpretation-id"]
    get_connection.return_value = connection

    result = interpret_visual_artifact("project", "artifact")

    assert result == {
        "artifact_id": "artifact",
        "interpretation_id": "interpretation-id",
        "review_status": "pending",
    }
    generate.assert_called_once()
    assert generate.call_args.args[2] == b"imagem-png-nao-persistida"
    persisted_arguments = repr(cursor.execute.call_args_list)
    assert "imagem-png-nao-persistida" not in persisted_arguments
    assert "data:image/png;base64" not in persisted_arguments
