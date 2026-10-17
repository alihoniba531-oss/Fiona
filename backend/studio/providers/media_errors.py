"""块 B 付费媒体调用的统一错误分类。

status 决定块 A 如何处置预留：
  - rejected  : 明确的 4xx / 429 / 内容审核以外的上游拒绝 —— 释放预留。
  - uncertain : 超时、断连、5xx、2xx 但无法解析 —— 保留预留，只能手动释放。
  - failed    : 内容审核拒绝 —— 按 0 结算。
"""
from __future__ import annotations

MEDIA_ERROR_STATUSES = frozenset({"rejected", "uncertain", "failed"})


class MediaCallError(Exception):
    """一次付费媒体调用的失败；不重试，由调用方按 status 处理预留。"""

    def __init__(self, status: str, code: str, message: str):
        if status not in MEDIA_ERROR_STATUSES:
            raise ValueError(f"未知的付费调用状态：{status!r}")
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message

    def __repr__(self) -> str:  # 便于测试排查；不泄漏请求体
        return f"MediaCallError(status={self.status!r}, code={self.code!r})"
