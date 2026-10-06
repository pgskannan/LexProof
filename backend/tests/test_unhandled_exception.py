"""Unhandled errors return JSON with CORS headers and a request id."""

from fastapi.testclient import TestClient

from app.lexproof.config import get_settings
from app.lexproof.main import create_app


def test_unhandled_error_is_json_with_cors_and_request_id():
    application = create_app()

    @application.get("/__paypal_test_boom")
    def boom():
        raise RuntimeError("secret internals")

    origin = get_settings().cors_origin_list()[0]
    client = TestClient(application, raise_server_exceptions=False)
    response = client.get("/__paypal_test_boom", headers={"Origin": origin, "X-Request-Id": "req-polish-1"})
    assert response.status_code == 500
    body = response.json()
    assert body["detail"] == "Internal server error"
    assert body["request_id"] == "req-polish-1"
    assert "secret" not in response.text
    assert response.headers["access-control-allow-origin"] == origin
    assert response.headers["x-request-id"] == "req-polish-1"


def test_http_errors_stay_http_errors():
    application = create_app()
    client = TestClient(application, raise_server_exceptions=False)
    response = client.get("/api/this-route-does-not-exist")
    assert response.status_code == 404
    assert response.json()["detail"] == "Not Found"
