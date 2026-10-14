from dataclasses import replace

import jwt
import pytest
from fastapi.testclient import TestClient

from app import main
from app.identity import encode_portal_launch_ticket, decode_portal_launch_ticket
from app.services import ActivityService
from app.sql_api import MemorySqlGateway

SECRET = "test-shared-comments-launch-secret-0123456789-abcdef"
TASK = {"tableName": "Z_SalesOrder", "fmsRefId": "8", "appId": "APP000001", "stageNo": "1"}
ACTIVE_EMPLOYEE = {
    "EmployeeCode": "0001",
    "EmployeeName": "Himanshu Sehgal",
    "OffEmail": "Systems2@hosexperts.com",
    "Active": "Y",
    "RoleID": 1,
    "RoleName": "Super Admin",
    "Department": "Management",
}


def setup_test_app(monkeypatch, *, employee_rows=None):
    cfg = replace(
        main.settings,
        app_env="test",
        sql_api_mode="mock",
        comments_launch_secret=SECRET,
        local_dev_identity_enabled=False,
        comments_session_minutes=60,
        comments_session_cookie="task_comments_test_session",
    )
    monkeypatch.setattr(main, "settings", cfg)
    main.app.state.gateway = MemorySqlGateway({
        "VM_EmployeeMaster": list(employee_rows if employee_rows is not None else [ACTIVE_EMPLOYEE]),
        "FMS_Comment_FMS_Stage_Map": [],
        "FMS_Comment_Log": [],
        "Pending_Tasks": [],
        "FMS_Comment_Case_Map": [],
        "FMS_Case_Labels": [],
    })
    main.app.state.used_launch_ticket_ids = {}
    return TestClient(main.app)


def make_ticket(*, task=None, employee_code="0001", jti="unique-ticket-1"):
    return encode_portal_launch_ticket(
        employee_code=employee_code,
        task=task or TASK,
        secret=SECRET,
        portal_session_id="portal-session-abc",
        jti=jti,
    )


def test_launch_ticket_contains_employee_code_not_email():
    ticket = make_ticket()
    decoded = decode_portal_launch_ticket(ticket, SECRET)
    assert decoded["employee_code"] == "0001"
    assert decoded["task"] == TASK
    assert "email" not in decoded
    assert "password" not in str(decoded).lower()


def test_launch_ticket_requires_complete_task_context():
    try:
        make_ticket(task={"tableName": "Z_SalesOrder", "fmsRefId": "8", "appId": "APP000001", "stageNo": ""})
    except ValueError as exc:
        assert "Stage No" in str(exc)
    else:
        raise AssertionError("Ticket minting should reject incomplete task context")


def test_comments_app_resolves_logged_in_employee_and_sets_httponly_cookie(monkeypatch):
    client = setup_test_app(monkeypatch)
    response = client.post("/auth/launch", data={"ticket": make_ticket()}, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/?tableName=Z_SalesOrder")
    cookie = response.headers.get("set-cookie", "")
    assert "task_comments_test_session=" in cookie
    assert "httponly" in cookie.lower()

    # The returned cookie is the authenticated identity source for subsequent requests.
    client.cookies.set("task_comments_test_session", response.cookies.get("task_comments_test_session"))
    who = client.get("/api/whoami").json()
    assert who["employeeCode"] == "0001"
    assert who["employeeName"] == "Himanshu Sehgal"
    assert who["email"] == "systems2@hosexperts.com"
    assert who["identitySource"] == "one-portal-session"


def test_inactive_employee_cannot_exchange_ticket(monkeypatch):
    inactive = {**ACTIVE_EMPLOYEE, "Active": "N"}
    client = setup_test_app(monkeypatch, employee_rows=[inactive])
    response = client.post("/auth/launch", data={"ticket": make_ticket(jti="inactive-ticket")}, follow_redirects=False)
    assert response.status_code == 403


def test_launch_ticket_can_only_be_used_once(monkeypatch):
    client = setup_test_app(monkeypatch)
    ticket = make_ticket(jti="one-time-ticket")
    first = client.post("/auth/launch", data={"ticket": ticket}, follow_redirects=False)
    second = client.post("/auth/launch", data={"ticket": ticket}, follow_redirects=False)
    assert first.status_code == 303
    assert second.status_code == 401


def test_browser_cannot_override_sender_email():
    cfg = replace(main.settings, comments_table="FMS_Comment_Log", users_table="VM_EmployeeMaster")
    gateway = MemorySqlGateway({"FMS_Comment_Log": []})
    service = ActivityService(gateway, cfg)
    service.add_new_comment({
        "commentId": "CTX-1", "tableName": "Z_SalesOrder", "fmsRefId": "8",
        "appId": "APP000001", "stageNo": "1", "text": "hello",
        "sender": "attacker@invalid.test", "mentionType": "Message",
    }, "systems2@hosexperts.com")
    row = gateway.select("FMS_Comment_Log")[0]
    assert row["Sender"] == "systems2@hosexperts.com"


def test_expired_launch_ticket_is_rejected(monkeypatch):
    client = setup_test_app(monkeypatch)
    ticket = encode_portal_launch_ticket(
        employee_code="0001", task=TASK, secret=SECRET,
        portal_session_id="portal-session-abc", ttl_seconds=1,
        jti="expired-ticket", now=1,
    )
    response = client.post("/auth/launch", data={"ticket": ticket}, follow_redirects=False)
    assert response.status_code == 401


def test_whoami_does_not_trust_query_email(monkeypatch):
    client = setup_test_app(monkeypatch)
    response = client.get("/api/whoami?user=somebody-else@example.com")
    assert response.status_code == 401
    assert "One Portal session" in response.json()["detail"]


def test_embed_widget_requests_ticket_from_portal_not_sender_email(monkeypatch):
    client = setup_test_app(monkeypatch)
    response = client.get("/embed.js")
    assert response.status_code == 200
    assert "/api/comments/launch-ticket" in response.text
    assert "/auth/launch" in response.text
    assert "localStorage.getItem(\"access_token\")" in response.text
    # FMS stage forms are nested inside the FMS dashboard iframe; the bridge is
    # on top-level One Portal, so the launcher must message window.top, not parent.
    assert "const portalWindow=window.top" in response.text
    assert "portalWindow.postMessage" in response.text
    assert "event.source!==portalWindow" in response.text
    assert "window.parent.postMessage" not in response.text
    assert "no-store, no-cache, must-revalidate" in response.headers["cache-control"]
