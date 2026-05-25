# -*- coding: utf-8 -*-
"""
用户分身成长状态管理。
每个用户的Chloe从"空"开始，随着对话轮数增加，逐渐被用户的说话习惯填满。

三个阶段：
  EMPTY     0-30 条消息  — 纯倾听者，不带预设，干净回应
  MIRRORING 31-100 条   — 开始镜像用户语气、节奏、用词习惯
  EMBODIED  100+ 条     — 完整分身，用户我执层的外化
"""

from enum import Enum
import re
from collections import Counter


class AvatarStage(Enum):
    EMPTY = "empty"
    MIRRORING = "mirroring"
    EMBODIED = "embodied"


def get_stage(message_count: int) -> AvatarStage:
    if message_count <= 30:
        return AvatarStage.EMPTY
    elif message_count <= 100:
        return AvatarStage.MIRRORING
    return AvatarStage.EMBODIED


# ── 语气特征提取 ──

_CURSE_WORDS = [
    "操", "靠", "妈的", "草", "日了", "日", "特么", "tm", "tmd",
    "傻逼", "sb", "脑残", "妈的", "我操", "卧槽", "艹", "fuck",
    "尼玛", "你妈", "老子", "他妈的",
]

_INFORMAL_PARTICLES = ["啊", "吧", "嘛", "呢", "哦", "呗", "哈", "咯", "啦", "呀", "哇", "唉", "哎"]

_EMOJI_PATTERN = re.compile(
    r"[\U0001F300-\U0001F9FF]|"       # 表情符号
    r"[\U0001FA00-\U0001FA6F]|"        # 扩展
    r"[☀-➿]|"                # 杂项符号
    r"[#*0-9]️?⃣"  # 键帽
)


def extract_tone_profile(messages: list[dict]) -> dict:
    """
    从用户最近的消息中提取语气特征。
    只取 role='user' 的消息，排除系统标记消息。
    """
    user_msgs = [
        m["content"] for m in messages
        if m.get("role") == "user" and m.get("content") and not m["content"].startswith("[")
    ]
    if not user_msgs:
        return _default_tone()

    total = len(user_msgs)
    total_chars = sum(len(m) for m in user_msgs)
    avg_len = total_chars / total

    # 脏话密度
    curse_count = sum(
        1 for m in user_msgs
        if any(cw in m.lower() for cw in _CURSE_WORDS)
    )
    curse_ratio = curse_count / total

    # 语气词密度
    particle_count = sum(
        1 for m in user_msgs
        if any(p in m for p in _INFORMAL_PARTICLES)
    )
    particle_ratio = particle_count / total

    # emoji 密度
    emoji_count = sum(
        len(_EMOJI_PATTERN.findall(m)) for m in user_msgs
    )
    emoji_ratio = emoji_count / total

    # 问句密度
    question_count = sum(1 for m in user_msgs if ("？" in m or "?" in m))
    question_ratio = question_count / total

    # 句子数（按中英文标点断句）
    sentence_breaks = sum(
        len(re.findall(r"[。！？\.\!\?]", m)) for m in user_msgs
    )
    avg_sentences_per_msg = sentence_breaks / total if total else 0

    return {
        "avg_len": round(avg_len, 1),
        "curse_ratio": round(curse_ratio, 2),
        "particle_ratio": round(particle_ratio, 2),
        "emoji_ratio": round(emoji_ratio, 2),
        "question_ratio": round(question_ratio, 2),
        "avg_sentences": round(avg_sentences_per_msg, 1),
        "total_msgs": total,
    }


def _default_tone() -> dict:
    return {
        "avg_len": 0,
        "curse_ratio": 0,
        "particle_ratio": 0,
        "emoji_ratio": 0,
        "question_ratio": 0,
        "avg_sentences": 0,
        "total_msgs": 0,
    }


def build_tone_description(tone: dict) -> str:
    """把语气特征转成人话描述，注入到分身 prompt 里"""
    if tone["total_msgs"] < 10:
        return ""

    parts = []

    # 消息长度
    if tone["avg_len"] <= 10:
        parts.append("说话很简短，像个不爱打字的")
    elif tone["avg_len"] <= 25:
        parts.append("说话不长不短")
    elif tone["avg_len"] <= 50:
        parts.append("说话比较能聊，一段话能说不少")
    else:
        parts.append("能长篇大论，表达欲挺强")

    # 脏话
    if tone["curse_ratio"] >= 0.3:
        parts.append("嘴上不干净，经常带脏字——你跟着带，别收敛")
    elif tone["curse_ratio"] >= 0.1:
        parts.append("偶尔蹦脏字，带点劲儿但不重")
    else:
        parts.append("不怎么骂人")

    # 语气词
    if tone["particle_ratio"] >= 0.5:
        parts.append("爱用语气词（啊吧嘛呢哦），说话带生活气")
    elif tone["particle_ratio"] <= 0.1:
        parts.append("说话干脆，不怎么拖语气词")

    # emoji
    if tone["emoji_ratio"] >= 0.2:
        parts.append("喜欢用表情包/emoji")
    elif tone["emoji_ratio"] <= 0.05:
        parts.append("基本不用表情")

    # 问句
    if tone["question_ratio"] >= 0.4:
        parts.append("爱问问题，经常反问")
    elif tone["question_ratio"] <= 0.1:
        parts.append("不怎么问问题，喜欢陈述")

    if not parts:
        return ""

    return "对方说话的样子：" + "；".join(parts) + "。\n你的语气、节奏和用词习惯，往对方的方向靠——他什么样你就什么样。"
