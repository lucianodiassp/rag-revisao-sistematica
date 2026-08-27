from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_FILES = (
    ROOT / "backend" / ".env.example",
    ROOT / "deploy" / "web.env.example",
    ROOT / ".streamlit" / "secrets.toml.example",
)


def test_safe_configuration_examples_are_available_without_real_keys():
    for path in EXAMPLE_FILES:
        assert path.is_file()
        content = path.read_text(encoding="utf-8")
        assert "AIza" not in content
        assert "-----BEGIN PRIVATE KEY-----" not in content


def test_gitignore_and_dockerignore_exclude_runtime_secrets():
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()

    assert ".streamlit/secrets.toml" in gitignore
    assert "deploy/web.env" in gitignore
    assert ".streamlit/secrets.toml" in dockerignore
    assert "deploy/web.env" in dockerignore
    assert "**/.env" in dockerignore
