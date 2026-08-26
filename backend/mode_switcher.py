# -*- coding: utf-8 -*-
"""
双模式系统：朋友模式 / 镜子模式

朋友模式（默认）：完整能力——工具调用、主动消息、建议、表态
镜子模式：纯陪伴——只回"嗯/我在/你说/反问"，不动手、不评价、不出主意

切换由 detect_mode() 自动判定，也可由用户对话信号手动切换。
状态存内存，重启清空。
"""

import re
import json
from datetime import datetime, timedelta
from typing import Literal

from llm import MAIN_EXTRA_BODY, MAIN_MODEL

ModeType = Literal["friend", "mirror"]

# ── 内存状态：username -> {mode, since, last_trigger} ───────────
_mode_state: dict[str, dict] = {}

# 镜子模式无新触发条件 + 用户开新话题超过该时长 → 切回朋友
MIRROR_TIMEOUT_MINUTES = 30


# ── 切换信号关键词 ─────────────────────────────────

# 用户明确说要切镜子模式
MANUAL_MIRROR_SIGNALS = [
    "别给建议", "别建议", "你别说话", "你别分析", "别分析我",
    "让我说", "你听就行", "听我说就行", "你就听着",
    "我现在不想被分析", "我就想说说", "我就想发泄",
    "别问我", "不要问我",
]

# 用户明确要切回朋友
MANUAL_FRIEND_SIGNALS = [
    "你说说", "你说点啥", "给我点建议", "你怎么看",
    "出个主意", "帮我想想", "你说一下",
]

# 单字/极短情绪表达（连续多条触发自动切镜子）
SHORT_EMOTION_REGEX = [
    re.compile(r"^[烦累操艹靠晕呵嗯哎唉哼]+[。！\.\!]?$"),
    re.compile(r"^\.{2,}$"),
    re.compile(r"^…+$"),
    re.compile(r"^[呜呵哈嘿]+$"),
    re.compile(r"^难受+$"),
    re.compile(r"^心累+$"),
]

# 用户问具体问题的指示词（镜子模式下自动切回朋友的信号）
CONCRETE_QUESTION_INDICATORS = [
    "几点", "几号", "帮我", "你觉得", "怎么办",
    "查一下", "搜一下", "打开", "发消息", "发个",
    "提醒", "打电话", "查查", "?", "？",
]

# 发泄情绪的预筛关键词（命中才调 LLM 判定，避免每条都调）
VENT_PRESCAN_KEYWORDS = [
    "烦", "累", "操", "崩溃", "受不了", "气死", "难受", "无语",
    "心累", "压力", "委屈", "孤独", "撑不住", "活不下去",
    "想死", "讨厌", "厌恶", "绝望",
]


def is_short_emotion(text: str) -> bool:
    """判断是否单字/极短情绪表达"""
    t = (text or "").strip()
    if not t or len(t) > 4:
        return False
    return any(p.match(t) for p in SHORT_EMOTION_REGEX)


def is_concrete_question(text: str) -> bool:
    """判断是否问具体问题"""
    return any(kw in text for kw in CONCRETE_QUESTION_INDICATORS)


def has_vent_signal(text: str) -> bool:
    """轻量预筛：消息是否有发泄/情绪倾向"""
    return any(kw in text for kw in VENT_PRESCAN_KEYWORDS)


# ── 状态读写 ────────────────────────────────────────

def get_user_mode(username: str) -> dict:
    """获取当前模式状态。新用户默认 friend"""
    if username not in _mode_state:
        _mode_state[username] = {
            "mode": "friend",
            "since": datetime.now(),
            "last_trigger": None,
        }
    return _mode_state[username]


def set_user_mode(username: str, mode: ModeType, trigger_reason: str = ""):
    """切换用户模式"""
    _mode_state[username] = {
        "mode": mode,
        "since": datetime.now(),
        "last_trigger": trigger_reason,
    }


def clear_user_mode(username: str):
    """清空状态（一般测试用）"""
    _mode_state.pop(username, None)


# ── 模式判定主函数 ─────────────────────────────────

