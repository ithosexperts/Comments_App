from __future__ import annotations
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any
import re
import uuid
import requests

from app.config import Settings

try:
    TZ = ZoneInfo("Asia/Kolkata")
except Exception:  # Defensive fallback; tzdata is also declared in requirements.txt.
    from datetime import timezone, timedelta
    TZ = timezone(timedelta(hours=5, minutes=30))
THREAD_COLOR_PALETTE = [
    '#FFB3BA', '#FFDAC1', '#FFC1CC', '#F5FFFA', '#F4C2C2', '#D4F1F4', '#E8DFF5',
    '#F3E5F5', '#FFDAB9', '#FDFFB6', '#FFDFBA', '#FFB7B2', '#C9A0DC', '#E0F2F1',
    '#F8C8DC', '#FCE1E4', '#E1BEE7', '#FFE5B4', '#CAFFBF', '#FFFFBA', '#E2F0CB',
    '#E0FFFF', '#A2D9CE', '#FEF5E7', '#A0E7E5', '#FCF4DD', '#CE93D8', '#FFFACD',
    '#9BF6FF', '#BAFFC9', '#B5EAD7', '#F0F8FF', '#E6E6FA', '#B4F8C8', '#DDEDEA',
    '#F8BBD0', '#FAFAD2', '#A0C4FF', '#BAE1FF', '#C7CEEA', '#FFB6C1', '#D1F2EB',
    '#D8A7CA', '#FBE7C6', '#DAEAF6', '#FFE4E1', '#BDB2FF'
]

def clean_id(value: Any) -> str:
    return re.sub(r"[\"'\s]", "", str(value or "")).casefold()

