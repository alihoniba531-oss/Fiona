"""块 B：CosyVoice / edge-tts 适配器的离线契约测试。

全部使用假 SDK（假工厂 + 假合成器）：不联网；本机未安装 edge-tts 也能跑。
覆盖参数传递、字节收集、错误分类，以及全局 dashscope.api_key 不被改写残留。
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

import pytest

from studio.providers import tts_cosy, tts_edge
from studio.providers.media_errors import MediaCallError


FIXTURES = Path(__file__).parent / "fixtures" / "studio"
BACKEND_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def dashscope_key(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-dashscope-key")
    return "test-dashscope-key"


def wait_until(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def read_fixture(name):
    return json.loads((FIXTURES / name).read_text("utf-8"))


class FakeSdkError(Exception):
    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code


class FakeCosyFactory:
    """假 SpeechSynthesizer 工厂：记录构造参数，按配置产生音频 / 失败 / 阻塞。"""

    def __init__(self, *, chunks=(), events=(), failure=None, raises=None, release=None):
        self.chunks = list(chunks)
        self.events = list(events)
        self.failure = failure
        self.raises = raises
        self.release = release
        self.params = None
        self.constructed_key = None
        self.texts = []
        self.timeouts = []
        self.closed = False

    def __call__(self, **params):
        import dashscope

        self.params = params
        self.constructed_key = dashscope.api_key
        callback = params["callback"]
        factory = self

        class FakeSynthesizer:
            def call(self, text, timeout_millis=None):
                factory.texts.append(text)
                factory.timeouts.append(timeout_millis)
                if factory.release is not None:
                    factory.release.wait(5.0)
                if factory.raises is not None:
                    raise factory.raises
                for chunk in factory.chunks:
                    callback.on_data(chunk)
                for message in factory.events:
                    callback.on_event(message)
                if factory.failure is not None:
                    callback.on_error(factory.failure)
                else:
                    callback.on_complete()

            def close(self):
                factory.closed = True

        return FakeSynthesizer()


class FakeEdgeFactory:
    """假 Communicate 工厂：把给定事件喂给 stream()。"""

    def __init__(self, *, events=(), raises=None, block=None):
        self.events = list(events)
        self.raises = raises
        self.block = block
        self.params = None

    def __call__(self, **params):
        self.params = params
        events, raises, block = self.events, self.raises, self.block

        class FakeCommunication:
            async def stream(self):
                if block is not None:
                    await asyncio.sleep(block)
                    return
                if raises is not None:
                    raise raises
                for event in events:
                    yield event

        return FakeCommunication()


COSY_TEXT = "你还给的是官府。不是我。"


async def cosyvoice(factory, **kwargs):
    params = {"voice": "longxiaoxia_v2", "rate": 0.9, "pitch": 1.1}
    params.update(kwargs)
    return await tts_cosy.synthesize_cosy(COSY_TEXT, synthesizer_factory=factory, **params)


def test_tts_result_is_shared_between_adapters():
    assert tts_edge.TtsResult is tts_cosy.TtsResult


@pytest.mark.anyio
async def test_cosyvoice_declares_sdk_parameters_and_collects_audio(dashscope_key):
    from dashscope.audio.tts_v2 import AudioFormat

    factory = FakeCosyFactory(chunks=[b"RIFF", b"-data-1", b"-data-2"])
    result = await cosyvoice(factory)

    assert factory.params["model"] == "cosyvoice-v2"
    assert factory.params["voice"] == "longxiaoxia_v2"
    assert factory.params["format"] is AudioFormat.WAV_48000HZ_MONO_16BIT
    # rate / pitch 映射到 SDK 的构造参数 speech_rate / pitch_rate。
    assert factory.params["speech_rate"] == 0.9
    assert factory.params["pitch_rate"] == 1.1
    assert factory.params["callback"] is not None
    assert factory.constructed_key == "test-dashscope-key"
    assert factory.texts == [COSY_TEXT]
    assert factory.timeouts == [120000]
    assert factory.closed is True

    assert result.audio == b"RIFF-data-1-data-2"
    assert result.audio_format == "wav"
    assert result.sample_rate == 48000
    assert result.engine == "cosyvoice"
    assert result.voice == "longxiaoxia_v2"
    assert result.chars == len(COSY_TEXT)
    assert result.words is None


@pytest.mark.anyio
async def test_cosyvoice_real_fixture_events_keep_words_none(dashscope_key):
    events = read_fixture("cosyvoice-20261016-131013.json")["events"]
    # 真实返回：句子事件里 words 恒为空，当前 SDK 不提供逐字时间戳。
    assert events[0]["payload"]["output"]["sentence"]["words"] == []

    factory = FakeCosyFactory(chunks=[b"wav"], events=[json.dumps(item) for item in events])
    result = await cosyvoice(factory)

    assert result.words is None
    assert result.audio == b"wav"


@pytest.mark.anyio
async def test_cosyvoice_restores_global_api_key(dashscope_key, monkeypatch):
    import dashscope

    monkeypatch.setattr(dashscope, "api_key", "previous-key", raising=False)

    factory = FakeCosyFactory(chunks=[b"x"])
    await cosyvoice(factory)
    assert factory.constructed_key == "test-dashscope-key"
    assert dashscope.api_key == "previous-key"

    # 失败路径同样要恢复，不能把 key 残留在进程全局里。
    failing = FakeCosyFactory(raises=RuntimeError("boom"))
    with pytest.raises(MediaCallError):
        await cosyvoice(failing)
    assert dashscope.api_key == "previous-key"


@pytest.mark.anyio
async def test_cosyvoice_timeout_is_uncertain(dashscope_key, monkeypatch):
    import dashscope

    monkeypatch.setattr(tts_cosy, "SYNTHESIS_TIMEOUT_S", 0.05)
    monkeypatch.setattr(dashscope, "api_key", "previous-key", raising=False)
    release = threading.Event()
    factory = FakeCosyFactory(chunks=[b"never"], release=release)

    started = time.monotonic()
    with pytest.raises(MediaCallError) as exc:
        await cosyvoice(factory)
    assert (exc.value.status, exc.value.code) == ("uncertain", "timeout")
    assert time.monotonic() - started < 2  # 没有等满 SDK 的 120 秒

    release.set()
    assert wait_until(lambda: dashscope.api_key == "previous-key")


@pytest.mark.anyio
async def test_cosyvoice_timeout_while_waiting_for_lock_never_calls_sdk(dashscope_key, monkeypatch):
    """超时只取消等待；线程拿到锁后必须直接返回，不能再发一次付费请求。"""
    import dashscope

    monkeypatch.setattr(tts_cosy, "SYNTHESIS_TIMEOUT_S", 0.05)
    monkeypatch.setattr(dashscope, "api_key", "previous-key", raising=False)
    factory = FakeCosyFactory(chunks=[b"never-called"])
    release = threading.Event()
    lock_taken = threading.Event()

    def hold_lock():
        tts_cosy._API_KEY_LOCK.acquire()
        lock_taken.set()
        release.wait(5.0)
        tts_cosy._API_KEY_LOCK.release()

    def lock_is_free():
        if tts_cosy._API_KEY_LOCK.acquire(blocking=False):
            tts_cosy._API_KEY_LOCK.release()
            return True
        return False

    holder = threading.Thread(target=hold_lock, daemon=True)
    holder.start()
    try:
        assert lock_taken.wait(2.0), "测试用的占锁线程没有起来"
        with pytest.raises(MediaCallError) as exc:
            await cosyvoice(factory)
        assert (exc.value.status, exc.value.code) == ("uncertain", "timeout")
        # 线程还在排队等锁；放开锁让它走到「已取消」检查。
        release.set()
        assert wait_until(lock_is_free), "占锁线程没有释放锁"
        # 等后台线程走完取消检查（它拿到锁后只做一次判断就返回）。
        time.sleep(0.2)
        assert factory.params is None and factory.texts == []
        assert dashscope.api_key == "previous-key"
    finally:
        release.set()
        holder.join(5.0)


@pytest.mark.anyio
async def test_cosyvoice_http_4xx_is_rejected_and_message_is_sanitized(dashscope_key):
    factory = FakeCosyFactory(raises=FakeSdkError("429 too many requests test-dashscope-key",
                                                 status_code=429))
    with pytest.raises(MediaCallError) as exc:
        await cosyvoice(factory)
    assert (exc.value.status, exc.value.code) == ("rejected", "FakeSdkError")
    assert "test-dashscope-key" not in exc.value.message

    failure = json.dumps({
        "header": {"event": "task-failed", "error_code": "InvalidParameter", "status_code": 400},
        "payload": {},
    })
    with pytest.raises(MediaCallError) as exc:
        await cosyvoice(FakeCosyFactory(failure=failure))
    assert (exc.value.status, exc.value.code) == ("rejected", "InvalidParameter")


@pytest.mark.anyio
async def test_cosyvoice_unknown_failure_is_uncertain(dashscope_key):
    factory = FakeCosyFactory(raises=RuntimeError("上游 502，正文包含 test-dashscope-key"))
    with pytest.raises(MediaCallError) as exc:
        await cosyvoice(factory)
    assert (exc.value.status, exc.value.code) == ("uncertain", "RuntimeError")
    assert "test-dashscope-key" not in exc.value.message
    assert "502" not in exc.value.code

    # 没有状态码的失败消息同理。
    with pytest.raises(MediaCallError) as exc:
        await cosyvoice(FakeCosyFactory(failure=json.dumps({"payload": {"code": "UnknownError"}})))
    assert (exc.value.status, exc.value.code) == ("uncertain", "UnknownError")


@pytest.mark.anyio
async def test_cosyvoice_transport_text_with_port_is_uncertain(dashscope_key):
    """断连文本里的 ``:443`` 不是 4xx：错误分类只看结构化状态码（规格 §2）。"""
    failures = [
        ConnectionError("Cannot connect to host dashscope.aliyuncs.com:443 ssl:default [reset]"),
        OSError("[Errno 54] Connection reset by peer wss://dashscope.aliyuncs.com:443/api-ws/v1/inference"),
    ]
    for failure in failures:
        with pytest.raises(MediaCallError) as exc:
            await cosyvoice(FakeCosyFactory(raises=failure))
        assert (exc.value.status, exc.value.code) == ("uncertain", type(failure).__name__)

    # task-failed 的说明文本里带端口 / 带「429ms」这类数字，同样不能当状态码。
    message = ("server busy, retry after 429ms；"
               "connect to wss://dashscope.aliyuncs.com:443/api-ws/v1/inference failed")
    with pytest.raises(MediaCallError) as exc:
        await cosyvoice(FakeCosyFactory(failure=json.dumps({
            "header": {"task_id": "abc", "event": "task-failed", "error_code": "InternalError",
                       "error_message": message},
            "payload": {},
        })))
    assert (exc.value.status, exc.value.code) == ("uncertain", "InternalError")

    # 整段失败信息就是纯文本（非 JSON）时也一样。
    with pytest.raises(MediaCallError) as exc:
        await cosyvoice(FakeCosyFactory(failure=f"task-failed: {message}"))
    assert (exc.value.status, exc.value.code) == ("uncertain", "upstream_error")


@pytest.mark.anyio
async def test_cosyvoice_structured_numeric_status_is_still_rejected(dashscope_key):
    """结构化的数值状态码仍然按 rejected 处理：429 与 400 都要释放预留。"""

    class StatusAttrError(Exception):
        status = 429

    class StatusCodeAttrError(Exception):
        status_code = 400

    for failure, code in ((StatusAttrError("too many requests"), "StatusAttrError"),
                          (StatusCodeAttrError("invalid parameter"), "StatusCodeAttrError")):
        with pytest.raises(MediaCallError) as exc:
            await cosyvoice(FakeCosyFactory(raises=failure))
        assert (exc.value.status, exc.value.code) == ("rejected", code)

    with pytest.raises(MediaCallError) as exc:
        await cosyvoice(FakeCosyFactory(failure=json.dumps({
            "header": {"event": "task-failed", "error_code": "Throttling", "status_code": 429},
            "payload": {},
        })))
    assert (exc.value.status, exc.value.code) == ("rejected", "Throttling")


@pytest.mark.anyio
async def test_cosyvoice_moderation_is_failed(dashscope_key):
    failure = json.dumps({
        "header": {"event": "task-failed", "error_code": "DataInspectionFailed",
                   "error_message": "text inspection failed", "status_code": 400},
        "payload": {},
    })
    with pytest.raises(MediaCallError) as exc:
        await cosyvoice(FakeCosyFactory(failure=failure))
    assert (exc.value.status, exc.value.code) == ("failed", "DataInspectionFailed")


@pytest.mark.anyio
async def test_cosyvoice_empty_audio_is_uncertain(dashscope_key):
    with pytest.raises(MediaCallError) as exc:
        await cosyvoice(FakeCosyFactory(chunks=[b""]))
    assert (exc.value.status, exc.value.code) == ("uncertain", "empty_audio")


@pytest.mark.anyio
async def test_cosyvoice_missing_key_never_builds_synthesizer(monkeypatch):
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    factory = FakeCosyFactory(chunks=[b"x"])
    with pytest.raises(MediaCallError) as exc:
        await cosyvoice(factory)
    assert (exc.value.status, exc.value.code) == ("failed", "missing_configuration")
    assert factory.params is None


def edge_events():
    fixture = read_fixture("edge-tts-20261016-131017.json")
    events = [{"type": "audio", "data": b"ID3\x04\x00"}, {"type": "audio", "data": b"mp3-payload"}]
    events += [{"type": "WordBoundary", "offset": item["offset"], "duration": item["duration"],
                "text": item["text"]} for item in fixture["word_boundaries"]]
    return fixture, events


@pytest.mark.anyio
async def test_edge_tts_declares_parameters_and_converts_word_boundaries():
    fixture, events = edge_events()
    factory = FakeEdgeFactory(events=events)
    text = fixture["parameters"]["text"]

    result = await tts_edge.synthesize_edge(text, voice="en-US-AndrewNeural", rate="+5%",
                                            pitch="-3Hz", communicate_factory=factory)

    assert factory.params == {"text": text, "voice": "en-US-AndrewNeural",
                              "rate": "+5%", "pitch": "-3Hz"}
    assert result.audio == b"ID3\x04\x00mp3-payload"
    assert result.audio_format == "mp3"
    assert result.sample_rate == 24000
    assert result.engine == "edge-tts"
    assert result.voice == "en-US-AndrewNeural"
    assert result.chars == len(text)
    # 100 纳秒 → 秒：1_000_000 ticks = 0.1s。
    assert len(result.words) == len(fixture["word_boundaries"]) == 14
    assert result.words[0] == {"offset_s": 0.1, "duration_s": 0.175, "text": "Let's"}
    assert result.words[-1]["offset_s"] == pytest.approx(4.3875)
    assert result.words[-1]["duration_s"] == pytest.approx(0.375)
    assert result.words[-1]["text"] == "dream"


@pytest.mark.anyio
async def test_edge_tts_without_boundaries_returns_empty_words():
    factory = FakeEdgeFactory(events=[{"type": "audio", "data": b"only-audio"}])
    result = await tts_edge.synthesize_edge("hello", voice="v", rate="+0%", pitch="+0Hz",
                                            communicate_factory=factory)
    assert result.words == []
    assert result.audio == b"only-audio"


@pytest.mark.anyio
async def test_edge_tts_empty_audio_is_uncertain():
    factory = FakeEdgeFactory(events=[{"type": "WordBoundary", "offset": 0, "duration": 0, "text": "hi"}])
    with pytest.raises(MediaCallError) as exc:
        await tts_edge.synthesize_edge("hello", voice="v", rate="+0%", pitch="+0Hz",
                                       communicate_factory=factory)
    assert (exc.value.status, exc.value.code) == ("uncertain", "empty_audio")


@pytest.mark.anyio
async def test_edge_tts_sdk_failure_is_uncertain_and_403_is_rejected():
    with pytest.raises(MediaCallError) as exc:
        await tts_edge.synthesize_edge("hello", voice="v", rate="+0%", pitch="+0Hz",
                                       communicate_factory=FakeEdgeFactory(raises=RuntimeError("boom")))
    assert (exc.value.status, exc.value.code) == ("uncertain", "RuntimeError")

    with pytest.raises(MediaCallError) as exc:
        await tts_edge.synthesize_edge("hello", voice="v", rate="+0%", pitch="+0Hz",
                                       communicate_factory=FakeEdgeFactory(
                                           raises=FakeSdkError("403 forbidden", status_code=403)))
    assert (exc.value.status, exc.value.code) == ("rejected", "FakeSdkError")


@pytest.mark.anyio
async def test_edge_tts_transport_text_with_port_is_uncertain():
    """aiohttp / edge-tts 的断连文本固定含 ``host:443``，不能当成 4xx。"""

    class ClientConnectorError(ConnectionError):
        pass

    for failure in (
        ClientConnectorError("Cannot connect to host speech.platform.bing.com:443 ssl:default [None]"),
        OSError("[Errno 54] Connection reset by peer wss://speech.platform.bing.com:443/consumer"),
    ):
        with pytest.raises(MediaCallError) as exc:
            await tts_edge.synthesize_edge("hello", voice="v", rate="+0%", pitch="+0Hz",
                                           communicate_factory=FakeEdgeFactory(raises=failure))
        assert (exc.value.status, exc.value.code) == ("uncertain", type(failure).__name__)


@pytest.mark.anyio
async def test_edge_tts_structured_numeric_status_is_still_rejected():
    class StatusAttrError(Exception):
        status = 429

    class StatusCodeAttrError(Exception):
        status_code = 400

    for failure, code in ((StatusAttrError("too many requests"), "StatusAttrError"),
                          (StatusCodeAttrError("bad request"), "StatusCodeAttrError")):
        with pytest.raises(MediaCallError) as exc:
            await tts_edge.synthesize_edge("hello", voice="v", rate="+0%", pitch="+0Hz",
                                           communicate_factory=FakeEdgeFactory(raises=failure))
        assert (exc.value.status, exc.value.code) == ("rejected", code)


@pytest.mark.anyio
async def test_edge_tts_timeout_is_uncertain(monkeypatch):
    monkeypatch.setattr(tts_edge, "SYNTHESIS_TIMEOUT_S", 0.05)
    started = time.monotonic()
    with pytest.raises(MediaCallError) as exc:
        await tts_edge.synthesize_edge("hello", voice="v", rate="+0%", pitch="+0Hz",
                                       communicate_factory=FakeEdgeFactory(block=5.0))
    assert (exc.value.status, exc.value.code) == ("uncertain", "timeout")
    assert time.monotonic() - started < 2


@pytest.mark.anyio
async def test_edge_tts_unavailable_is_uncertain_without_request(monkeypatch):
    # sys.modules 里塞 None 会让 import edge_tts 抛 ImportError。
    monkeypatch.setitem(sys.modules, "edge_tts", None)
    with pytest.raises(MediaCallError) as exc:
        await tts_edge.synthesize_edge("hello", voice="v", rate="+0%", pitch="+0Hz")
    assert (exc.value.status, exc.value.code) == ("uncertain", "edge_tts_unavailable")


def test_adapters_defer_sdk_imports():
    """导入两个适配器模块本身不得拉起 dashscope / edge_tts（含未安装 edge-tts 的场景）。"""
    code = ("import sys; import studio.providers.tts_cosy, studio.providers.tts_edge; "
            "print('dashscope' in sys.modules, 'edge_tts' in sys.modules)")
    env = dict(os.environ, PYTHONPATH=str(BACKEND_ROOT))
    done = subprocess.run([sys.executable, "-c", code], cwd=BACKEND_ROOT, env=env,
                          capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "False False"
