"""R3 capture status contracts without git history, npm packages or networking."""

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
LIMITATION = "屏幕锁定或显示器休眠时 macOS 不允许截取窗口，期间无法监控"


@pytest.fixture(scope="module", autouse=True)
def block_real_network():
    patch = pytest.MonkeyPatch()

    def forbidden(*args, **kwargs):
        raise AssertionError("R3 frontend tests forbid sockets and DNS")

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


def run_node(script, functions):
    node = shutil.which("node")
    if not node:
        pytest.skip("node is unavailable; no npm packages are required")
    runner = "\n".join(
        "function " + name + "(" + arguments + ") {" + function_body(name) + "}"
        for name, arguments in functions
    )
    result = subprocess.run([node, "-e", runner + "\n" + script], capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def test_rule_response_has_capture_metadata_but_writable_draft_excludes_it():
    source = LOGIC.read_text(encoding="utf-8")
    capture = source.split("export interface LocalWatchCapture {", 1)[1].split("}", 1)[0]
    assert re.search(r"\bok\s*:\s*boolean\b", capture)
    assert re.search(r"\bmessage\s*:\s*string\b", capture)
    assert re.search(r"\bsince\?\s*:\s*string\b", capture)
    rule = source.split("export interface LocalWatchRule {", 1)[1].split("}", 1)[0]
    assert re.search(r"\bcapture\?\s*:\s*LocalWatchCapture\b", rule)
    assert 'Omit<LocalWatchRule, "id" | "capture">' in source


@pytest.mark.parametrize("capture,expected", [
    ({"ok": True, "message": "后端正常状态", "since": "2026-10-11T12:00:00Z"}, "监控中"),
    ({"ok": False, "message": "截图失败：屏幕可能已锁定或显示器已休眠，也可能缺少屏幕录制权限"},
     "截图失败：屏幕可能已锁定或显示器已休眠，也可能缺少屏幕录制权限"),
    ({"ok": False, "message": "没有找到匹配的窗口（窗口可能已关闭或最小化）"},
     "没有找到匹配的窗口（窗口可能已关闭或最小化）"),
    ({"ok": False, "message": "截图失败，请查看监控程序日志"}, "截图失败，请查看监控程序日志"),
    ({"ok": False, "message": "监控程序未在运行"}, "监控程序未在运行"),
    (None, "监控程序未在运行"),
])
def test_status_text_displays_backend_message_and_supports_old_rule_responses(capture, expected):
    rule = {"id": 7}
    if capture is not None:
        rule["capture"] = capture
    actual = run_node("const rule=" + json.dumps(rule, ensure_ascii=False) + ";\n"
                      "process.stdout.write(JSON.stringify(localWatchCaptureMessage(rule)));",
                      [("localWatchCaptureMessage", "rule")])
    assert actual == expected


@pytest.mark.parametrize("capture", [
    {"ok": True, "message": "监控中", "since": "2026-10-11T12:00:00Z"},
    {"ok": False, "message": "监控程序未在运行"},
])
def test_editing_rule_never_sends_capture_metadata_to_create_or_patch(capture):
    rule = {
        "id": 7, "name": " 工作 ", "app_match": " 微信 ", "title_match": "",
        "kind": "keyword", "params": {"keywords": ["@我"]}, "interval_seconds": 3,
        "cooldown_seconds": 60, "enabled": True, "conversation_id": None,
        "capture": capture,
    }
    script = "const rule=" + json.dumps(rule, ensure_ascii=False) + ";\n" + """
        const draft=localWatchDraft(rule);
        const payload=localWatchRulePayload({...draft,capture:rule.capture,id:7});
        process.stdout.write(JSON.stringify({draft,payload}));
    """
    actual = run_node(script, [("localWatchRulePayload", "draft"), ("localWatchDraft", "rule")])
    fields = {"name", "app_match", "title_match", "kind", "params", "interval_seconds",
              "cooldown_seconds", "enabled", "conversation_id"}
    assert set(actual["draft"]) == set(actual["payload"]) == fields
    assert actual["payload"]["name"] == "工作" and actual["payload"]["app_match"] == "微信"


def test_each_rule_renders_readable_status_and_highlights_failures():
    source = SETTINGS.read_text(encoding="utf-8")
    row = source.split("{rules.map(rule =>", 1)[1].split("</li>)}</ul>", 1)[0]
    assert "{localWatchCaptureMessage(rule)}" in row
    status = row.split('{localWatchCaptureMessage(rule)}', 1)[0].rsplit("<p", 1)[1]
    assert 'role="status"' in status
    assert 'rule.capture?.ok || rule.capture?.neutral ? noteClass' in status
    assert "text-[color:var(--seal)]" in status
    assert "break-all" in status


def test_settings_explains_locked_screen_limitation_and_security_tradeoff():
    source = SETTINGS.read_text(encoding="utf-8")
    description = source.split("本机监控</h2>", 1)[1].split("{loading &&", 1)[0]
    assert LIMITATION in description
    assert "系统设置 → 锁定屏幕" in description
    assert "延长自动锁定时间" in description
    assert "权衡安全" in description


def test_visible_status_refresh_is_periodic_and_cleaned_up_for_account_changes():
    source = SETTINGS.read_text(encoding="utf-8")
    assert "window.setInterval(onVisible, 10_000)" in source
    assert 'document.visibilityState === "visible"' in source
    assert "window.clearInterval(timer)" in source
    assert "if (!request.isCurrent()) return;" in source
    assert "setDevices([]); setRules([]); setWindows([]);" in source
    assert 'setToken(""); setFormOpen(false); setEditingId(null);' in source
