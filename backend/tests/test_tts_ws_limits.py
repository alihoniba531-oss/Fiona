# -*- coding: utf-8 -*-
import asyncio
import json

from tts_ws import handle_tts_ws


class _FakeWebSocket:
    def __init__(self, messages):
        self.messages = list(messages)
        self.accepted = False
        self.close_codes = []

    async def accept(self):
        self.accepted = True

    async def receive_text(self):
        return self.messages.pop(0)

    async def send_bytes(self, chunk):
        raise AssertionError("invalid input must not start audio output")

    async def close(self, code=1000):
        self.close_codes.append(code)


def test_tts_websocket_rejects_oversized_text_before_synthesis():
    ws = _FakeWebSocket([
        json.dumps({"type": "text", "chunk": "a" * 2001}),
    ])

    asyncio.run(handle_tts_ws(ws))

    assert ws.accepted is True
    assert ws.close_codes == [1009]


def test_tts_websocket_rejects_invalid_voice_before_synthesis():
    ws = _FakeWebSocket([
        json.dumps({"type": "text", "chunk": "hello", "voice": "../../bad"}),
    ])

    asyncio.run(handle_tts_ws(ws))

    assert ws.accepted is True
    assert ws.close_codes == [1008]
