"""面向用户的日期和时间统一使用北京时间。"""

from datetime import datetime
from zoneinfo import ZoneInfo


BEIJING = ZoneInfo("Asia/Shanghai")


def beijing_now() -> datetime:
    return datetime.now(BEIJING)
