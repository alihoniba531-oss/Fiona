"""独立语音探针；SDK 仅在选中相应子命令后导入。"""
from __future__ import annotations

import asyncio
from contextlib import redirect_stderr, redirect_stdout
import importlib
from importlib import metadata
import inspect
import io
import json
import re
import threading

from _studio_probe_common import MAX_MEDIA_BYTES, ProbeFailure, error_details


DEFAULT_VOICE = "longxiaoxia_v2"


def quote(args, rt):
    count = len(args.text)
    # 字数只用于估价；0.01–0.5 是本期单次探针的参考区间，不代表官方报价。
    estimated = count * 0.2 / 1000
    return {"min_cny": max(0.01, min(0.5, estimated * .5)),
            "max_cny": max(0.01, min(0.5, estimated * 2 + .01)),
            "characters": count, "note": "按字数估算，单价待核实；参考区间 0.01–0.50 元，以账单为准"}


def edge_module():
    try:
        module = importlib.import_module("edge_tts")
    except ImportError:
        return None, None
    version = getattr(module, "__version__", None)
    if version is None:
        try:
            version = metadata.version("edge-tts")
        except metadata.PackageNotFoundError:
            pass
    return module, version


def _timestamp_samples(value):
    samples = []
    if isinstance(value, dict):
        if any(key in value for key in ("words", "word_timestamps", "timestamps", "begin_time", "start_time", "offset")):
            samples.append(value)
        else:
            for child in value.values():
                samples.extend(_timestamp_samples(child))
    elif isinstance(value, list):
        for child in value:
            samples.extend(_timestamp_samples(child))
    return samples[:20]


def run_cosyvoice(args, rt, record):
    import dashscope
    from dashscope.audio.tts_v2 import AudioFormat, ResultCallback, SpeechSynthesizer

    if not args.text.strip():
        raise ProbeFailure("error", "配音文本不能为空")
    complete = threading.Event()
    chunks = bytearray()
    events = []
    failures = []

    class Callback(ResultCallback):
        def on_open(self):
            pass

        def on_close(self):
            pass

        def on_data(self, data):
            if failures:
                return
            if len(chunks) + len(data) > MAX_MEDIA_BYTES:
                failures.append(ProbeFailure("error", "语音返回超过 300MB"))
                complete.set()
                return
            chunks.extend(data)

        def on_event(self, message):
            try:
                events.append(json.loads(message) if isinstance(message, str) else message)
            except ValueError:
                events.append({"message": str(message)})

        def on_complete(self):
            complete.set()

        def on_error(self, message):
            try:
                data = json.loads(message) if isinstance(message, str) else message
            except ValueError:
                data = {"message": str(message)}
            code, detail = error_details(data)
            failures.append(ProbeFailure("rejected", detail, code=code, response=data))
            complete.set()

    class ProbeSynthesizer(SpeechSynthesizer):
        def async_streaming_complete(self, complete_timeout_millis=120000):
            # 当前 SDK 的 call 在有 callback 时会启动一个未托管等待线程。
            # 复用公开同步完成方法收尾；仍只有一次 run-task 和一次 call。
            return self.streaming_complete(complete_timeout_millis)

        def on_error(self, ws, error):
            # SDK 默认会从后台线程直接打印原始异常；在这里仅收集，不输出。
            status = getattr(error, "status_code", None)
            failures.append(ProbeFailure("rejected" if status is not None else "uncertain",
                                         str(error), code=type(error).__name__, http_status=status))
            complete.set()
            for name in ("start_event", "complete_event"):
                event = getattr(self, name, None)
                if event is not None:
                    event.set()

    params = {"model": args.model, "voice": args.voice,
              "format": AudioFormat.WAV_48000HZ_MONO_16BIT, "callback": Callback()}
    supported = inspect.signature(SpeechSynthesizer).parameters
    timestamp_parameter = next((name for name in ("word_timestamp_enabled", "enable_word_timestamp")
                                if name in supported), None)
    if timestamp_parameter:
        params[timestamp_parameter] = True
    # 当前 SDK 没有重试参数，且单次 call 没有重连循环；以后出现参数时显式关闭。
    for name in ("max_retries", "retry_count"):
        if name in supported:
            params[name] = 0
    record.update(timestamp_support="已请求" if timestamp_parameter else "不支持：当前 SDK 未提供逐词或逐字时间戳参数",
                  requested_audio={"format": "wav", "sample_rate": 48000, "channels": 1, "bits_per_sample": 16})
    record["request"] = {"transport": "dashscope-websocket", "body": {
        "model": args.model, "voice": args.voice, "text": args.text,
        "format": "wav", "sample_rate": 48000,
        **({timestamp_parameter: True} if timestamp_parameter else {}),
    }}
    previous_key = dashscope.api_key
    dashscope.api_key = rt.require_env("DASHSCOPE_API_KEY")
    synth = None
    try:
        # SDK 的 WebSocket 错误回调可能直接 print；原始输出不进入终端或日志。
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            synth = ProbeSynthesizer(**params)

            def once():
                started = rt.monotonic()
                try:
                    result = synth.call(args.text, timeout_millis=120000)
                except Exception:
                    if failures:
                        raise failures[0]
                    raise
                if isinstance(result, bytes):
                    chunks.extend(result)
                    complete.set()
                if not complete.wait(max(0, 120 - (rt.monotonic() - started))):
                    raise TimeoutError("CosyVoice 等待完整响应超时")
                if failures:
                    raise failures[0]
                if not chunks:
                    raise ProbeFailure("uncertain", "CosyVoice 未返回完整音频")

            rt.paid_call(record, once)
            response = synth.get_response() if hasattr(synth, "get_response") else None
            record["response"] = response
            record["events"] = events
    finally:
        try:
            if synth is not None and hasattr(synth, "close"):
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    synth.close()
        except Exception:
            pass
        dashscope.api_key = previous_key
        record["events"] = events
        record["timestamps"] = _timestamp_samples(events)
        record["has_timestamps"] = bool(record["timestamps"])
    path = rt.save_media(bytes(chunks), ".wav", record)
    record["ffprobe"] = rt.probe_media(path)
    record["usage"] = (record.get("response") or {}).get("usage") if isinstance(record.get("response"), dict) else None
    record["actual_cost_cny"] = None
    record["billing_note"] = "返回字段原样保留，未提供可核实单价时不伪造实付金额"
    record["status"] = "succeeded"


