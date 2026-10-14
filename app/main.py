from __future__ import annotations
import asyncio
import base64
import mimetypes
import os
import re
import secrets
import uuid
from urllib.parse import urlencode
from pathlib import Path
from typing import Any
from fastapi import FastAPI, Request, HTTPException, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, Response, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from app.config import settings, PROJECT_ROOT
from app.sql_api import HttpSqlGateway, MemorySqlGateway
from app.services import ActivityService, CaseService
from app.identity import decode_portal_launch_ticket, encode_comment_session, decode_comment_session
import jwt

app = FastAPI(title="Task Activity Feed API", version="1.0.0")
templates = Jinja2Templates(directory=str(PROJECT_ROOT / "app" / "templates"))
settings.upload_dir.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(settings.upload_dir), check_dir=False), name="uploads")
app.mount("/static", StaticFiles(directory=str(PROJECT_ROOT / "app" / "static"), check_dir=False), name="static")

def build_gateway():
    mode = settings.sql_api_mode
    if mode == "mock":
        return MemorySqlGateway()
    if mode in {"test", "production"}:
        return HttpSqlGateway(
            base_url=settings.sql_api_url,
            token=settings.sql_api_token,
            timeout=settings.sql_api_timeout_seconds,
            production=mode == "production",
            allow_production_writes=settings.allow_production_writes,
        )
    raise RuntimeError("SQL_API_MODE must be mock, test, or production")

app.state.gateway = build_gateway()
# Single-use ticket tracking for the single-process app. For multiple replicas,
# replace this with a shared Redis/SQL nonce store before horizontal scaling.
app.state.used_launch_ticket_ids = {}
app.state.launch_ticket_lock = asyncio.Lock()

def get_gateway(request: Request):
    return request.app.state.gateway

def get_current_identity(request: Request) -> dict[str, str]:
    """Read the verified Comments session created from a signed One Portal ticket.

    No identity is accepted from query parameters or browser-supplied email headers.
    A fixed DEV_USER_EMAIL fallback is available only for local development previews.
    """
    cookie = request.cookies.get(settings.comments_session_cookie, "").strip()
    if cookie:
        try:
            claims = decode_comment_session(cookie, settings.comments_launch_secret)
        except jwt.ExpiredSignatureError as exc:
            raise HTTPException(status_code=401, detail="Comments session expired. Reopen Comments from One Portal.") from exc
        except (jwt.InvalidTokenError, ValueError) as exc:
            raise HTTPException(status_code=401, detail="Invalid Comments session. Reopen Comments from One Portal.") from exc
        return {
            "employee_code": str(claims.get("employee_code", "") or "").strip(),
            "email": str(claims.get("email", "") or "").strip().casefold(),
            "full_name": str(claims.get("full_name", "") or "").strip(),
            "role_id": str(claims.get("role_id", "") or "").strip(),
            "role_name": str(claims.get("role_name", "") or "").strip(),
            "department": str(claims.get("department", "") or "").strip(),
            "identity_source": "one-portal-session",
        }

    if settings.app_env in {"local", "development", "dev"} and settings.local_dev_identity_enabled:
        activity, _cases = services(request)
        employee = activity.get_active_employee_by_email(settings.dev_user_email)
        if employee:
            return {**{key: str(value or "") for key, value in employee.items()}, "identity_source": "local-development"}
        return {
            "employee_code": "LOCAL-DEV",
            "email": settings.dev_user_email.casefold(),
            "full_name": "Local Development User",
            "role_id": "",
            "role_name": "Local Development",
            "department": "",
            "identity_source": "local-development",
        }

    raise HTTPException(status_code=401, detail="No authenticated One Portal session. Open this application from One Portal.")


def get_current_user_email(request: Request) -> str:
    """Compatibility wrapper for legacy routes; email always comes from verified identity."""
    identity = get_current_identity(request)
    email = str(identity.get("email", "") or "").strip()
    if not email:
        raise HTTPException(status_code=401, detail="The authenticated employee has no OffEmail in VM_EmployeeMaster.")
    return email

def services(request: Request):
    gateway = get_gateway(request)
    return ActivityService(gateway, settings), CaseService(gateway, settings)

@app.get("/health")
def health():
    return {"ok": True, "app": "Task Activity Feed API", "sql_api_mode": settings.sql_api_mode}

