from fastapi.testclient import TestClient

from sec_filing_agent.core.config import Settings
from sec_filing_agent.main import create_app

TEST_DATABASE_URL = "postgresql+asyncpg://test:test@127.0.0.1:5432/sec_filing_test"


def build_client() -> TestClient:
    settings = Settings(
        environment="test",
        sec_user_agent="test-agent",
        database_url=TEST_DATABASE_URL,
    )
    return TestClient(create_app(settings))


def test_embedding_routes_are_exposed_as_not_implemented_placeholders() -> None:
    with build_client() as client:
        build_response = client.post("/embeddings/tickers/RKLB/index", json={})
        search_response = client.post("/embeddings/search", json={"query": "revenue"})

    assert build_response.status_code == 501
    assert search_response.status_code == 501


def test_embedding_search_request_is_validated_before_the_placeholder_handler() -> None:
    with build_client() as client:
        response = client.post("/embeddings/search", json={"query": "", "top_k": 0})

    assert response.status_code == 422
