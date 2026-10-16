"""价目和用量的纯本地核验，不创建 HTTP 客户端。"""

from decimal import Decimal

from fastapi import HTTPException
import pytest

from studio import pricing


def params(**overrides):
    return {"first_frame_asset_id": "image-id", "prompt": "她推开窗，风掀起窗帘。", **overrides}


@pytest.mark.parametrize("model", ["wan3.0-video", "wan3.0-video-prime"])
@pytest.mark.parametrize("resolution,unit", [("480P", ".3"), ("720P", ".6"), ("1080P", "1.2")])
def test_wan_price_and_actual_duration(model, resolution, unit):
    estimate = pricing.estimate(params(model=model, resolution=resolution, duration=5))
    assert Decimal(str(estimate["est_min_cny"])) == Decimal(unit) * 5 * Decimal(".7")
    assert Decimal(str(estimate["est_max_cny"])) == Decimal(unit) * 5
    assert pricing.actual_cost("wan", resolution, {"duration": 5}) == Decimal(unit) * 5


@pytest.mark.parametrize("resolution,rate", [("480p", 9700), ("720p", 21600), ("1080p", 48938)])
def test_seedance_resolution_tiers_and_uncertainty(resolution, rate):
    estimate = pricing.estimate(params(provider="seedance", resolution=resolution, duration=5))
    assert Decimal(str(estimate["est_min_cny"])) == Decimal(5 * rate) * Decimal(".05544") / 1000 * Decimal(".8")
    assert Decimal(str(estimate["est_max_cny"])) == Decimal(5 * rate) * Decimal(".07") / 1000 * Decimal("1.2")


@pytest.mark.parametrize("provider,minimum", [("wan", 2), ("seedance", 4)])
def test_intelligent_duration_prices_supported_full_range(provider, minimum):
    estimate = pricing.estimate(params(provider=provider, duration=-1))
    lower = pricing.estimate(params(provider=provider, duration=minimum))
    upper = pricing.estimate(params(provider=provider, duration=30))
    assert estimate["duration_min_s"] == minimum
    assert estimate["duration_max_s"] == 30
    assert estimate["est_min_cny"] == lower["est_min_cny"]
    assert estimate["est_max_cny"] == upper["est_max_cny"]


@pytest.mark.parametrize("provider,duration", [
    ("wan", 1), ("wan", 31), ("wan", 0), ("wan", -2), ("wan", 2.5), ("wan", True),
    ("seedance", 3), ("seedance", 31), ("seedance", 4.5), ("seedance", "5"),
])
def test_invalid_durations_rejected_at_quote(provider, duration):
    with pytest.raises(HTTPException) as error:
        pricing.estimate(params(provider=provider, duration=duration))
    assert error.value.status_code == 422


@pytest.mark.parametrize("overrides", [
    {"provider": "other"}, {"model": "other"}, {"provider": "seedance", "model": "wan3.0-video"},
    {"resolution": "4K"}, {"prompt": " "}, {"prompt": "字" * 2001}, {"audio": "true"},
    {"first_frame_asset_id": "data:image/png;base64,YWJj"},
])
def test_quote_validation(overrides):
    with pytest.raises(HTTPException) as error:
        pricing.estimate(params(**overrides))
    assert error.value.status_code == 422


def test_exact_usage_settlement_and_reported_wan_sr():
    assert pricing.actual_cost("wan", "480P", {"duration": 5, "SR": 480}) == Decimal("1.50000000")
    assert pricing.actual_cost("wan", "480P", {"duration": 5, "SR": 720.0}) == Decimal("3.00000000")
    assert pricing.actual_cost("seedance", "480p", {"completion_tokens": 48324}) == Decimal("3.38268000")


@pytest.mark.parametrize("usage", [None, {}, {"duration": -1}, {"duration": True}, {"duration": float("nan")}, {"duration": "5"}])
def test_missing_or_invalid_wan_usage_is_zero(usage):
    assert pricing.actual_cost("wan", "480P", usage) == 0


@pytest.mark.parametrize("usage", [None, {}])
def test_missing_seedance_usage_is_zero(usage):
    assert pricing.actual_cost("seedance", "480p", usage) == 0


@pytest.mark.parametrize("tokens", [48324, 48324.0, "48324", "48324.0", "4.8324e4", Decimal("48324.0")])
def test_seedance_accepts_integral_numeric_tokens(tokens):
    assert pricing.actual_cost("seedance", "480p", {"completion_tokens": tokens}) == Decimal("3.38268000")


@pytest.mark.parametrize("tokens", [-1, -1.0, "-1", 1.5, "1.5", True, None, "invalid",
                                   float("nan"), float("inf"), "NaN", "Infinity"])
def test_invalid_seedance_tokens_cannot_be_settled(tokens):
    assert pricing.actual_cost("seedance", "480p", {"completion_tokens": tokens}) is None


@pytest.mark.parametrize("tokens", [0, 0.0, "0", "0.0"])
def test_valid_zero_seedance_tokens_can_be_settled(tokens):
    assert pricing.actual_cost("seedance", "480p", {"completion_tokens": tokens}) == 0


@pytest.mark.parametrize("amount", ["1e30", "1e308", "1.7976931348623157e308"])
def test_large_finite_amounts_keep_eight_decimal_places(amount):
    result = pricing.money(amount)
    assert result == Decimal(amount)
    assert result.as_tuple().exponent == -8
