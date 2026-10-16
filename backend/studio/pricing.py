"""短片价目；金额先用 Decimal 计算，再在接口边界转换。"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
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
