# -*- coding: utf-8 -*-
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest


@pytest.mark.skipif(not hasattr(time, "tzset"), reason="tzset unavailable")
def test_user_facing_dates_use_beijing_when_process_is_new_york(monkeypatch):
    import utils.beijing_time as clock
    from tools.system_tools import get_datetime
    from tools.web_search import _today_directive as search_today
    from tools.travel_plan import _today_directive as travel_today
    from tools.topic_expand import _build_expand_prompt
    from tools.card_detail import _build_detail_prompt
    from persona import get_time_context, _build_special_date_note

    # One instant falls on Monday in New York and Tuesday in Beijing. Freezing
    # the clock makes this a regression test regardless of when pytest runs.
    instant = datetime(2026, 9, 28, 20, 45, tzinfo=timezone.utc)
    new_york = instant.astimezone(ZoneInfo("America/New_York"))
    beijing = instant.astimezone(ZoneInfo("Asia/Shanghai"))
    assert (new_york.date(), new_york.weekday()) != (beijing.date(), beijing.weekday())

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return instant.astimezone(tz) if tz else instant.astimezone().replace(tzinfo=None)

    try:
        with monkeypatch.context() as tz_patch:
            tz_patch.setenv("TZ", "America/New_York")
            tz_patch.setattr(clock, "datetime", FixedDatetime)
            time.tzset()
            assert clock.beijing_now() == beijing
            assert clock.beijing_now().utcoffset().total_seconds() == 8 * 3600
            assert get_datetime() == "2026年9月29日 周二 04:45"
            assert "今天是 2026-09-29（周二）" in search_today()
            assert "今天是 2026-09-29（周二）" in travel_today()
            assert "【今日日期：2026年9月29日】" in _build_expand_prompt()
            assert "当前日期为 2026-09-29" in _build_detail_prompt()
            assert "今天是 2026 年 9 月 29 日 周二" in get_time_context()
            assert "现在是凌晨" in get_time_context()
            special = {"special_dates": ["09-29 测试日期"]}
            assert "今天是测试日期" in _build_special_date_note(special)
    finally:
        time.tzset()
