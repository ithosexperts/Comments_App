from dataclasses import dataclass
import os
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

@dataclass(frozen=True)
class Settings:
    app_env: str = os.getenv("APP_ENV", "local").strip().lower()
    sql_api_mode: str = os.getenv("SQL_API_MODE", "mock").strip().lower()
    test_sql_api_url: str = (os.getenv("TEST_SQL_API_URL", "").strip() or "https://api.hosexperts.com:85/apiv2.php")
    production_sql_api_url: str = (os.getenv("PRODUCTION_SQL_API_URL", "").strip() or "https://api.hosexperts.com:85/apiv3.php")
    sql_api_token: str = os.getenv("SQL_API_TOKEN", "").strip()
    sql_api_timeout_seconds: float = float(os.getenv("SQL_API_TIMEOUT_SECONDS", "20"))
    allow_production_writes: bool = os.getenv("ALLOW_PRODUCTION_WRITES", "false").strip().lower() in {"1", "true", "yes", "y"}
    comments_table: str = os.getenv("SQL_COMMENTS_TABLE", "FMS_Comment_Log").strip()
    stage_map_table: str = os.getenv("SQL_STAGE_MAP_TABLE", "FMS_Comment_FMS_Stage_Map").strip()
    users_table: str = os.getenv("SQL_USERS_TABLE", "VM_EmployeeMaster").strip()
    app_master_table: str = os.getenv("SQL_APP_MASTER_TABLE", "TM_Application_Master").strip()
    pending_tasks_table: str = os.getenv("SQL_PENDING_TASKS_TABLE", "Pending_Tasks").strip()
    case_map_table: str = os.getenv("SQL_CASE_MAP_TABLE", "FMS_Comment_Case_Map").strip()
    case_labels_table: str = os.getenv("SQL_CASE_LABELS_TABLE", "FMS_Case_Labels").strip()
    case_system_api_url: str = os.getenv("CASE_SYSTEM_API_URL", "").strip()
    upload_tunnel_url: str = os.getenv("UPLOAD_TUNNEL_URL", "").strip()
    upload_dir: Path = PROJECT_ROOT / os.getenv("UPLOAD_DIR", "data/uploads")
    dev_user_email: str = os.getenv("DEV_USER_EMAIL", "local.user@hosexperts.com").strip()
    # Shared only between the authenticated One Portal backend and this app backend.
    # Never place this secret in JavaScript, HTML, URL parameters, or a Git repository.
    comments_launch_secret: str = os.getenv("COMMENTS_LAUNCH_SECRET", "").strip()
    local_dev_identity_enabled: bool = os.getenv("LOCAL_DEV_IDENTITY_ENABLED", "true").strip().lower() in {"1", "true", "yes", "y"}
    comments_session_minutes: int = int(os.getenv("COMMENTS_SESSION_MINUTES", "480"))
    comments_session_cookie: str = os.getenv("COMMENTS_SESSION_COOKIE", "task_comments_session").strip() or "task_comments_session"
    comments_cookie_samesite: str = os.getenv("COMMENTS_COOKIE_SAMESITE", "none").strip().lower()
    case_url_base: str = os.getenv("CASE_URL_BASE", "https://systems-suraj.github.io/CASESYSTEM/").strip()

    @property
    def sql_api_url(self) -> str:
        if self.sql_api_mode == "production":
            return self.production_sql_api_url
        if self.sql_api_mode == "test":
            return self.test_sql_api_url
        return ""

    def assert_write_allowed(self) -> None:
        if self.sql_api_mode == "production" and not self.allow_production_writes:
            raise PermissionError(
                "Production writes are disabled. Set ALLOW_PRODUCTION_WRITES=true only after verifying the target database."
            )
        if self.sql_api_mode not in {"mock", "test", "production"}:
            raise RuntimeError("SQL_API_MODE must be mock, test, or production")

settings = Settings()
