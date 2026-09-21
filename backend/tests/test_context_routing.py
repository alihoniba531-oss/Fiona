# -*- coding: utf-8 -*-
"""
T1 模型路由验收：指代信号 + 会话深度阈值 + 预算闸门优先级。

model_router 是纯函数模块（无 DB、无 fastapi 依赖），所以这里不用 conftest 的
client fixture，直接调用即可。预算状态一律用 monkeypatch 改，测试结束自动还原。
"""
from datetime import date

import pytest

import model_router
from model_router import (
    CONTEXT_DEPTH_DEFAULT,
    MAIN_DAILY_LIMIT,
    choose_model,
    has_context_reference,
)


@pytest.fixture(autouse=True)
def _isolated_router(monkeypatch):
    """每个用例都从"预算未超限 + 阈值取默认值"的干净状态开始。"""
    monkeypatch.setattr(model_router.token_budget, "_data", {})
    monkeypatch.delenv("CONTEXT_DEPTH_MAIN_THRESHOLD", raising=False)


# --------------------------------------------------------------------------
# §4.1-1 指代命中
# --------------------------------------------------------------------------
def test_reference_short_message_goes_main():
    assert choose_model("u", "那他呢？", "normal", 0) == "main"


# --------------------------------------------------------------------------
# §4.1-2 反例：词表不得宽到把一切都判成 main
# --------------------------------------------------------------------------
def test_plain_chitchat_stays_light():
    assert choose_model("u", "今天天气不错", "normal", 0) == "light"


# --------------------------------------------------------------------------
# §4.1-3 单字指代误伤已处理
# --------------------------------------------------------------------------
@pytest.mark.parametrize("message", ["其他人也这么说", "其它的都可以", "我在弹吉他"])
def test_single_char_reference_false_positives_stay_light(message):
    assert choose_model("u", message, "normal", 0) == "light"


def test_stripping_does_not_eat_real_reference():
    # 剔除"其他/其它/吉他"之后，真正的复数指代仍必须命中
    assert choose_model("u", "他们同意了吗", "normal", 0) == "main"


# --------------------------------------------------------------------------
# §4.1-4 深度阈值边界（正控：两侧都断言）
# --------------------------------------------------------------------------
def test_context_depth_boundary_both_sides():
    assert choose_model("u", "嗯", "normal", 6) == "main"   # >= 阈值
    assert choose_model("u", "嗯", "normal", 5) == "light"  # 差一条，不触发


# --------------------------------------------------------------------------
# §4.1-5 阈值可关闭（成本回退）
# --------------------------------------------------------------------------
def test_threshold_zero_disables_depth_rule(monkeypatch):
    monkeypatch.setenv("CONTEXT_DEPTH_MAIN_THRESHOLD", "0")
    assert choose_model("u", "嗯", "normal", 999) == "light"


def test_threshold_negative_disables_depth_rule(monkeypatch):
    monkeypatch.setenv("CONTEXT_DEPTH_MAIN_THRESHOLD", "-3")
    assert choose_model("u", "嗯", "normal", 999) == "light"


# --------------------------------------------------------------------------
# §4.1-6 预算闸门优先级（成本红线）
# --------------------------------------------------------------------------
def _over_budget(monkeypatch):
    today = date.today().isoformat()
    monkeypatch.setattr(
        model_router.token_budget, "_data", {"u": {today: MAIN_DAILY_LIMIT}}
    )
    assert model_router.token_budget.is_over_budget("u") is True


def test_budget_gate_beats_reference_and_depth(monkeypatch):
    _over_budget(monkeypatch)
    # 规则 1 压住规则 4（指代）与规则 5（深度 999）
    assert choose_model("u", "那他呢？", "normal", 999) == "light"


def test_budget_gate_keeps_creative_on_main(monkeypatch):
    _over_budget(monkeypatch)
    # 正控：预算超限时含创作关键词仍走 main，证明规则 1 没有把创作也压掉
    assert choose_model("u", "帮我续写这段故事", "normal", 0) == "main"


def test_budget_gate_via_is_over_budget_stub(monkeypatch):
    monkeypatch.setattr(model_router.token_budget, "is_over_budget", lambda u: True)
    assert choose_model("u", "那他呢？", "normal", 999) == "light"


