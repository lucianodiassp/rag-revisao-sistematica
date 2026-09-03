from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_credential_pages_show_dynamic_deployment_scope():
    for relative_path in (
        "frontend/views/4_Configuracao_IA.py",
        "frontend/views/6_Fontes_Bibliograficas.py",
    ):
        source = (ROOT / relative_path).read_text(encoding="utf-8")

        assert "application_metadata" in source
        assert "metadata['deployment_label']" in source
        assert "metadata['user_mode_label']" in source
        assert "Escopo atual: instalação local" not in source


def test_visual_catalog_is_exposed_with_explicit_human_review_scope():
    navigation = (ROOT / "frontend/app.py").read_text(encoding="utf-8")
    page = (ROOT / "frontend/views/14_Catalogo_Visual.py").read_text(
        encoding="utf-8"
    )

    assert 'title="Catálogo Visual"' in navigation
    assert "Nenhuma imagem ou tabela é" in page
    assert "interpretada por IA" in page
    assert "Confirmo que conferi este candidato no PDF" in page
    assert "Autorizo o envio deste recorte aprovado" in page
    assert "Aprove ou corrija o candidato visual" in page
    assert "Confirmo que comparei a interpretação com o recorte" in page
    assert "ficará fora do RAG e do relatório" in page
