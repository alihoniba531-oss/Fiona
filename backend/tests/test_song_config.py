# -*- coding: utf-8 -*-
"""写歌配置与火山 v4.3 枚举常量的离线测试。"""

from __future__ import annotations

import pytest

from song import config as song_config
from song import volc_options


SONG_ENV_NAMES = (
    "FIONA_SONG_AGENT",
    "FIONA_SONG_USERS",
    "FIONA_SONG_STRAWBERRIES",
    "FIONA_DAILY_SONGS",
    "FIONA_SONG_MAX_INFLIGHT",
    "FIONA_SONG_DIR",
    "FIONA_SONG_EXPLICIT_WATERMARK",
    "FIONA_AIGC_PRODUCER",
    "VOLC_MUSIC_ACCESS_KEY",
    "VOLC_MUSIC_SECRET_KEY",
)


@pytest.fixture(autouse=True)
def _isolated_song_env(monkeypatch, tmp_path):
    """每个用例都从干净的写歌环境变量开始，音频目录固定到 tmp_path。"""
    for name in SONG_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("FIONA_SONG_DIR", str(tmp_path / "song_data"))
    monkeypatch.setattr(song_config, "_INVALID_SETTINGS_WARNED", set())
    yield


def test_defaults(monkeypatch, capsys):
    monkeypatch.delenv("FIONA_SONG_DIR", raising=False)

    assert song_config.song_agent_enabled() is False
    assert song_config.song_users() == ()
    assert song_config.song_enabled_for("alice") is False
    assert song_config.song_price_strawberries() == 30
    assert song_config.song_daily_limit() == 10
    assert song_config.song_max_inflight() == 2
    assert song_config.song_explicit_watermark() is True
    assert song_config.aigc_producer() == "Fiona"
    assert song_config.volc_credentials() == ("", "")
    assert song_config.song_configured() is False
    expected_dir = (song_config.BACKEND_DIR / "song_data").resolve()
    assert song_config.song_dir() == expected_dir
    assert capsys.readouterr().out == ""


def test_agent_switch_only_literal_one(monkeypatch, capsys):
    monkeypatch.setenv("FIONA_SONG_AGENT", "1")
    assert song_config.song_agent_enabled() is True

    monkeypatch.setenv("FIONA_SONG_AGENT", "0")
    assert song_config.song_agent_enabled() is False

    monkeypatch.setenv("FIONA_SONG_AGENT", "true")
    assert song_config.song_agent_enabled() is False
    assert capsys.readouterr().out == (
        "[song] code=config_invalid name=FIONA_SONG_AGENT\n"
    )

    # 只告警一次。
    assert song_config.song_agent_enabled() is False
    assert capsys.readouterr().out == ""

    monkeypatch.setenv("FIONA_SONG_AGENT", "")
    assert song_config.song_agent_enabled() is False
    assert capsys.readouterr().out == ""


def test_whitelist_requires_exact_username_and_enabled_switch(monkeypatch):
    monkeypatch.setenv("FIONA_SONG_AGENT", "1")
    monkeypatch.setenv("FIONA_SONG_USERS", "alice, bob ,,ALICE,alice")

    assert song_config.song_users() == ("alice", "bob", "ALICE")
    assert song_config.song_enabled_for("alice") is True
    assert song_config.song_enabled_for("bob") is True
    assert song_config.song_enabled_for("ALICE") is True
    assert song_config.song_enabled_for("Alice") is False
    assert song_config.song_enabled_for(" alice") is False
    assert song_config.song_enabled_for("bob ") is False
    assert song_config.song_enabled_for("") is False
    assert song_config.song_enabled_for(None) is False
    assert song_config.song_enabled_for(123) is False

    # 开关关闭时即使命中白名单也不开放。
    monkeypatch.setenv("FIONA_SONG_AGENT", "0")
    assert song_config.song_enabled_for("alice") is False

    # 空白名单 = 没人可用。
    monkeypatch.setenv("FIONA_SONG_AGENT", "1")
    monkeypatch.setenv("FIONA_SONG_USERS", "   ")
    assert song_config.song_users() == ()
    assert song_config.song_enabled_for("alice") is False


