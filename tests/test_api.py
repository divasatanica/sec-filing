from fastapi.testclient import TestClient

from sec_filing_agent.core.config import Settings
from sec_filing_agent.main import create_app


def build_client() -> TestClient:
    settings = Settings(environment="test", data_dir="/tmp/sec-filing-agent-test")
    return TestClient(create_app(settings))


def test_health_is_available_without_infrastructure() -> None:
    with build_client() as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "environment": "test"}


def test_unconfigured_rag_has_actionable_response() -> None:
    with build_client() as client:
        response = client.post("/v1/research/query", json={"query": "What changed?"})

    assert response.status_code == 501
    assert response.json()["code"] == "core_not_configured"


def test_openapi_exposes_the_bot_facing_endpoints() -> None:
    with build_client() as client:
        schema = client.get("/openapi.json").json()

    assert "/health" in schema["paths"]
    assert "/v1/filings/sync" in schema["paths"]
    assert "/v1/research/query" in schema["paths"]
