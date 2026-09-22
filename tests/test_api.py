from fastapi.testclient import TestClient

from sec_filing_agent.core.config import Settings
from sec_filing_agent.main import create_app


def build_client() -> TestClient:
    settings = Settings(environment="test")
    return TestClient(create_app(settings))


def test_health_is_available() -> None:
    with build_client() as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_openapi_exposes_the_bot_facing_endpoints() -> None:
    with build_client() as client:
        schema = client.get("/openapi.json").json()

    assert "/health" in schema["paths"]


def test_settings_loads_the_file_for_the_requested_environment(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SEC_FILING_AGENT_HOST", raising=False)
    monkeypatch.delenv("SEC_FILING_AGENT_PORT", raising=False)
    (tmp_path / ".env.development").write_text(
        "SEC_FILING_AGENT_HOST=0.0.0.0\nSEC_FILING_AGENT_PORT=8001\n"
    )
    (tmp_path / ".env.production").write_text(
        "SEC_FILING_AGENT_HOST=10.0.0.1\nSEC_FILING_AGENT_PORT=9000\n"
    )

    development_settings = Settings(environment="development")
    production_settings = Settings(environment="production")

    assert (development_settings.host, development_settings.port) == ("0.0.0.0", 8001)
    assert (production_settings.host, production_settings.port) == ("10.0.0.1", 9000)