def test_strawberry_price_boundaries_and_invalid_fallback(monkeypatch, capsys):
    assert song_config.song_price_strawberries() == 30

    monkeypatch.setenv("FIONA_SONG_STRAWBERRIES", "1")
    assert song_config.song_price_strawberries() == 1
    monkeypatch.setenv("FIONA_SONG_STRAWBERRIES", "500")
    assert song_config.song_price_strawberries() == 500
    monkeypatch.setenv("FIONA_SONG_STRAWBERRIES", "250")
    assert song_config.song_price_strawberries() == 250

    monkeypatch.setenv("FIONA_SONG_STRAWBERRIES", "0")
    assert song_config.song_price_strawberries() == 30
    assert capsys.readouterr().out == (
        "[song] code=config_invalid name=FIONA_SONG_STRAWBERRIES\n"
    )
    # 同名的后续非法值不再重复告警，仍回落默认。
    monkeypatch.setenv("FIONA_SONG_STRAWBERRIES", "501")
    assert song_config.song_price_strawberries() == 30
    monkeypatch.setenv("FIONA_SONG_STRAWBERRIES", "abc")
    assert song_config.song_price_strawberries() == 30
    monkeypatch.setenv("FIONA_SONG_STRAWBERRIES", "-1")
    assert song_config.song_price_strawberries() == 30
    monkeypatch.setenv("FIONA_SONG_STRAWBERRIES", "1.5")
    assert song_config.song_price_strawberries() == 30
    monkeypatch.setenv("FIONA_SONG_STRAWBERRIES", "9" * 5000)
    assert song_config.song_price_strawberries() == 30
    assert capsys.readouterr().out == ""

    # 空字符串按未设置处理，不告警。
    monkeypatch.setenv("FIONA_SONG_STRAWBERRIES", "")
    assert song_config.song_price_strawberries() == 30
    assert capsys.readouterr().out == ""


def test_daily_song_limit_boundaries_and_invalid_fallback(monkeypatch, capsys):
    assert song_config.song_daily_limit() == 10

    monkeypatch.setenv("FIONA_DAILY_SONGS", "1")
    assert song_config.song_daily_limit() == 1
    monkeypatch.setenv("FIONA_DAILY_SONGS", "100")
    assert song_config.song_daily_limit() == 100
    monkeypatch.setenv("FIONA_DAILY_SONGS", "50")
    assert song_config.song_daily_limit() == 50

    for invalid in ("0", "101", "ten", "1.0", "-3"):
        monkeypatch.setenv("FIONA_DAILY_SONGS", invalid)
        assert song_config.song_daily_limit() == 10
    assert capsys.readouterr().out == (
        "[song] code=config_invalid name=FIONA_DAILY_SONGS\n"
    )


def test_max_inflight_boundaries_and_invalid_fallback(monkeypatch, capsys):
    assert song_config.song_max_inflight() == 2

    monkeypatch.setenv("FIONA_SONG_MAX_INFLIGHT", "1")
    assert song_config.song_max_inflight() == 1
    monkeypatch.setenv("FIONA_SONG_MAX_INFLIGHT", "5")
    assert song_config.song_max_inflight() == 5
    monkeypatch.setenv("FIONA_SONG_MAX_INFLIGHT", "3")
    assert song_config.song_max_inflight() == 3

    for invalid in ("0", "6", "two", "2.0"):
        monkeypatch.setenv("FIONA_SONG_MAX_INFLIGHT", invalid)
        assert song_config.song_max_inflight() == 2
    assert capsys.readouterr().out == (
        "[song] code=config_invalid name=FIONA_SONG_MAX_INFLIGHT\n"
    )


def test_song_dir_relative_to_backend_and_absolute_preserved(monkeypatch, tmp_path, capsys):
    relative = song_config.BACKEND_DIR / "my_song_data"
    monkeypatch.setenv("FIONA_SONG_DIR", "my_song_data")
    assert song_config.song_dir() == relative.resolve()
    assert song_config.song_dir().is_absolute()

    absolute = tmp_path / "absolute_songs"
    monkeypatch.setenv("FIONA_SONG_DIR", str(absolute))
    assert song_config.song_dir() == absolute.resolve()
    assert song_config.song_dir().is_absolute()

    # 读取配置不创建目录。
    assert not absolute.exists()
    assert not relative.exists()

    monkeypatch.setenv("FIONA_SONG_DIR", "")
    assert song_config.song_dir() == (song_config.BACKEND_DIR / "song_data").resolve()
    assert capsys.readouterr().out == ""


