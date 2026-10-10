from fastapi.testclient import TestClient
from app.main import app
from app.config import settings
from app.sql_api import MemorySqlGateway

def setup_client():
    app.state.gateway = MemorySqlGateway()
    return TestClient(app)

def test_health_reports_mockable_service():
    client = setup_client()
    response = client.get('/health')
    assert response.status_code == 200
    assert response.json()['ok'] is True

def test_rpc_add_then_read_comment_without_network():
    client = setup_client()
    payload = {"args": [{"commentId":"RPC-1", "taskId":"123", "text":"Hello", "mentionType":"Message", "receiver":"local.user@hosexperts.com"}]}
    added = client.post('/api/rpc/addNewComment', json=payload)
    assert added.status_code == 200, added.text
    fetched = client.post('/api/rpc/getCommentsOnly', json={"args":["RPC-1"]})
    assert fetched.status_code == 200
    assert fetched.json()[0]['text'] == 'Hello'

def test_stage_mapping_endpoint_validates_fields():
    client = setup_client()
    response = client.post('/api/stage-map', json={"fmsRefId":"F1", "appId":"A1"}, params={"user":"dev@example.com"})
    assert response.status_code == 422

def test_stage_mapping_endpoint_insert_and_fetch_in_mock():
    client = setup_client()
    response = client.post('/api/stage-map?user=dev@example.com', json={"tableName":"Z_SalesOrder", "fmsRefId":"F1", "appId":"A1", "stageNo":"5"})
    assert response.status_code == 200, response.text
    fetched = client.get('/api/stage-map?user=dev@example.com&tableName=Z_SalesOrder&fmsRefId=F1')
    assert fetched.status_code == 200
    assert fetched.json()[0]['Stage No'] == '5'
    assert fetched.json()[0]['TableName'] == 'Z_SalesOrder'
    assert fetched.json()[0]['FMS Ref Id'] == 'F1'
    assert fetched.json()[0]['App ID'] == 'A1'


def test_home_renders_converted_template_without_gas_markers():
    client = setup_client()
    response = client.get('/?commentId=C1&user=dev@example.com')
    assert response.status_code == 200, response.text[:500]
    assert "Task Activity Feed" in response.text
    assert "<?!=" not in response.text
    assert 'SERVER_COMMENT_ID = "C1"' in response.text


def test_production_gateway_blocks_writes_without_opt_in():
    from app.sql_api import HttpSqlGateway
    gateway = HttpSqlGateway('https://prod.invalid/api.php', production=True, allow_production_writes=False)
    try:
        gateway.insert('dbo.FMS_Comment_Log', {'Comment ID': 'NO-WRITE'})
    except PermissionError as exc:
        assert 'Production writes are blocked' in str(exc)
    else:
        raise AssertionError('Production write should have been blocked')

def test_http_gateway_uses_existing_crud_api_envelope(monkeypatch):
    from app.sql_api import HttpSqlGateway
    class FakeResponse:
        def raise_for_status(self): pass
        def json(self): return {'status': 'success', 'data': [{'Comment ID': 'C1'}]}
    calls = {}
    def fake_post(url, **kwargs):
        calls['url'] = url
        calls.update(kwargs)
        return FakeResponse()
    gateway = HttpSqlGateway('https://test.invalid/apiv2.php')
    monkeypatch.setattr(gateway.session, 'post', fake_post)
    rows = gateway.select('dbo.FMS_Comment_Log', {'Comment ID': "x' OR 1=1 --"}, 'Timestamp DESC')
    assert calls['url'] == 'https://test.invalid/apiv2.php'
    assert calls['json']['action'] == 'select'
    assert calls['json']['table'] == 'FMS_Comment_Log'
    assert calls['json']['filters'] == {'CommentID': "x' OR 1=1 --"}
    assert calls['json']['orderBy'] == '[Timestamp] DESC'
    assert calls['json']['fetchAll'] is True
    assert 'query' not in calls['json'] and 'params' not in calls['json']
    assert rows == [{'Comment ID': 'C1'}]


def test_http_gateway_uses_insert_and_update_envelopes(monkeypatch):
    from app.sql_api import HttpSqlGateway
    calls = []
    class FakeResponse:
        def raise_for_status(self): pass
        def json(self): return {'status': 'success'}
    gateway = HttpSqlGateway('https://test.invalid/apiv2.php')
    monkeypatch.setattr(gateway.session, 'post', lambda url, **kwargs: (calls.append(kwargs['json']) or FakeResponse()))
    gateway.insert('dbo.FMS_Comment_Log', {'Comment ID': 'C2', 'Text': 'hello'})
    gateway.update('dbo.FMS_Comment_Log', {'Status': 'Read'}, {'RecordID': 8})
    assert calls[0] == {'action': 'insert', 'table': 'FMS_Comment_Log', 'data': {'CommentID': 'C2', 'Text': 'hello'}}
    assert calls[1] == {'action': 'update', 'table': 'FMS_Comment_Log', 'data': {'Status': 'Read'}, 'where': {'RecordID': 8}}


