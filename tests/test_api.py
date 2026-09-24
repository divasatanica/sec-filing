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


def test_health_is_available() -> None:
    with build_client() as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_request_id_is_returned_and_can_be_supplied_by_the_caller() -> None:
    request_id = "test-request-123"

    with build_client() as client:
        response = client.get("/health", headers={"X-Request-ID": request_id})

    assert response.headers["X-Request-ID"] == request_id


def test_unhandled_handler_exception_returns_safe_500_with_request_id() -> None:
    app = create_app(
        Settings(
            environment="test",
            sec_user_agent="test-agent",
            database_url=TEST_DATABASE_URL,
        )
    )

    @app.get("/test/raises")
    async def raises_unexpected_error() -> None:
        raise RuntimeError("database password must not appear in the response")

    request_id = "request-that-fails"
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/test/raises", headers={"X-Request-ID": request_id})

    assert response.status_code == 500
    assert response.headers["X-Request-ID"] == request_id
    assert response.json() == {
        "detail": "Internal server error",
        "request_id": request_id,
    }


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

    development_settings = Settings(
        environment="development",
        sec_user_agent="test-agent",
        database_url=TEST_DATABASE_URL,
    )
    production_settings = Settings(
        environment="production",
        sec_user_agent="test-agent",
        database_url=TEST_DATABASE_URL,
    )

    assert (development_settings.host, development_settings.port) == ("0.0.0.0", 8001)
    assert (production_settings.host, production_settings.port) == ("10.0.0.1", 9000)


def test_log_format_defaults_by_environment() -> None:
    development_settings = Settings(
        environment="development",
        sec_user_agent="test-agent",
        database_url=TEST_DATABASE_URL,
    )
    production_settings = Settings(
        environment="production",
        sec_user_agent="test-agent",
        database_url=TEST_DATABASE_URL,
    )

    assert development_settings.use_json_logs is False
    assert production_settings.use_json_logs is True