@app.post("/auth/launch")
async def launch_from_one_portal(request: Request, ticket: str = Form(...), view: str = Form("full")):
    """Consume a short-lived One Portal ticket, resolve Active employee data, and set an HttpOnly cookie."""
    secret = settings.comments_launch_secret
    if not secret or len(secret) < 32:
        raise HTTPException(status_code=503, detail="COMMENTS_LAUNCH_SECRET must be configured in both server environments.")
    try:
        claims = decode_portal_launch_ticket(ticket.strip(), secret)
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=401, detail="One Portal launch ticket expired. Please reopen the Comments button.") from exc
    except (jwt.InvalidTokenError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Invalid One Portal launch ticket.") from exc

    jti = str(claims.get("jti", "") or "").strip()
    if not jti:
        raise HTTPException(status_code=401, detail="Launch ticket is missing its unique ID.")
    async with request.app.state.launch_ticket_lock:
        used = request.app.state.used_launch_ticket_ids
        now = int(__import__("time").time())
        for previous_id, expiry in list(used.items()):
            if expiry < now:
                used.pop(previous_id, None)
        if jti in used:
            raise HTTPException(status_code=401, detail="This launch ticket has already been used. Reopen Comments from One Portal.")
        used[jti] = int(claims.get("exp", now + 45))

    employee_code = str(claims.get("employee_code") or claims.get("sub") or "").strip()
    if not employee_code:
        raise HTTPException(status_code=401, detail="Launch ticket has no EmployeeCode.")
    activity, _cases = services(request)
    employee = activity.get_active_employee_by_code(employee_code)
    if not employee:
        raise HTTPException(status_code=403, detail="EmployeeCode was not found as Active='Y' in VM_EmployeeMaster, or OffEmail/EmployeeName is missing.")

    try:
        session_token = encode_comment_session(
            employee=employee,
            secret=secret,
            portal_session_id=str(claims.get("portal_session_id", "") or ""),
            ttl_seconds=max(60, settings.comments_session_minutes * 60),
        )
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    context = claims.get("task") if isinstance(claims.get("task"), dict) else {}
    task_context = {
        "tableName": str(context.get("tableName", "") or "").strip(),
        "fmsRefId": str(context.get("fmsRefId", "") or "").strip(),
        "appId": str(context.get("appId", "") or "").strip(),
        "stageNo": str(context.get("stageNo", "") or "").strip(),
        "rowId": str(context.get("rowId", "") or "").strip(),
        "primaryKey": str(context.get("primaryKey", "") or "").strip(),
        "taskId": str(context.get("taskId", "") or "").strip(),
    }
    if not all(task_context[key] for key in ("tableName", "fmsRefId", "appId", "stageNo")):
        raise HTTPException(status_code=422, detail="Launch ticket has incomplete task context.")

    # View only controls presentation; task and identity are still from the signed ticket.
    selected_view = "compact" if str(view or "").strip().lower() == "compact" else "full"
    response = RedirectResponse(url="/?" + urlencode({key: value for key, value in {**task_context, "view": selected_view}.items() if value != ""}), status_code=303)
    same_site = settings.comments_cookie_samesite if settings.comments_cookie_samesite in {"lax", "strict", "none"} else "lax"
    local_mode = settings.app_env in {"local", "development", "dev"}
    response.set_cookie(
        key=settings.comments_session_cookie,
        value=session_token,
        max_age=max(60, settings.comments_session_minutes * 60),
        httponly=True,
        # SameSite=None requires Secure; localhost/127.0.0.1 are treated as
        # potentially trustworthy by modern browsers. Production must use HTTPS.
        secure=(same_site == "none") or not local_mode,
        samesite=same_site,
        path="/",
    )
    return response


@app.get("/api/whoami")
def who_am_i(request: Request):
    """Diagnostic endpoint: shows which employee the server resolved, never password/token."""
    identity = get_current_identity(request)
    return {
        "employeeCode": identity.get("employee_code", ""),
        "employeeName": identity.get("full_name", ""),
        "email": identity.get("email", ""),
        "roleId": identity.get("role_id", ""),
        "department": identity.get("department", ""),
        "identitySource": identity.get("identity_source", ""),
    }


@app.get("/", response_class=HTMLResponse)
def home(request: Request, commentId: str | None = None, tableName: str | None = None,
         fmsRefId: str | None = None, appId: str | None = None, stageNo: str | None = None,
         rowId: str | None = None, primaryKey: str | None = None, taskId: str | None = None,
         view: str = "full"):
    current_identity = get_current_identity(request)
    current_email = str(current_identity.get("email", "") or "").strip()
    if not current_email:
        raise HTTPException(status_code=401, detail="Authenticated employee has no OffEmail.")
    activity, _cases = services(request)
    task_details = None
    role = "User"
    context_error = ""
    try:
        role = activity.get_user_role(current_email)
        if all((tableName, fmsRefId, appId, stageNo)):
            task_details = activity.get_form_context(
                tableName, fmsRefId, appId, stageNo,
                row_id=rowId or "", primary_key=primaryKey or "", task_id=taskId or "",
            )
            commentId = task_details["commentId"]
        elif commentId:
            task_details = activity.get_pending_task_details_by_comment_id(commentId)
        if commentId and task_details:
            activity.mark_comments_as_read(commentId, current_email)
    except Exception as exc:
        context_error = str(exc)
        if settings.sql_api_mode != "mock":
            print(f"Startup data lookup failed ({settings.sql_api_mode} API): {exc}")
    return templates.TemplateResponse(request, "index.html", {
        "comment_id": commentId, "current_user_email": current_email,
        "current_user_name": current_identity.get("full_name", ""),
        "current_employee_code": current_identity.get("employee_code", ""),
        "current_user_role": role,
        "current_user_role_id": current_identity.get("role_id", ""),
        "compact_view": str(view or "").strip().lower() == "compact",
        "taskDetails": task_details,
        "table_name": tableName or (task_details or {}).get("tableName", ""),
        "context_error": context_error,
        "sql_api_mode": settings.sql_api_mode,
        "case_system_api_url": "",
    })

@app.get("/embed.js")
def embed_widget():
    """Inline Comments launcher for FMS forms.

    Inserts the Comments icon beside the Lead Time Extension control when one
    exists, or in the stage heading for forms without that control. The modal
    receives a compact view; Open in new tab receives the full task view.
    Identity is always exchanged using a signed One Portal launch ticket.
    """
    js = r'''(function(){
 'use strict';
 const script=document.currentScript, src=new URL(script.src), p=src.searchParams, commentsOrigin=src.origin;
 const read=(param,selectorParam)=>{const selector=p.get(selectorParam);if(selector){const el=document.querySelector(selector);if(el)return String(el.value||el.textContent||el.getAttribute("data-value")||"").trim()}return p.get(param)||""};
 const context=()=>({tableName:read("tableName","tableSelector"),fmsRefId:read("fmsRefId","fmsRefSelector"),appId:read("appId","appSelector"),stageNo:read("stageNo","stageSelector"),rowId:read("rowId","rowSelector"),primaryKey:read("primaryKey","primaryKeySelector"),taskId:read("taskId","taskSelector")});
 const waitForBridgeTicket=(ctx)=>new Promise((resolve,reject)=>{
   const portalOrigin=p.get("portalOrigin");if(!portalOrigin){reject(new Error("Cross-origin app requires portalOrigin in the embed URL."));return}
   const requestId="comments-"+Date.now()+"-"+Math.random().toString(36).slice(2);
   const timer=setTimeout(()=>{window.removeEventListener("message",listener);reject(new Error("No response from One Portal identity bridge."))},12000);
   const listener=(event)=>{if(event.source!==window.parent||event.origin!==portalOrigin||!event.data||event.data.type!=="ONEPORTAL_COMMENTS_LAUNCH_TICKET"||event.data.requestId!==requestId)return;clearTimeout(timer);window.removeEventListener("message",listener);if(event.data.error)reject(new Error(event.data.error));else if(event.data.ticket)resolve(event.data.ticket);else reject(new Error("One Portal did not return a launch ticket."))};
   window.addEventListener("message",listener);window.parent.postMessage({type:"ONEPORTAL_COMMENTS_LAUNCH_REQUEST",requestId,context:ctx},portalOrigin);
 });
 const requestTicket=async(ctx)=>{
   if(!ctx.tableName||!ctx.fmsRefId||!ctx.appId||!ctx.stageNo)throw new Error("Comments launcher needs Table Name, FMS Ref Id/value, App ID and Stage No.");
   if(window.parent!==window&&p.get("portalOrigin"))return await waitForBridgeTicket(ctx);
   const portalBase=(p.get("portalApiBase")||window.location.origin).replace(/\/$/,"");
   let accessToken="";try{accessToken=localStorage.getItem("access_token")||localStorage.getItem("auth_token")||""}catch(e){}
   if(!accessToken)throw new Error("No One Portal login token found. Please open this form from a signed-in One Portal session.");
   const response=await fetch(portalBase+"/api/comments/launch-ticket",{method:"POST",headers:{"Content-Type":"application/json","Authorization":"Bearer "+accessToken},body:JSON.stringify(ctx),credentials:"same-origin"});
   let body={};try{body=await response.json()}catch(e){}
   if(!response.ok||!body.ticket)throw new Error(body.detail||body.message||"One Portal could not issue a Comments launch ticket. Check the Comments SSO configuration.");
   return body.ticket;
 };
 const postTicket=(ticket,target,view)=>{const form=document.createElement("form");form.method="POST";form.action=commentsOrigin+"/auth/launch";form.target=target;form.style.display="none";[["ticket",ticket],["view",view]].forEach(([name,value])=>{const input=document.createElement("input");input.type="hidden";input.name=name;input.value=value;form.appendChild(input)});document.body.appendChild(form);form.submit();form.remove()};
 const css=document.createElement("style");css.textContent=`
 .task-comments-inline-trigger{display:inline-flex;align-items:center;justify-content:center;flex:0 0 auto;width:34px;height:30px;padding:0;margin-left:3px;border:1px solid #bfdbfe;border-radius:6px;background:#eff6ff;color:#1d4ed8;cursor:pointer;vertical-align:middle;transition:background .15s,border-color .15s,transform .15s;position:relative}
 .task-comments-inline-trigger:hover,.task-comments-inline-trigger:focus-visible{background:#dbeafe;border-color:#60a5fa;transform:translateY(-1px);outline:2px solid #93c5fd;outline-offset:1px}
 .task-comments-inline-trigger svg{width:18px;height:18px;display:block;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}
 .task-comments-inline-trigger:after{content:'Comments';position:absolute;top:calc(100% + 7px);left:50%;transform:translateX(-50%);opacity:0;pointer-events:none;white-space:nowrap;background:#111827;color:#fff;border-radius:6px;padding:5px 8px;font:600 11px/1.2 sans-serif;z-index:2147483000;transition:opacity .15s}
 .task-comments-inline-trigger:hover:after,.task-comments-inline-trigger:focus-visible:after{opacity:1}
 #task-comments-overlay{display:none;position:fixed;inset:0;background:#0f172a99;z-index:2147483001;align-items:center;justify-content:center;padding:2vh 2vw}
 #task-comments-panel{background:#fff;width:min(1400px,98vw);height:94vh;border-radius:14px;overflow:hidden;display:flex;flex-direction:column;box-shadow:0 20px 70px #0f172a55}
 #task-comments-toolbar{display:flex;gap:10px;align-items:center;justify-content:flex-end;padding:8px 12px;border-bottom:1px solid #e5e7eb;flex:none}
 #task-comments-toolbar button{border:0;border-radius:7px;padding:8px 12px;background:#2563eb;color:#fff;cursor:pointer;font:600 13px/1.2 system-ui,sans-serif}
 #task-comments-toolbar button.close{background:#475569}
 #task-comments-status{margin-right:auto;color:#475569;font:13px system-ui,sans-serif;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
 #task-comments-frame{border:0;width:100%;height:100%;flex:1;min-height:0;background:#f8fafc}
 @media(max-width:600px){#task-comments-overlay{padding:0}#task-comments-panel{width:100vw;height:100vh;border-radius:0}#task-comments-toolbar{gap:6px;padding:8px}#task-comments-toolbar button{padding:8px;font-size:12px}}
 `;document.head.appendChild(css);
 const overlay=document.createElement("div");overlay.id="task-comments-overlay";overlay.innerHTML='<div id="task-comments-panel" role="dialog" aria-modal="true" aria-label="Task comments"><div id="task-comments-toolbar"><span id="task-comments-status">Ready</span><button id="task-comments-newtab" type="button">↗ Open in new tab</button><button class="close" id="task-comments-close" type="button">Close ✕</button></div><iframe id="task-comments-frame" name="task-comments-frame" title="Task comments"></iframe></div>';document.body.appendChild(overlay);
 const status=(msg)=>{const el=document.getElementById("task-comments-status");if(el)el.textContent=msg};
 const openCompact=async()=>{overlay.style.display="flex";status("Connecting to One Portal...");try{const ticket=await requestTicket(context());status("Loading conversation...");postTicket(ticket,"task-comments-frame","compact")}catch(e){overlay.style.display="none";alert(e.message||String(e))}};
 const openFullTab=async()=>{const win=window.open("about:blank","_blank");if(!win){alert("Allow pop-ups to open Comments in a new tab.");return}const target="comments-tab-"+Date.now();win.name=target;try{const ticket=await requestTicket(context());postTicket(ticket,target,"full")}catch(e){win.close();alert(e.message||String(e))}};
 // Prefer to sit directly beside any stage-specific Lead Time Extension icon.
 const title=document.querySelector('.stage1-custom .card__title, section.card > h3.card__title, section.card > h3, .card__title');
 const titleGroup=title&&title.querySelector('div')||title;
 const ltg=document.querySelector('.lead-time-extension-btn, .s2-lead-time-extension-btn, .s3-lead-time-extension-btn');
 const btn=document.createElement('button');btn.id='task-comments-trigger';btn.type='button';btn.className='btn btn-sm task-comments-inline-trigger';btn.title='Open comments for this task and stage';btn.setAttribute('aria-label','Open task comments');btn.innerHTML='<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M21 11.5a8.4 8.4 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.4 8.4 0 0 1-3.8-.9L3 21l1.9-5.7a8.4 8.4 0 0 1-.9-3.8A8.5 8.5 0 0 1 8.7 3.9a8.4 8.4 0 0 1 3.8-.9h.5a8.5 8.5 0 0 1 8 8z"/></svg>';
 if(ltg&&ltg.parentElement){ltg.insertAdjacentElement('afterend',btn)}else if(titleGroup){titleGroup.appendChild(btn)}else{document.body.appendChild(btn)}
 btn.addEventListener('click',openCompact);
 document.getElementById('task-comments-newtab').addEventListener('click',openFullTab);
 document.getElementById('task-comments-close').addEventListener('click',()=>{overlay.style.display='none'});
 overlay.addEventListener('click',e=>{if(e.target===overlay)overlay.style.display='none'});
 document.addEventListener('keydown',e=>{if(e.key==='Escape'&&overlay.style.display==='flex')overlay.style.display='none'});
})();
'''
    return Response(content=js, media_type="application/javascript")

class RpcPayload(BaseModel):
    args: list[Any] = Field(default_factory=list)

@app.post("/api/rpc/{method_name}")
def rpc(method_name: str, body: RpcPayload, request: Request):
    current_identity = get_current_identity(request)
    current_email = str(current_identity.get("email", "") or "").strip()
    if not current_email:
        raise HTTPException(status_code=401, detail="Authenticated employee has no OffEmail.")
    activity, cases = services(request)
    args = body.args or []
    try:
        if method_name == "getAllUsers":
            result = activity.get_all_users()
        elif method_name == "getUserRole":
            # Ignore any browser-supplied email; rights are for the logged-in employee.
            result = activity.get_user_role(current_email)
        elif method_name == "getPendingTaskDetailsByCommentId":
            result = activity.get_pending_task_details_by_comment_id(str(args[0] if args else ""))
        elif method_name in {"getCommentsOnly", "getComments"}:
            result = activity.get_comments(str(args[0] if args else ""))
        elif method_name == "addNewComment":
            result = activity.add_new_comment(args[0] if args else None, current_email)
        elif method_name == "postReply":
            vals = (args + ["", "Reply", "", "", "", ""])[:6]
            result = activity.post_reply(str(vals[0]), str(vals[1]), str(vals[2] or "Reply"), str(vals[3] or ""), str(vals[4] or ""), str(vals[5] or ""), current_email)
        elif method_name == "markCommentsAsRead":
            # The receiver is always the authenticated employee, never a client-provided identity.
            activity.mark_comments_as_read(str(args[0] if args else ""), current_email)
            result = {"success": True}
        else:
            raise HTTPException(status_code=404, detail=f"Unsupported backend method: {method_name}")
        return JSONResponse(content=result)
    except HTTPException:
        raise
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

class UploadPayload(BaseModel):
    base64: str
    name: str = "attachment.bin"
    mime: str = "application/octet-stream"

@app.post("/api/uploads")
def upload_attachment(body: UploadPayload, request: Request):
    # Local-safe replacement for the GAS upload tunnel. When configured, an existing upload endpoint can be proxied.
    if settings.upload_tunnel_url:
        import requests
        response = requests.post(settings.upload_tunnel_url, json=body.model_dump(), timeout=60)
        response.raise_for_status()
        try:
            result = response.json()
        except ValueError as exc:
            raise HTTPException(status_code=502, detail="Upload integration returned non-JSON") from exc
        return result
    try:
        raw = base64.b64decode(body.base64, validate=True)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid base64 file content") from exc
    safe_name = Path(body.name or "attachment.bin").name
    suffix = Path(safe_name).suffix[:20]
    target_name = f"{uuid.uuid4().hex}{suffix}"
    target = settings.upload_dir / target_name
    target.write_bytes(raw)
    return {"status": "success", "url": str(request.base_url).rstrip("/") + "/uploads/" + target_name, "fileName": safe_name, "mime": body.mime}


class CaseProxyPayload(BaseModel):
    action: str
    params: dict[str, Any] = Field(default_factory=dict)

@app.post("/api/case/system-command")
def case_system_command(body: CaseProxyPayload):
    # Keep the external Case System URL off the browser and allow only commands used by the UI.
    allowed_actions = {"getLabels", "addLabel", "getResumableUploadUrl", "uploadChunkToDrive"}
    if body.action not in allowed_actions:
        raise HTTPException(status_code=400, detail="Unsupported Case System command")
    if not settings.case_system_api_url:
        raise HTTPException(status_code=503, detail="CASE_SYSTEM_API_URL is not configured")
    import requests
    try:
        response = requests.post(
            settings.case_system_api_url,
            json={"action": body.action, "params": body.params},
            headers={"Content-Type": "text/plain;charset=utf-8"},
            timeout=60,
        )
        response.raise_for_status()
        return JSONResponse(content=response.json())
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Case System API request failed: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="Case System API returned invalid JSON") from exc

