"""工作室共用付费密钥，因此日额度按全工作室计算，不按作者拆分。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from . import pricing
from .config import get_settings


RESERVED_STATUSES = frozenset({"queued", "submitting", "submitted", "running", "uncertain", "succeeded"})
ZERO_STATUSES = frozenset({"rejected", "cancelled", "released", "filtered"})
SETTLED_STATUSES = frozenset({"downloaded", "failed", "expired"})


def shanghai_day(now: datetime | str | None = None) -> str:
    from .store import parse_time
    instant = datetime.now(timezone.utc) if now is None else parse_time(now)
    try:
        zone = ZoneInfo("Asia/Shanghai")
    except Exception:
        zone = timezone(timedelta(hours=8))
    return instant.astimezone(zone).date().isoformat()


async def committed(db, day: str) -> Decimal:
    """在调用者的读快照或写事务里求和，避免 SQLite 浮点累加误差。"""
    async with db.execute(
        "SELECT status, reserved_cny, actual_cny FROM studio_jobs WHERE confirmed_day=?", (day,)
    ) as cursor:
        rows = await cursor.fetchall()
    amount = Decimal(0)
    for row in rows:
        if row["status"] in ZERO_STATUSES:
            continue
        if row["actual_cny"] is not None:
            amount += pricing.money(row["actual_cny"])
        elif row["status"] in RESERVED_STATUSES | SETTLED_STATUSES:
            # 已结束但用量无效的任务尚未结算，仍须占用原预留额度。
            amount += pricing.money(row["reserved_cny"])
    return pricing.money(amount)


async def today(owner: str | None = None, *, now=None, db=None) -> dict:
    """owner 仅为调用兼容参数，不能绕过共用 API 密钥的总花费上限。"""
    if db is None:
        from .store import connection
        async with connection() as current:
            return await today(owner, now=now, db=current)
    occupied = await committed(db, shanghai_day(now))
    remaining = max(Decimal(0), pricing.money(get_settings().daily_cny) - occupied)
    return {"committed_cny": float(occupied), "remaining_cny": float(remaining)}


async def check_reservation(db, amount, *, now=None) -> str:
    """只能在确认报价的 BEGIN IMMEDIATE 事务内调用。"""
    day = shanghai_day(now)
    occupied = await committed(db, day)
    remaining = max(Decimal(0), pricing.money(get_settings().daily_cny) - occupied)
    if pricing.money(amount) > remaining:
        raise HTTPException(409, f"今日额度不足，剩余额度 ¥{remaining:.2f}")
    return day


async def check_quote_budget(db, amount, *, now=None) -> str:
    """人民币报价的单次上限与日上限；只能在确认或写入报价的写事务内调用。"""
    value = pricing.money(amount)
    cap = pricing.money(get_settings().max_quote_cny)
    if value > cap:
        raise HTTPException(409, f"超过单次报价上限 ¥{cap:.2f}，超出 ¥{value - cap:.2f}")
    return await check_reservation(db, value, now=now)


async def settle_job(job_id: str, expected_status, status: str, *, usage=None, run_token=None, **updates) -> bool:
    """终态和额度在同一条 CAS 中提交，重复结算不会重复计费。"""
    from . import store
    if status not in ZERO_STATUSES | SETTLED_STATUSES:
        raise ValueError("只允许结算终态任务")
    if usage is not None:
        updates["usage_json"] = usage
    updates["status"] = status
    return await store.cas_job(job_id, expected_status, updates, run_token=run_token)


def shanghai_month(now=None) -> str:
    return shanghai_day(now)[:7]


async def brain_month_used(owner: str, *, now=None, db=None) -> Decimal:
    if db is None:
        from .store import connection
        async with connection() as current:
            return await brain_month_used(owner, now=now, db=current)
    async with db.execute("""SELECT status,reserved_amount,actual_amount FROM studio_jobs
        WHERE kind IN ('brain','kb_shot','kb_review') AND owner=? AND currency='USD'
        AND confirmed_month=?""",
                          (owner, shanghai_month(now))) as cursor:
        rows = await cursor.fetchall()
    amount = Decimal(0)
    for row in rows:
        if row["status"] in ZERO_STATUSES:
            continue
        value = row["actual_amount"] if row["actual_amount"] is not None else row["reserved_amount"]
        amount += pricing.money(value or 0)
    return pricing.money(amount)


async def check_brain_budget(db, owner: str, totals: dict, *, now=None) -> None:
    cny = pricing.money(totals.get("CNY", 0))
    maximum = pricing.money(get_settings().max_quote_cny)
    if cny > maximum:
        raise HTTPException(409, f"超过单次报价上限 ¥{maximum:.4f}，超出 ¥{cny - maximum:.4f}")
    occupied = await committed(db, shanghai_day(now))
    daily_remaining = max(Decimal(0), pricing.money(get_settings().daily_cny) - occupied)
    if cny > daily_remaining:
        raise HTTPException(409, f"今日额度不足，剩余额度 ¥{daily_remaining:.4f}，还差 ¥{cny - daily_remaining:.4f}")
    remaining = max(Decimal(0), pricing.money(get_settings().brain_monthly_usd)
                    - await brain_month_used(owner, now=now, db=db))
    if pricing.money(totals.get("USD", 0)) > remaining:
        shortage = pricing.money(totals.get("USD", 0)) - remaining
        raise HTTPException(409, f"Claude 本月额度不足，剩余额度 ${remaining:.4f}，还差 ${shortage:.4f}")