def test_dynamic_form_context_creates_stable_task_comment_key_and_displays_application_name():
    client = setup_client()
    gateway = app.state.gateway
    gateway.tables[settings.stage_map_table] = [{
        "TableName": "Z_SalesOrder", "FMS Ref Id": "Pick ID", "App ID": "APP000001", "Stage No": "1"
    }]
    gateway.tables["Z_SalesOrder"] = [{
        "Pick ID": "8", "Task ID": "TASK-9", "Stage Name": "Picking", "Application Name": "Sales Order Application"
    }]
    response = client.get('/?tableName=Z_SalesOrder&fmsRefId=8&appId=APP000001&stageNo=1&user=dev@example.com')
    assert response.status_code == 200, response.text
    assert 'CURRENT_TABLE_NAME = "Z_SalesOrder"' in response.text
    assert 'CURRENT_FMS_REF_ID = "8"' in response.text
    assert 'CURRENT_APP_ID = "APP000001"' in response.text
    assert 'CURRENT_STAGE_NO = "1"' in response.text
    assert 'CTX-' in response.text
    assert '<h1 class="text-xl md:text-2xl font-bold text-gray-900 truncate">Sales Order Application</h1>' in response.text
    assert '<h1 class="text-3xl font-bold mb-4">Z_SalesOrder</h1>' not in response.text

def test_comment_row_uses_exact_existing_fms_comment_log_headers():
    from app.services import ActivityService
    client = setup_client()
    gateway = app.state.gateway
    gateway.tables[settings.stage_map_table] = [{
        "TableName": "Z_SalesOrder", "FMS Ref Id": "Pick ID", "App ID": "APP000001", "Stage No": "1"
    }]
    gateway.tables["Z_SalesOrder"] = [{
        "Pick ID": "8", "Task ID": "TASK-9", "Stage Name": "Picking", "Application Name": "Sales Order Application"
    }]
    ActivityService(gateway, settings).add_new_comment({
        "tableName": "Z_SalesOrder", "fmsRefId": "8", "appId": "APP000001", "stageNo": "1",
        "taskId": "TASK-9", "stageName": "Picking", "appName": "Sales Order Application",
        "text": "Checking task", "mentionType": "Message"
    }, "dev@example.com")
    row = gateway.select(settings.comments_table)[0]
    expected = {
        "Comment ID", "FMS Ref Id", "Task ID", "Stage Name", "App ID", "App Name", "Text",
        "Attachment URL", "Timestamp", "Sender", "Receiver", "Attachment Filename", "Type",
        "Ask ID", "Status", "Notification Message", "Open Thread", "Complete Status", "Unique ID",
        "Thread ID", "Thread Color", "Unique", "Extracted Text", "Timestamp in text"
    }
    # MemorySqlGateway adds RecordID to simulate SQL Server's identity column.
    assert expected == set(row.keys()) - {"RecordID"}
    assert row["Comment ID"].startswith("CTX-")
    assert row["FMS Ref Id"] == "8"
    assert row["App ID"] == "APP000001"
    assert "TableName" not in row and "Stage No" not in row


def test_embed_widget_has_modal_and_new_tab_action():
    client = setup_client()
    response = client.get('/embed.js')
    assert response.status_code == 200
    assert 'task-comments-overlay' in response.text
    assert 'Open in new tab' in response.text
    assert 'stageSelector' in response.text


def test_served_ui_does_not_include_case_creation_form_or_controls():
    client = setup_client()
    response = client.get('/?user=dev@example.com')
    assert response.status_code == 200
    assert 'Create Case' not in response.text
    assert 'convForm' not in response.text
    assert 'openCaseModal' not in response.text


def test_user_directory_maps_vm_employee_master_and_applies_admin_rights_rule():
    client = setup_client()
    gateway = app.state.gateway
    gateway.tables[settings.users_table] = [
        {"EmployeeName": "Admin By Role", "OffEmail": "role@example.com", "RoleID": 2, "Department": "Sales", "Active": "Y"},
        {"EmployeeName": "Admin By Department", "OffEmail": "mdo@example.com", "RoleID": 9, "Department": "MDO Operations", "Active": "Y"},
        {"EmployeeName": "Management Admin", "OffEmail": "management@example.com", "RoleID": 8, "Department": "Management", "Active": "Y"},
        {"EmployeeName": "Regular User", "OffEmail": "user@example.com", "RoleID": 9, "Department": "Sales", "Active": "Y"},
    ]

    response = client.post('/api/rpc/getAllUsers?user=dev@example.com', json={"args": []})
    assert response.status_code == 200, response.text
    by_email = {row["email"]: row for row in response.json()}
    assert by_email["role@example.com"]["name"] == "Admin By Role"
    assert by_email["role@example.com"]["rights"] == "Admin"
    assert by_email["mdo@example.com"]["rights"] == "Admin"
    assert by_email["management@example.com"]["rights"] == "Admin"
    assert by_email["user@example.com"]["rights"] == "User"
    assert by_email["user@example.com"]["role"] == "User"


