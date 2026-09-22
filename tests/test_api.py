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
