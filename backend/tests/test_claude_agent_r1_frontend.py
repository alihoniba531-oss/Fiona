"""Offline source-driven R1 image status and backend-only CI contracts."""

import hashlib
import json
import re
import socket
import subprocess
from pathlib import Path

import pytest

from test_claude_agent_frontend import block_after, render_card


ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "frontend/app/page.tsx"
BUBBLE = ROOT / "frontend/components/ChatBubble.tsx"
FRONTEND_TEST = ROOT / "backend/tests/test_claude_agent_frontend.py"


@pytest.fixture(scope="module", autouse=True)
def block_real_network():
    patch = pytest.MonkeyPatch()

    def forbidden(*args, **kwargs):
        raise AssertionError("R1 frontend tests forbid sockets and DNS")

    for name in ("connect", "connect_ex"):
        patch.setattr(socket.socket, name, forbidden)
    for name in ("create_connection", "getaddrinfo", "gethostbyname", "gethostbyname_ex"):
        patch.setattr(socket, name, forbidden)
    yield
    patch.undo()


def run_image_events(events, request_mode="chat"):
    source = PAGE.read_text()
    start = source.index('          if (data.status === "generating_image"')
    handler = source[start:source.index("          if (data.card", start)]
    done = block_after(source, "if (data.done) {")
    check_start = source.index("      if (generatingImage && !generatedImageReceived")
    checks = source[check_start:source.index("      focusChatInput();", check_start)]
    catch_start = source.index("    } catch (err) {\n      if (!isCurrentStream()) return;", check_start)
    catch = source[catch_start:source.index("    } finally {", catch_start)]
    catch = catch.replace("const failure: Partial<Message>", "const failure")
    label_start = source.index("          const replyModel = parseReplyModel(data.reply_model);")
    labels = source[label_start:source.index("          if (data.tool)", label_start)]
    runner = """
(async () => {
  const events = JSON.parse(process.argv[1]);
  const requestMode = process.argv[2];
  const replyId = 'reply', text = '画一只猫', requestAspectRatio = '1:1';
  const requestImageModel = 'qwen-image-3.0', username = 'offline';
  const currentConversation = {id:'conversation'}, requestReferenceImages = [];
  const API = '', streamDoneRef = {current:false}, states = [];
  let reply = '', ttsBuf = '', clears = 0, cancellations = 0;
  let generatingImage = requestMode !== 'chat', imageGenerationFromTool = false;
  let editingImage = requestMode === 'image_edit', generatedImageReceived = false, responseComplete = false;
  let messages = [{id:replyId, content:'', isTyping:true}, {id:'other', content:'另一条'}];
  const setMessages = update => { messages = update(messages); };
  const clearTtsQueue = () => { clears++; }, flushSentences = () => {};
  const isCurrentStream = () => true;
  const reader = {cancel:async () => { cancellations++; }};
  const generatedImagePath = path => path.startsWith('/uploads/generated_') ? path : null;
  const parseReplyModel = value => value && typeof value.label === 'string' ? value : null;
  try {
    for (const data of events) {
""" + labels + handler + "\n" + done.replace("            break;", "") + """
      states.push(JSON.parse(JSON.stringify({generatingImage, editingImage, messages})));
    }
""" + checks + catch + """
  }
  process.stdout.write(JSON.stringify({reply, ttsBuf, clears, cancellations, messages, states,
    generatingImage, editingImage, generatedImageReceived, responseComplete}));
})().catch(error => { process.stderr.write(error.stack); process.exitCode = 1; });
"""
    result = subprocess.run(["node", "-e", runner, json.dumps(events), request_mode],
                            capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def test_tool_image_failure_resets_status_and_keeps_complete_reply_and_speech():
    events = [
        {"reply_model": {"source": "byok", "label": "Claude · claude-sonnet-5-5"}},
        {"text": "我来画。"},
        {"status": "generating_image", "source": "tool"},
        {"status": "image_failed", "source": "tool"},
        {"text": "这次没有画成，我们换个描述。"},
        {"done": True},
    ]
    actual = run_image_events(events)
    assert actual["reply"] == actual["messages"][0]["content"] == "我来画。这次没有画成，我们换个描述。"
    assert actual["ttsBuf"] == actual["reply"] and actual["clears"] == 0
    assert actual["states"][2]["messages"][0]["generationStatus"] == "正在生成图片…"
    assert actual["states"][3]["messages"][0].get("generationStatus") is None
    assert not actual["states"][3]["generatingImage"] and not actual["states"][3]["editingImage"]
    assert actual["responseComplete"] and actual["cancellations"] == 0
    assert actual["messages"][0]["replyModelLabel"] == "Claude · claude-sonnet-5-5"
    assert actual["messages"][1] == {"id": "other", "content": "另一条"}


def test_tool_done_without_image_still_finishes_normal_reply():
    actual = run_image_events([{"status": "generating_image", "source": "tool"},
                               {"text": "图片没画成，我可以继续帮你。"}, {"done": True}])
    assert actual["messages"][0]["content"] == actual["reply"] == "图片没画成，我可以继续帮你。"
    assert actual["clears"] == 0 and actual["cancellations"] == 0


@pytest.mark.parametrize("mode,status,error", [
    ("image", "generating_image", "图片生成未完成，请重试。"),
    ("image_edit", "editing_image", "图片修改未完成，请重试。"),
])
def test_panel_missing_image_still_errors_and_offers_retry(mode, status, error):
    actual = run_image_events([{"status": status, "source": "panel"}, {"done": True}], mode)
    message = actual["messages"][0]
    assert message["content"] == "错误：" + error
    assert message["imageGenerationRetry"]["prompt"] == "画一只猫"
    assert message["imageGenerationRetry"]["imageModel"] == "qwen-image-3.0"
    assert actual["clears"] == 1 and message.get("generationStatus") is None


@pytest.mark.parametrize("source,mode,retry", [("tool", "chat", False), ("panel", "image", True)])
def test_legacy_error_events_keep_queue_cancellation_and_retry_rules(source, mode, retry):
    actual = run_image_events([{"text": "已有文字"}, {"status": "generating_image", "source": source},
                               {"error": "审核失败"}], mode)
    message = actual["messages"][0]
    assert message["content"] == "已有文字\n\n错误：审核失败"
    assert bool(message.get("imageGenerationRetry")) is retry
    assert actual["clears"] == actual["cancellations"] == 1 and actual["ttsBuf"] == ""


def test_status_type_explicitly_accepts_image_failed():
    event_type = PAGE.read_text().split("interface ChatStreamEvent {", 1)[1].split("\n}", 1)[0]
    assert re.search(r'status\?:[^;]*"image_failed"', event_type)


def test_existing_error_flow_remains_byte_for_byte_unchanged():
    source = PAGE.read_text()
    start = source.index("    } catch (err) {\n      if (!isCurrentStream()) return;",
                         source.index("    let generatingImage ="))
    end = source.index("    } finally {", start)
    assert hashlib.sha256(source[start:end].encode()).hexdigest() == (
        "ea57ba31491623f9fe06288a0d83553db7c8ca6fa925b0a4e1de2b295e7a70cf"
    )


@pytest.mark.parametrize("missing", ["typescript", "react", "react-dom/server"])
def test_render_helper_skips_when_any_frontend_package_is_missing(monkeypatch, missing):
    calls = []

    def absent(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, json.dumps([missing]), "")

    monkeypatch.setattr(subprocess, "run", absent)
    with pytest.raises(pytest.skip.Exception, match=re.escape(missing)):
        render_card({"source": "联网搜索", "subtype": "web_sources", "points": [], "sources": []})
    assert len(calls) == 1 and "require.resolve" in calls[0][2]


def test_web_sources_branch_has_package_free_source_contracts():
    source = BUBBLE.read_text()
    assert 'cardData.subtype === "web_sources" ? "联网搜索"' in source
    assert '{cardData.subtype !== "web_sources" && <ul' in source
    assert 'cardData.subtype !== "web_sources" && safeSources.length === 0 && cardData.url' in source
    assert 'cardData.subtype !== "web_sources" && <div className="mb-1.5' in source
    assert "safeSources.map" in source and "openExternal(url)" in source


def test_append_branch_never_assigns_legacy_card_text_or_speech_fields():
    branch = block_after(PAGE.read_text(), "if (data.card && data.append === true)")
    assert "cards: [...(m.cards ?? []), card]" in branch
    for forbidden in ("cardData:", "content:", "pendingTtsText:", "clearTtsQueue", "ttsBuf =", "reply ="):
        assert forbidden not in branch