def test_get_user_role_uses_same_roleid_or_department_admin_rule():
    from app.services import ActivityService
    gateway = MemorySqlGateway({settings.users_table: [
        {"EmployeeName": "Role Three", "OffEmail": "r3@example.com", "RoleID": "3", "Department": "Sales", "Active": "Y"},
        {"EmployeeName": "Department Admin", "OffEmail": "dep@example.com", "RoleID": "99", "Department": "Corporate Management", "Active": "Y"},
        {"EmployeeName": "Regular", "OffEmail": "reg@example.com", "RoleID": "99", "Department": "Operations", "Active": "Y"},
    ]})
    service = ActivityService(gateway, settings)
    assert service.get_user_role("r3@example.com") == "Admin"
    assert service.get_user_role("dep@example.com") == "Admin"
    assert service.get_user_role("reg@example.com") == "User"


def test_user_tab_is_present_with_requested_columns_and_search():
    client = setup_client()
    response = client.get('/?user=dev@example.com')
    assert response.status_code == 200
    assert 'id="users-tab-button"' in response.text
    assert '<th scope="col" class="px-3 py-3 border-b">User Name</th>' in response.text
    assert '<th scope="col" class="px-3 py-3 border-b">Email</th>' in response.text
    assert '<th scope="col" class="px-3 py-3 border-b">Rights</th>' in response.text
    assert 'function renderUsersDirectory()' in response.text


def test_user_tab_explains_that_mock_mode_has_no_real_employees():
    client = setup_client()
    response = client.get('/?commentId=C1&user=dev@example.com')
    assert response.status_code == 200
    assert 'Local mock mode has no employee records' in response.text
    assert 'Copy .env.example to .env' in response.text


def test_local_launcher_loads_env_before_defaulting_to_mock():
    from pathlib import Path
    launcher = (Path(__file__).resolve().parents[1] / 'run_local.py').read_text(encoding='utf-8')
    assert launcher.index('load_dotenv(PROJECT_ROOT / ".env"') < launcher.index('os.environ.setdefault("SQL_API_MODE", "mock")')


def test_shell_launchers_do_not_override_sql_api_mode_from_env_file():
    import re
    from pathlib import Path
    project = Path(__file__).resolve().parents[1]
    for launcher_name in ('run_local.ps1', 'run_local.sh'):
        source = (project / launcher_name).read_text(encoding='utf-8')
        assert not re.search(r'(?m)^\s*(?:\$env:SQL_API_MODE\s*=|export\s+SQL_API_MODE=)', source)


def test_form_context_does_not_require_comment_id_or_successful_fms_lookup():
    client = setup_client()

    class LookupFailGateway(MemorySqlGateway):
        def select(self, table, filters=None, order_by=None):
            if table == "Z_SalesOrder":
                raise RuntimeError("Mock SQL API: FMS field mapping not configured")
            return super().select(table, filters, order_by)

    app.state.gateway = LookupFailGateway()
    response = client.get(
        "/?tableName=Z_SalesOrder&fmsRefId=8&appId=APP000001&stageNo=1&user=dev@example.com"
    )
    assert response.status_code == 200, response.text
    assert 'SERVER_COMMENT_ID = "CTX-' in response.text
    assert 'CURRENT_TABLE_NAME = "Z_SalesOrder"' in response.text
    assert 'CURRENT_FMS_REF_ID = "8"' in response.text
    assert 'CURRENT_APP_ID = "APP000001"' in response.text
    assert 'CURRENT_STAGE_NO = "1"' in response.text
    assert "No Comment ID provided" not in response.text
    assert "Task Comment Key:" not in response.text
    # A fallback warning exists in the JS source for bare/manual launches, but
    # this request has all four required task-context fields and a generated key.
    assert 'CURRENT_FMS_REF_ID = "8"' in response.text and 'CURRENT_APP_ID = "APP000001"' in response.text


def test_form_context_uses_mapping_fmsrefid_as_reference_column_name():
    client = setup_client()
    gateway = app.state.gateway
    gateway.tables[settings.stage_map_table] = [{
        "TableName": "Z_SalesOrder", "FMS Ref Id": "Pick ID", "App ID": "APP000001", "Stage No": "1"
    }]
    gateway.tables["Z_SalesOrder"] = [
        {"Pick ID": "7", "Task ID": "TASK-7", "Application Name": "Other Application"},
        {"Pick ID": "8", "Task ID": "TASK-8", "Application Name": "Sales Order Application"},
    ]
    response = client.get('/?tableName=Z_SalesOrder&fmsRefId=8&appId=APP000001&stageNo=1&user=dev@example.com')
    assert response.status_code == 200, response.text
    assert '<h1 class="text-xl md:text-2xl font-bold text-gray-900 truncate">Sales Order Application</h1>' in response.text
    assert 'CURRENT_FMS_REF_ID = "8"' in response.text


