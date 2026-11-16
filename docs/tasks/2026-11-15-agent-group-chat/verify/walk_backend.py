"""隔离走查用的后端启动器（只在会话临时副本里用，不进仓库）。

真实后端代码原样运行，只把两处「出站到模型厂商」的调用换成本地脚本：
  1. 自带 Claude 的出站流 open_agent_stream → 按用户原话的关键词决定调哪个工具；只会调本轮下发了的工具。
  2. 平台意图识别用的客户端 → 按关键词返回意图 JSON；只有提示词里带讨论群片段时才返回讨论群意图。
另外：tester 账号被当成「自带 Claude 已启用」，其余账号走平台模型；模式判定固定为 friend。
开关 FIONA_DISCUSS_CHAT / FIONA_DISCUSS_CHAT_CARDS 每秒从 <DATA>/flags.json 读一次，方便走查中途切换。
每次脚本化的模型调用都往 <DATA>/model-calls.jsonl 追加一行，供核对「发给模型的是什么」。
"""
import json
import os
import re
import sys
import threading
import time
from types import SimpleNamespace as NS

DATA = os.environ["WALK_DATA"]
LOG = os.path.join(DATA, "model-calls.jsonl")
FLAGS = os.path.join(DATA, "flags.json")
CLAUDE_USER = "tester"

sys.path.insert(0, os.getcwd())
import main  # noqa: E402  先让全部模块按原样加载
import intent_router  # noqa: E402
import services.chat_service as chat  # noqa: E402
import services.claude_agent as agent  # noqa: E402


def log(kind, **fields):
    with open(LOG, "a", encoding="utf-8") as handle:
        handle.write(json.dumps({"t": time.strftime("%H:%M:%S"), "kind": kind, **fields}, ensure_ascii=False) + "\n")


def watch_flags():
    while True:
        try:
            with open(FLAGS, encoding="utf-8") as handle:
                flags = json.load(handle)
            for name in ("FIONA_DISCUSS_CHAT", "FIONA_DISCUSS_CHAT_CARDS"):
                value = flags.get(name)
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = str(value)
        except (OSError, ValueError):
            pass
        time.sleep(1)


threading.Thread(target=watch_flags, daemon=True).start()

# ── 1. tester 当成自带 Claude 已启用 ──
_real_internal_config = chat.get_internal_config


async def fake_internal_config(username):
    if username == CLAUDE_USER:
        return {"enabled": True, "provider": "anthropic", "model": "claude-sonnet-5-5", "base_url": None,
                "effort": "low", "status": "ok", "api_key": "walk-placeholder-key"}
    return await _real_internal_config(username)


chat.get_internal_config = fake_internal_config
chat.detect_mode = lambda *args, **kwargs: "friend"


# ── 2. Claude 出站流 ──
class FakeStream:
    def __init__(self, final, text=""):
        self.final_message = final
        self.stop_reason = final.stop_reason
        self.refused = False
        self.closed = False
        self._chunks = iter([NS(choices=[NS(delta=NS(content=text))])] if text else [])

    def __iter__(self):
        return self

    def __next__(self):
        return next(self._chunks)

    def close(self):
        self.closed = True


def _message(stop="end_turn", content=None, text=""):
    return NS(stop_reason=stop, content=content or ([{"type": "text", "text": text}] if text else []),
              usage=NS(input_tokens=10, output_tokens=5))


