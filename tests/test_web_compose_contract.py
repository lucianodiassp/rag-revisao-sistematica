from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEB_COMPOSE = ROOT / "docker-compose.web.yml"


def _service_block(service_name: str) -> str:
    lines = WEB_COMPOSE.read_text(encoding="utf-8").splitlines()
    marker = f"  {service_name}:"
    start = lines.index(marker)
    end = len(lines)

    for index in range(start + 1, len(lines)):
        line = lines[index]
        if line.startswith("  ") and not line.startswith("    ") and line.endswith(":"):
            end = index
            break

    return "\n".join(lines[start:end])


def test_web_app_and_worker_have_independent_healthchecks():
    app = _service_block("app")
    worker = _service_block("worker")

    assert app.count("    healthcheck:") == 1
    assert "        - app" in app
    assert "        - worker" not in app

    assert worker.count("    healthcheck:") == 1
    assert "        - worker" in worker
    assert "        - app" not in worker


def test_only_proxy_publishes_public_ports_in_web_profile():
    compose = WEB_COMPOSE.read_text(encoding="utf-8")
    proxy = _service_block("proxy")

    assert compose.count("    ports:") == 1
    assert "    ports:" in proxy
    assert '      - "80:80"' in proxy
    assert '      - "443:443"' in proxy

