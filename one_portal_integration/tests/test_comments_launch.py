import jwt
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from one_portal_integration.app.routers.comments_launch import router

SECRET = "comments-test-shared-secret-0123456789-abcdef-0123456789"


def make_test_app(*, authenticated: bool = True) -> FastAPI:
    test_app = FastAPI()
    test_app.include_router(router)

    @test_app.middleware("http")
    async def fake_existing_portal_auth(request: Request, call_next):
        # Simulate the existing One Portal JWT middleware. The router itself
        # never reads EmployeeCode/email from the submitted body.
        if authenticated:
            request.state.user = {
                "employee_code": "0001",
                "session_id": "portal-session-test",
            }
        return await call_next(request)

    return test_app


def test_launch_route_uses_employee_code_from_verified_request_state(monkeypatch):
    monkeypatch.setenv("COMMENTS_LAUNCH_SECRET", SECRET)
    client = TestClient(make_test_app())
    response = client.post("/api/comments/launch-ticket", json={
        "tableName": "Z_SalesOrder",
        "fmsRefId": "8",
        "appId": "APP000001",
        "stageNo": "1",
        "EmployeeCode": "9999",
        "email": "attacker@example.test",
    })
    assert response.status_code == 200, response.text
    result = response.json()
    claims = jwt.decode(result["ticket"], SECRET, algorithms=["HS256"], audience="task-comments", issuer="one-portal")
    assert claims["employee_code"] == "0001"
    assert claims["task"] == {"tableName": "Z_SalesOrder", "fmsRefId": "8", "appId": "APP000001", "stageNo": "1"}
    assert "email" not in claims


def test_launch_route_requires_authenticated_portal_session(monkeypatch):
    monkeypatch.setenv("COMMENTS_LAUNCH_SECRET", SECRET)
    client = TestClient(make_test_app(authenticated=False))
    response = client.post("/api/comments/launch-ticket", json={
        "tableName": "Z_SalesOrder", "fmsRefId": "8", "appId": "APP000001", "stageNo": "1"
    })
    assert response.status_code == 401


def test_launch_route_requires_shared_secret(monkeypatch):
    monkeypatch.delenv("COMMENTS_LAUNCH_SECRET", raising=False)
    client = TestClient(make_test_app())
    response = client.post("/api/comments/launch-ticket", json={
        "tableName": "Z_SalesOrder", "fmsRefId": "8", "appId": "APP000001", "stageNo": "1"
    })
    assert response.status_code == 503
