"""Exercise the frontend SSE branches without a browser or network access."""

import json
import re
import socket
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "frontend/app/page.tsx"
BUBBLE = ROOT / "frontend/components/ChatBubble.tsx"
SETTINGS = ROOT / "frontend/components/ChatModelSection.tsx"


@pytest.fixture(autouse=True)
def image_tool_enabled(monkeypatch):
    monkeypatch.setenv("FIONA_CHAT_IMAGE_TOOL", "1")


@pytest.fixture(autouse=True)
def block_real_network(monkeypatch):
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex

    def guarded_connect(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            raise AssertionError("Frontend image tool tests forbid real connections")
        return original_connect(sock, address)

    def guarded_connect_ex(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            raise AssertionError("Frontend image tool tests forbid real connections")
        return original_connect_ex(sock, address)

    def guarded_dns(*args, **kwargs):
        raise AssertionError("Frontend image tool tests forbid DNS requests")

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", guarded_connect_ex)
    monkeypatch.setattr(socket, "getaddrinfo", guarded_dns)


def run_js(body, bindings=None):
    """Execute only the extracted, local event/render logic in Node."""
    program = """
const body = process.argv[1];
const bindings = JSON.parse(process.argv[2]);
const result = Function(...Object.keys(bindings), body)(...Object.values(bindings));
process.stdout.write(JSON.stringify(result));
"""
    result = subprocess.run(
        ["node", "-e", program, body, json.dumps(bindings or {})],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def block_after(source, marker):
    start = source.index(marker)
    opening = source.index("{", start)
    depth = 0
    for index in range(opening, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if not depth:
                return source[start : index + 1]
    raise AssertionError(f"Unclosed branch: {marker}")


@pytest.mark.parametrize(
    "content,is_typing,status,visible",
    [
        ("我来画一张。", False, "正在生成图片…", True),
        ("我来画一张。", True, "正在生成图片…", True),
        ("", True, "正在生成图片…", False),
        ("", False, "正在生成图片…", False),
        ("", True, None, True),
        ("普通回复", False, None, True),
        ("[发了一张图片]", False, None, False),
    ],
)
def test_generation_status_keeps_existing_text(content, is_typing, status, visible):
    source = BUBBLE.read_text()
    section = source.split("{/* 文字气泡", 1)[1]
    expression = re.search(r"\{(.*?)\s*&&\s*\(\s*<div", section, re.S).group(1)
    actual = run_js(
        f"return Boolean({expression});",
        {"message": {"content": content, "isTyping": is_typing, "generationStatus": status}},
    )
    assert actual is visible


@pytest.mark.parametrize("speak,spoken", [(False, "已有缓冲"), (True, "已有缓冲描述行"), (None, "已有缓冲描述行")])
def test_silent_text_is_saved_but_never_added_to_speech(speak, spoken):
    branch = block_after(PAGE.read_text(), "if (data.text) {\n            reply += data.text;")
    event = {"text": "描述行"}
    if speak is not None:
        event["speak"] = speak
    result = run_js(
        "let reply = '前导'; let ttsBuf = '已有缓冲'; let flushes = 0; let messages; "
        "const replyId = 'reply'; const flushSentences = () => { flushes++; }; "
        "const setMessages = update => { messages = update([{id: replyId, content: reply}]); }; "
        + branch
        + " return {reply, ttsBuf, flushes, content: messages[0].content};",
        {"data": event},
    )
    assert result["reply"] == result["content"] == "前导描述行"
    assert result["ttsBuf"] == spoken
    assert result["flushes"] == (0 if speak is False else 1)


@pytest.mark.parametrize("source,has_image,retry", [("tool", False, False), (None, False, True), ("panel", False, True), ("tool", True, False)])
def test_only_panel_failures_offer_image_retry(source, has_image, retry):
    page = PAGE.read_text()
    status_branch = block_after(page, 'if (data.status === "generating_image" || data.status === "editing_image")')
    condition = re.search(r"imageGenerationRetry:\s*([^\n]+?)\s*\?\s*\{\s*\n\s*prompt:", page).group(1)
    result = run_js(
        "let generatingImage = false; let editingImage = false; let imageGenerationFromTool = false; "
        "const setMessages = () => {}; const replyId = 'reply'; "
        + status_branch
        + f" return Boolean({condition});",
        {"data": {"status": "generating_image", "source": source}, "generatedImageReceived": has_image},
    )
    assert result is retry


def test_stream_event_declares_optional_speech_and_source_fields():
    event_type = PAGE.read_text().split("interface ChatStreamEvent {", 1)[1].split("\n}", 1)[0]
    assert re.search(r"\bspeak\?\s*:\s*boolean\s*;", event_type)
    assert re.search(r"\bsource\?\s*:\s*string\s*;", event_type)


def test_chat_request_still_carries_panel_image_model():
    page = PAGE.read_text()
    assert "const requestImageModel = imageModel;" in page
    assert "image_model: requestImageModel," in page


def test_byok_settings_disclose_model_decision_platform_billing_and_seedream_privacy():
    settings = SETTINGS.read_text()
    for phrase in (
        "由你的模型决定何时生图",
        "平台的生图判断器",
        "最近 6 条对话",
        "阿里云 DashScope",
        "生图由平台执行并扣草莓",
        "默认使用 Seedream 5.0 Flash",
        "字节跳动火山引擎",
    ):
        assert phrase in settings
    paragraph = (
        "生图：选 Claude 或 DeepSeek（deepseek-v4-pro、deepseek-flash）时，由你的模型决定何时生图并撰写画面描述；"
        "选其他厂商时，在你的消息或上一条回复涉及画图时，平台的生图判断器（阿里云 DashScope 千问 qwen3.8-flash）"
        "会读取最近 6 条对话来决定是否生图、撰写画面描述。生图由平台执行并扣草莓，默认使用 Seedream 5.0 Flash，"
        "画面描述会发送给字节跳动火山引擎（点名千问时发送给阿里云），可能包含对话中出现过的内容。"
    )
    assert f"<p>{paragraph}</p>" in settings
    assert "看图、工具、生图、朗读和画像提取仍由平台处理" not in settings