def _plain(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(block.get("text", "") for block in content if isinstance(block, dict) and block.get("type") == "text")
    return ""


def _group_from(text):
    match = re.search(r"《(.+?)》", text)
    return match.group(1) if match else ""


def scripted_agent_stream(config, messages, *, username, tools, deadline_seconds, control=None):
    names = [tool["name"] for tool in tools]
    last = messages[-1]
    content = last.get("content")
    results = [block for block in content if isinstance(block, dict) and block.get("type") == "tool_result"] \
        if isinstance(content, list) else []
    if results:
        fed = results[0].get("content")
        fed = fed if isinstance(fed, str) else json.dumps(fed, ensure_ascii=False)
        log("claude_round2", tools=names, tool_result=fed)
        reply = "（走查脚本）我收到的工具结果开头是：" + fed[:80]
        return FakeStream(_message(text=reply), reply)
    text = _plain(content)
    wanted, args = None, {}
    if "任务卡" in text:
        wanted = "draft_discuss_task"
        args = {"request": "调研面向东南亚市场的 AI 短剧出海值不值得做，给出明确结论和起步方案",
                "materials": "三个人的小团队，预算二十万以内。\n先看印尼和泰国。", "max_rounds": 4, "budget_strawberries": 3000}
        if "超限" in text:
            args.update(request="太短", budget_strawberries=99999, max_rounds=9)
    elif "告诉他们" in text:
        wanted = "draft_discuss_note"
        args = {"group": _group_from(text), "text": "别查越南了，先把印尼和泰国查透。\n成本那一节补上工具名字。"}
    elif "哪些讨论群" in text:
        wanted = "list_discuss_groups"
    elif "到哪一步" in text:
        wanted, args = "read_discuss_group", {"group": _group_from(text), "part": "progress"}
    elif "成果" in text:
        wanted, args = "read_discuss_group", {"group": _group_from(text), "part": "output"}
    log("claude_round1", tools=names, wanted=wanted, user_tail=text[-80:], system_has_discuss="讨论群" in json.dumps(messages[:1], ensure_ascii=False))
    if wanted and wanted in names:
        lead = "我来处理。"
        return FakeStream(_message("tool_use", content=[
            {"type": "text", "text": lead},
            {"type": "tool_use", "id": f"walk-{int(time.time() * 1000)}", "name": wanted, "input": args},
        ]), lead)
    reply = "（走查脚本）这一轮没有可用的讨论群工具，我只能直接回答。" if wanted else "（走查脚本）你好。"
    return FakeStream(_message(text=reply), reply)


agent.open_agent_stream = scripted_agent_stream


# ── 3. 平台意图识别 ──
class _Completions:
    def __init__(self, real):
        self._real = real

    def create(self, **kwargs):
        messages = kwargs.get("messages") or []
        system = messages[0].get("content", "") if messages else ""
        if not (isinstance(system, str) and system.startswith(intent_router.INTENT_PROMPT[:40])):
            return self._real.create(**kwargs)
        user = messages[-1].get("content", "")
        current = user.split("【当前消息】\n", 1)[1] if "【当前消息】\n" in user else user
        has_discuss = "【作者的讨论群（仅本人，免费）】" in system
        intent = {"intent": None}
        if has_discuss:
            group = _group_from(current)
            if "哪些讨论群" in current:
                intent = {"intent": "discuss_list", "params": {}}
            elif "到哪一步" in current:
                intent = {"intent": "discuss_read", "params": {"group": group, "part": "progress"}}
            elif "接着读" in current:
                found = re.findall(r"接着读请从 (\d+) 开始", user)
                intent = {"intent": "discuss_read", "params": {"group": group, "part": "output", "offset": found[-1] if found else 0}}
            elif "成果" in current:
                intent = {"intent": "discuss_read", "params": {"group": group, "part": "output"}}
        log("intent", has_discuss_prompt=has_discuss, system_chars=len(system), current=current[-80:], intent=intent)
        body = NS(content=json.dumps(intent, ensure_ascii=False))
        return NS(choices=[NS(message=body)])


class _ClientProxy:
    def __init__(self, real):
        self._real = real
        self.chat = NS(completions=_Completions(real.chat.completions))

    def __getattr__(self, name):
        return getattr(self._real, name)


chat.client = _ClientProxy(chat.client)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(main.app, host="127.0.0.1", port=8001, log_level="info")
