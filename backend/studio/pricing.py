"""短片价目；金额先用 Decimal 计算，再在接口边界转换。"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
import os
import uuid

from fastapi import HTTPException


DEFAULT_SEEDANCE_MODEL = "doubao-seedance-2-5-260628"
WAN_PRICES = {"480P": Decimal("0.3"), "720P": Decimal("0.6"), "1080P": Decimal("1.2")}
SEEDANCE_TOKENS_PER_SECOND = {"480p": 9700, "720p": 21600, "1080p": 48938}
MONEY_PRECISION = Decimal("0.00000001")


def money(value) -> Decimal:
    amount = Decimal(str(value))
    if not amount.is_finite() or amount < 0:
        raise ValueError("金额必须是非负有限数字")
    # 配置允许任意正有限数；默认 28 位上下文不能量化 1e30 这样的合法上限。
    with localcontext() as context:
        context.prec = max(28, amount.adjusted() + 10, len(amount.as_tuple().digits))
        return amount.quantize(MONEY_PRECISION, rounding=ROUND_HALF_UP)


def normalize_params(raw: dict) -> dict:
    """只保存允许的生成参数；首帧必须是素材 ID，不能带内联图片。"""
    provider = raw.get("provider", "wan")
    if provider not in {"wan", "seedance"}:
        raise HTTPException(422, "视频供应商必须为 wan 或 seedance")
    model = raw.get("model") or ("wan3.0-video" if provider == "wan" else DEFAULT_SEEDANCE_MODEL)
    supported = {"wan3.0-video", "wan3.0-video-prime"} if provider == "wan" else {DEFAULT_SEEDANCE_MODEL}
    if model not in supported:
        raise HTTPException(422, "所选供应商不支持该视频模型")
    raw_resolution = raw.get("resolution", "480P")
    if not isinstance(raw_resolution, str):
        raise HTTPException(422, "分辨率必须为 480P、720P 或 1080P")
    resolution = raw_resolution.upper() if provider == "wan" else raw_resolution.lower()
    if resolution not in (WAN_PRICES if provider == "wan" else SEEDANCE_TOKENS_PER_SECOND):
        raise HTTPException(422, "分辨率必须为 480P、720P 或 1080P")
    duration = raw.get("duration", 5)
    minimum = 2 if provider == "wan" else 4
    if isinstance(duration, bool) or not isinstance(duration, int) or (
        duration != -1 and not minimum <= duration <= 30
    ):
        raise HTTPException(422, f"时长必须为 -1 或 {minimum}–30 的整数秒")
    prompt = raw.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip() or not 1 <= len(prompt) <= 2000:
        raise HTTPException(422, "提示词须为 1–2000 字")
    asset_id = raw.get("first_frame_asset_id")
    if not isinstance(asset_id, str) or not asset_id.strip() or len(asset_id) > 128 or asset_id.startswith("data:"):
        raise HTTPException(422, "请提供有效的首帧素材 ID")
    audio = raw.get("audio", True)
    if not isinstance(audio, bool):
        raise HTTPException(422, "audio 必须为布尔值")
    return {
        "first_frame_asset_id": asset_id,
        "prompt": prompt,
        "provider": provider,
        "model": model,
        "resolution": resolution,
        "duration": duration,
        "audio": audio,
        "duration_min_s": minimum if duration == -1 else duration,
        "duration_max_s": 30 if duration == -1 else duration,
    }


def estimate(params: dict) -> dict:
    params = normalize_params(params)
    lower, upper = params["duration_min_s"], params["duration_max_s"]
    if params["provider"] == "wan":
        unit = WAN_PRICES[params["resolution"]]
        minimum = Decimal(lower) * unit * Decimal("0.7")
        maximum = Decimal(upper) * unit
    else:
        rate = Decimal(SEEDANCE_TOKENS_PER_SECOND[params["resolution"]])
        minimum = Decimal(lower) * rate * Decimal("0.05544") / 1000 * Decimal("0.8")
        maximum = Decimal(upper) * rate * Decimal("0.07") / 1000 * Decimal("1.2")
    return {
        "est_min_cny": float(money(minimum)),
        "est_max_cny": float(money(maximum)),
        "duration_min_s": lower,
        "duration_max_s": upper,
    }


def quote_item(params: dict) -> dict:
    params = normalize_params(params)
    item_id = str(uuid.uuid4())
    return {"id": item_id, "quote_item_id": item_id, "params": params,
            "provider": params["provider"], "model": params["model"], **estimate(params)}


def actual_cost(provider: str, resolution: str, usage: dict | None) -> Decimal | None:
    """缺失用量记 0；显式无效的 token 数无法结算，不能按免费处理。"""
    if not isinstance(usage, dict):
        return money(0)
    if provider == "seedance":
        if "completion_tokens" not in usage:
            return money(0)
        tokens = usage["completion_tokens"]
        if isinstance(tokens, bool) or not isinstance(tokens, (int, float, Decimal, str)):
            return None
        try:
            tokens = Decimal(str(tokens))
            if not tokens.is_finite() or tokens < 0 or tokens != tokens.to_integral_value():
                return None
            return money(tokens * Decimal("0.07") / 1000)
        except (InvalidOperation, ValueError):
            return None
    if provider != "wan":
        return money(0)
    duration = usage.get("duration")
    if isinstance(duration, bool) or not isinstance(duration, (int, float, Decimal)):
        return money(0)
    try:
        duration = Decimal(str(duration))
        if not duration.is_finite() or duration < 0:
            return money(0)
        billed_resolution = str(usage.get("SR", "")).upper().removesuffix("P")
        # 部分接口将 SR 返回为 JSON 浮点数。
        if billed_resolution.endswith(".0"):
            billed_resolution = billed_resolution[:-2]
        key = billed_resolution + "P"
        if key not in WAN_PRICES:
            key = str(resolution).upper()
        if key not in WAN_PRICES:
            return money(0)
        return money(duration * WAN_PRICES[key])
    except (InvalidOperation, ValueError):
        return money(0)


# 每百万 token；平台模型默认价沿用 WO0，待核实，可逐模型覆盖。
BRAIN_PRICES = {
    "claude-opus-5-5": ("USD", "4", "20", "0.20"),
    "claude-sonnet-5-5": ("USD", "2", "10", "0.20"),
    "claude-haiku-5-5": ("USD", "0.10", "0.50", "0.10"),
    "qwen3.8-max": ("CNY", "6", "24", "6"),
    "deepseek-v4-pro": ("CNY", "2", "3", "2"),
    "qwen3-vl-plus": ("CNY", "1", "10", "1"),  # 待核实：作者账号实测可用，价格以账单为准。
    "qwen-vl-max": ("CNY", "2.4", "9.6", "2.4"),
}
REPAIR_OVERHEAD_TOKENS = 2048


def brain_price_env(model: str) -> str:
    import re
    return "FIONA_STUDIO_PRICE_" + re.sub(r"[^A-Za-z0-9]", "_", model).upper()


def brain_price(model: str) -> dict:
    """覆盖格式为 JSON {input,output,cache_read?}，单位 / 百万 token。"""
    import json
    import os
    name = brain_price_env(model)
    default = BRAIN_PRICES.get(model)
    # 自定义千问视觉模型仍计入人民币日上限；旧 Claude 覆盖保持美元语义。
    currency = default[0] if default else ("USD" if model.startswith("claude-") else "CNY")
    raw = os.getenv(name)
    try:
        if raw is not None:
            value = json.loads(raw)
            values = [value["input"], value["output"], value.get("cache_read", value["input"])]
        elif default:
            values = default[1:]
        else:
            raise ValueError
        rates = [Decimal(str(value)) for value in values]
        if any(not value.is_finite() or value < 0 for value in rates):
            raise ValueError
    except (ValueError, TypeError, KeyError, InvalidOperation):
        raise HTTPException(409, f"模型 {model} 单价未配置或无效，请设置环境变量 {name}") from None
    return dict(zip(("currency", "input", "output", "cache_read"), (currency, *rates)))


def estimate_brain(model: str, input_chars: int, max_tokens: int, *, image_tokens: int = 0) -> dict:
    from math import ceil
    return estimate_brain_tokens(model, ceil(input_chars * 1.5) + image_tokens, max_tokens)


def estimate_brain_tokens(model: str, input_tokens: int, max_tokens: int) -> dict:
    price = brain_price(model)
    prices = [price]
    if model in {"claude-sonnet-5-5", "claude-opus-5-5"}:
        # 这两个型号启用服务端 default fallback，预留必须覆盖已知 Claude 型号的最高价。
        for candidate in BRAIN_PRICES:
            if candidate.startswith("claude-") and candidate != model:
                try:
                    prices.append(brain_price(candidate))
                except HTTPException:
                    # 无法定价的 fallback 会按本次预留结算，不可影响已配置的请求模型。
                    pass
    if model.startswith("claude-"):
        input_rate = max(max(item["input"] * Decimal("1.25"), item["cache_read"]) for item in prices)
    else:
        input_rate = max(price["input"], price["cache_read"])
    output_rate = max(item["output"] for item in prices)
    amount = (input_tokens * input_rate + max_tokens * output_rate) / 1_000_000
    return {"currency": price["currency"], "amount": float(money(amount))}


def estimate_brain_repair(model: str, input_chars: int, max_tokens: int, *, image_tokens: int = 0) -> dict:
    """上轮输出以其 token 上限计入，不将生成 token 再当字符放大。"""
    from math import ceil
    inputs = ceil(input_chars * 1.5) + image_tokens + max_tokens + REPAIR_OVERHEAD_TOKENS
    return estimate_brain_tokens(model, inputs, max_tokens)


def brain_actual_cost(model: str, usage: dict | None) -> dict:
    price = brain_price(model)
    result = {"currency": price["currency"], "amount": None}
    if not isinstance(usage, dict):
        return result
    def count(key, *, required=False):
        value = usage.get(key, None if required else 0)
        if isinstance(value, bool) or value is None:
            raise ValueError
        value = Decimal(str(value))
        if not value.is_finite() or value < 0 or value != value.to_integral_value():
            raise ValueError
        return value
    try:
        inputs = count("input_tokens", required=True)
        outputs = count("output_tokens", required=True)
        cached = count("cache_read_input_tokens")
        created = count("cache_creation_input_tokens")
        # Anthropic input_tokens 不包括缓存；OpenAI 兼容用量包含缓存命中。
        ordinary = inputs if model.startswith("claude-") else max(Decimal(0), inputs - cached)
        amount = ((ordinary + created * Decimal("1.25")) * price["input"] + cached * price["cache_read"]
                  + outputs * price["output"]) / 1_000_000
        result["amount"] = float(money(amount))
    except (ValueError, TypeError, InvalidOperation):
        pass
    return result


def settle_brain_response(model: str, usage: dict | None, *, currency: str, reserved_amount) -> tuple[dict, list[str]]:
    """完整响应按实际模型计价；无法定价时最多结算本次已确认预留。"""
    try:
        return brain_actual_cost(model, usage), []
    except HTTPException as exc:
        if exc.status_code != 409:
            raise
        return ({"currency": currency, "amount": float(money(reserved_amount))},
                ["fallback 模型单价未配置，按预留计"])


# 定妆出图与声线的参考单价，单位人民币，可被环境变量覆盖；非法值回落默认并只告警一次。
# Seedream 响应不含计费字段，按此价预留与结算（待核实）。
DEFAULT_SEEDREAM_PRICE_CNY = Decimal("0.30")
# CosyVoice 按字符数计费，2 元/万字符（待核实）。
DEFAULT_COSYVOICE_PRICE_CNY_PER_10K_CHARS = Decimal("2.0")
MIN_COSYVOICE_PRICE_CNY = Decimal("0.01")
PRICE_SEEDREAM_ENV = "FIONA_STUDIO_PRICE_SEEDREAM_CNY"
PRICE_COSYVOICE_ENV = "FIONA_STUDIO_PRICE_COSYVOICE_CNY_PER_10K_CHARS"
_PRICE_WARNED: set[str] = set()


def _price_warn(name: str) -> None:
    if name not in _PRICE_WARNED:
        print(f"[studio] {name} 无效，使用默认值")
        _PRICE_WARNED.add(name)


def _price(name: str, default: Decimal) -> Decimal:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = Decimal(str(raw).strip())
        if not value.is_finite() or value < 0:
            raise ValueError("invalid price")
        return money(value)
    except (InvalidOperation, ValueError, TypeError):
        _price_warn(name)
        return default


def seedream_price() -> Decimal:
    """每张定妆图的预留与结算单价。"""
    return _price(PRICE_SEEDREAM_ENV, DEFAULT_SEEDREAM_PRICE_CNY)


def cosyvoice_price_per_10k_chars() -> Decimal:
    return _price(PRICE_COSYVOICE_ENV, DEFAULT_COSYVOICE_PRICE_CNY_PER_10K_CHARS)


def estimate_sheets(count: int) -> dict:
    """出图报价 = 张数 × 单价。"""
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise HTTPException(422, "出图张数必须是正整数")
    return {"currency": "CNY", "amount": float(money(seedream_price() * count))}


def estimate_speech(chars: int, engine: str) -> dict:
    """CosyVoice 按字符数预留与结算（最低 0.01 元）；edge-tts 免费。"""
    if engine == "edge-tts":
        return {"currency": "CNY", "amount": 0.0}
    if engine != "cosyvoice":
        raise HTTPException(422, "配音引擎必须为 cosyvoice 或 edge-tts")
    if isinstance(chars, bool) or not isinstance(chars, int) or chars < 1:
        raise HTTPException(422, "试听台词不能为空")
    amount = cosyvoice_price_per_10k_chars() * Decimal(chars) / 10000
    return {"currency": "CNY", "amount": float(money(max(amount, MIN_COSYVOICE_PRICE_CNY)))}
