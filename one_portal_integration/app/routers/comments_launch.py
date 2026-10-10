"""One Portal -> Task Activity Feed identity handoff.

Install into the existing One Portal backend and include this router in app/main.py.
The existing JWTValidationMiddleware must remain enabled for /api/comments/launch-ticket.
"""
from __future__ import annotations
from datetime import datetime, timezone
import os
import secrets
from typing import Any

import jwt
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/comments", tags=["Comments Identity Handoff"])


class LaunchContext(BaseModel):
    tableName: str = Field(min_length=1, max_length=256)
    fmsRefId: str = Field(min_length=1, max_length=256)
    appId: str = Field(min_length=1, max_length=128)
    stageNo: str = Field(min_length=1, max_length=64)


@router.post("/launch-ticket")
async def create_comments_launch_ticket(body: LaunchContext, request: Request) -> dict[str, Any]:
    """Issue a <=45-second signed ticket from the current, middleware-verified session.

    Deliberately ignores email/name/EmployeeCode fields sent in the JSON body.
    The authoritative employee code comes from request.state.user populated by
    One Portal's JWTValidationMiddleware after its session + Active checks.
    """
    user = getattr(request.state, "user", None)
    if not isinstance(user, dict):
        raise HTTPException(status_code=401, detail="Sign in to One Portal before opening Comments.")

    employee_code = str(user.get("employee_code") or user.get("EmployeeCode") or user.get("sub") or "").strip()
    if not employee_code:
        raise HTTPException(status_code=401, detail="Authenticated One Portal session has no EmployeeCode.")

    secret = os.getenv("COMMENTS_LAUNCH_SECRET", "").strip()
    if len(secret) < 32:
        raise HTTPException(status_code=503, detail="Configure a shared COMMENTS_LAUNCH_SECRET in both backend environments.")

    now = int(datetime.now(timezone.utc).timestamp())
    session_id = str(user.get("session_id") or user.get("sessionId") or "").strip()
    task = {
        "tableName": body.tableName.strip(),
        "fmsRefId": body.fmsRefId.strip(),
        "appId": body.appId.strip(),
        "stageNo": body.stageNo.strip(),
    }
    token = jwt.encode(
        {
            "iss": "one-portal",
            "aud": "task-comments",
            "sub": employee_code,
            "employee_code": employee_code,
            "portal_session_id": session_id,
            "task": task,
            "iat": now,
            "nbf": now - 1,
            "exp": now + 45,
            "jti": secrets.token_urlsafe(24),
        },
        secret,
        algorithm="HS256",
    )
    return {"ticket": token, "expiresIn": 45, "task": task}