def extract_message_only(text: Any) -> str:
    if not text:
        return ""
    cleaned = str(text).replace("\u00a0", " ").replace("&nbsp;", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned.startswith("@"):
        return cleaned
    words = cleaned.split(" ")
    return " ".join(words[2:]) if len(words) > 2 else ""

def now_local() -> datetime:
    return datetime.now(TZ).replace(tzinfo=None, microsecond=0)

def timestamp_text(task_id: Any, timestamp: datetime | None = None) -> str:
    """Format YYYYMMDDHHmm + Task ID (example: 202609101236123 for task 123)."""
    stamp = timestamp or now_local()
    return stamp.strftime("%Y%m%d%H%M") + str(task_id or "")

def _canonical_column_name(value: Any) -> str:
    """Normalize SQL API column names (e.g. Comment ID and CommentID)."""
    return re.sub(r"[^a-z0-9]", "", str(value or "").casefold())

def _get(row: dict[str, Any], *keys: str, default: Any = "") -> Any:
    for key in keys:
        if key in row and row[key] is not None:
            return row[key]
    canonical_map = {_canonical_column_name(k): v for k, v in row.items()}
    for key in keys:
        value = canonical_map.get(_canonical_column_name(key))
        if value is not None:
            return value
    return default

def _is_empty(value: Any) -> bool:
    return value is None or str(value).strip() == ""

class ActivityService:
    def __init__(self, gateway: Any, settings: Settings):
        self.db = gateway
        self.settings = settings

    @staticmethod
    def _has_admin_rights(row: dict[str, Any]) -> bool:
        """Admin rule requested for the User tab and current-user role.

        Admin rights apply when RoleID is 1, 2, or 3 OR the Department contains
        the Management or MDO department token (case-insensitive).
        """
        role_id = str(_get(row, "RoleID", "Role Id", "RoleId", default="") or "").strip()
        # SQL drivers can return numeric IDs as 1, 1.0, or string values.
        try:
            role_value = float(role_id) if role_id else None
            role_number = int(role_value) if role_value is not None and role_value.is_integer() else None
        except (TypeError, ValueError, OverflowError):
            role_number = None
        department = str(_get(row, "Department", "DepartmentName", default="") or "").strip().casefold()
        department_tokens = set(re.findall(r"[a-z]+", department))
        return role_number in {1, 2, 3} or bool(department_tokens.intersection({"management", "mdo"}))

    @staticmethod
    def _is_active_employee(row: dict[str, Any]) -> bool:
        """Only employees with Active exactly Y (case-insensitive) are selectable."""
        return str(_get(row, "Active", "IsActive", default="") or "").strip().upper() == "Y"

    @staticmethod
    def _normalize_email(value: Any) -> str:
        """Normalize master-data and comment emails for reliable joins."""
        return str(value or "").strip().strip('"').strip("'").strip().casefold()

    def _active_employee_rows(self) -> list[dict[str, Any]]:
        # Filter at the SQL API first, then enforce the rule again in Python in
        # case a gateway version returns extra rows despite the filter.
        rows = self.db.select(self.settings.users_table, {"Active": "Y"})
        return [row for row in rows if self._is_active_employee(row)]

    def get_active_employee_by_code(self, employee_code: str) -> dict[str, Any] | None:
        """Resolve a trusted employee identity by EmployeeCode and require Active='Y'."""
        target = str(employee_code or "").strip().casefold()
        if not target:
            return None
        # Query by code first, then use the Active=Y directory as a compatibility
        # fallback for SQL API versions that don't consistently apply filters.
        candidates = self.db.select(self.settings.users_table, {"EmployeeCode": str(employee_code).strip()})
        if not candidates:
            candidates = self._active_employee_rows()
        for row in candidates:
            code = str(_get(row, "EmployeeCode", "Employee Code", default="") or "").strip().casefold()
            if code != target or not self._is_active_employee(row):
                continue
            email = self._normalize_email(_get(row, "OffEmail", default=""))
            name = str(_get(row, "EmployeeName", default="") or "").strip()
            if not email or not name:
                return None
            return {
                "employee_code": str(_get(row, "EmployeeCode", "Employee Code", default="") or "").strip(),
                "email": email,
                "full_name": name,
                "role_id": str(_get(row, "RoleID", default="") or "").strip(),
                "role_name": str(_get(row, "RoleName", default="") or "").strip(),
                "department": str(_get(row, "Department", default="") or "").strip(),
                "active": "Y",
            }
        return None

    def get_active_employee_by_email(self, email: str) -> dict[str, Any] | None:
        """Development-only email resolver; production identity always comes from a Portal ticket."""
        target = self._normalize_email(email)
        if not target:
            return None
        for row in self._active_employee_rows():
            candidate = self._normalize_email(_get(row, "OffEmail", default=""))
            if candidate == target:
                return self.get_active_employee_by_code(str(_get(row, "EmployeeCode", default="")))
        return None

    def get_user_role(self, email: str) -> str:
        if not email:
            return "User"
        user_email = self._normalize_email(email)
        for row in self._active_employee_rows():
            candidate = self._normalize_email(_get(row, "OffEmail", "Email", "EmailID", "email", default=""))
            if candidate and candidate == user_email:
                return "Admin" if self._has_admin_rights(row) else "User"
        return "User"

    def get_all_users(self) -> list[dict[str, str]]:
        """Return only Active=Y VM_EmployeeMaster rows for @mentions and User tab."""
        output = []
        for row in self._active_employee_rows():
            # EmployeeName and OffEmail are the authoritative display-name mapping.
            name = str(_get(row, "EmployeeName", default="") or "").strip()
            email = self._normalize_email(_get(row, "OffEmail", default=""))
            if name and email:
                rights = "Admin" if self._has_admin_rights(row) else "User"
                output.append({
                    "name": name,
                    "email": email,
                    "active": "Y",
                    # Keep `role` for the legacy mention/case-picker widgets.
                    "role": rights,
                    "rights": rights,
                    "roleId": str(_get(row, "RoleID", "Role Id", "RoleId", default="") or "").strip(),
                    "department": str(_get(row, "Department", "DepartmentName", default="") or "").strip(),
                    "mobile": str(_get(row, "OffMobile", "Mobile", "Mobile Number", "MobileNo", "mobile", default="") or "").strip(),
                })
        return output

    def get_pending_task_details_by_comment_id(self, comment_id: str) -> dict[str, Any] | None:
        if not comment_id:
            return None
        rows = self.db.select(self.settings.pending_tasks_table, {"Comment ID": comment_id})
        target = clean_id(comment_id)
        if not rows:
            rows = [r for r in self.db.select(self.settings.pending_tasks_table) if clean_id(_get(r, "Comment ID", "CommentID")) == target]
        if rows:
            row = rows[0]
            planned = _get(row, "Planned", "Planned Date", "PlannedDate", default="")
            planned_iso, planned_display = "", ""
            if planned:
                if isinstance(planned, datetime):
                    planned_iso, planned_display = planned.isoformat(), planned.strftime("%d/%m/%Y")
                else:
                    planned_iso = str(planned)
                    try:
                        planned_display = datetime.fromisoformat(str(planned).replace("Z", "+00:00")).strftime("%d/%m/%Y")
                    except ValueError:
                        planned_display = str(planned)
            return {
                "fmsName": _get(row, "Application Name", "ApplicationName", "App Name", "AppName", "FMS Name", "FMSName"),
                "taskId": _get(row, "Task ID", "TaskID"),
                "stageName": _get(row, "Stage Name", "StageName"),
                "plannedDate": planned_iso,
                "plannedDateDisplay": planned_display,
                "doer": _get(row, "Doer"),
                "processOwner": _get(row, "Process Owner", "ProcessOwner"),
                "manager": _get(row, "Manager"),
                "submissionLink": _get(row, "Submission Link", "SubmissionLink"),
                "fmsLink": _get(row, "FMS Link", "FMSLink"),
                "userEmail": _get(row, "User Email", "UserEmail"),
                "managerEmail": _get(row, "Manager Email", "ManagerEmail"),
                "commentId": _get(row, "Comment ID", "CommentID", default=comment_id),
                "fmsRefId": _get(row, "FMS Ref Id", "FMSRefID"),
                "appId": _get(row, "App ID", "AppID"),
                "appName": _get(row, "Application Name", "ApplicationName", "App Name", "AppName"),
                "stageNo": _get(row, "Stage No", "StageNo"),
            }
        # Match the legacy fallback: recover FMS/task/stage from the comment log if the pending row is gone.
        comments = self.db.select(self.settings.comments_table)
        for row in comments:
            if clean_id(_get(row, "Comment ID")) == target:
                return {
                    "fmsName": _get(row, "Application Name", "ApplicationName", "App Name", "AppName", "FMS Name", "FMSName"),
                    "taskId": _get(row, "Task ID"),
                    "stageName": _get(row, "Stage Name"),
                    "plannedDate": "", "plannedDateDisplay": "", "doer": "", "processOwner": "", "manager": "",
                    "submissionLink": "", "fmsLink": "", "userEmail": "", "managerEmail": "", "commentId": comment_id,
                    "fmsRefId": _get(row, "FMS Ref Id"), "appId": _get(row, "App ID"), "appName": _get(row, "Application Name", "ApplicationName", "App Name", "AppName"), "stageNo": "",
                }
        return None

    @staticmethod
    def context_comment_id(table_name: str, fms_ref_id: str, app_id: str, stage_no: str) -> str:
        """Stable task-scoped comment key derived from the four form context values."""
        import hashlib
        raw = "\x1f".join(str(v or "").strip() for v in (table_name, fms_ref_id, app_id, stage_no))
        return "CTX-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:40]

    def get_application_name(self, app_id: str) -> str:
        """Resolve the display name from TM_Application_Master if the FMS row lacks it."""
        target = str(app_id or "").strip().casefold()
        if not target:
            return ""
        try:
            rows = self.db.select(self.settings.app_master_table)
        except Exception:
            # The application master is an optional fallback; task rendering should
            # continue if a deployment exposes application names on the FMS row instead.
            return ""
        for row in rows:
            row_app_id = str(_get(row, "AppID", "App ID", "APP_ID", "app_id", default="") or "").strip().casefold()
            if row_app_id != target:
                continue
            name = str(_get(
                row, "AppName", "App Name", "APP_NAME", "ApplicationName",
                "Application Name", "FMSName", "FMS Name", default=""
            ) or "").strip()
            if name:
                return name
        return ""

    def get_form_context(self, table_name: str, fms_ref_id: str, app_id: str, stage_no: str) -> dict[str, Any]:
        """Resolve the reference column from FMS_Comment_FMS_Stage_Map, then fetch the form row.

        URL fmsRefId is the *record value* (for example 8). The mapping table's
        [FMS Ref Id] column stores the *source column name* (for example Pick ID).
        """
        table_name = str(table_name or "").strip()
        fms_ref_id = str(fms_ref_id or "").strip()
        app_id = str(app_id or "").strip()
        stage_no = str(stage_no or "").strip()
        if not all((table_name, fms_ref_id, app_id, stage_no)):
            raise ValueError("TableName, FMS reference value, App ID and Stage No are required")

        # Use the exact mapping-table headers. TableName has no space; the other
        # mapping columns are named "FMS Ref Id", "App ID", and "Stage No".
        map_rows = self.db.select(
            self.settings.stage_map_table,
            {"TableName": table_name, "App ID": app_id, "Stage No": stage_no},
        )
        form_row: dict[str, Any] = {}
        chosen_mapping: dict[str, Any] = {}
        # Multiple mapping rows are tolerated; try each configured reference column
        # until the URL's value resolves a row in the target FMS table.
        for candidate in map_rows:
            source_column = str(_get(candidate, "FMS Ref Id", default="") or "").strip()
            if not source_column:
                continue
            # Preserve spaces: the actual form table may have a column named "Pick ID".
            # The SQL API must receive that exact field name, not "PickID".
            candidate_rows = self.db.select(table_name, {source_column: fms_ref_id})
            if candidate_rows:
                form_row = candidate_rows[0]
                chosen_mapping = candidate
                break
        if not chosen_mapping and len(map_rows) == 1:
            chosen_mapping = map_rows[0]

        application_name = str(_get(
            form_row, "ApplicationName", "Application Name", "AppName", "App Name", "FMSName", "FMS Name", default=""
        ) or "").strip()
        if not application_name:
            application_name = self.get_application_name(app_id)
        return {
            "tableName": table_name, "fmsRefId": fms_ref_id, "appId": app_id, "stageNo": stage_no,
            "commentId": self.context_comment_id(table_name, fms_ref_id, app_id, stage_no),
            "taskId": _get(form_row, "TaskID", "Task ID", "TaskId", default=fms_ref_id),
            "stageName": _get(form_row, "StageName", "Stage Name", "Stage", default=stage_no),
            # Display application name, never the physical FMS table name.
            "fmsName": application_name,
            "appName": application_name,
            "plannedDate": str(_get(form_row, "Planned", "PlannedDate", "Planned Date", default="") or ""),
            "plannedDateDisplay": str(_get(form_row, "Planned", "PlannedDate", "Planned Date", default="") or ""),
            "doer": _get(form_row, "Doer", "DoerName", "Doer Name", default=""),
            "processOwner": _get(form_row, "ProcessOwner", "Process Owner", default=""),
            "manager": _get(form_row, "Manager", default=""),
            "submissionLink": _get(form_row, "SubmissionLink", "Submission Link", default=""),
            "fmsLink": _get(form_row, "FMSLink", "FMS Link", default=""),
            "userEmail": _get(form_row, "UserEmail", "User Email", default=""),
            "managerEmail": _get(form_row, "ManagerEmail", "Manager Email", default=""),
        }

    def _all_comments(self) -> list[dict[str, Any]]:
        return self.db.select(self.settings.comments_table)

    def _next_top_level_ask_id(self) -> str:
        highest = 1000
        for row in self._all_comments():
            value = str(_get(row, "Ask ID", default="")).strip()
            match = re.fullmatch(r"Ask(\d+)", value)
            if match:
                highest = max(highest, int(match.group(1)))
        return f"Ask{highest + 1}"

    def _next_sub_ask_id(self, parent_ask_id: str) -> str:
        if not re.fullmatch(r"Ask\d+(?:-\d+)*", str(parent_ask_id or "")):
            return self._next_top_level_ask_id()
        prefix = parent_ask_id + "-"
        highest = 0
        for row in self._all_comments():
            value = str(_get(row, "Ask ID", default="")).strip()
            if value.startswith(prefix):
                suffix = value[len(prefix):]
                if suffix.isdigit():
                    highest = max(highest, int(suffix))
        return f"{parent_ask_id}-{highest + 1}"

    def _next_thread_id(self) -> str:
        highest = 0
        for row in self._all_comments():
            value = str(_get(row, "Thread ID", default="")).strip()
            match = re.fullmatch(r"T(\d+)", value, re.IGNORECASE)
            if match:
                highest = max(highest, int(match.group(1)))
        return f"T{highest + 1}"

    def _thread_color(self, thread_id: str) -> str:
        digits = re.sub(r"\D", "", str(thread_id or ""))
        if not digits:
            return THREAD_COLOR_PALETTE[0]
        return THREAD_COLOR_PALETTE[(int(digits) * 17) % len(THREAD_COLOR_PALETTE)]

    def _resolve_mapping(self, payload: dict[str, Any]) -> dict[str, Any]:
        # The URL's fmsRefId is the actual row value. The mapping table's
        # [FMS Ref Id] is the reference-column name, e.g. "Pick ID".
        fms_ref_value = str(_get(payload, "fmsRefId", "fmsRefID", "FMSRefId", "FMS Ref Id", default="") or "").strip()
        app_id = str(_get(payload, "appId", "appID", "AppID", "App ID", default="") or "").strip()
        stage_no = str(_get(payload, "stageNo", "stageNumber", "StageNo", "Stage No", default="") or "").strip()
        table_name = str(_get(payload, "tableName", "TableName", "table", "Table Name", default="") or "").strip()
        filters = {}
        if table_name: filters["TableName"] = table_name
        if app_id: filters["App ID"] = app_id
        if stage_no: filters["Stage No"] = stage_no
        mapping_rows = self.db.select(self.settings.stage_map_table, filters) if len(filters) == 3 else []
        chosen = mapping_rows[0] if mapping_rows else {}
        return {
            "tableName": _get(chosen, "TableName", "Table Name", default=table_name),
            "refColumn": _get(chosen, "FMS Ref Id", default=""),
            # In FMS_Comment_Log, FMS Ref Id stores the URL's actual key value,
            # not the name of the source column from the map table.
            "fmsRefId": fms_ref_value,
            "appId": _get(chosen, "App ID", default=app_id),
            "stageNo": _get(chosen, "Stage No", default=stage_no),
        }

    def add_new_comment(self, data: Any, current_user_email: str = "") -> dict[str, Any]:
        if not data:
            return {"success": False, "message": "Comment payload is empty"}
        if isinstance(data, list):
            for item in data:
                self._save_single_comment(item or {}, current_user_email)
            return {"success": True}
        if not isinstance(data, dict):
            raise ValueError("Comment payload must be an object or array")
        return self._save_single_comment(data, current_user_email)

    def _save_single_comment(self, data: dict[str, Any], current_user_email: str = "") -> dict[str, Any]:
        comment_type = str(_get(data, "mentionType", "type", default="Message") or "Message").strip()
        parent_ask_id = str(_get(data, "parentAskId", default="") or "").strip()
        if comment_type == "Ask":
            ask_id = self._next_sub_ask_id(parent_ask_id) if parent_ask_id else self._next_top_level_ask_id()
        elif comment_type == "Reply":
            ask_id = parent_ask_id
        else:
            ask_id = str(_get(data, "askId", "Ask ID", default="") or "")

        thread_id = str(_get(data, "threadId", "Thread ID", default="") or "")
        thread_id = re.sub(r"[\"'\s]", "", thread_id)
        thread_color = str(_get(data, "threadColor", "Thread Color", default="") or "")
        if not thread_id:
            thread_id = self._next_thread_id()
            thread_color = self._thread_color(thread_id)

        stamp = now_local()
        task_id = _get(data, "taskId", "Task ID", default="")
        mapping = self._resolve_mapping(data)
        comment_id = _get(data, "commentId", "Comment ID", default="")
        if not comment_id and all(str(mapping.get(k) or "").strip() for k in ("tableName", "fmsRefId", "appId", "stageNo")):
            comment_id = self.context_comment_id(mapping["tableName"], mapping["fmsRefId"], mapping["appId"], mapping["stageNo"])
        message_text = _get(data, "text", "Text", default="")
        unique_id = _get(data, "uniqueId", "Unique ID", default="") or uuid.uuid4().hex
        # These are the exact existing FMS_Comment_Log column headers from SSMS.
        # TableName and Stage No belong to FMS_Comment_FMS_Stage_Map, not this log.
        row = {
            "Comment ID": comment_id,
            "FMS Ref Id": mapping["fmsRefId"],
            "Task ID": task_id,
            "Stage Name": _get(data, "stageName", "Stage Name", default=""),
            "App ID": mapping["appId"],
            "App Name": _get(data, "appName", "App Name", "fmsName", default=""),
            "Text": message_text or "",
            "Attachment URL": _get(data, "attachmentUrl", "Attachment URL", default=""),
            "Timestamp": stamp.isoformat(sep=" "),
            # Sender is always the trusted server-resolved logged-in identity.
            # Never accept a sender email/name submitted by browser-side JavaScript.
            "Sender": current_user_email or "unknown@system",
            "Receiver": _get(data, "receiver", "Receiver", default=""),
            "Attachment Filename": _get(data, "attachmentFileName", "attachmentFilename", "Attachment Filename", default=""),
            "Type": comment_type,
            "Ask ID": ask_id,
            "Status": _get(data, "status", "Status", default=""),
            "Notification Message": _get(data, "notificationMessage", "Notification Message", default=""),
            "Open Thread": _get(data, "openThread", "Open Thread", default=""),
            "Complete Status": _get(data, "completeStatus", "Complete Status", default=""),
            "Unique ID": unique_id,
            "Thread ID": thread_id,
            "Thread Color": thread_color,
            "Unique": _get(data, "unique", "Unique", default=""),
            "Extracted Text": extract_message_only(message_text),
            "Timestamp in text": _get(data, "timestampText", "Timestamp in text", default="") or timestamp_text(task_id, stamp),
        }
        self.db.insert(self.settings.comments_table, row)
        return {"success": True, "commentId": comment_id, "askId": ask_id, "threadId": thread_id, "uniqueId": unique_id}

    def get_comments(self, comment_id: str) -> list[dict[str, Any]]:
        target = clean_id(comment_id)
        rows = self.db.select(self.settings.comments_table, {"Comment ID": comment_id}, order_by="Timestamp ASC")
        if not rows:
            rows = [r for r in self._all_comments() if clean_id(_get(r, "Comment ID")) == target]
        else:
            rows = [r for r in rows if clean_id(_get(r, "Comment ID")) == target]
        output = []
        for row in rows:
            ask_id = _get(row, "Ask ID", default="")
            parent_id = None
            if ask_id and "-" in str(ask_id):
                parent_id = "-".join(str(ask_id).split("-")[:-1])
            output.append({
                "text": _get(row, "Text", default=""),
                "attachmentUrl": _get(row, "Attachment URL", default=""),
                "attachmentFileName": _get(row, "Attachment Filename", default="") or None,
                "timestamp": str(_get(row, "Timestamp", default="") or "") or None,
                "sender": _get(row, "Sender", default=""),
                "receiver": _get(row, "Receiver", default=""),
                "type": _get(row, "Type", default=""),
                "askId": ask_id,
                "parentAskId": parent_id,
                "uniqueId": _get(row, "Unique ID", default=""),
                "threadId": _get(row, "Thread ID", default=""),
                "threadColor": _get(row, "Thread Color", default=""),
                "status": _get(row, "Status", default=""),
                "notificationMessage": _get(row, "Notification Message", default=""),
                # TableName is not a column in FMS_Comment_Log; the context is scoped by Comment ID.
                "tableName": "",
                "fmsRefId": _get(row, "FMS Ref Id", default=""),
                "appId": _get(row, "App ID", default=""),
                # Stage No is in the mapping table, not in FMS_Comment_Log.
                "stageNo": "",
                "appName": _get(row, "App Name", default=""),
                "timestampText": _get(row, "Timestamp in text", default=""),
            })
        output.sort(key=lambda item: str(item.get("timestamp") or ""))
        return output

    def mark_comments_as_read(self, comment_id: str, current_user_email: str) -> None:
        user = (current_user_email or "").strip().casefold()
        if not user:
            return
        target = clean_id(comment_id)
        rows = [r for r in self._all_comments() if clean_id(_get(r, "Comment ID")) == target]
        related_ask_ids = []
        for row in rows:
            receivers = [p.strip().replace('"', '').casefold() for p in re.split(r"[;,]", str(_get(row, "Receiver", default="") or ""))]
            typ = str(_get(row, "Type", default="") or "").strip()
            status = _get(row, "Status", default="")
            ask_id = _get(row, "Ask ID", default="")
            if user not in receivers:
                continue
            if typ in {"Message", "Reply"} and _is_empty(status):
                self._update_comment_status(row, "Read")
            if ask_id:
                related_ask_ids.append(str(ask_id))
        current_rows = self._all_comments()
        for ask_id in set(related_ask_ids):
            has_reply = any(str(_get(r, "Ask ID", default="")) == ask_id and str(_get(r, "Type", default="")).strip() == "Reply" for r in current_rows)
            if not has_reply:
                continue
            for row in current_rows:
                if str(_get(row, "Ask ID", default="")) == ask_id and str(_get(row, "Type", default="")).strip() == "Ask" and _is_empty(_get(row, "Status", default="")):
                    self._update_comment_status(row, "Read")

    def _update_comment_status(self, row: dict[str, Any], status: str) -> None:
        record_id = _get(row, "RecordID", default=None)
        if record_id is not None:
            self.db.update(self.settings.comments_table, {"Status": status}, {"RecordID": record_id})
        else:
            # Conservative fallback: update one matching row by the strongest available identity fields.
            identity = {"Comment ID": _get(row, "Comment ID"), "Unique ID": _get(row, "Unique ID")}
            self.db.update(self.settings.comments_table, {"Status": status}, identity)

    def post_reply(self, parent_ask_id: str, text: str, mention_type: str = "Reply", attachment_url: str = "", attachment_file_name: str = "", receiver_emails: str = "", current_user_email: str = "") -> str:
        if not parent_ask_id:
            raise ValueError("Parent Ask ID is required for reply.")
        rows = [r for r in self._all_comments() if str(_get(r, "Ask ID", default="")).strip().casefold() == str(parent_ask_id).strip().casefold()]
        if not rows:
            raise ValueError("Parent thread not found. Cannot inherit thread.")
        rows.sort(key=lambda r: str(_get(r, "Timestamp", default="")))
        parent = rows[-1]
        payload = {
            "commentId": _get(parent, "Comment ID"), "taskId": _get(parent, "Task ID"),
            "stageName": _get(parent, "Stage Name"), "fmsName": _get(parent, "App Name"),
            # Replies keep the stable parent Comment ID. The UI's addNewComment path
            # also sends the full four-part context directly from the current URL.
            "fmsRefId": _get(parent, "FMS Ref Id"), "appId": _get(parent, "App ID"),
            "text": text, "attachmentUrl": attachment_url, "attachmentFileName": attachment_file_name,
            "sender": current_user_email, "receiver": receiver_emails or _get(parent, "Sender", default=""),
            "mentionType": mention_type or "Reply", "parentAskId": parent_ask_id,
            "threadId": _get(parent, "Thread ID"), "threadColor": _get(parent, "Thread Color"),
        }
        self._save_single_comment(payload, current_user_email)
        return "Success"

class CaseService:
    def __init__(self, gateway: Any, settings: Settings):
        self.db = gateway
        self.settings = settings

    def get_linked_cases(self, comment_id: str) -> list[dict[str, Any]]:
        if not comment_id:
            return []
        rows = self.db.select(self.settings.case_map_table, {"CommentID": comment_id})
        if not rows:
            target = clean_id(comment_id)
            rows = [r for r in self.db.select(self.settings.case_map_table) if clean_id(_get(r, "Comment ID")) == target]
        return [{"caseId": _get(r, "Case ID", "CaseID"), "url": _get(r, "Case URL", "CaseURL")} for r in rows]

    def get_case_labels(self) -> list[str]:
        return [str(_get(r, "Label", "Name", default="")).strip() for r in self.db.select(self.settings.case_labels_table) if str(_get(r, "Label", "Name", default="")).strip()]

    def add_case_label(self, new_label: str) -> dict[str, Any]:
        label = str(new_label or "").strip()
        if not label:
            raise ValueError("Label cannot be empty")
        if any(existing.casefold() == label.casefold() for existing in self.get_case_labels()):
            return {"success": True, "label": label, "alreadyExists": True}
        self.db.insert(self.settings.case_labels_table, {"Label": label})
        return {"success": True, "label": label}

    def create_case(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.settings.case_system_api_url:
            raise RuntimeError("CASE_SYSTEM_API_URL is not configured. The external Case System is a separate integration.")
        response = requests.post(self.settings.case_system_api_url, json={"action": "createCase", "params": payload}, timeout=30)
        response.raise_for_status()
        try:
            result = response.json()
        except ValueError as exc:
            raise RuntimeError("Invalid response from Case System API") from exc
        if not result.get("success"):
            raise RuntimeError(str(result.get("error") or result.get("message") or "Failed to create case"))
        details = result.get("data") if isinstance(result.get("data"), dict) else {}
        case_id = result.get("id") or details.get("id") or result.get("caseId")
        case_url = result.get("url") or details.get("url") or result.get("caseUrl")
        mobile = result.get("mobile") or details.get("mobile") or ""
        if not case_url and case_id:
            mobile = mobile or self.get_mobile_number(payload.get("reqUserEmail", ""))
            from urllib.parse import urlencode
            case_url = self.settings.case_url_base.rstrip("/") + "/?" + urlencode({"mobileno": mobile, "autologin": "1", "open": case_id})
        self.db.insert(self.settings.case_map_table, {
            "CommentID": payload.get("commentId", ""), "TaskID": payload.get("taskId", ""),
            "StageName": payload.get("stageName", ""), "FMSName": payload.get("fmsName", ""),
            "CaseID": case_id or "", "CaseURL": case_url or "",
        })
        return {"success": True, "id": case_id, "url": case_url, "mobile": mobile}

    def get_mobile_number(self, email: str) -> str:
        target = (email or "").strip().casefold().replace('"', '')
        for row in self.db.select(self.settings.users_table):
            user_email = str(_get(row, "OffEmail", "Email", "Email ID", "EmailID", default="")).strip().casefold().replace('"', '')
            if target and user_email == target:
                return str(_get(row, "Mobile", "Mobile Number", "MobileNo", "mobile", default="") or "").strip()
        return ""

    def get_creator_name(self, email: str) -> str:
        target = (email or "").strip().casefold().replace('"', "").replace("'", "")
        for row in self.db.select(self.settings.users_table):
            user_email = str(_get(row, "OffEmail", "Email", "Email ID", "EmailID", default="")).strip().casefold().replace('"', '').replace("'", "")
            if target and user_email == target:
                return str(_get(row, "EmployeeName", "Name", default="")).strip() or (target.split("@")[0].title() if "@" in target else target)
        return target.split("@")[0].title() if "@" in target else (target or "Unknown")
