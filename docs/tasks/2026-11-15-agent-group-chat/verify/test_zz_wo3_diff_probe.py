"""差分探针：同一份文件放进基线（eb9ec55）与新代码的 backend/tests/ 各跑一遍，
把「开关关着时」发给模型的请求、事件、落库调用记成 JSON，再逐字节比较两份输出。
只引用基线里也有的符号。输出路径由环境变量 WO3_PROBE_OUT 指定。
"""
import asyncio
import json
import os
from pathlib import Path

import pytest

from test_claude_agent_runtime import FakeStream, call, harness, message, run  # noqa: F401

OUT = Path(os.environ["WO3_PROBE_OUT"])
USER = "agent-user"

BASES = {
    "plain": {},
    "novel": {"FIONA_NOVEL": "1", "FIONA_NOVEL_USERS": USER, "FIONA_NOVEL_CHAT": "1",
              "FIONA_NOVEL_CHAT_CREATE": "1", "FIONA_NOVEL_CHAT_FEEDBACK": "1"},
    "song": {"FIONA_SONG_AGENT": "1", "FIONA_SONG_USERS": USER},
}
BASES["novel_song"] = {**BASES["novel"], **BASES["song"]}

# 这些组合下「聊天看讨论群」都应该是关的
OFF_ENVS = {
    "E0_none": {},
    "E1_discuss_on_chat_unset": {"FIONA_DISCUSS": "1", "FIONA_DISCUSS_USERS": USER},
    "E2_chat0_cards1": {"FIONA_DISCUSS": "1", "FIONA_DISCUSS_USERS": USER,
                        "FIONA_DISCUSS_CHAT": "0", "FIONA_DISCUSS_CHAT_CARDS": "1"},
    "E3_not_whitelisted": {"FIONA_DISCUSS": "1", "FIONA_DISCUSS_USERS": "someone-else",
                           "FIONA_DISCUSS_CHAT": "1", "FIONA_DISCUSS_CHAT_CARDS": "1"},
    "E4_discuss_off": {"FIONA_DISCUSS_USERS": USER, "FIONA_DISCUSS_CHAT": "1", "FIONA_DISCUSS_CHAT_CARDS": "1"},
    "E5_truthy_words": {"FIONA_DISCUSS": "1", "FIONA_DISCUSS_USERS": USER,
                        "FIONA_DISCUSS_CHAT": "true", "FIONA_DISCUSS_CHAT_CARDS": "yes"},
    "E6_whitelist_prefix": {"FIONA_DISCUSS": "1", "FIONA_DISCUSS_USERS": "agent-user2,agent",
                            "FIONA_DISCUSS_CHAT": "1", "FIONA_DISCUSS_CHAT_CARDS": "1"},
}
RECORD = {}


def _apply(monkeypatch, *envs):
    for name in list(os.environ):
        if name.startswith(("FIONA_DISCUSS", "FIONA_NOVEL", "FIONA_SONG")):
            monkeypatch.delenv(name, raising=False)
    for env in envs:
        for name, value in env.items():
            monkeypatch.setenv(name, value)


def _dump(value):
    return json.dumps(value, ensure_ascii=False, default=repr)


@pytest.mark.parametrize("base", list(BASES))
@pytest.mark.parametrize("env", list(OFF_ENVS))
def test_agent_turn(harness, monkeypatch, base, env):
    _apply(monkeypatch, BASES[base], OFF_ENVS[env])
    h = harness
    h.streams.extend([
        FakeStream(message("tool_use", content=[call("get_weather", {"city": "北京"})]), "我查一下。"),
        # 模型乱叫一个没下发的讨论群工具：必须被忽略
        FakeStream(message("tool_use", content=[call("draft_discuss_task", {"request": "调研东南亚短剧市场的主要平台"}, identity="x-1")]), "再看看。"),
        FakeStream(message(text="今天晴。"), "今天晴。"),
    ])
    events = run(h)
    tools = h.agent.client_tools_for_turn(h.ctx, h.state)
    RECORD[f"agent/{base}/{env}"] = {
        "requests": _dump(h.requests),
        "events": _dump(events),
        "saves": _dump(h.saves),
        "executions": _dump(h.executions),
        "caps": _dump(h.caps),
        "trace": _dump(h.state.trace),
        "leftover_streams": len(h.streams),
        "tool_names": [tool["name"] for tool in tools],
        "tools_is_constant": tools is h.agent.CLAUDE_CLIENT_TOOLS,
        "tools_json": _dump(tools),
    }


class _FakeCompletions:
    def __init__(self, payload, captured):
        self.payload, self.captured = payload, captured

    def create(self, **kwargs):
        self.captured.append(kwargs)
        content = json.dumps(self.payload, ensure_ascii=False)
        message_ = type("M", (), {"content": content})()
        choice = type("C", (), {"message": message_})()
        return type("R", (), {"choices": [choice]})()


class _FakeClient:
    def __init__(self, payload, captured):
        self.chat = type("Chat", (), {"completions": _FakeCompletions(payload, captured)})()


PAYLOADS = {
    "discuss_read": {"intent": "discuss_read", "params": {"group": " 短剧 ", "part": "output", "offset": "12"}},
    "discuss_list": {"intent": "discuss_list", "params": {}},
    "novel_read": {"intent": "novel_read", "params": {"book": "春山", "chapter": "1"}},
    "web_search": {"intent": "web_search", "params": {"query": "东南亚短剧"}},
    "none": {"intent": None},
}


@pytest.mark.parametrize("base", ["plain", "novel"])
@pytest.mark.parametrize("env", list(OFF_ENVS))
def test_intent_recognition(monkeypatch, base, env):
    import intent_router
    import services.chat_service as chat

    _apply(monkeypatch, BASES[base], OFF_ENVS[env])
    history = [{"role": "user", "content": "我有个讨论群"}, {"role": "assistant", "content": "嗯，你说。"}]
    out = {}
    for name, payload in PAYLOADS.items():
        captured = []
        direct_user = intent_router.recognize_intent(_FakeClient(payload, captured), "那个群到哪一步了", history, username=USER)
        direct_anon = intent_router.recognize_intent(_FakeClient(payload, captured), "那个群到哪一步了", history)
        monkeypatch.setattr(chat, "client", _FakeClient(payload, captured))
        ctx = chat.ChatContext(USER, "那个群到哪一步了", False, None, "那个群到哪一步了", history, 0,
                               "persona", [{"role": "user", "content": "那个群到哪一步了"}],
                               conversation_id="conversation")
        state = chat.ChatState(trace={}, sys_prompt_final="persona")
        via_chat = asyncio.run(chat._recognize_turn_intent(ctx, state))
        out[name] = {"direct_user": direct_user, "direct_anon": direct_anon, "via_chat": via_chat,
                     "requests": _dump(captured)}
    RECORD[f"intent/{base}/{env}"] = out


def test_zz_write():
    assert len(RECORD) == len(BASES) * len(OFF_ENVS) + 2 * len(OFF_ENVS), len(RECORD)
    OUT.write_text(json.dumps(RECORD, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