def test_sql_api_comment_insert_uses_exact_existing_column_headers():
    from app.services import ActivityService
    client = setup_client()
    gateway = app.state.gateway
    gateway.tables[settings.stage_map_table] = [{
        "TableName": "Z_SalesOrder", "FMS Ref Id": "Pick ID", "App ID": "APP000001", "Stage No": "1"
    }]
    ActivityService(gateway, settings).add_new_comment({
        "tableName": "Z_SalesOrder", "fmsRefId": "8", "appId": "APP000001", "stageNo": "1",
        "text": "Test", "mentionType": "Message", "commentId": "CTX-test"
    }, "dev@example.com")
    row = gateway.select(settings.comments_table)[0]
    expected = {
        "Comment ID", "FMS Ref Id", "Task ID", "Stage Name", "App ID", "App Name", "Text",
        "Attachment URL", "Timestamp", "Sender", "Receiver", "Attachment Filename", "Type",
        "Ask ID", "Status", "Notification Message", "Open Thread", "Complete Status", "Unique ID",
        "Thread ID", "Thread Color", "Unique", "Extracted Text", "Timestamp in text"
    }
    # MemorySqlGateway adds RecordID to simulate the SQL identity column.
    assert set(row.keys()) - {"RecordID"} == expected
    assert row["Comment ID"] == "CTX-test"
    assert row["FMS Ref Id"] == "8"
    assert row["App ID"] == "APP000001"
    assert "CommentID" not in row and "TableName" not in row and "FMSRefId" not in row


def test_http_gateway_normalizes_legacy_field_aliases_to_verified_compact_sql_columns(monkeypatch):
    """Compact column names in the verified Test_OperationsDB schema are sent to the PHP API."""
    from app.sql_api import HttpSqlGateway

    calls = []

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"status": "success", "data": []}

    gateway = HttpSqlGateway("https://test.invalid/apiv2.php")
    monkeypatch.setattr(
        gateway.session,
        "post",
        lambda url, **kwargs: (calls.append(kwargs["json"]) or FakeResponse()),
    )

    gateway.insert("dbo.FMS_Comment_Log", {
        "CommentID": "CTX-1",
        "FMSRefId": "8",
        "TaskID": "TASK-1",
        "StageName": "Picking",
        "AppID": "APP000001",
        "AppName": "Sales Order Application",
        "TableName": "Z_SalesOrder",
        "StageNo": "1",
        "Text": "Test comment",
    })
    gateway.select("dbo.FMS_Comment_FMS_Stage_Map", {
        "TableName": "Z_SalesOrder",
        "FMSRefId": "Pick ID",
        "AppID": "APP000001",
        "StageNo": "1",
    })

    assert calls[0]["table"] == "FMS_Comment_Log"
    assert calls[0]["data"] == {
        "CommentID": "CTX-1",
        "FMSRefId": "8",
        "TaskID": "TASK-1",
        "StageName": "Picking",
        "AppID": "APP000001",
        "AppName": "Sales Order Application",
        "Text": "Test comment",
    }
    assert calls[1]["table"] == "FMS_Comment_FMS_Stage_Map"
    assert calls[1]["filters"] == {
        "TableName": "Z_SalesOrder",
        "FMSRefId": "Pick ID",
        "AppID": "APP000001",
        "StageNo": "1",
    }


def test_application_name_falls_back_to_application_master_by_app_id():
    client = setup_client()
    gateway = app.state.gateway
    gateway.tables[settings.stage_map_table] = [{
        "TableName": "Z_SalesOrder", "FMS Ref Id": "Pick ID", "App ID": "APP000001", "Stage No": "1"
    }]
    # The physical FMS row has task data but no display application name.
    gateway.tables["Z_SalesOrder"] = [{"Pick ID": "8", "Task ID": "TASK-8", "Stage Name": "Picking"}]
    gateway.tables[settings.app_master_table] = [{"APP_ID": "APP000001", "APP_NAME": "Pack to Dispatch Details"}]

    response = client.get('/?tableName=Z_SalesOrder&fmsRefId=8&appId=APP000001&stageNo=1')
    assert response.status_code == 200, response.text[:500]
    assert '<h1 class="text-xl md:text-2xl font-bold text-gray-900 truncate">Pack to Dispatch Details</h1>' in response.text
    assert 'Z_SalesOrder</h1>' not in response.text
