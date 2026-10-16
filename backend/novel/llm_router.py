"""Provider routing, bounded retries, cache reuse and atomic token reservations."""

from __future__ import annotations

import asyncio
import copy
import inspect
import json
import os
import time

from .fake_llm import FakeLLM, input_characters
from .prompt_rules import JSON_STRING_QUOTE_RULE
from .run_store import ConfigurationError, StepStore
from .billing import InsufficientStrawberries, NovelBilling, NovelBudgetExceeded, RunNoLongerActive


PROVIDERS = {
    "dashscope": ("https://dashscope.aliyuncs.com/compatible-mode/v1", "DASHSCOPE_API_KEY"),
    "deepseek": ("https://api.deepseek.com", "DEEPSEEK_API_KEY"),
    "anthropic": ("https://api.anthropic.com", "ANTHROPIC_API_KEY"),
    "ark": ("https://ark.cn-beijing.volces.com/api/v3", "ARK_API_KEY"),
}
MODEL_ALLOWLISTS = {
    "ark": frozenset({"doubao-seed-2-1-pro-260915", "doubao-seed-2-1-pro-260628"}),
}
ARK_MODELS = MODEL_ALLOWLISTS["ark"]
POLLUTING_VARIABLES = ("ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN",
                       "ANTHROPIC_CUSTOM_HEADERS", "OPENAI_BASE_URL")
CLAUDE_THINKING = {
    "claude-sonnet-5-5": {"type": "between_tools"},
    "claude-haiku-5-5": {"type": "disabled"},
    "claude-opus-5-5": None,
}
KNOWN_MODELS = {
    "anthropic": frozenset(CLAUDE_THINKING),
    "dashscope": frozenset({"qwen3.8-max", "qwen3.8-omni-flash", "qwen3.8-flash"}),
    "deepseek": frozenset({"deepseek-flash", "deepseek-v4-pro"}),
    "ark": ARK_MODELS,
}


async def maybe_await(value):
    """File storage is synchronous; database storage uses the same protocol."""
    return await value if inspect.isawaitable(value) else value


class BudgetExhausted(RuntimeError):
    exit_code = 3
    status = "budget_exhausted"


class StepFailed(RuntimeError):
    exit_code = 4

    def __init__(self, message="步骤失败，请检查步骤记录后续跑", *, status="step_failed", step_key=None):
        super().__init__(message)
        self.status = status
        self.step_key = step_key


def parse_model(model: str):
    if not isinstance(model, str) or ":" not in model:
        raise ConfigurationError("模型规格必须为 提供方:型号")
    provider, name = model.split(":", 1)
    if provider not in (*PROVIDERS, "fake", "byok") or not name.strip():
        raise ConfigurationError("模型提供方必须为 dashscope、deepseek、anthropic、ark、byok 或 fake，且型号非空")
    if provider == "byok" and name != "self":
        raise ConfigurationError("自带模型规格必须为 byok:self")
    if provider == "ark" and name not in ARK_MODELS:
        raise ConfigurationError("火山方舟型号未在白名单内")
    return provider, name


def validate_environment(models, dry_run=False, environ=None):
    """Only inspect environment variables when a real provider is selected."""
    values = list(models.values()) if isinstance(models, dict) else [models] if isinstance(models, str) else list(models)
    providers = {parse_model(model)[0] for model in values}
    real = providers - {"fake", "byok"}
    if dry_run or not real:
        return
    environment = os.environ if environ is None else environ
    polluted = [name for name in POLLUTING_VARIABLES if environment.get(name)]
    if polluted:
        raise ConfigurationError("请先 unset 这些变量：" + "、".join(polluted))
    missing = [PROVIDERS[provider][1] for provider in sorted(real)
               if not environment.get(PROVIDERS[provider][1])]
    if missing:
        raise ConfigurationError("缺少环境变量：" + "、".join(missing))


def validate_model_settings(models, dry_run=False, *, announce=True):
    """Check real Claude settings before inspecting keys or constructing clients."""
    values = list(models.values()) if isinstance(models, dict) else [models] if isinstance(models, str) else list(models)
    parsed = [parse_model(model) for model in values]
    if dry_run:
        return
    names = {name for provider, name in parsed if provider == "anthropic"}
    if names - CLAUDE_THINKING.keys():
        raise ConfigurationError("未知的 Claude 型号，无法确定如何关闭思考")
    if announce and "claude-opus-5-5" in names:
        print("opus-5-5 无法关闭思考，输出 token 会显著增加")