def detect_mode(
    client,
    username: str,
    current_msg: str,
    recent_history: list[dict],
) -> ModeType:
    """
    判定当前用户应该处于什么模式。

    优先级（从高到低）：
    1. 用户明确手动切换信号
    2. 镜子模式下用户问具体问题/明确要切回 → 切回朋友
    3. 朋友模式下连续 3 条短情绪 → 切镜子
    4. 朋友模式下 LLM 判定"发泄不在求解" → 切镜子
    5. 镜子模式持续 ≥ 30 分钟 + 用户开新话题 → 切回朋友
    """
    state = get_user_mode(username)
    current_mode = state["mode"]
    msg = (current_msg or "").strip()

    # ── 优先级 1：用户明确切镜子 ──
    for signal in MANUAL_MIRROR_SIGNALS:
        if signal in msg:
            set_user_mode(username, "mirror", f"manual: '{signal}'")
            return "mirror"

    # ── 镜子模式下的切回判定 ──
    if current_mode == "mirror":
        # 用户明确要切回
        for signal in MANUAL_FRIEND_SIGNALS:
            if signal in msg:
                set_user_mode(username, "friend", f"manual back: '{signal}'")
                return "friend"

        # 用户问具体问题（隐含要她干活/回答）
        if is_concrete_question(msg):
            set_user_mode(username, "friend", "concrete question")
            return "friend"

        # 超时 + 用户主动开较长新话题
        elapsed = datetime.now() - state["since"]
        if elapsed > timedelta(minutes=MIRROR_TIMEOUT_MINUTES) and len(msg) > 10:
            set_user_mode(username, "friend", "timeout + new topic")
            return "friend"

        # 镜子模式保持
        return "mirror"

    # ── 朋友模式下的切镜子判定 ──

    # 优先级 3：连续 3 条短情绪
    recent_user_msgs = [
        m["content"] for m in recent_history
        if m.get("role") == "user" and m.get("content")
    ][-2:]
    if len(recent_user_msgs) >= 2 and is_short_emotion(msg):
        if all(is_short_emotion(m) for m in recent_user_msgs):
            set_user_mode(username, "mirror", "3 consecutive short emotions")
            return "mirror"

    # 优先级 4：LLM 判定（只在有发泄信号 + 消息有一定长度时调用）
    if len(msg) >= 6 and has_vent_signal(msg):
        if _llm_is_venting(client, msg, recent_history):
            set_user_mode(username, "mirror", "LLM: venting not seeking")
            return "mirror"

    return "friend"


def _llm_is_venting(client, current_msg: str, history: list[dict]) -> bool:
    """LLM 判定用户当前是发泄还是求解（JSON mode 轻量调用）"""
    # 只取最近 4 条上下文
    context_msgs = [
        f"{m['role']}: {m['content'][:80]}"
        for m in history[-4:]
        if m.get("content")
    ]
    context = "\n".join(context_msgs) if context_msgs else "（无上下文）"

    prompt = (
        "判断用户当前主要是发泄情绪还是求建议/求帮助。只输出 JSON。\n\n"
        "发泄：抱怨、宣泄、不求方案、不想被分析。\n"
        "求解：明确问问题、想要建议或方案、想要她做某事。\n\n"
        '输出格式（严格 JSON）：{"is_venting": true|false, "confidence": 0.0-1.0}'
    )

    try:
        resp = client.chat.completions.create(
            model=MAIN_MODEL,
            extra_body=MAIN_EXTRA_BODY,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": f"上下文：\n{context}\n\n最新消息：{current_msg}"},
            ],
            response_format={"type": "json_object"},
            max_tokens=30,
            temperature=0.1,
        )
        result = json.loads(resp.choices[0].message.content)
        return result.get("is_venting", False) and result.get("confidence", 0) >= 0.7
    except Exception:
        return False


# ── 镜子模式的 prompt 增量 ────────────────────────

MIRROR_PROMPT_APPENDIX = """

——

【当前状态：陪着】
你现在不是干活的状态，是陪着的状态。
对方不需要建议、不需要分析、不需要你出主意。
你只是在，听着。

反应短到不能再短。"嗯" / "我在" / "你说" / 一个反问 / 不接话也行。
不主动开新话题，不打趣，不调侃。
他停了你就停，他说你就嗯一下。
他突然说"你说点啥"才回到正常聊天，否则保持。

这不是冷淡，是真陪着——朋友最贵的状态。
"""


def apply_mode_prompt(system_prompt: str, mode: ModeType) -> str:
    """给 system_prompt 追加模式增量"""
    if mode == "mirror":
        return system_prompt + MIRROR_PROMPT_APPENDIX
    return system_prompt