def test_explicit_watermark_only_literal_zero_disables(monkeypatch, capsys):
    assert song_config.song_explicit_watermark() is True

    monkeypatch.setenv("FIONA_SONG_EXPLICIT_WATERMARK", "0")
    assert song_config.song_explicit_watermark() is False
    monkeypatch.setenv("FIONA_SONG_EXPLICIT_WATERMARK", "1")
    assert song_config.song_explicit_watermark() is True

    monkeypatch.setenv("FIONA_SONG_EXPLICIT_WATERMARK", "false")
    assert song_config.song_explicit_watermark() is True
    assert capsys.readouterr().out == (
        "[song] code=config_invalid name=FIONA_SONG_EXPLICIT_WATERMARK\n"
    )
    assert song_config.song_explicit_watermark() is True
    assert capsys.readouterr().out == ""

    monkeypatch.setenv("FIONA_SONG_EXPLICIT_WATERMARK", "")
    assert song_config.song_explicit_watermark() is True
    assert capsys.readouterr().out == ""


def test_aigc_producer_visible_length_and_invalid_fallback(monkeypatch, capsys):
    assert song_config.aigc_producer() == "Fiona"

    monkeypatch.setenv("FIONA_AIGC_PRODUCER", "Fiona 工作室")
    assert song_config.aigc_producer() == "Fiona 工作室"

    monkeypatch.setenv("FIONA_AIGC_PRODUCER", "A")
    assert song_config.aigc_producer() == "A"
    monkeypatch.setenv("FIONA_AIGC_PRODUCER", "A" * 40)
    assert song_config.aigc_producer() == "A" * 40

    monkeypatch.setenv("FIONA_AIGC_PRODUCER", "SECRET" * 10)
    assert song_config.aigc_producer() == "Fiona"
    output = capsys.readouterr().out
    assert output == "[song] code=config_invalid name=FIONA_AIGC_PRODUCER\n"
    assert "SECRET" not in output

    monkeypatch.setenv("FIONA_AIGC_PRODUCER", "Fiona\nSECRET")
    assert song_config.aigc_producer() == "Fiona"
    assert capsys.readouterr().out == ""
    assert "SECRET" not in song_config.aigc_producer()

    monkeypatch.setenv("FIONA_AIGC_PRODUCER", "   ")
    assert song_config.aigc_producer() == "Fiona"

    monkeypatch.setenv("FIONA_AIGC_PRODUCER", "")
    assert song_config.aigc_producer() == "Fiona"
    assert capsys.readouterr().out == ""


def test_volc_credentials_and_configured_never_leak(monkeypatch, capsys):
    assert song_config.song_configured() is False

    monkeypatch.setenv("VOLC_MUSIC_ACCESS_KEY", "AK-SECRET-VALUE")
    assert song_config.song_configured() is False
    monkeypatch.setenv("VOLC_MUSIC_SECRET_KEY", "")
    assert song_config.song_configured() is False

    monkeypatch.setenv("VOLC_MUSIC_SECRET_KEY", "SK-SECRET-VALUE")
    assert song_config.song_configured() is True
    assert song_config.volc_credentials() == ("AK-SECRET-VALUE", "SK-SECRET-VALUE")

    # 校验过程中不打印任何值。
    output = capsys.readouterr().out
    assert output == ""
    assert "AK-SECRET-VALUE" not in output
    assert "SK-SECRET-VALUE" not in output


def test_invalid_value_warning_once_and_exact_format(monkeypatch, capsys):
    monkeypatch.setenv("FIONA_SONG_MAX_INFLIGHT", "999")
    assert song_config.song_max_inflight() == 2
    assert song_config.song_max_inflight() == 2
    assert capsys.readouterr().out == (
        "[song] code=config_invalid name=FIONA_SONG_MAX_INFLIGHT\n"
    )

    monkeypatch.setenv("FIONA_DAILY_SONGS", "0")
    assert song_config.song_daily_limit() == 10
    assert capsys.readouterr().out == (
        "[song] code=config_invalid name=FIONA_DAILY_SONGS\n"
    )


