# -*- coding: utf-8 -*-
"""
模型路由层——根据对话场景分发请求。
槽位标签："main" = 主力大脑 qwen3.8-omni-flash，"light" = 轻量槽 qwen3.8-flash。

路由规则：
  mirror 模式  → light（短陪伴，轻量足够）
  image 模式   → light（简单回复，不需要高密度）
  normal 模式  → 按优先级依次判定，命中即返回：
    1. 主脑今日 token 预算耗尽 + 非创作消息 → light
       （成本闸门优先级最高：此时含创作关键词仍走 main，
         但下面的第 4/5 条不得把非创作请求抬回 main）
    2. 消息含创作关键词 → main
    3. 消息长度 > 80 字 → main
    4. 消息含指代/省略信号（has_context_reference，如"那他呢？"）→ main
    5. 会话已积累历史条数 >= CONTEXT_DEPTH_MAIN_THRESHOLD（默认 6）→ main
       （该环境变量 <= 0 时本条规则整体关闭，用于成本回退）
    6. 默认（短闲聊、不依赖上文）→ light
"""
from __future__ import annotations
import os
from datetime import date
from typing import Literal

# 触发主力大脑的创作关键词
CREATIVE_KEYWORDS = [
    "设定", "背景", "分镜", "故事", "人物", "世界观", "剧情",
    "小说", "写作", "角色", "性格", "脑暴", "补全", "续写",
    "改写", "扩写", "剧本", "台词", "场景描写",
]

# 草莓预算上限（主力大脑用量）
MAIN_DAILY_LIMIT   = 30_000   # 今日草莓上限
MAIN_MONTHLY_LIMIT = 500_000  # 本月草莓上限

# 必须依赖上文才能解析的指代/省略信号
CONTEXT_REFERENCE_KEYWORDS = (
    # 近指 / 远指
    "那个", "那件", "那条", "那张", "那款", "那家", "那位", "那边",
    "这个", "这件", "这条", "这张", "这款", "这家", "这位", "这边",
    # 人称指代
    "他", "她", "它", "他们", "她们", "它们",
    # 时间/位置回指
    "刚才", "刚刚", "方才", "上面", "前面", "之前", "上次", "上一个", "上一条",
    # 序数与选择
    "第一个", "第二个", "第三个", "第几", "哪个",
    # 承接与追加
    "还是", "继续", "接着", "然后呢", "那呢", "再来", "再来一个", "换一个", "换个",
    # 类比与引述
    "一样", "同样", "同上", "你说的", "你刚说", "按你说的",
)

# 会让单字 "他"/"它" 误命中的词，匹配前先整体剔除
_FALSE_POSITIVE_TOKENS = ("其他", "其它", "吉他")

# 会话深度阈值：历史条数 >= 该值时走主力模型
CONTEXT_DEPTH_ENV = "CONTEXT_DEPTH_MAIN_THRESHOLD"
CONTEXT_DEPTH_DEFAULT = 6


def _context_depth_threshold() -> int:
    """每次调用现读环境变量，解析失败回落默认值 6（不抛异常）。"""
    raw = os.getenv(CONTEXT_DEPTH_ENV)
    if raw is None:
        return CONTEXT_DEPTH_DEFAULT
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return CONTEXT_DEPTH_DEFAULT


def has_context_reference(message: str) -> bool:
    """消息是否含有必须依赖上文才能解析的指代/省略信号。"""
    if not isinstance(message, str) or not message:
        return False
    # 先剔除误伤词，再对同一份文本做全部词表匹配
    text = message
    for token in _FALSE_POSITIVE_TOKENS:
        text = text.replace(token, "")
    return any(kw in text for kw in CONTEXT_REFERENCE_KEYWORDS)


class TokenBudget:
    """内存计数器：追踪每个用户的今日 + 本月草莓用量。"""

    def __init__(self):
        self._data: dict[str, dict[str, int]] = {}  # {username: {date_str: tokens}}

    def _today(self) -> str:
        return date.today().isoformat()          # e.g. "2026-05-12"

    def _month(self) -> str:
        return date.today().strftime("%Y-%m")    # e.g. "2026-05"

    def add(self, username: str, tokens: int) -> None:
        d = self._today()
        user = self._data.setdefault(username, {})
        user[d] = user.get(d, 0) + tokens

    def get_daily(self, username: str) -> int:
        return self._data.get(username, {}).get(self._today(), 0)

    def get_monthly(self, username: str) -> int:
        prefix = self._month()
        return sum(
            v for k, v in self._data.get(username, {}).items()
            if k.startswith(prefix)
        )

    # 兼容旧调用
    def get(self, username: str) -> int:
        return self.get_daily(username)

    def is_over_budget(self, username: str) -> bool:
        return self.get_daily(username) >= MAIN_DAILY_LIMIT


# 全局单例
token_budget = TokenBudget()


def choose_model(
    username: str,
    message: str,
    mode: str,
    history_len: int = 0,
) -> Literal["main", "light"]:
    """
    返回 "main" 或 "light"，供聊天服务选择客户端和参数。

    mode 取值：
      "mirror"  — 镜子模式（Chloe纯陪伴，无工具）
      "image"   — 保留分支；实际图片消息在 chat_service 里直接走
                  stream_image(qwen-vl-max 看图)，不会路由到这里
      "normal"  — 普通对话

    history_len — 当前会话已积累的历史消息条数（第 4 个位置参数，默认 0）。
    """
    # mirror / image → 永远轻量槽
    if mode in ("mirror", "image"):
        return "light"

    # normal 模式
    has_creative = any(kw in message for kw in CREATIVE_KEYWORDS)

    # 规则 1｜预算超限时：创作仍走主脑，闲聊切轻量槽（成本闸门，压住下面的 4/5）
    if token_budget.is_over_budget(username):
        return "main" if has_creative else "light"

    # 规则 2｜创作消息走主力大脑
    if has_creative:
        return "main"

    # 规则 3｜长消息走主力大脑
    if len(message.strip()) > 80:
        return "main"

    # 规则 4｜短消息但依赖上文（"那他呢？"）也走主力大脑
    if has_context_reference(message):
        return "main"

    # 规则 5｜会话已积累足够深度，短句大概率承接上文
    threshold = _context_depth_threshold()
    if threshold > 0 and history_len >= threshold:
        return "main"

    # 规则 6｜默认：短闲聊走轻量槽
    return "light"
