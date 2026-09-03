import base64

import fitz
import pytest

from backend.app.visual_catalog import (
    detect_visual_artifacts,
    review_visual_artifact,
    summarize_visual_artifacts,
)


PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUB"
    "AScY42YAAAAASUVORK5CYII="
)


def test_detects_embedded_figure_with_page_traceability(tmp_path):
    path = tmp_path / "paper.pdf"
    document = fitz.open()
    page = document.new_page(width=595, height=842)
    page.insert_image(fitz.Rect(100, 120, 480, 360), stream=PNG_1X1)
    page.insert_text(
        (100, 385),
        "Figura 1 - Fluxo experimental do estudo",
        fontsize=11,
    )
    page.insert_text(
        (72, 430),
        "O texto da pagina apresenta o contexto verificavel da figura.",
        fontsize=10,
    )
    document.save(path)
    document.close()

    result = detect_visual_artifacts(path)

    figures = [item for item in result["artifacts"] if item["artifact_type"] == "figure"]
    assert len(result["file_sha256"]) == 64
    assert result["total_pages"] == 1
    assert figures
    assert figures[0]["page_number"] == 1
    assert figures[0]["detection_method"] == "embedded_image"
    assert figures[0]["bbox"] == [100.0, 120.0, 480.0, 360.0]
    assert figures[0]["caption"].startswith("Figura 1")
    assert figures[0]["detection_metadata"]["semantic_interpretation"] is False


def test_catalogs_caption_without_inventing_visual_interpretation(tmp_path):
    path = tmp_path / "caption.pdf"
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 100), "Tabela 2: Resultados consolidados", fontsize=11)
    document.save(path)
    document.close()

    result = detect_visual_artifacts(path)

    tables = [item for item in result["artifacts"] if item["artifact_type"] == "table"]
    assert len(tables) == 1
    assert tables[0]["detection_method"] == "caption_only"
    assert tables[0]["bbox"] is None
    assert tables[0]["extracted_content"] is None
    assert tables[0]["detection_metadata"]["semantic_interpretation"] is False


def test_summarizes_review_states():
    summary = summarize_visual_artifacts(
        [
            {"artifact_type": "figure", "review_status": "pending"},
            {"artifact_type": "table", "review_status": "approved"},
            {"artifact_type": "table", "review_status": "rejected"},
        ]
    )

    assert summary == {
        "total": 3,
        "figures": 1,
        "tables": 2,
        "pending": 1,
        "reviewed": 2,
    }


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"action": "unknown", "reviewer_name": "Pessoa"}, "Decisão"),
        ({"action": "approved", "reviewer_name": ""}, "responsável"),
        (
            {
                "action": "approved",
                "reviewer_name": "Pessoa",
                "human_description": "curta",
            },
            "10 caracteres",
        ),
        (
            {
                "action": "rejected",
                "reviewer_name": "Pessoa",
                "human_notes": "não",
            },
            "rejeição",
        ),
    ],
)
def test_rejects_invalid_human_review_before_database_access(kwargs, message):
    with pytest.raises(ValueError, match=message):
        review_visual_artifact("project", "artifact", **kwargs)