@app.post("/api/stage-map")
def add_stage_mapping(payload: dict[str, Any], request: Request):
    current_email = get_current_user_email(request)
    # This endpoint intentionally supports INSERT only and checks all three natural-key values.
    table_name = str(payload.get("tableName") or payload.get("TableName") or payload.get("Table Name") or "").strip()
    fms_ref_id = str(payload.get("fmsRefId") or payload.get("FMS Ref Id") or "").strip()
    app_id = str(payload.get("appId") or payload.get("App ID") or "").strip()
    stage_no = str(payload.get("stageNo") or payload.get("Stage No") or "").strip()
    if not all((table_name, fms_ref_id, app_id, stage_no)):
        raise HTTPException(status_code=422, detail="Table Name, FMS Ref Id, App ID and Stage No are required")
    gateway = get_gateway(request)
    try:
        existing = gateway.select(settings.stage_map_table, {"TableName": table_name, "FMS Ref Id": fms_ref_id, "App ID": app_id, "Stage No": stage_no})
        if existing:
            return {"success": True, "alreadyExists": True, "mapping": existing[0]}
        result = gateway.insert(settings.stage_map_table, {"TableName": table_name, "FMS Ref Id": fms_ref_id, "App ID": app_id, "Stage No": stage_no})
        return {"success": True, "createdBy": current_email, "result": result}
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

@app.get("/api/stage-map")
def get_stage_mapping(request: Request, tableName: str | None = None, fmsRefId: str | None = None, appId: str | None = None, stageNo: str | None = None):
    _ = get_current_user_email(request)
    where = {}
    if tableName: where["TableName"] = tableName
    if fmsRefId: where["FMS Ref Id"] = fmsRefId
    if appId: where["App ID"] = appId
    if stageNo: where["Stage No"] = stageNo
    try:
        return get_gateway(request).select(settings.stage_map_table, where)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

@app.get("/api/config")
def public_config():
    # Never return API keys or the production URL to the browser.
    return {"sqlApiMode": settings.sql_api_mode, "caseIntegrationConfigured": bool(settings.case_system_api_url), "uploadMode": "proxy" if settings.upload_tunnel_url else "local"}
