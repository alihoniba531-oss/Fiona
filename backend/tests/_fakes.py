# -*- coding: utf-8 -*-
"""测试用假对象：模拟 OpenAI 流式响应。generate() 按 chunk.choices[0].delta.content 消费。"""


class _FakeDelta:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content, finish_reason=None):
        self.delta = _FakeDelta(content)
        self.finish_reason = finish_reason


class _FakeChunk:
    def __init__(self, content, finish_reason=None):
        self.choices = [_FakeChoice(content, finish_reason)]


class FakeStream:
    """默认吐 '测试'+'回复'（带 stop）。chunks 可传 [(content, finish_reason), ...] 自定义。"""
    def __init__(self, chunks=None):
        self._chunks = chunks if chunks is not None else [("测试", None), ("回复", "stop")]

    def __iter__(self):
        for content, fr in self._chunks:
            yield _FakeChunk(content, fr)
