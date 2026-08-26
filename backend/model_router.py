# -*- coding: utf-8 -*-
"""
模型路由层——根据对话场景分发请求。
槽位标签："main" = 主力大脑 qwen3.8-max，"light" = 轻量槽 qwen-plus。

路由规则：
  mirror 模式  → light（短陪伴，轻量足够）
  image 模式   → light（简单回复，不需要高密度）
  normal 模式  → 按优先级：
    1. 主脑今日 token 预算耗尽 + 非创作消息 → light
    2. 消息含创作关键词 → main
    3. 消息长度 > 80 字 → main
    4. 默认（短闲聊）→ light
"""
from __future__ import annotations
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
) -> Literal["main", "light"]:
    """
    返回 "main" 或 "light"，供聊天服务选择客户端和参数。

    mode 取值：
      "mirror"  — 镜子模式（Chloe纯陪伴，无工具）
      "image"   — 有图片的对话（简短告知看不到）
      "normal"  — 普通对话
    """
    # mirror / image → 永远轻量槽
    if mode in ("mirror", "image"):
        return "light"

    # normal 模式
    has_creative = any(kw in message for kw in CREATIVE_KEYWORDS)

    # 预算超限时：创作仍走主脑，闲聊切轻量槽
    if token_budget.is_over_budget(username):
        return "main" if has_creative else "light"

    # 预算充足：创作或长消息走主力大脑
    if has_creative or len(message.strip()) > 80:
        return "main"

    # 默认：短闲聊走轻量槽
    return "light"
