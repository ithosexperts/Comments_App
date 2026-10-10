from datetime import datetime
from zoneinfo import ZoneInfo

from app.config import settings
from app.services import ActivityService, extract_message_only, timestamp_text
from app.sql_api import MemorySqlGateway, quote_identifier

def make_service(seed=None):
    return ActivityService(MemorySqlGateway(seed or {}), settings)

def test_extract_message_only_mentions():
    assert extract_message_only("@Alex please review this") == "review this"
    assert extract_message_only("@Alex") == ""
    assert extract_message_only("plain message") == "plain message"

def test_timestamp_text_uses_minute_plus_task_id():
    stamp = datetime(2026, 9, 10, 12, 36, 34, tzinfo=ZoneInfo("Asia/Kolkata")).replace(tzinfo=None)
    assert timestamp_text("123", stamp) == "202609101236123"

def test_add_comment_populates_requested_fields_and_thread():
    service = make_service()
    result = service.add_new_comment({
        "commentId": "C-1", "taskId": "123", "stageName": "Packing", "fmsName": "Hose FMS",
        "text": "@Alex please check", "sender": "sender@example.com", "receiver": "alex@example.com",
        "mentionType": "Ask", "fmsRefId": "FMS-9", "appId": "APP-2", "stageNo": "4"
    })
    assert result["success"] is True
    assert result["askId"] == "Ask1001"
    assert result["threadId"] == "T1"
    row = service.db.select(settings.comments_table)[0]
    assert row["FMS Ref Id"] == "FMS-9"
    assert row["App ID"] == "APP-2"
    assert row["App Name"] == "Hose FMS"
    assert row["Extracted Text"] == "check"
    assert row["Timestamp in text"].endswith("123")
    assert row["Unique ID"]
    assert row["Thread Color"].startswith("#")

def test_reply_inherits_thread_and_parent_ask_id():
    service = make_service()
    service.add_new_comment({"commentId":"C-2", "taskId":"2", "text":"Need review", "mentionType":"Ask", "receiver":"b@example.com"})
    result = service.add_new_comment({"commentId":"C-2", "taskId":"2", "text":"Done", "mentionType":"Reply", "parentAskId":"Ask1001", "threadId":"T1", "threadColor":"#FFB3BA"})
    rows = service.db.select(settings.comments_table)
    assert result["askId"] == "Ask1001"
    assert rows[1]["Thread ID"] == "T1"
    assert rows[1]["Thread Color"] == "#FFB3BA"

def test_mark_read_requires_receiver_and_reply_for_ask():
    service = make_service()
    service.add_new_comment({"commentId":"C-3", "taskId":"3", "text":"Question", "mentionType":"Ask", "receiver":"reader@example.com"})
    service.add_new_comment({"commentId":"C-3", "taskId":"3", "text":"Reply", "mentionType":"Reply", "parentAskId":"Ask1001", "receiver":"reader@example.com", "sender":"owner@example.com", "threadId":"T1"})
    service.mark_comments_as_read("C-3", "reader@example.com")
    rows = service.db.select(settings.comments_table)
    assert rows[0]["Status"] == "Read"
    assert rows[1]["Status"] == "Read"

def test_stage_mapping_is_used_when_keys_are_provided():
    service = make_service({settings.stage_map_table: [
        {"FMS Ref Id":"FMS-A", "App ID":"APP-A", "Stage No":"3"}
    ]})
    result = service.add_new_comment({"commentId":"C-4", "taskId":"4", "text":"Mapped", "fmsRefId":"FMS-A", "appId":"APP-A", "stageNo":"3"})
    row = service.db.select(settings.comments_table)[0]
    assert result["success"] is True
    assert row["FMS Ref Id"] == "FMS-A"
    assert row["App ID"] == "APP-A"

def test_sql_identifier_quoting_and_rejection():
    assert quote_identifier("dbo.FMS_Comment_Log") == "[dbo].[FMS_Comment_Log]"
    try:
        quote_identifier("Users; DROP TABLE users")
    except ValueError:
        pass
    else:
        raise AssertionError("Unsafe identifier should fail")
