from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CADDYFILE = ROOT / "deploy" / "Caddyfile"


def test_access_logs_remove_headers_and_oauth_query_values():
    config = CADDYFILE.read_text(encoding="utf-8")

    assert "format filter {" in config
    assert "wrap json" in config
    assert "request>headers delete" in config
    assert "request>remote_ip ip_mask 16 32" in config
    assert "request>client_ip ip_mask 16 32" in config
    assert "request>uri query {" in config

    for parameter in (
        "code",
        "state",
        "scope",
        "authuser",
        "prompt",
        "iss",
        "error",
        "error_description",
        "login_hint",
        "email",
    ):
        assert f"delete {parameter}" in config
