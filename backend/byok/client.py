"""Per-request SDK clients and compatible text streams with bounded lifetimes."""
from __future__ import annotations

from copy import deepcopy
import logging
import math
import os
import re
import socket
from threading import Lock, Timer
from types import SimpleNamespace

import anthropic
import httpx
import openai

from .crypto import ensure_available
from .errors import ByokTimeoutError, EmptyReplyError, NeedsReentryError, RefusalError
from .providers import PROVIDERS, validate_model, validate_provider
from .url_safety import PinnedTransport, normalize_custom_base_url

_warned: set[str] = set()


def _setting(name: str, default: float, minimum: float, maximum: float, *, integer: bool = False):
    raw = os.getenv(name, str(default))
    try:
        if integer and not re.fullmatch(r"[0-9]+", raw):
            raise ValueError
        value = int(raw) if integer else float(raw)
        if not math.isfinite(value) or not minimum <= value <= maximum:
            raise ValueError
        return value
    except (ValueError, OverflowError):
        if name not in _warned:
            _warned.add(name)
            logging.getLogger(__name__).warning("BYOK setting invalid category=%s", name)
        return int(default) if integer else default


def max_streams() -> int:
    return _setting("FIONA_BYOK_MAX_STREAMS", 8, 1, 64, integer=True)


def total_seconds() -> float:
    return _setting("FIONA_BYOK_TOTAL_SECONDS", 120.0, 10, 240)


def convert_messages(provider: str, messages: list[dict], username: str) -> tuple[str, list[dict]]:
    """Copy the caller's messages; only system prompts contain redacted account ids."""
    copied = deepcopy(messages)
    for message in copied:
        if message.get("role") == "system" and isinstance(message.get("content"), str) and len(username) >= 3:
            message["content"] = message["content"].replace(username, "（账号已隐藏）")
    if provider == "dashscope":
        return "", copied
    system = "\n\n".join(message["content"] for message in copied if message.get("role") == "system" and isinstance(message.get("content"), str) and message["content"])
    normalized: list[dict] = []
    for message in copied:
        role, content = message.get("role"), message.get("content")
        if role not in {"user", "assistant"} or not isinstance(content, str) or not content.strip():
            continue
        if not normalized and role == "assistant":
            continue
        if normalized and normalized[-1]["role"] == role:
            normalized[-1]["content"] += "\n\n" + content
        else:
            normalized.append({"role": role, "content": content})
    while normalized and normalized[-1]["role"] == "assistant":
        normalized.pop()
    return system, normalized if provider == "anthropic" else ([{"role": "system", "content": system}] if system else []) + normalized


def _chunk(text: str | None, finish_reason: str | None = None):
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=text), finish_reason=finish_reason)])


class ReplyInterruptedError(Exception):
    """The request owner cancelled a reply, without replacing cancellation."""


class ReplyStreamControl:
    """Request-scoped abort handle, usable before SDK stream creation returns."""
    def __init__(self):
        self.lock = Lock()
        self.resources = None
        self.aborted = False

    def bind(self, resources):
        with self.lock:
            self.resources = resources
            aborted = self.aborted
        if aborted:
            resources.abort()

    def abort(self) -> None:
        with self.lock:
            self.aborted = True
            resources = self.resources
        if resources is not None:
            resources.abort()


class _Resources:
    def __init__(self):
        self.client = None
        self.http_client = None
        self.stream = None
        self.manager = None
        self.transport = None
        self.closed = False
        self.disposed = False
        self.timed_out = False
        self.lock = Lock()
        self.timer = Timer(total_seconds(), self.expire)
        self.timer.daemon = True

    def start(self):
        self.timer.start()

    def expire(self):
        with self.lock:
            if self.closed:
                return
            self.timed_out = True
            self.closed = True
        self._interrupt()

    def attach_stream(self, stream, manager=None):
        with self.lock:
            self.stream = stream
            self.manager = manager
            closed = self.closed
        if closed:
            self.close()
            raise ByokTimeoutError if self.timed_out else ReplyInterruptedError

    def attach_client(self, sdk_client):
        with self.lock:
            self.client = sdk_client
            closed = self.closed
        if closed:
            self.close()
            raise ByokTimeoutError if self.timed_out else ReplyInterruptedError

    def _interrupt(self):
        # Both SDKs expose the underlying response and network stream publicly.
        try:
            response = getattr(self.stream, "response", None)
            network_stream = response.extensions.get("network_stream") if response is not None else None
            sock = network_stream.get_extra_info("socket") if network_stream is not None else None
            if sock is not None:
                sock.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass
        # Custom connections may exist before an SDK response is available.
        if self.transport is not None:
            try:
                self.transport.abort()
            except Exception:
                pass

    def abort(self):
        # Closing a socket in another thread can lose the shutdown wakeup.
        # Only the consumer closes handles after its blocking call returns.
        with self.lock:
            if self.closed:
                return
            self.closed = True
        self.timer.cancel()
        self._interrupt()

    def _close_handles(self):
        for handle in (self.stream, self.client, self.http_client):
            if handle is not None:
                try:
                    handle.close()
                except Exception:
                    pass
        if self.manager is not None:
            try:
                self.manager.__exit__(None, None, None)
            except Exception:
                pass

    def close(self):
        with self.lock:
            if self.disposed:
                return
            interrupted = self.closed
            self.closed = True
            self.disposed = True
        self.timer.cancel()
        if not interrupted:
            self._interrupt()
        self._close_handles()


