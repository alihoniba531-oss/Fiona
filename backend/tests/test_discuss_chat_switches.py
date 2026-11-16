# -*- coding: utf-8 -*-
"""讨论群聊天开关与每日上限（规格 4.2、4.4、6.1、6.3）。"""

import pytest

from discuss import config
import rate_limit
from rate_limit import limiter


USER = "alice"
OTHER = "bob"


@pytest.fixture
def discuss_env(monkeypatch):
    monkeypatch.setenv("FIONA_DISCUSS", "1")
    monkeypatch.setenv("FIONA_DISCUSS_USERS", f"{USER}, {OTHER}")
    monkeypatch.setenv("FIONA_DISCUSS_CHAT", "1")
    monkeypatch.setenv("FIONA_DISCUSS_CHAT_CARDS", "1")
    return monkeypatch


def test_chat_enabled_requires_every_condition(discuss_env):
    assert config.chat_enabled(USER) is True
    assert config.chat_enabled(OTHER) is True

    # 危机轮、空账号、白名单外一律不开放。
    assert config.chat_enabled(USER, crisis=True) is False
    assert config.chat_enabled(None) is False
    assert config.chat_enabled("") is False
    assert config.chat_enabled("ALICE") is False
    assert config.chat_enabled("alice ") is False
    assert config.chat_enabled("carol") is False

    # 主开关缺失或不是字面 "1" 都不开放。
    for value in (None, "0", "true", "2"):
        if value is None:
            discuss_env.delenv("FIONA_DISCUSS", raising=False)
        else:
            discuss_env.setenv("FIONA_DISCUSS", value)
        assert config.chat_enabled(USER) is False
    discuss_env.setenv("FIONA_DISCUSS", "1")

    # 聊天开关缺失或不是字面 "1" 都不开放。
    for value in (None, "0", "true", "2"):
        if value is None:
            discuss_env.delenv("FIONA_DISCUSS_CHAT", raising=False)
        else:
            discuss_env.setenv("FIONA_DISCUSS_CHAT", value)
        assert config.chat_enabled(USER) is False


def test_chat_enabled_reads_environment_on_every_call(discuss_env):
    assert config.chat_enabled(USER) is True
    discuss_env.setenv("FIONA_DISCUSS_CHAT", "0")
    assert config.chat_enabled(USER) is False
    discuss_env.setenv("FIONA_DISCUSS_CHAT", "1")
    assert config.chat_enabled(USER) is True
    discuss_env.setenv("FIONA_DISCUSS_USERS", OTHER)
    assert config.chat_enabled(USER) is False
    discuss_env.setenv("FIONA_DISCUSS_USERS", OTHER)
    assert config.chat_enabled(OTHER) is True


def test_chat_enabled_is_off_by_default(monkeypatch):
    for name in ("FIONA_DISCUSS", "FIONA_DISCUSS_USERS", "FIONA_DISCUSS_CHAT"):
        monkeypatch.delenv(name, raising=False)
    assert config.chat_enabled(USER) is False


def test_chat_cards_enabled_requires_cards_switch_and_chat(discuss_env):
    assert config.chat_cards_enabled(USER) is True

    discuss_env.setenv("FIONA_DISCUSS_CHAT_CARDS", "0")
    assert config.chat_cards_enabled(USER) is False
    discuss_env.setenv("FIONA_DISCUSS_CHAT_CARDS", "true")
    assert config.chat_cards_enabled(USER) is False
    discuss_env.delenv("FIONA_DISCUSS_CHAT_CARDS", raising=False)
    assert config.chat_cards_enabled(USER) is False

    discuss_env.setenv("FIONA_DISCUSS_CHAT_CARDS", "1")
    discuss_env.setenv("FIONA_DISCUSS_CHAT", "0")
    assert config.chat_cards_enabled(USER) is False
    discuss_env.setenv("FIONA_DISCUSS_CHAT", "1")
    discuss_env.setenv("FIONA_DISCUSS", "0")
    assert config.chat_cards_enabled(USER) is False
    discuss_env.setenv("FIONA_DISCUSS", "1")
    discuss_env.setenv("FIONA_DISCUSS_USERS", OTHER)
    assert config.chat_cards_enabled(USER) is False
    assert config.chat_cards_enabled(None) is False


@pytest.fixture
def daily_cap_env(monkeypatch):
    monkeypatch.setenv("DEV_MODE", "0")
    monkeypatch.setattr(limiter, "enabled", True)

    def reset():
        limiter.reset()

    reset()
    yield monkeypatch
    reset()


def test_discuss_daily_cap_is_registered_and_defaults_to_60(daily_cap_env):
    assert rate_limit._DAILY_SETTINGS["discuss_read"] == (
        "FIONA_DAILY_DISCUSS_READS", 60)
    daily_cap_env.delenv("FIONA_DAILY_DISCUSS_READS", raising=False)
    assert rate_limit.daily_cap("discuss_read") == 60
    assert rate_limit.daily_cap_message("discuss_read") == (
        "今天看讨论群的次数已用完，明天再来。")


def test_discuss_daily_cap_reads_override_and_falls_back(daily_cap_env):
    daily_cap_env.setenv("FIONA_DAILY_DISCUSS_READS", "7")
    assert rate_limit.daily_cap("discuss_read") == 7
    for value in ("0", "-1", "abc", "", "1.5"):
        daily_cap_env.setenv("FIONA_DAILY_DISCUSS_READS", value)
        assert rate_limit.daily_cap("discuss_read") == 60


def test_discuss_daily_cap_counts_only_success_and_blocks_at_limit(daily_cap_env):
    daily_cap_env.setenv("FIONA_DAILY_DISCUSS_READS", "2")
    user = "daily-cap-success"

    def read_once(*, success):
        # 先预检；只有成功读取才计数。列群完全不经过这里。
        blocked = rate_limit.check_chat_daily_cap(
            "discuss_read", user, hit=False)
        if blocked is not None:
            return blocked
        if success:
            return rate_limit.check_chat_daily_cap(
                "discuss_read", user, hit=True)
        return None

    # 列群、找不到群、没有成果都不计数，连续失败多次仍可读。
    for _ in range(10):
        assert read_once(success=False) is None
    assert rate_limit.check_chat_daily_cap(
        "discuss_read", user, hit=False) is None

    # 成功两次后到达每日上限。
    assert read_once(success=True) is None
    assert rate_limit.check_chat_daily_cap(
        "discuss_read", user, hit=False) is None
    assert read_once(success=True) is None
    message = "今天看讨论群的次数已用完，明天再来。"
    assert read_once(success=False) == message
    assert rate_limit.check_chat_daily_cap(
        "discuss_read", user, hit=True) == message

    # 别的账号不受影响。
    assert rate_limit.check_chat_daily_cap(
        "discuss_read", "daily-cap-other", hit=False) is None