def _get(value, key, default=None):
    return value.get(key, default) if isinstance(value, dict) else getattr(value, key, default)


def normalize_openai_usage(usage):
    details = _get(usage, "prompt_tokens_details")
    cached = _get(details, "cached_tokens")
    if cached is None:
        cached = _get(usage, "prompt_cache_hit_tokens", 0)
    return {"input_tokens": int(_get(usage, "prompt_tokens", 0) or 0),
            "output_tokens": int(_get(usage, "completion_tokens", 0) or 0),
            "cached_tokens": int(cached or 0)}


def normalize_anthropic_usage(usage):
    return {"input_tokens": int(_get(usage, "input_tokens", 0) or 0),
            "output_tokens": int(_get(usage, "output_tokens", 0) or 0),
            "cached_tokens": int(_get(usage, "cache_read_input_tokens", 0) or 0)}


def is_retryable(exc):
    import anthropic
    import httpx
    import httpx2
    import openai

    code = getattr(exc, "status_code", None)
    if code is None:
        code = getattr(getattr(exc, "response", None), "status_code", None)
    connection_errors = (anthropic.APIConnectionError, openai.APIConnectionError,
                         httpx.ConnectError, httpx.RemoteProtocolError,
                         httpx2.ConnectError, httpx2.RemoteProtocolError)
    return isinstance(exc, (TimeoutError, ConnectionError, *connection_errors)) or "Timeout" in type(exc).__name__ or code == 429 or (
        isinstance(code, int) and 500 <= code <= 599)


def _exception_metadata(exc):
    """Persist diagnostics without recording provider messages or response bodies."""
    errors = [type(exc).__name__]
    code = getattr(exc, "status_code", None)
    if code is None:
        code = getattr(getattr(exc, "response", None), "status_code", None)
    if isinstance(code, int):
        errors.append(f"HTTP {code}")
    return errors


