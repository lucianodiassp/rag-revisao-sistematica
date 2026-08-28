from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOCAL_COMPOSE = ROOT / "docker-compose.yml"


def _service_block(service_name: str) -> str:
    lines = LOCAL_COMPOSE.read_text(encoding="utf-8").splitlines()
    marker = f"  {service_name}:"
    start = lines.index(marker)
    end = len(lines)
    for index in range(start + 1, len(lines)):
        line = lines[index]
        if line.startswith("  ") and not line.startswith("    ") and line.endswith(":"):
            end = index
            break
    return "\n".join(lines[start:end])


def test_local_backup_scheduler_is_private_and_shares_protected_storage():
    scheduler = _service_block("backup-scheduler")

    assert "    ports:" not in scheduler
    assert "RAG_DEPLOYMENT_PROFILE: local" in scheduler
    assert "RAG_USER_MODE: single_user" in scheduler
    assert "backend.app.external_backup" in scheduler
    assert "        - --healthcheck" in scheduler
    assert "./data/pdfs:/app/data/pdfs" in scheduler
    assert "./data/backups:/app/data/backups" in scheduler
    assert "app_private_data:/app/data/private" in scheduler
    assert "      - rag_network" in scheduler


def test_local_application_services_force_the_local_single_user_profile():
    for service_name in ("app", "worker", "backup-scheduler"):
        service = _service_block(service_name)
        assert "RAG_DEPLOYMENT_PROFILE: local" in service
        assert "RAG_USER_MODE: single_user" in service