# --------------------------------------------------------------------------
# §4.1-7 mirror 恒 light
# --------------------------------------------------------------------------
@pytest.mark.parametrize("mode", ["mirror", "image"])
def test_mirror_and_image_always_light(mode):
    assert choose_model("u", "那他呢？", mode, 999) == "light"


# --------------------------------------------------------------------------
# §4.1-8 向后兼容：只传 3 个参数
# --------------------------------------------------------------------------
def test_three_positional_args_still_work():
    assert choose_model("u", "今天天气不错", "normal") == "light"


def test_history_len_is_fourth_positional():
    # 既有测试用 lambda *args 打桩，新参数必须能按位置传入
    assert choose_model("u", "嗯", "normal", 6) == "main"


# --------------------------------------------------------------------------
# 既有规则不得回归（规则 2 / 3）
# --------------------------------------------------------------------------
def test_creative_keyword_goes_main():
    assert choose_model("u", "帮我补全世界观", "normal", 0) == "main"


def test_long_message_goes_main():
    assert choose_model("u", "水" * 81, "normal", 0) == "main"
    assert choose_model("u", "水" * 80, "normal", 0) == "light"


# --------------------------------------------------------------------------
# has_context_reference 直接单测：词表每一类至少一个代表词
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "message",
    [
        "那个呢",           # 远指
        "这边看看",         # 近指
        "她走了吗",         # 人称（单字）
        "它们能跑吗",       # 人称（复数）
        "刚才说什么",       # 时间回指
        "上一条不算",       # 位置回指
        "第二个吧",         # 序数
        "哪个好",           # 选择
        "还是算了吧",       # 承接
        "继续",             # 承接
        "再来一个",         # 追加
        "换一个",           # 追加
        "跟之前一样",       # 类比
        "同上",             # 类比
        "按你说的做",       # 引述
        "你刚说的那句",     # 引述
        "然后呢",           # 省略
        "那呢",             # 省略
    ],
)
def test_has_context_reference_hits(message):
    assert has_context_reference(message) is True


@pytest.mark.parametrize(
    "message",
    [
        "今天天气不错",
        "其他人也这么说",
        "其它的都可以",
        "我在弹吉他",
        "嗯",
        "",
    ],
)
def test_has_context_reference_misses(message):
    assert has_context_reference(message) is False


def test_has_context_reference_tolerates_bad_input():
    # None / 非字符串不得抛异常，按"无指代"处理
    assert has_context_reference(None) is False
    assert has_context_reference(123) is False
    assert has_context_reference(["他"]) is False


# --------------------------------------------------------------------------
# 阈值解析：现读环境变量、失败回落默认值
# --------------------------------------------------------------------------
@pytest.mark.parametrize("raw", ["abc", "", "  ", "6.7", "None"])
def test_threshold_parse_failure_falls_back_to_default(monkeypatch, raw):
    monkeypatch.setenv("CONTEXT_DEPTH_MAIN_THRESHOLD", raw)
    assert model_router._context_depth_threshold() == CONTEXT_DEPTH_DEFAULT == 6
    # 回落到 6 之后，深度规则仍按 6 生效（两侧边界都验）
    assert choose_model("u", "嗯", "normal", 6) == "main"
    assert choose_model("u", "嗯", "normal", 5) == "light"


def test_threshold_unset_uses_default(monkeypatch):
    monkeypatch.delenv("CONTEXT_DEPTH_MAIN_THRESHOLD", raising=False)
    assert model_router._context_depth_threshold() == 6


@pytest.mark.parametrize("raw,expected", [("0", 0), ("-1", -1), ("12", 12), (" 8 ", 8)])
def test_threshold_parses_integers(monkeypatch, raw, expected):
    monkeypatch.setenv("CONTEXT_DEPTH_MAIN_THRESHOLD", raw)
    assert model_router._context_depth_threshold() == expected


def test_threshold_is_read_at_call_time(monkeypatch):
    # 不得在模块导入时固化：改了环境变量，下一次调用立刻生效
    assert choose_model("u", "嗯", "normal", 2) == "light"
    monkeypatch.setenv("CONTEXT_DEPTH_MAIN_THRESHOLD", "2")
    assert choose_model("u", "嗯", "normal", 2) == "main"
