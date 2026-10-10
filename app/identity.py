"""Trusted identity-token helpers for the One Portal -> Comments App handoff.

The browser is never allowed to declare the current sender email. The source
One Portal backend signs an expiring launch ticket from its validated JWT
middleware state; this app validates the ticket and resolves EmployeeCode to an
Active='Y' row in VM_EmployeeMaster before setting an HttpOnly session cookie.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any
import jwt

PORTAL_ISSUER = "one-portal"
PORTAL_AUDIENCE = "task-comments"
COMMENTS_ISSUER = "task-activity-feed"
COMMENTS_AUDIENCE = "task-activity-session"
ALGORITHM = "HS256"


def utc_timestamp() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def encode_portal_launch_ticket(*, employee_code: str, task: dict[str, str], secret: str,
                                portal_session_id: str = "", ttl_seconds: int = 45,
                                jti: str = "test-ticket-id", now: int | None = None) -> str:
    """Mint a ticket for tests/tools. Production tickets are minted by One Portal."""
    if not secret or len(secret) < 32:
        raise ValueError("COMMENTS_LAUNCH_SECRET must be at least 32 characters")
    stamp = utc_timestamp() if now is None else now
    code = str(employee_code or "").strip()
    if not code:
        raise ValueError("EmployeeCode is required")
    context_keys = ("tableName", "fmsRefId", "appId", "stageNo")
    clean_task = {key: str(task.get(key, "") or "").strip() for key in context_keys}
    if not all(clean_task.values()):
        raise ValueError("Table Name, FMS Ref Id, App ID and Stage No are required")
    claims = {
        "iss": PORTAL_ISSUER,
        "aud": PORTAL_AUDIENCE,
        "sub": code,
        "employee_code": code,
        "portal_session_id": str(portal_session_id or ""),
        "task": clean_task,
        "iat": stamp,
        "nbf": stamp - 1,
        "exp": stamp + max(1, min(int(ttl_seconds), 60)),
        "jti": str(jti),
    }
    return jwt.encode(claims, secret, algorithm=ALGORITHM)


def decode_portal_launch_ticket(ticket: str, secret: str) -> dict[str, Any]:
    if not secret or len(secret) < 32:
        raise ValueError("COMMENTS_LAUNCH_SECRET is not configured or is too short")
    return jwt.decode(
        ticket,
        secret,
        algorithms=[ALGORITHM],
        issuer=PORTAL_ISSUER,
        audience=PORTAL_AUDIENCE,
        options={"require": ["exp", "iat", "jti", "sub", "employee_code", "task"]},
        leeway=3,
    )


def encode_comment_session(*, employee: dict[str, Any], secret: str,
                           portal_session_id: str = "", ttl_seconds: int = 28800,
                           now: int | None = None) -> str:
    if not secret or len(secret) < 32:
        raise ValueError("COMMENTS_LAUNCH_SECRET must be at least 32 characters")
    stamp = utc_timestamp() if now is None else now
    code = str(employee.get("employee_code", "") or "").strip()
    email = str(employee.get("email", "") or "").strip().casefold()
    name = str(employee.get("full_name", "") or "").strip()
    if not code or not email or not name:
        raise ValueError("A verified EmployeeCode, EmployeeName and OffEmail are required")
    claims = {
        "iss": COMMENTS_ISSUER,
        "aud": COMMENTS_AUDIENCE,
        "sub": code,
        "employee_code": code,
        "email": email,
        "full_name": name,
        "role_id": str(employee.get("role_id", "") or ""),
        "role_name": str(employee.get("role_name", "") or ""),
        "department": str(employee.get("department", "") or ""),
        "active": "Y",
        "portal_session_id": str(portal_session_id or ""),
        "iat": stamp,
        "nbf": stamp - 1,
        "exp": stamp + max(60, int(ttl_seconds)),
    }
    return jwt.encode(claims, secret, algorithm=ALGORITHM)


def decode_comment_session(token: str, secret: str) -> dict[str, Any]:
    if not secret or len(secret) < 32:
        raise ValueError("COMMENTS_LAUNCH_SECRET is not configured or is too short")
    return jwt.decode(
        token,
        secret,
        algorithms=[ALGORITHM],
        issuer=COMMENTS_ISSUER,
        audience=COMMENTS_AUDIENCE,
        options={"require": ["exp", "iat", "sub", "employee_code", "email", "full_name"]},
        leeway=3,
    )
