"""工作室视频供应商。"""
from .base import PollResult, ProviderError, Submission, VideoProvider
from .video_seedance import SeedanceProvider
from .video_wan import WanProvider


def get_provider(name: str, *, transport=None) -> VideoProvider:
    if name == "wan":
        return WanProvider(transport=transport)
    if name == "seedance":
        return SeedanceProvider(transport=transport)
    raise ProviderError("failed", "invalid_provider", "不支持的视频供应商")


__all__ = ["PollResult", "ProviderError", "Submission", "VideoProvider", "WanProvider", "SeedanceProvider", "get_provider"]