class LLMRouter:
    def __init__(self, store: StepStore, *, fake=None, dry_run=False, billing=None, byok_bridge=None):
        self.store = store
        self.fake = fake if fake is not None else FakeLLM()
        self.dry_run = bool(dry_run)
        self.retry_delay = 5
        self._clients = {}
        self._step_locks = {}
        self.billing = billing
        self.byok_bridge = byok_bridge

    async def _single_real_call(self, request):
        """The sole real-call seam; tests replace it without constructing SDKs."""
        provider, name = parse_model(request["model"])
        byok = provider == "byok"
        resolved = None
        if byok:
            if self.byok_bridge is None:
                raise ConfigurationError("请先启用可用于小说工坊的自带模型")
            resolved = await self.byok_bridge.resolve()
            provider, name = resolved["provider"], resolved["model"]
            base_url, api_key = resolved["base_url"], resolved["api_key"]
            validate_model_settings([f"{provider}:{name}"], announce=False)
        else:
            validate_model_settings([request["model"]], announce=False)
            validate_environment([request["model"]])
            base_url, key_name = PROVIDERS[provider]
            api_key = os.environ[key_name]
        if byok or provider not in self._clients:
            if provider == "anthropic":
                from anthropic import AsyncAnthropic
                client = AsyncAnthropic(base_url=base_url, api_key=api_key,
                                        timeout=300, max_retries=0)
            else:
                from openai import AsyncOpenAI
                client = AsyncOpenAI(base_url=base_url, api_key=api_key,
                                    timeout=300, max_retries=0)
            if not byok:
                self._clients[provider] = client
        else:
            client = self._clients[provider]
        try:
            return await self._provider_call(client, provider, name, request)
        finally:
            if byok:
                try:
                    await client.close()
                finally:
                    resolved.clear()
                    api_key = None

    async def _provider_call(self, client, provider, name, request):
        """Shared provider construction for platform and ephemeral BYOK calls."""
        if provider == "anthropic":
            systems = [message["content"] for message in request["messages"] if message["role"] == "system"]
            messages = copy.deepcopy([message for message in request["messages"] if message["role"] != "system"])
            for message in messages:
                if message["role"] == "user":
                    if isinstance(message["content"], str):
                        message["content"] = [{"type": "text", "text": message["content"],
                                               "cache_control": {"type": "ephemeral"}}]
                    elif message["content"]:
                        message["content"][-1]["cache_control"] = {"type": "ephemeral"}
                    break
            parameters = {"model": name, "system": [{"type": "text", "text": "\n\n".join(systems),
                                                       "cache_control": {"type": "ephemeral"}}], "messages": messages,
                          "max_tokens": request["max_tokens"]}
            thinking = CLAUDE_THINKING[name]
            if thinking is not None:
                parameters["thinking"] = copy.deepcopy(thinking)
            response = await client.messages.create(**parameters)
            raw = "".join(_get(block, "text", "") for block in response.content if _get(block, "type") == "text")
            usage = _get(response, "usage")
            complete_usage = usage is not None and all(_get(usage, key) is not None
                                                        for key in ("input_tokens", "output_tokens"))
            return raw, normalize_anthropic_usage(usage) if complete_usage else None, _get(response, "stop_reason")
        parameters = {"model": name, "messages": request["messages"], "max_tokens": request["max_tokens"],
                      "extra_body": {"enable_thinking": False} if provider == "dashscope" else
                                    {"thinking": {"type": "disabled"}}}
        if request["output"] == "json":
            parameters["response_format"] = {"type": "json_object"}
        response = await client.chat.completions.create(**parameters)
        choice = response.choices[0]
        reason = _get(choice, "finish_reason")
        reason = {"length": "max_tokens", "content_filter": "refusal"}.get(reason, reason)
        usage = _get(response, "usage")
        complete_usage = usage is not None and all(_get(usage, key) is not None
                                                    for key in ("prompt_tokens", "completion_tokens"))
        return choice.message.content or "", normalize_openai_usage(usage) if complete_usage else None, reason

    async def _reserve(self, amount):
        async with self.store.budget_lock:
            if self.store.total_tokens + self.store.reserved_tokens + amount > self.store.max_total_tokens:
                raise BudgetExhausted("预计调用将超过 max-total-tokens；放宽预算后可在相同 --out 续跑")
            self.store.reserved_tokens += amount

    @staticmethod
    def _response_parts(response, request):
        stop_reason = None
        if isinstance(response, tuple):
            if len(response) == 3:
                raw, usage, stop_reason = response
            else:
                raw, usage = response
        elif isinstance(response, dict) and ("text" in response or "raw_response" in response):
            raw = response.get("text", response.get("raw_response"))
            usage = response.get("usage", {})
            stop_reason = response.get("stop_reason")
        else:
            raw, usage = response, {}
        if not isinstance(raw, str):
            raw = json.dumps(raw, ensure_ascii=False)
        usage = {"input_tokens": int(_get(usage, "input_tokens", input_characters(request["messages"])) or 0),
                 "output_tokens": int(_get(usage, "output_tokens", len(raw)) or 0),
                 "cached_tokens": int(_get(usage, "cached_tokens", 0) or 0)}
        stop_reason = {"length": "max_tokens", "content_filter": "refusal"}.get(stop_reason, stop_reason)
        return raw, usage, stop_reason

    async def _attempt(self, request, attempt):
        input_chars = input_characters(request["messages"])
        reservation = input_chars + request["max_tokens"]
        await self._reserve(reservation)
        started = time.monotonic()
        raw = ""
        stop_reason = None
        usage = {"input_tokens": 0, "output_tokens": 0, "cached_tokens": 0}
        succeeded = False
        billed = False
        invoked = False
        record = {key: request[key] for key in ("experiment", "arm", "chapter", "role", "model", "step_key")}
        try:
            provider, _ = parse_model(request["model"])
            if self.billing is not None and not self.dry_run and provider != "fake":
                billed = bool(await self.billing.reserve(request))
            invoked = True
            response = await self.fake(request) if self.dry_run or provider == "fake" else await self._single_real_call(request)
            raw, usage, stop_reason = self._response_parts(response, request)
            if isinstance(response, tuple):
                supplied = response[1] if len(response) > 1 else None
            elif isinstance(response, dict):
                supplied = response.get("usage")
            else:
                supplied = None
            record["billing_pending"] = billed
            record["known_usage"] = supplied is not None and all(_get(supplied, key) is not None
                                                                for key in ("input_tokens", "output_tokens"))
            succeeded = True
        finally:
            duration = round((time.monotonic() - started) * 1000, 3)
            record.update(usage, duration_ms=duration, attempts=1, attempt_index=attempt, ok=succeeded,
                          input_chars=input_chars, max_tokens=request["max_tokens"],
                          provider="fake" if self.dry_run else parse_model(request["model"])[0],
                          stop_reason=stop_reason)
            async def finish_usage():
                async with self.store.budget_lock:
                    self.store.reserved_tokens -= reservation
                    if invoked:
                        await maybe_await(self.store.append_usage(record))
            try:
                await NovelBilling._drain(finish_usage())
            except BaseException:
                if billed:
                    await self._refund_attempt(request)
                raise
            if billed and not succeeded:
                await self._refund_attempt(request)
            if invoked:
                if getattr(self.store, "novel_id", None) is not None:
                    print(f"novel_id={self.store.novel_id} chapter={request['chapter']} "
                          f"role={request['role']} model={request['model']} "
                          f"input_tokens={usage['input_tokens']} output_tokens={usage['output_tokens']} "
                          f"cached_tokens={usage['cached_tokens']} duration_ms={duration:.1f} "
                          f"status={'ok' if succeeded else 'failed'}")
                else:
                    print(f"实验={request['experiment']} 章节={request['chapter']} 阶段={request['task']} "
                          f"角色={request['role']} 模型={request['model']} "
                          f"token={usage['input_tokens'] + usage['output_tokens']} 耗时={duration:.1f}ms")
        return raw, usage, record

    async def _refund_attempt(self, request):
        try:
            await self.billing.refund(request)
        except RunNoLongerActive:
            # Deletion/recovery refunds before invalidating the worker.
            pass

    async def _complete_response(self, request, raw, usage_record, totals, attempts, started, validator):
        """Validate and durably complete one received response, without network I/O.

        The caller shields and drains this short phase. Valid output and its
        charge share one commit; invalid actual attempts are still charged.
        """
        stop_reason = usage_record["stop_reason"]
        billed = usage_record.get("billing_pending", False)
        actual_usage = usage_record if usage_record.get("known_usage") else None
        settled = False
        try:
            result, errors = None, []
            if stop_reason not in {"refusal", "max_tokens"}:
                try:
                    if request["output"] == "json":
                        from .schemas import parse_json
                        result = parse_json(raw)
                    else:
                        result = raw
                    if validator is not None:
                        checked = validator(result)
                        if inspect.isawaitable(checked):
                            checked = await checked
                        if checked is not None:
                            result = checked
                except Exception as exc:
                    declared = getattr(exc, "errors", None)
                    errors = [str(item)[:500] for item in declared] if isinstance(declared, (list, tuple)) else [
                        "JSON 解析或字段校验失败，请检查格式和字段约束。"]
                    diagnostics = _exception_metadata(exc)
                else:
                    await self._save_step(request, raw, result, totals, attempts, started, "ok", [],
                                          stop_reason=stop_reason, bill=billed, billing_usage=actual_usage)
                    settled = True
                    return True, result, [], []
            else:
                errors, diagnostics = [stop_reason], []
            await maybe_await(self.store.mark_usage(usage_record, ok=False))
            if billed:
                await self.billing.settle(request, actual_usage)
                settled = True
            return False, result, errors, diagnostics
        finally:
            if billed and not settled:
                # After settlement this is an idempotent no-op. Before a
                # successful commit it returns the entire reservation.
                await self._refund_attempt(request)

    async def call(self, *, step_key, role, model, messages, max_tokens, validator=None, output="json",
                   experiment=None, arm="", chapter=0, failure_status="step_failed"):
        parse_model(model)
        if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or max_tokens < 1:
            raise ConfigurationError("max_tokens 必须为正整数")
        lock = self._step_locks.setdefault(str(step_key), asyncio.Lock())
        async with lock:
            cached = await maybe_await(self.store.read_step(step_key))
            if cached is not None and cached.get("status") == "ok":
                return copy.deepcopy(cached["result"])
            request = {"step_key": str(step_key), "role": role, "model": model,
                       "messages": copy.deepcopy(messages), "max_tokens": max_tokens, "output": output,
                       "experiment": experiment or self.store.manifest.get("experiment", ""),
                       "arm": arm, "chapter": chapter}
            request["task"] = FakeLLM.payload(request).get("task", role)
            return await self._with_retries(request, validator, failure_status)

    async def _with_retries(self, request, validator, failure_status):
        """One network retry and one repair retry, shared by every pipeline step."""
        network_retries = validation_retries = attempts = 0
        started = time.monotonic()
        raw = ""
        stop_reason = None
        result = None
        totals = {"input_tokens": 0, "output_tokens": 0, "cached_tokens": 0}
        errors = []
        while True:
            attempts += 1
            try:
                raw, usage, usage_record = await self._attempt(request, attempts)
                stop_reason = usage_record["stop_reason"]
                for key in totals:
                    totals[key] += usage[key]
            except BudgetExhausted:
                attempts -= 1
                await self._save_step(request, raw, result, totals, attempts, started, "budget_exhausted",
                                ["调用前预算检查未通过"], stop_reason=stop_reason)
                raise
            except (ConfigurationError, InsufficientStrawberries, NovelBudgetExceeded, RunNoLongerActive):
                raise
            except Exception as exc:
                if is_retryable(exc) and network_retries < 1:
                    network_retries += 1
                    await asyncio.sleep(self.retry_delay)
                    continue
                await self._save_step(request, raw, result, totals, attempts, started, failure_status,
                                _exception_metadata(exc), stop_reason=stop_reason)
                raise StepFailed(status=failure_status, step_key=request["step_key"]) from None
            completed, result, errors, diagnostics = await NovelBilling._drain(self._complete_response(
                request, raw, usage_record, totals, attempts, started, validator))
            if completed:
                return result
            if stop_reason == "refusal":
                await self._save_step(request, raw, None, totals, attempts, started, "step_failed", ["refusal"],
                                      stop_reason=stop_reason)
                raise StepFailed(status="step_failed", step_key=request["step_key"]) from None
            if stop_reason == "max_tokens":
                if validation_retries < 1:
                    validation_retries += 1
                    self._append_repair(request, raw, errors,
                                        "上一次输出因长度上限被截断。请压缩各字段文字，重新输出完整、合法的结果。")
                    continue
                await self._save_step(request, raw, None, totals, attempts, started, failure_status, errors,
                                      stop_reason=stop_reason)
                raise StepFailed("输出被截断，请检查步骤记录后续跑", status=failure_status,
                                 step_key=request["step_key"]) from None
            if validation_retries < 1:
                validation_retries += 1
                self._append_repair(request, raw, errors, "请根据上述错误重新输出完整结果，保持原输出格式。")
                continue
            await self._save_step(request, raw, result, totals, attempts, started, failure_status,
                                  [*errors, *diagnostics], stop_reason=stop_reason)
            raise StepFailed("输出校验失败，请检查步骤记录后续跑", status=failure_status,
                             step_key=request["step_key"]) from None

    @staticmethod
    def _append_repair(request, raw, errors, instruction):
        if request["output"] == "json":
            instruction += "\n" + JSON_STRING_QUOTE_RULE
        request["messages"].append({"role": "assistant", "content": raw or "（上一轮输出为空）"})
        request["messages"].append({"role": "user", "content": json.dumps({
            "校验错误": errors, "修正要求": instruction}, ensure_ascii=False)})

    async def _save_step(self, request, raw, result, usage, attempts, started, status, errors, *, stop_reason=None,
                         bill=False, billing_usage=None):
        record = {
            "step_key": request["step_key"], "model": request["model"], "messages": request["messages"],
            "raw_response": raw, "result": result, "usage": usage, "attempts": attempts,
            "duration_ms": round((time.monotonic() - started) * 1000, 3), "status": status, "errors": errors,
            "stop_reason": stop_reason,
        }
        atomic = (bill and getattr(self.billing, "atomic_step_settlement", False) and
                  getattr(self.store, "novel_id", None) is not None)
        if atomic:
            await self.billing.settle(request, billing_usage, step_record=record)
        else:
            if bill:
                await self.billing.settle(request, billing_usage)
            await maybe_await(self.store.write_step(request["step_key"], record))
        if status != "ok":
            await maybe_await(self.store.set_status(status, failed_step=request["step_key"]))
        elif self.store.manifest.get("failed_step") == request["step_key"]:
            await maybe_await(self.store.set_status("running", failed_step=None))
