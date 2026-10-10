"""Run the Claude agent's card handling and shared rendering entirely offline."""

import hashlib
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
DISCLOSURE = (
    "选 Claude 时，Claude 可以直接查看你本轮发送的图片，自行调用天气、旅行、路线、热榜和生图工具"
    "（工具由平台执行，天气只查询你亲口说过的城市，使用工具的回合按次扣草莓），并可使用 Anthropic 的联网搜索和网页读取"
    "（由 Anthropic 执行，按其价格计入你的 API 额度，搜索约每 1000 次 10 美元）。图片和工具结果会发送给 Anthropic。"
)


@pytest.fixture(scope="module", autouse=True)
def block_real_network():
    patch = pytest.MonkeyPatch()

    def forbidden(*args, **kwargs):
        raise AssertionError("Claude agent frontend tests forbid sockets and DNS")

    for name in ("connect", "connect_ex"):
        patch.setattr(socket.socket, name, forbidden)
    for name in ("create_connection", "getaddrinfo", "gethostbyname", "gethostbyname_ex"):
        patch.setattr(socket, name, forbidden)
    yield
    patch.undo()


def block_after(source, marker):
    start = source.index(marker)
    opening = source.index("{", start)
    depth = 0
    for index in range(opening, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise AssertionError(f"Unclosed branch: {marker}")


def run_cards(events):
    source = PAGE.read_text()
    start = source.index("          if (data.card")
    branch = source[start : source.index("          if (data.done)", start)]
    branch = branch.replace("const card: CardData", "const card")
    body = (
        "let reply = '已有回复'; let ttsBuf = '待朗读'; let clears = 0;"
        "const replyId = 'reply'; const clearTtsQueue = () => { clears++; };"
        "const weatherForecastCondition = f => f.dayWeather === f.nightWeather"
        " ? f.dayWeather : [f.dayWeather, f.nightWeather].filter(Boolean).join('转');"
        "let messages = [{id: replyId, content: reply, cardData: {source: '旧卡', points: ['旧要点']},"
        "pendingTtsText: '旧朗读'}, {id: 'other', content: '另一条'}];"
        "const setMessages = update => { messages = update(messages); };"
        "for (const data of JSON.parse(process.argv[1])) {"
        + branch
        + "} process.stdout.write(JSON.stringify({reply, ttsBuf, clears, messages}));"
    )
    result = subprocess.run(
        ["node", "-e", body, json.dumps(events)], capture_output=True, text=True, check=True
    )
    return json.loads(result.stdout)


def test_append_cards_preserve_text_legacy_card_and_speech_queue():
    cards = [
        {"source": "天气", "subtype": "weather", "points": ["晴天"]},
        {"source": "联网搜索", "subtype": "web_sources", "points": [], "sources": []},
    ]
    result = run_cards([{"card": card, "append": True} for card in cards])
    message = result["messages"][0]
    assert message["content"] == result["reply"] == "已有回复"
    assert message["cards"] == cards
    assert message["cardData"] == {"source": "旧卡", "points": ["旧要点"]}
    assert message["pendingTtsText"] == "旧朗读"
    assert result["ttsBuf"] == "待朗读" and result["clears"] == 0
    assert result["messages"][1] == {"id": "other", "content": "另一条"}


@pytest.mark.parametrize("append", [None, False, "true", 1])
@pytest.mark.parametrize(
    "card,tip",
    [
        ({"source": "网页", "points": ["要点"]}, "搜到了，详情在下面的卡片里"),
        ({"source": "旅行", "subtype": "travel_plan", "points": ["行程"]}, ""),
        ({"source": "网页", "points": ["失败原因"], "error": True}, "失败原因"),
        ({"source": "网页", "points": [], "error": True}, "这次没查到可靠的结果"),
        ({"source": "天气", "subtype": "weather", "points": [], "weather": {
            "location": "上海", "forecast": [{"dayWeather": "小雨", "nightWeather": "晴",
            "low": "18", "high": "25"}]}}, "上海今天小雨转晴，18~25°。记得带伞。"),
    ],
)
def test_non_append_cards_keep_previous_behavior(append, card, tip):
    event = {"card": card}
    if append is not None:
        event["append"] = append
    result = run_cards([event])
    message = result["messages"][0]
    assert result["reply"] == message["content"] == tip
    assert message["cardData"] == card
    assert message.get("cards") is None
    assert message.get("pendingTtsText") == (tip or None)
    assert result["ttsBuf"] == "" and result["clears"] == 1


def test_non_append_processing_body_is_unchanged():
    source = PAGE.read_text()
    start = source.index("            // 旅行规划卡：")
    end = source.index("          if (data.done)", start)
    assert hashlib.sha256(source[start:end].encode()).hexdigest() == (
        "e0718e4916e73ad0b697656069e77abaff73b6473c6a5dbe0af97c892c42b0ce"
    )


def test_card_types_and_order_reuse_shared_renderer_after_text():
    page = PAGE.read_text().split("interface ChatStreamEvent {", 1)[1].split("\n}", 1)[0]
    bubble = BUBBLE.read_text()
    assert re.search(r"\bappend\?\s*:\s*boolean\s*;", page)
    assert re.search(r"\bcards\?\s*:\s*CardData\[\]\s*;", bubble)
    assert "<ChatCard card={message.cardData}" in bubble
    assert "message.cards?.map" in bubble
    assert "<ChatCard key={index} card={card}" in bubble
    assert bubble.index("{/* 文字气泡") < bubble.index("message.cards?.map")


def require_rendering_dependencies():
    probe = """
const packages = ['typescript', 'react', 'react-dom/server'];
const missing = packages.filter(name => {
  try { require.resolve(name, {paths: [process.argv[1]]}); return false; }
  catch { return true; }
});
process.stdout.write(JSON.stringify(missing));
"""
    try:
        result = subprocess.run(
            ["node", "-e", probe, str(ROOT / "frontend")],
            capture_output=True, text=True, check=True,
        )
    except FileNotFoundError:
        pytest.skip("Frontend SSR requires Node.js; source-only card contracts still run")
    missing = json.loads(result.stdout)
    if missing:
        pytest.skip("Frontend SSR dependencies unavailable: " + ", ".join(missing))


def render_card(card):
    require_rendering_dependencies()
    bubble = BUBBLE.read_text()
    helpers = "\n".join(block_after(bubble, marker) for marker in (
        "function weatherDayLabel(", "function weatherCondition(",
        "function weatherTemperature(", "function ChatCard(",
    ))
    runner = """
const ts = require('typescript');
const React = require('react');
const {renderToStaticMarkup} = require('react-dom/server');
const cn = (...values) => values.filter(Boolean).join(' ');
const Globe = () => null, ArrowUpRight = () => null;
const openExternal = () => {};
const toSafeExternalUrl = value => {
  try { const url = new URL(value); return ['https:', 'http:'].includes(url.protocol) && !url.username && !url.password ? url.href : null; }
  catch { return null; }
};
const compiled = ts.transpileModule(process.argv[1], {compilerOptions: {jsx: ts.JsxEmit.React}}).outputText;
const ChatCard = Function('React', 'cn', 'Globe', 'ArrowUpRight', 'openExternal', 'toSafeExternalUrl', compiled + '\\nreturn ChatCard;')
  (React, cn, Globe, ArrowUpRight, openExternal, toSafeExternalUrl);
process.stdout.write(renderToStaticMarkup(React.createElement(ChatCard, {card: JSON.parse(process.argv[2])})));
"""
    result = subprocess.run(
        ["node", "-e", runner, helpers, json.dumps(card)],
        cwd=ROOT / "frontend", capture_output=True, text=True, check=True,
    )
    return result.stdout


@pytest.mark.parametrize("points", [[], ["不应展示的要点"]])
def test_web_sources_card_renders_only_valid_sources_with_fixed_title(points):
    html = render_card({"source": "应忽略的标题", "subtype": "web_sources",
                        "points": points, "url": "https://ignored.example/page",
                        "sources": [{"title": "官方消息", "url": "https://example.com/news", "site_name": "官方站点"},
                                    {"title": "危险来源", "url": "javascript:alert(1)"}]})
    assert "联网搜索" in html and "官方消息" in html and "官方站点" in html
    assert "打开来源：官方消息" in html
    assert "应忽略的标题" not in html and "不应展示的要点" not in html
    assert "危险来源" not in html and "ignored.example" not in html


def test_shared_renderer_keeps_weather_and_generic_cards():
    weather = render_card({"source": "天气", "subtype": "weather", "points": [], "weather": {
        "location": "上海", "forecast": [{"date": "2026-10-10", "day": "周六",
        "dayWeather": "晴", "nightWeather": "晴", "low": "18", "high": "25", "dayWind": "东风2级", "nightWind": "东风2级"}]}})
    generic = render_card({"source": "旅行规划", "points": ["游览博物馆"],
                           "sources": [{"title": "场馆信息", "url": "https://example.com/museum"}]})
    assert all(phrase in weather for phrase in ("天气", "上海", "18°~25°", "晴", "东风2级"))
    assert all(phrase in generic for phrase in ("旅行规划", "游览博物馆", "场馆信息"))


def test_settings_disclosure_is_exact_and_after_image_paragraph():
    source = SETTINGS.read_text()
    assert f"<p>{DISCLOSURE}</p>" in source
    assert source.index("<p>生图：") < source.index(f"<p>{DISCLOSURE}</p>")
