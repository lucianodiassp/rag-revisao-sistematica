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
