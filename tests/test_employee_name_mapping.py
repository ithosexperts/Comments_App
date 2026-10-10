from app.config import settings
from app.services import ActivityService
from app.sql_api import MemorySqlGateway
from pathlib import Path


def test_user_directory_returns_only_active_y_using_employee_name_and_offemail():
    gateway = MemorySqlGateway({settings.users_table: [
        {
            "EmployeeName": "Shweta Srivastava",
            "OffEmail": "  SarthakSrivastava@hosexperts.com  ",
            "Active": "Y",
            "RoleID": 4,
            "Department": "Sales",
            "OffMobile": "9999999999",
        },
        {"EmployeeName": "Inactive Employee", "OffEmail": "inactive@example.com", "Active": "N", "RoleID": 2},
        {"EmployeeName": "No Status Employee", "OffEmail": "nostatus@example.com", "RoleID": 4},
    ]})
    users = ActivityService(gateway, settings).get_all_users()
    assert users == [{
        "name": "Shweta Srivastava",
        "email": "sarthaksrivastava@hosexperts.com",
        "active": "Y",
        "role": "User",
        "rights": "User",
        "roleId": "4",
        "department": "Sales",
        "mobile": "9999999999",
    }]


def test_user_role_does_not_grant_rights_for_inactive_master_record():
    gateway = MemorySqlGateway({settings.users_table: [
        {"EmployeeName": "Inactive Admin", "OffEmail": "inactive@example.com", "Active": "N", "RoleID": 1, "Department": "Management"},
        {"EmployeeName": "Active Employee", "OffEmail": "active@example.com", "Active": "Y", "RoleID": 4, "Department": "Sales"},
    ]})
    service = ActivityService(gateway, settings)
    assert service.get_user_role("inactive@example.com") == "User"
    assert service.get_user_role(" ACTIVE@example.com ") == "User"


def test_comment_and_composer_name_lookup_use_normalized_offemail():
    project = Path(__file__).resolve().parents[1]
    comments_js = (project / "app" / "templates" / "js-comments.html").read_text(encoding="utf-8")
    mentions_js = (project / "app" / "templates" / "js-mentions.html").read_text(encoding="utf-8")
    users_js = (project / "app" / "templates" / "js-users.html").read_text(encoding="utf-8")
    utils_js = (project / "app" / "templates" / "js-utils.html").read_text(encoding="utf-8")
    assert "normalizeEmployeeEmail(c.sender)" in comments_js
    assert "normalizeEmployeeEmail(u && u.email)" in comments_js
    assert "normalizeEmployeeEmail(u.email) === normalizeEmployeeEmail(CURRENT_USER_EMAIL)" in mentions_js
    assert "function normalizeEmployeeEmail(value)" in utils_js
    assert "user.active ?? user.Active" in users_js