def run_edge(args, rt, record):
    module, version = edge_module()
    if module is None:
        raise ProbeFailure("skipped", "未安装 edge_tts（需要 ≥7.3.1），跳过")
    parts = tuple(int(item) for item in re.findall(r"\d+", str(version))[:3])
    if parts < (7, 3, 1):
        raise ProbeFailure("skipped", "edge_tts 版本无法确认或低于 7.3.1，跳过")
    record.update(edge_tts_version=version, word_boundaries=[], http_403=False,
                  request={"body": {"text": args.text, "voice": args.voice}})
    audio = bytearray()

    async def collect():
        options = {"text": args.text, "voice": args.voice}
        if "boundary" in inspect.signature(module.Communicate).parameters:
            options["boundary"] = "WordBoundary"
        communication = module.Communicate(**options)
        async for event in communication.stream():
            if event["type"] == "audio":
                audio.extend(event["data"])
                if len(audio) > MAX_MEDIA_BYTES:
                    raise ProbeFailure("error", "英文配音超过 300MB")
            elif event["type"] == "WordBoundary" and len(record["word_boundaries"]) < 20:
                record["word_boundaries"].append(event)

    try:
        asyncio.run(asyncio.wait_for(collect(), timeout=120))
    except ProbeFailure:
        raise
    except Exception as exc:
        status = getattr(exc, "status", getattr(exc, "status_code", None))
        record["http_403"] = status == 403 or bool(re.search(r"\b403\b", str(exc)))
        raise ProbeFailure("rejected" if record["http_403"] else "error", str(exc),
                           code=type(exc).__name__, http_status=status) from None
    path = rt.save_media(bytes(audio), ".mp3", record)
    record.update(ffprobe=rt.probe_media(path), status="succeeded", actual_cost_cny=0)
