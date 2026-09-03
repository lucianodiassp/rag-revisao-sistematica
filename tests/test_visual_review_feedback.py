"""Verifica o feedback real do formulário, sem banco nem chamadas a provedores."""

from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from streamlit.testing.v1 import AppTest


PAGE = Path(__file__).resolve().parents[1] / "frontend/views/14_Catalogo_Visual.py"


def _label(elements, label):
    return next(item for item in elements if item.label == label)


@pytest.fixture
def review_page():
    artifact = {
        "id": "artifact-1",
        "paper_id": "paper-1",
        "paper_title": "Artigo de teste",
        "page_number": 2,
        "artifact_type": "figure",
        "review_status": "approved",
        "detection_method": "embedded_image",
        "human_description": "Duas etapas conectadas no diagrama.",
    }
    interpretation = {
        "id": "interpretation-1",
        "review_status": "pending",
        "interpretation_jsonb": {"summary": "Duas etapas conectadas no diagrama."},
    }

    def save(_project, _interpretation, action, reviewer, **_kwargs):
        interpretation.update(review_status=action, reviewer_name=reviewer)
        return dict(interpretation)

    with ExitStack() as stack:
        stack.enter_context(patch(
            "frontend.project_selector.selecionar_projeto_ativo",
            return_value={"id": "project-1", "title": "Projeto de teste"},
        ))
        stack.enter_context(patch(
            "backend.app.visual_catalog.list_visual_artifacts", return_value=[artifact]
        ))
        stack.enter_context(patch(
            "backend.app.visual_catalog.render_visual_artifact_preview",
            side_effect=FileNotFoundError("Prévia não usada neste teste"),
        ))
        stack.enter_context(patch(
            "backend.app.background_jobs.get_latest_job", return_value=None
        ))
        stack.enter_context(patch(
            "frontend.background_jobs_ui.render_job_status", return_value=None
        ))
        stack.enter_context(patch(
            "backend.app.ai_config.get_generation_config",
            return_value=SimpleNamespace(provider="google_gemini", model="modelo-teste"),
        ))
        stack.enter_context(patch(
            "backend.app.visual_interpretation.get_current_visual_interpretation",
            side_effect=lambda *_args: dict(interpretation),
        ))
        save_mock = stack.enter_context(patch(
            "backend.app.visual_interpretation.review_visual_interpretation",
            side_effect=save,
        ))
        app = AppTest.from_file(str(PAGE), default_timeout=10).run()
        assert not app.exception
        yield app, save_mock


def _submit(app, *, confirm=True):
    _label(app.text_input, "Responsável pela segunda revisão").set_value("Pessoa revisora")
    _label(
        app.checkbox,
        "Confirmo que comparei a interpretação com o recorte e o PDF original.",
    ).set_value(confirm)
    _label(app.button, "Registrar segunda revisão").click().run()


@pytest.mark.parametrize("decision, status", [
    ("Aprovar interpretação", "Aprovado"),
    ("Corrigir resumo", "Corrigido"),
    ("Rejeitar interpretação", "Rejeitado"),
])
def test_confirmation_survives_save_rerun_with_updated_status(review_page, decision, status):
    app, save = review_page
    _label(app.radio, "Segunda decisão humana").set_value(decision)
    _label(app.text_area, "Justificativa ou notas da segunda revisão").set_value(
        "Conferido com o PDF original."
    )
    _submit(app)

    assert not app.exception
    save.assert_called_once()
    assert any(
        "Segunda revisão salva com sucesso." in item.value and f"Estado: {status}" in item.value
        for item in app.success
    )
    assert any(f"**Estado da segunda revisão:** {status}" == item.value for item in app.markdown)
    app.run()
    assert not app.success  # Não repete uma confirmação antiga em outra interação.
    save.assert_called_once()


def test_missing_confirmation_does_not_show_save_success(review_page):
    app, save = review_page
    _submit(app, confirm=False)

    assert not app.exception
    save.assert_not_called()
    assert not app.success
    assert any("Confirme a conferência humana" in item.value for item in app.warning)


@pytest.mark.parametrize("error", [ValueError("Revisão inválida"), RuntimeError("Falha no banco")])
def test_save_failure_does_not_leave_false_success_after_rerun(review_page, error):
    app, save = review_page
    save.side_effect = error
    _submit(app)

    assert not app.exception
    assert not app.success
    assert any(str(error) in item.value for item in [*app.error, *app.warning])
    app.run()
    assert not app.success