class ReplyStream:
    """One consumer, compatible chunks, and explicit final stop semantics."""
    def __init__(self, resources: _Resources, *, anthropic_stream: bool, character_limit: int):
        self.resources = resources
        self.anthropic_stream = anthropic_stream
        self.character_limit = character_limit
        self.stop_reason: str | None = None
        self.refused = False
        self.text_length = 0
        self._iterator = self._consume()

    def __iter__(self):
        return self

    def __next__(self):
        return next(self._iterator)

    def _consume(self):
        resources = self.resources
        try:
            source = resources.stream.text_stream if self.anthropic_stream else resources.stream
            for item in source:
                if resources.timed_out:
                    raise ByokTimeoutError
                if resources.closed:
                    raise ReplyInterruptedError
                finish = None
                if self.anthropic_stream:
                    text = item if isinstance(item, str) else None
                else:
                    choices = getattr(item, "choices", None)
                    if not choices:
                        continue
                    choice = choices[0]
                    text = getattr(choice.delta, "content", None)
                    finish = getattr(choice, "finish_reason", None)
                    if finish:
                        self.stop_reason = finish
                if isinstance(text, str) and text:
                    remaining = self.character_limit - self.text_length
                    if len(text) > remaining:
                        self.stop_reason = "max_tokens"
                        self.text_length += remaining
                        # Close immediately, even if the consumer pauses at this yield.
                        resources.close()
                        yield _chunk(text[:remaining] or None, "length")
                        return
                    self.text_length += len(text)
                    yield _chunk(text, "length" if finish in {"length", "max_tokens"} else None)
                elif finish in {"length", "max_tokens"}:
                    yield _chunk(None, "length")
            if resources.timed_out:
                raise ByokTimeoutError
            if resources.closed:
                raise ReplyInterruptedError
            if self.anthropic_stream:
                final = resources.stream.get_final_message()
                self.stop_reason = final.stop_reason
                self.refused = final.stop_reason == "refusal"
                if final.stop_reason == "max_tokens":
                    yield _chunk(None, "length")
        except Exception:
            if resources.timed_out:
                raise ByokTimeoutError from None
            raise
        finally:
            resources.close()

    def close(self) -> None:
        self.resources.close()

    def abort(self) -> None:
        self.resources.abort()


def _open(config: dict, messages: list[dict], *, mirror: bool, username: str, testing: bool, control: ReplyStreamControl | None = None) -> ReplyStream:
    ensure_available()
    provider = validate_provider(config.get("provider"))
    model = validate_model(provider, config.get("model"))
    api_key = config.get("api_key")
    if not isinstance(api_key, str) or not api_key:
        raise NeedsReentryError
    spec = PROVIDERS[provider]
    base_url = normalize_custom_base_url(config.get("base_url")) if provider == "custom" else spec["base_url"]
    system, prepared = convert_messages(provider, messages, username)
    resources = _Resources()
    if control is not None:
        control.bind(resources)
        if control.aborted:
            raise ReplyInterruptedError
    try:
        if provider == "anthropic":
            resources.attach_client(anthropic.Anthropic(api_key=api_key, base_url=base_url, timeout=60.0, max_retries=0))
            kwargs = {"model": model, "messages": prepared,
                      "max_tokens": 1024 if testing else (2048 if mirror else 4096), "output_config": {"effort": "low"}}
            if system:
                kwargs["system"] = system
            endpoint = resources.client.messages
            if model in {"claude-opus-5-5", "claude-sonnet-5-5"}:
                endpoint = resources.client.beta.messages
                kwargs.update(betas=["server-side-fallback-2026-07-01"], fallbacks="default")
            resources.start()
            if resources.closed:
                raise ByokTimeoutError if resources.timed_out else ReplyInterruptedError
            manager = endpoint.stream(**kwargs)
            resources.attach_stream(manager.__enter__(), manager)
        else:
            client_kwargs = {"api_key": api_key, "base_url": base_url, "timeout": 60.0, "max_retries": 0}
            if provider == "custom":
                resources.transport = PinnedTransport(base_url)
                resources.http_client = httpx.Client(transport=resources.transport, follow_redirects=False, trust_env=False, timeout=60.0)
                client_kwargs["http_client"] = resources.http_client
            resources.attach_client(openai.OpenAI(**client_kwargs))
            kwargs = {"model": model, "messages": prepared, "stream": True, "max_tokens": 16 if testing else (512 if mirror else 2048)}
            if spec.get("extra_body"):
                kwargs["extra_body"] = deepcopy(spec["extra_body"])
            resources.start()
            if resources.closed:
                raise ByokTimeoutError if resources.timed_out else ReplyInterruptedError
            resources.attach_stream(resources.client.chat.completions.create(**kwargs))
        return ReplyStream(resources, anthropic_stream=provider == "anthropic", character_limit=600 if mirror else 4000)
    except Exception:
        resources.close()
        if resources.timed_out:
            raise ByokTimeoutError from None
        raise


def open_reply_stream(config: dict, messages: list[dict], *, mirror: bool, username: str, control: ReplyStreamControl | None = None) -> ReplyStream:
    return _open(config, messages, mirror=mirror, username=username, testing=False, control=control)


def test_connection(config: dict, *, control: ReplyStreamControl | None = None) -> None:
    stream = _open(config, [{"role": "user", "content": "只回复：好"}], mirror=False, username="", testing=True, control=control)
    try:
        for _ in stream:
            pass
        if stream.text_length == 0:
            raise RefusalError if stream.refused else EmptyReplyError
    finally:
        stream.close()