OPTION_COUNTS = {
    "GENRE": 119,
    "GENRE_EXTRA": 119,
    "MOOD": 26,
    "TIMBRE": 27,
    "KMODE": 2,
    "TEMPO": 8,
    "INSTRUMENT": 22,
    "SCENE": 108,
    "LANG": 3,
    "KEY": 13,
}


def test_volc_option_counts_sets_and_labels():
    for prefix, expected in OPTION_COUNTS.items():
        values = getattr(volc_options, f"{prefix}_VALUES")
        value_set = getattr(volc_options, f"{prefix}_SET")
        labels = getattr(volc_options, f"{prefix}_LABELS")

        assert isinstance(values, tuple)
        assert isinstance(value_set, frozenset)
        assert len(values) == expected
        assert len(set(values)) == expected, f"{prefix} 有重复值"
        assert value_set == frozenset(values)
        assert len(value_set) == expected
        assert set(labels) == set(values)
        assert all(isinstance(label, str) and label for label in labels.values())

    assert volc_options.GENRE_EXTRA_VALUES == volc_options.GENRE_VALUES
    assert volc_options.GENRE_EXTRA_SET is volc_options.GENRE_SET
    assert volc_options.GENRE_EXTRA_SET == volc_options.GENRE_SET


def test_volc_option_spot_members_and_order():
    assert volc_options.GENRE_VALUES[0] == "Blues"
    assert volc_options.GENRE_VALUES[-1] == "Chillwave"
    assert volc_options.SCENE_VALUES[0] == "Autumn"
    assert volc_options.SCENE_VALUES[-1] == "Grassland"
    assert volc_options.TEMPO_VALUES == (
        "Grave",
        "Adagio",
        "Moderato",
        "Largo",
        "Andante",
        "Allegro",
        "Vivace",
        "Presto",
    )
    assert volc_options.KMODE_VALUES == ("Major", "Minor")
    assert volc_options.LANG_VALUES == ("Chinese", "English", "Cantonese")
    assert volc_options.KEY_VALUES == (
        "A",
        "A#",
        "B",
        "C",
        "C#",
        "Cb",
        "D",
        "D#",
        "E",
        "F",
        "F#",
        "G",
        "Ab",
    )

    for member in (
        "Hip Hop/Rap",
        "R&B/Soul",
        "Classic R&B / Soul",
        "China-Wave",
        "8 Bit",
        "Classical period",
        "Drum&Bass",
        "DJ",
        "EDM",
        "Chinese Opera",
    ):
        assert member in volc_options.GENRE_SET
        assert member in volc_options.GENRE_EXTRA_SET
    assert "hip hop/rap" not in volc_options.GENRE_SET
    assert "Pop " not in volc_options.GENRE_SET

    for member in (
        "Sweet_SA_MOOD",
        "Thrilling/Suspenseful/Tense",
        "Sentimental/Melancholic/Lonely",
    ):
        assert member in volc_options.MOOD_SET
    for member in ("Romantic_AUDIO_TIMBRE", "Sexy/Lazy", "Chinese Opera Tune"):
        assert member in volc_options.TIMBRE_SET
    for member in ("Congas/Bongos", "Acoustic_Piano", "Electric_Guitar"):
        assert member in volc_options.INSTRUMENT_SET
    for member in (
        "National's Day",
        "Undergound",
        "Valentine's day",
        "Mid-autumn Festival",
        "Qi Xi",
        "Vlog/DailyLife",
        "Park",
    ):
        assert member in volc_options.SCENE_SET
    assert "Underground" not in volc_options.SCENE_SET

    assert volc_options.GENRE_LABELS["Hip Hop/Rap"] == "嘻哈"
    assert volc_options.MOOD_LABELS["Sweet_SA_MOOD"] == "甜蜜"
    assert volc_options.SCENE_LABELS["Undergound"] == "地下"
    assert volc_options.LANG_LABELS["Cantonese"] == "粤语"
