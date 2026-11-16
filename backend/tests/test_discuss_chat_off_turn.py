"""讨论群应为关时，Claude 一整轮与四个讨论群变量都不存在时逐字节一致。

规格 6.1 第 4 条、v1.2「6 测试要求（再追加）」第 15 条，复核
``04-review.md`` 第 4 节必须修复 1。用例在 harness 上跑真实的一整轮
``stream_claude_agent``：第一轮模型乱调一个本轮没有下发的讨论群工具，
第二轮正常作答；对照请求、SSE 事件与落库调用。全部离线，不访问网络。
"""
from datetime import datetime
import json

import pytest

from test_claude_agent_runtime import FakeStream, call, harness, message, run


USER = "agent-user"
OUTSIDER = "discuss-outsider"
DISCUSS_ENV = (
    "FIONA_DISCUSS",
    "FIONA_DISCUSS_USERS",
    "FIONA_DISCUSS_CHAT",
    "FIONA_DISCUSS_CHAT_CARDS",
)
# 同一组合直接断言常量对象时，小说与写歌都必须关着。
OTHER_ENV = (
    "FIONA_NOVEL_CHAT",
    "FIONA_NOVEL",
    "FIONA_NOVEL_USERS",
    "FIONA_SONG_AGENT",
    "FIONA_SONG_USERS",
)
# 合法任务卡参数；讨论群关着时 draft_discuss_task 不在本轮工具里。
TASK_ARGS = {
    "request": "调研东南亚短剧市场，列出主要平台与题材偏好",
    "materials": "已有三份平台报告，重点看越南和泰国",
    "max_rounds": 4,
    "budget_strawberries": 3000,
}
FINAL_TEXT = "这是一轮正常文字回复。"

OFF_COMBOS = [
    pytest.param(
        {
            "FIONA_DISCUSS": "1",
            "FIONA_DISCUSS_USERS": USER,
            "FIONA_DISCUSS_CHAT": "0",
            "FIONA_DISCUSS_CHAT_CARDS": "1",
        },
        id="chat-0-cards-1-whitelisted",
    ),
    pytest.param(
        {
            "FIONA_DISCUSS": "1",
            "FIONA_DISCUSS_USERS": OUTSIDER,
            "FIONA_DISCUSS_CHAT": "1",
            "FIONA_DISCUSS_CHAT_CARDS": "1",
        },
        id="outside-whitelist",
    ),
    pytest.param(
        {
            "FIONA_DISCUSS": "0",
            "FIONA_DISCUSS_USERS": USER,
            "FIONA_DISCUSS_CHAT": "1",
            "FIONA_DISCUSS_CHAT_CARDS": "1",
        },
        id="discuss-0",
    ),
]


def _clear_env(monkeypatch):
    for name in DISCUSS_ENV + OTHER_ENV:
        monkeypatch.delenv(name, raising=False)


def _reset_turn(h):
    """按用例要求清空上一轮的请求、事件与落库记录。"""
    import services.chat_service as chat

    h.state = chat.ChatState(trace={}, sys_prompt_final="persona")
    h.streams.clear()
    h.requests.clear()
    h.saves.clear()
    h.followups.clear()
    h.clears.clear()


def _run_round(h):
    """装两条流：先乱调没下发的任务卡工具，再正常作答。"""
    h.streams.extend([
        FakeStream(message("tool_use", content=[call("draft_discuss_task", TASK_ARGS)])),
        FakeStream(message(text=FINAL_TEXT), FINAL_TEXT),
    ])
    return run(h)


def _request_json(h):
    assert len(h.requests) >= 1, "这一轮没有抓到发给模型的请求"
    captured = []
    for messages, kwargs in h.requests:
        params = {
            key: value
            for key, value in kwargs.items()
            if key not in ("deadline_seconds", "control")
        }
        captured.append({"messages": messages, "params": params})
    return json.dumps(captured, ensure_ascii=False, sort_keys=True, default=str)


def _jsonable(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _fresh_state():
    import services.chat_service as chat

    return chat.ChatState(trace={})


@pytest.mark.parametrize("combo", OFF_COMBOS)
def test_discuss_off_turn_matches_all_variables_absent(harness, monkeypatch, combo):
    import services.claude_agent as agent

    _clear_env(monkeypatch)
    # 请求里的当前北京时间取固定值，避免对照两轮跨分钟造成假失败。
    monkeypatch.setattr(agent, "beijing_now", lambda: datetime(2026, 11, 16, 9, 30))
    h = harness

    # 对照轮：FIONA_DISCUSS / USERS / CHAT / CHAT_CARDS 四个都不存在。
    _reset_turn(h)
    baseline_events = _run_round(h)
    baseline = {
        "requests": _request_json(h),
        "events": _jsonable(baseline_events),
        "saves": _jsonable(h.saves),
    }

    for name, value in combo.items():
        monkeypatch.setenv(name, value)

    _reset_turn(h)
    combo_events = _run_round(h)
    actual = {
        "requests": _request_json(h),
        "events": _jsonable(combo_events),
        "saves": _jsonable(h.saves),
    }

    assert actual["requests"] == baseline["requests"], "请求与开关不存在时不同"
    assert actual["events"] == baseline["events"], "SSE 事件与开关不存在时不同"
    assert actual["saves"] == baseline["saves"], "落库调用与开关不存在时不同"

    # 同一组合：小说、写歌都关时，工具表必须是常量对象本身。
    assert agent.client_tools_for_turn(h.ctx, _fresh_state()) is agent.CLAUDE_CLIENT_TOOLS
