"""Strawberry accounting for the agent discussion groups.

The transaction boundaries mirror :mod:`novel.billing`: a reservation and its
step row commit together, and a settlement returns the difference while writing
the validated step in the same commit. Only the budget rule differs from the
novel workshop: the whole group budget may be used, without the 80% ceiling.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal, InvalidOperation
import hashlib
import json
import logging
import os

import aiosqlite

from novel.billing import (
    InsufficientStrawberries,
    NovelBilling,
    NovelBudgetExceeded,
    RunNoLongerActive,
    calculate_cost,
)
from novel.fake_llm import input_characters
from novel.run_store import utc_now


DEFAULT_PRICES = {
    "dashscope:qwen3.8-max": {"input": 1.80, "output": 5.40},
    "deepseek:deepseek-flash": {"input": 0.33, "output": 1.30},
    "ark:doubao-seed-2-1-pro-260915": {"input": 0.90, "output": 4.50},
}
_warned_bad_price = False
logger = logging.getLogger(__name__)


class DiscussBudgetExceeded(NovelBudgetExceeded):
    status = "budget"

    def __init__(self):
        RuntimeError.__init__(self, "本次调用会超过这个讨论群的预算，请调高预算后继续")


def get_prices():
    """A whole-table override is validated without echoing its contents."""
    global _warned_bad_price
    raw = os.getenv("FIONA_DISCUSS_PRICE_JSON")
    if raw is not None:
        try:
            parsed = json.loads(raw)
            if not isinstance(parsed, dict) or set(parsed) != set(DEFAULT_PRICES):
                raise ValueError
            prices = {}
            for model, value in parsed.items():
                if not isinstance(value, dict) or set(value) != {"input", "output"}:
                    raise ValueError
                prices[model] = {}
                for direction in ("input", "output"):
                    amount = value[direction]
                    if isinstance(amount, bool) or not isinstance(amount, (int, float)):
                        raise ValueError
                    number = Decimal(str(amount))
                    if not number.is_finite() or number < 0:
                        raise ValueError
                    prices[model][direction] = float(number)
            return prices
        except (ValueError, TypeError, InvalidOperation):
            if not _warned_bad_price:
                logger.warning("讨论群价目覆盖无效，已回落默认价目")
                _warned_bad_price = True
    return {model: dict(value) for model, value in DEFAULT_PRICES.items()}


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class DiscussBilling:
    atomic_step_settlement = True

    def __init__(self, username, group_id, run_token=None):
        self.username, self.group_id, self.run_token = username, group_id, run_token
        self._lock = asyncio.Lock()

    @staticmethod
    def is_free(call):
        return (os.getenv("DEV_MODE", "0") == "1" or call.get("dry_run", False) or
                call["model"] == "byok:self" or call["model"].startswith("fake:"))

    async def _active(self, db):
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT g.* FROM discuss_groups g JOIN users u ON u.username=g.username "
            "WHERE g.id=? AND g.username=?", (self.group_id, self.username))
        row = await cursor.fetchone()
        if row is None or (self.run_token is not None and row["run_token"] != self.run_token):
            raise RunNoLongerActive()
        return row

    async def reserve(self, call):
        if self.is_free(call):
            return 0
        amount = calculate_cost(call["model"], input_characters(call["messages"]),
                                call["max_tokens"], prices=get_prices())
        try:
            return await NovelBilling._drain(self._reserve_transaction(call, amount))
        except asyncio.CancelledError:
            # The protected transaction may have committed. Compensate using
            # its durable reserved row, never a second untracked balance refund.
            await self.refund(call)
            raise

    async def _reserve_transaction(self, call, amount):
        import database
        async with self._lock:
            async with aiosqlite.connect(database.DB_PATH, timeout=database.SQLITE_BUSY_TIMEOUT) as db:
                await db.execute("BEGIN IMMEDIATE")
                group = await self._active(db)
                if (group["spent_strawberries"] + group["reserved_strawberries"] + amount
                        > group["budget_strawberries"]):
                    raise DiscussBudgetExceeded()
                await database._apply_daily_refill(db, self.username, database.strawberry_daily_refill())
                cursor = await db.execute(
                    "UPDATE users SET strawberry_balance=strawberry_balance-? "
                    "WHERE username=? AND strawberry_balance>=? RETURNING strawberry_balance",
                    (amount, self.username, amount))
                if await cursor.fetchone() is None:
                    raise InsufficientStrawberries()
                now = utc_now()
                digest = hashlib.sha256(
                    _json(call["messages"]).encode()
                ).hexdigest()
                await db.execute(
                    "INSERT INTO discuss_steps (group_id,username,step_key,role,model,status,"
                    "request_digest,strawberries_reserved,strawberries_charged,billing_status,"
                    "created_at,updated_at) "
                    "VALUES (?,?,?,?,?,'interrupted',?,?,0,'reserved',?,?) "
                    "ON CONFLICT(group_id,step_key) DO UPDATE SET role=excluded.role,"
                    "model=excluded.model,request_digest=excluded.request_digest,"
                    "strawberries_reserved=excluded.strawberries_reserved,"
                    "status='interrupted',billing_status='reserved',updated_at=excluded.updated_at",
                    (self.group_id, self.username, call["step_key"], call["role"], call["model"],
                     digest, amount, now, now))
                await db.execute(
                    "UPDATE discuss_groups SET reserved_strawberries=reserved_strawberries+?,"
                    "updated_at=? WHERE id=? AND username=?",
                    (amount, now, self.group_id, self.username))
                await db.commit()
        return amount

    async def settle(self, call, usage, *, step_record=None):
        if self.is_free(call):
            return 0
        known = bool(usage) and usage.get("input_tokens") is not None and usage.get("output_tokens") is not None
        amount = (calculate_cost(call["model"], usage["input_tokens"], usage["output_tokens"],
                                 prices=get_prices())
                  if known else None)
        return await self._finish(call, amount, step_record=step_record)

    async def refund(self, call):
        return await self._finish(call, None)

    async def _finish(self, call, charge, *, step_record=None):
        return await NovelBilling._drain(
            self._finish_transaction(call, charge, step_record=step_record))

    async def _finish_transaction(self, call, charge, *, step_record=None):
        import database
        async with self._lock:
            async with aiosqlite.connect(database.DB_PATH, timeout=database.SQLITE_BUSY_TIMEOUT) as db:
                await db.execute("BEGIN IMMEDIATE")
                await self._active(db)
                cursor = await db.execute(
                    "SELECT strawberries_reserved,billing_status FROM discuss_steps "
                    "WHERE group_id=? AND username=? AND step_key=?",
                    (self.group_id, self.username, call["step_key"]))
                row = await cursor.fetchone()
                if row is None or row["billing_status"] != "reserved":
                    return 0
                reserved = row["strawberries_reserved"]
                charged = 0 if charge is None else min(reserved, charge)
                now = utc_now()
                await db.execute(
                    "UPDATE users SET strawberry_balance=strawberry_balance+? WHERE username=?",
                    (reserved - charged, self.username))
                await db.execute(
                    "UPDATE discuss_groups SET reserved_strawberries=MAX(0,reserved_strawberries-?),"
                    "spent_strawberries=spent_strawberries+?,updated_at=? WHERE id=? AND username=?",
                    (reserved, charged, now, self.group_id, self.username))
                await db.execute(
                    "UPDATE discuss_steps SET billing_status=?,"
                    "strawberries_charged=strawberries_charged+?,updated_at=? "
                    "WHERE group_id=? AND username=? AND step_key=?",
                    ("refunded" if charge is None else "settled", charged, now,
                     self.group_id, self.username, call["step_key"]))
                if step_record is not None:
                    # A validated paid result becomes reusable in the exact
                    # transaction that charges it. No paid-but-incomplete gap.
                    from .store import DiscussStepStore
                    await DiscussStepStore.write_step_on_connection(
                        db, self.username, self.group_id, call["step_key"], step_record)
                await db.commit()
                return charged

    async def refund_reserved(self):
        """Recover all outstanding attempts once, including a killed process."""
        return await NovelBilling._drain(self._refund_reserved_transaction())

    async def _refund_reserved_transaction(self):
        import database
        from .store import refund_reserved_on_connection
        async with self._lock:
            async with aiosqlite.connect(database.DB_PATH, timeout=database.SQLITE_BUSY_TIMEOUT) as db:
                await db.execute("BEGIN IMMEDIATE")
                amount = await refund_reserved_on_connection(db, self.username, self.group_id)
                await db.commit()
        return amount

    async def reserve_fixed(self, step_key, role, amount):
        if self.is_free({"model": "search"}) or amount == 0:
            return 0
        try:
            return await NovelBilling._drain(
                self._reserve_fixed_transaction(step_key, role, amount))
        except asyncio.CancelledError:
            await self.refund_fixed(step_key)
            raise

    async def _reserve_fixed_transaction(self, step_key, role, amount):
        import database
        async with self._lock:
            async with aiosqlite.connect(database.DB_PATH, timeout=database.SQLITE_BUSY_TIMEOUT) as db:
                await db.execute("BEGIN IMMEDIATE")
                group = await self._active(db)
                if (group["spent_strawberries"] + group["reserved_strawberries"] + amount
                        > group["budget_strawberries"]):
                    raise DiscussBudgetExceeded()
                await database._apply_daily_refill(db, self.username, database.strawberry_daily_refill())
                cursor = await db.execute(
                    "UPDATE users SET strawberry_balance=strawberry_balance-? "
                    "WHERE username=? AND strawberry_balance>=? RETURNING strawberry_balance",
                    (amount, self.username, amount))
                if await cursor.fetchone() is None:
                    raise InsufficientStrawberries()
                now = utc_now()
                await db.execute(
                    "INSERT INTO discuss_steps (group_id,username,step_key,role,model,status,"
                    "strawberries_reserved,strawberries_charged,billing_status,created_at,updated_at) "
                    "VALUES (?,?,?,?,'search','interrupted',?,0,'reserved',?,?) "
                    "ON CONFLICT(group_id,step_key) DO UPDATE SET role=excluded.role,"
                    "model='search',strawberries_reserved=excluded.strawberries_reserved,"
                    "status='interrupted',billing_status='reserved',updated_at=excluded.updated_at",
                    (self.group_id, self.username, str(step_key), role, amount, now, now))
                await db.execute(
                    "UPDATE discuss_groups SET reserved_strawberries=reserved_strawberries+?,"
                    "updated_at=? WHERE id=? AND username=?",
                    (amount, now, self.group_id, self.username))
                await db.commit()
        return amount

    async def settle_fixed(self, step_key, step_record):
        return await NovelBilling._drain(
            self._settle_fixed_transaction(step_key, step_record))

    async def _settle_fixed_transaction(self, step_key, step_record):
        import database
        async with self._lock:
            async with aiosqlite.connect(database.DB_PATH, timeout=database.SQLITE_BUSY_TIMEOUT) as db:
                await db.execute("BEGIN IMMEDIATE")
                await self._active(db)
                async with db.execute(
                    "SELECT strawberries_reserved,billing_status FROM discuss_steps "
                    "WHERE group_id=? AND username=? AND step_key=?",
                    (self.group_id, self.username, str(step_key)),
                ) as cursor:
                    row = await cursor.fetchone()
                settled = 0
                now = utc_now()
                if row is not None and row["billing_status"] == "reserved":
                    settled = row["strawberries_reserved"]
                    await db.execute(
                        "UPDATE discuss_groups SET "
                        "reserved_strawberries=MAX(0,reserved_strawberries-?),"
                        "spent_strawberries=spent_strawberries+?,updated_at=? "
                        "WHERE id=? AND username=?",
                        (settled, settled, now, self.group_id, self.username))
                    await db.execute(
                        "UPDATE discuss_steps SET billing_status='settled',"
                        "strawberries_charged=strawberries_charged+?,updated_at=? "
                        "WHERE group_id=? AND username=? AND step_key=?",
                        (settled, now, self.group_id, self.username, str(step_key)))
                if step_record is not None:
                    from .store import DiscussStepStore
                    await DiscussStepStore.write_step_on_connection(
                        db, self.username, self.group_id, step_key, step_record)
                await db.commit()
        return settled

    async def refund_fixed(self, step_key):
        return await NovelBilling._drain(self._refund_fixed_transaction(step_key))

    async def _refund_fixed_transaction(self, step_key):
        import database
        async with self._lock:
            async with aiosqlite.connect(database.DB_PATH, timeout=database.SQLITE_BUSY_TIMEOUT) as db:
                await db.execute("BEGIN IMMEDIATE")
                await self._active(db)
                async with db.execute(
                    "SELECT strawberries_reserved,billing_status FROM discuss_steps "
                    "WHERE group_id=? AND username=? AND step_key=?",
                    (self.group_id, self.username, str(step_key)),
                ) as cursor:
                    row = await cursor.fetchone()
                amount = 0
                if row is not None and row["billing_status"] == "reserved":
                    amount = row["strawberries_reserved"]
                    now = utc_now()
                    await db.execute(
                        "UPDATE users SET strawberry_balance=strawberry_balance+? WHERE username=?",
                        (amount, self.username))
                    await db.execute(
                        "UPDATE discuss_groups SET "
                        "reserved_strawberries=MAX(0,reserved_strawberries-?),updated_at=? "
                        "WHERE id=? AND username=?",
                        (amount, now, self.group_id, self.username))
                    await db.execute(
                        "UPDATE discuss_steps SET billing_status='refunded',status='interrupted',"
                        "updated_at=? WHERE group_id=? AND username=? AND step_key=?",
                        (now, self.group_id, self.username, str(step_key)))
                await db.commit()
        return amount
