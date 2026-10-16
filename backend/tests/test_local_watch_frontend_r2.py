"""R2 frontend regressions using local Node alone, without npm or git history."""

import json
import re
import shutil
import socket
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
LOGIC = ROOT / "frontend/lib/localWatch.ts"
SETTINGS = ROOT / "frontend/components/LocalWatchSection.tsx"


@pytest.fixture(scope="module", autouse=True)
def block_real_network():
    patch = pytest.MonkeyPatch()

    def forbidden(*args, **kwargs):
        raise AssertionError("R2 frontend tests forbid sockets and DNS")

    for name in ("connect", "connect_ex", "sendto", "bind", "listen"):
        patch.setattr(socket.socket, name, forbidden)
    for name in ("create_connection", "getaddrinfo", "gethostbyname", "gethostbyname_ex", "gethostbyaddr"):
        patch.setattr(socket, name, forbidden)
    yield
    patch.undo()


def function_body(name):
    source = LOGIC.read_text(encoding="utf-8")
    start = source.index("export function " + name)
    opening = source.index("{", start)
    depth = 1
    end = opening + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[opening + 1:end - 1]


def run_node(script):
    node = shutil.which("node")
    if not node:
        pytest.skip("node is unavailable; no npm packages are required")
    runner = "\n".join(
        "function " + name + "(" + args + ") {" + function_body(name) + "}"
        for name, args in (
            ("localWatchMessage", "alert"),
            ("appendLocalWatchMessages", "messages, alerts, conversationId, busy"),
            ("localWatchRulePayload", "draft"),
            ("localWatchDraft", "rule"),
        )
    )
    result = subprocess.run([node, "-e", runner + "\n" + script], capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


@pytest.mark.parametrize("current_rule_name", ["刚改的新名字", "已删除规则"])
def test_inserted_message_uses_exact_stored_content_after_rule_rename_or_delete(current_rule_name):
    content = "【本机提醒 · 微信】张三：今晚开会\n请准时（规则：盯老板）"
    alert = {
        "id": 7, "message_id": 42, "conversation_id": "current",
        "rule_name": current_rule_name, "summary": "已改变的摘要",
        "content": content, "created_at": "2026-10-11 12:00:00",
    }
    actual = run_node("const alert=" + json.dumps(alert, ensure_ascii=False) + ";\n"
                      "process.stdout.write(JSON.stringify(localWatchMessage(alert)));")
    assert actual["content"] == content
    assert actual["role"] == "assistant" and actual["dbId"] == 42
    assert actual["id"] == "db-42" and actual["timestamp"].endswith("Z")


def test_current_chat_retains_exact_content_deduplication_and_busy_buffering():
    content = "【本机提醒 · Safari】下载完成（规则：下载）"
    alert = {"id": 7, "message_id": 42, "conversation_id": "current", "rule_name": "后来改名",
             "summary": "忽略这个旧字段", "content": content, "created_at": "2026-10-11T12:00:00Z"}
    script = "const alert=" + json.dumps(alert, ensure_ascii=False) + ";\n" + """
        const original=[{id:'db-2',dbId:2,content:'已有消息',role:'assistant'}];
        const busy=appendLocalWatchMessages(original,[alert],'current',true);
        const resumed=appendLocalWatchMessages(busy,[alert],'current',false);
        const duplicate=appendLocalWatchMessages(resumed,[alert],'current',false);
        const other=appendLocalWatchMessages(original,[alert],'other',false);
        process.stdout.write(JSON.stringify({busy,resumed,duplicate,other}));
    """
    actual = run_node(script)
    assert len(actual["busy"]) == len(actual["other"]) == 1
    assert len(actual["resumed"]) == len(actual["duplicate"]) == 2
    assert actual["resumed"][1]["content"] == actual["duplicate"][1]["content"] == content


def test_alert_contract_requires_content_and_has_no_reconstructed_fallback():
    source = LOGIC.read_text(encoding="utf-8")
    interface = source.split("export interface LocalWatchAlert {", 1)[1].split("}", 1)[0]
    assert re.search(r"\bcontent\s*:\s*string\b", interface)
    body = function_body("localWatchMessage")
    assert "content: alert.content" in body
    assert "alert.rule_name" not in body and "alert.summary" not in body


@pytest.mark.parametrize("app_name,title", [
    ("应" * 61, "题" * 80),
    ("😀" * 80, "🚀" * 80),
    ("微信😀" * 30, "群聊🚀" * 30),
    ("A" * 60, "B" * 60),
    ("微信", "工作群"),
    ("微信", ""),
])
def test_window_click_prefills_both_matches_at_most_60_unicode_characters(app_name, title):
    source = SETTINGS.read_text(encoding="utf-8")
    # Execute the real JSX window-click draft expression, without React, Next,
    # TypeScript compilation or node_modules. This also tests the wired handler.
    start = source.index("editRule(); setDraft(") + len("editRule(); setDraft(")
    depth = 1
    end = start
    while depth:
        depth += (source[end] == "(") - (source[end] == ")")
        end += 1
    expression = source[start:end - 1]
    window = {"app_name": app_name, "title": title, "bundle_id": "org.example.app"}
    script = "const window=" + json.dumps(window, ensure_ascii=False) + ";\n"
    script += "const emptyRule=()=>localWatchDraft(); const draft=" + expression + ";\n"
    script += "process.stdout.write(JSON.stringify({draft,payload:localWatchRulePayload(draft)}));"
    actual = run_node(script)
    assert actual["draft"]["app_match"] == app_name[:60]
    assert actual["draft"]["title_match"] == title[:60]
    assert actual["payload"]["app_match"] == app_name[:60]
    assert actual["payload"]["title_match"] == title[:60]
    assert len(actual["payload"]["app_match"]) <= 60
    assert len(actual["payload"]["title_match"]) <= 60
