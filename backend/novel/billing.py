"""Durable per-attempt strawberry accounting for the shared novel engine."""

from __future__ import annotations

import asyncio
from decimal import Decimal, InvalidOperation, ROUND_CEILING
import hashlib
import json
import logging
import os

import aiosqlite

from .fake_llm import input_characters
from .run_store import utc_now


# RMB / million * 100 strawberries/RMB * 1.5 / 1000, rounded UP to .01.
# USD prices first use the author's fixed exchange rate of 7.2 RMB/USD.
DEFAULT_PRICES = {
    "dashscope:qwen3.8-max": {"input": 1.80, "output": 5.40},
    "deepseek:deepseek-flash": {"input": 0.33, "output": 1.30},
    "ark:doubao-seed-2-1-pro-260915": {"input": 0.90, "output": 4.50},
}
_warned_bad_price = False
logger = logging.getLogger(__name__)


class InsufficientStrawberries(RuntimeError):
    status = "insufficient_strawberries"

    def __init__(self):
        super().__init__("草莓余额不足，请补充后继续")


class NovelBudgetExceeded(RuntimeError):
    status = "budget_80"

    def __init__(self):
        super().__init__("本次调用将超过本书预算的 80%，请调高预算后继续")


class RunNoLongerActive(RuntimeError):
    """The owner or task token disappeared; never recreate deleted data."""


def get_prices():
    """A whole-table override is validated without echoing its contents."""
    global _warned_bad_price
    raw = os.getenv("FIONA_NOVEL_PRICE_JSON")
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
                logger.warning("小说工坊价目覆盖无效，已回落默认价目")
                _warned_bad_price = True
    return {model: dict(value) for model, value in DEFAULT_PRICES.items()}


def calculate_cost(model, input_tokens, output_tokens, *, prices=None):
    if model == "byok:self" or str(model).startswith("fake:"):
        return 0
    table = get_prices() if prices is None else prices
    if model not in table:
        raise ValueError("该平台模型没有小说工坊价目")
    price = table[model]
    amount = (Decimal(str(max(0, input_tokens))) * Decimal(str(price["input"])) +
              Decimal(str(max(0, output_tokens))) * Decimal(str(price["output"]))) / Decimal(1000)
    return max(1, int(amount.to_integral_value(rounding=ROUND_CEILING)))


def estimate_cost(agents, panel_mode="critique", target=None, recent_steps=()):
    """Estimate from the last 20 real calls, otherwise the measured A2 baseline.

    The baseline is chapter-one usage: input grows linearly through chapter ten
    to twice that level, then stays flat because context is bounded.
    """
    target = target or {}
    minimum = int(target.get("min_chapters", 10))
    maximum = int(target.get("max_chapters", 60))
    advisors = [role for role in agents if role not in {"editor", "writer", "archivist", "reviewer"}]
    critique = panel_mode == "critique" and bool(advisors)
    counts = {role: 1 for role in agents}
    if critique:
        counts["editor"] = 2
    # Writing includes the ordinary revision allowance; archival arc summaries
    # every ten chapters are represented as a fractional additional call.
    counts["writer"] = 2 if "writer" in agents else 0
    if "archivist" in agents:
        counts["archivist"] = 1.1
    history = [row for row in recent_steps if row.get("model") in DEFAULT_PRICES and
               row.get("input_tokens") is not None and row.get("output_tokens") is not None][-20:]
    baseline_in, baseline_out = (110_000, 19_000) if critique else (55_000, 10_000)
    divisor = sum(counts.values()) or 1
    prices = get_prices()

    def chapter_cost(chapter):
        growth = 1 + min(max(chapter - 1, 0), 9) / 9
        amount = 0
        for role, model in agents.items():
            if model == "byok:self" or model.startswith("fake:"):
                continue
            matched = [row for row in history if row.get("model") == model and row.get("role") == role]
            if matched:
                # SQLite rows aggregate schema/network repair attempts in a
                # single step, whereas the baseline is per actual call.
                attempts = sum(max(1, row.get("attempts") or 1) for row in matched)
                incoming = sum(row["input_tokens"] for row in matched) / attempts
                outgoing = sum(row["output_tokens"] for row in matched) / attempts
            else:
                incoming, outgoing = baseline_in / divisor * growth, baseline_out / divisor
            amount += counts.get(role, 1) * calculate_cost(model, incoming, outgoing, prices=prices)
        return amount

    low_chapter = int(chapter_cost(1) * .8)
    high_chapter = int(Decimal(str(chapter_cost(maximum) * 1.2)).to_integral_value(rounding=ROUND_CEILING))
    low_total = int(sum(chapter_cost(chapter) for chapter in range(1, minimum + 1)) * .8)
    high_total = int(Decimal(str(sum(chapter_cost(chapter) for chapter in range(1, maximum + 1)) * 1.2))
                     .to_integral_value(rounding=ROUND_CEILING))
    return {"per_chapter": {"min": low_chapter, "max": high_chapter},
            "total": {"min": low_total, "max": high_total},
            "chapter_range": [low_chapter, high_chapter], "book_range": [low_total, high_total],
            "method": "最近20条真实步骤均值；无历史时采用A2基线，输入第1至10章线性增长至2倍，之后保持不变；区间为估值的80%至120%"}


class NovelBilling:
    atomic_step_settlement = True

    def __init__(self, username, novel_id, run_token=None):
        self.username, self.novel_id, self.run_token = username, novel_id, run_token
        self._lock = asyncio.Lock()

    @staticmethod
    def is_free(call):
        return (os.getenv("DEV_MODE", "0") == "1" or call.get("dry_run", False) or
                call["model"] == "byok:self" or call["model"].startswith("fake:"))

    async def _active(self, db):
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT n.* FROM novels n JOIN users u ON u.username=n.username "
            "WHERE n.id=? AND n.username=?", (self.novel_id, self.username))
        row = await cursor.fetchone()
        if row is None or (self.run_token is not None and row["run_token"] != self.run_token):
            raise RunNoLongerActive()
        return row

    @staticmethod
    async def _drain(operation):
        """Finish a database operation before delivering external cancellation.

        aiosqlite cannot cancel a statement already queued on its worker thread.
        Shield the whole transaction, including connection cleanup, and consume
        its result before propagating cancellation to the calling worker.
        """
        task = asyncio.create_task(operation)
        cancelled = False
        while True:
            try:
                result = await asyncio.shield(task)
                break
            except asyncio.CancelledError:
                if task.done() and task.cancelled():
                    raise
                cancelled = True
        if cancelled:
            raise asyncio.CancelledError
        return result

    async def reserve(self, call):
        if self.is_free(call):
            return 0
        amount = calculate_cost(call["model"], input_characters(call["messages"]), call["max_tokens"])
        try:
            return await self._drain(self._reserve_transaction(call, amount))
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
                book = await self._active(db)
                if book["spent_strawberries"] + book["reserved_strawberries"] + amount >= book["budget_strawberries"] * .8:
                    raise NovelBudgetExceeded()
                await database._apply_daily_refill(db, self.username, database.strawberry_daily_refill())
                cursor = await db.execute(
                    "UPDATE users SET strawberry_balance=strawberry_balance-? "
                    "WHERE username=? AND strawberry_balance>=? RETURNING strawberry_balance",
                    (amount, self.username, amount))
                if await cursor.fetchone() is None:
                    raise InsufficientStrawberries()
                now = utc_now()
                digest = hashlib.sha256(json.dumps(call["messages"], ensure_ascii=False,
                                                   sort_keys=True).encode()).hexdigest()
                await db.execute(
                    "INSERT INTO novel_steps (novel_id,username,step_key,role,model,status,request_digest,"
                    "strawberries_reserved,strawberries_charged,billing_status,created_at,updated_at) "
                    "VALUES (?,?,?,?,?,'interrupted',?,?,0,'reserved',?,?) "
                    "ON CONFLICT(novel_id,step_key) DO UPDATE SET role=excluded.role,model=excluded.model,"
                    "request_digest=excluded.request_digest,strawberries_reserved=excluded.strawberries_reserved,"
                    "status='interrupted',billing_status='reserved',updated_at=excluded.updated_at",
                    (self.novel_id, self.username, call["step_key"], call["role"], call["model"], digest, amount, now, now))
                await db.execute("UPDATE novels SET reserved_strawberries=reserved_strawberries+?,updated_at=? "
                                 "WHERE id=? AND username=?", (amount, now, self.novel_id, self.username))
                await db.commit()
        return amount

    async def settle(self, call, usage, *, step_record=None):
        if self.is_free(call):
            return 0
        known = usage and usage.get("input_tokens") is not None and usage.get("output_tokens") is not None
        amount = calculate_cost(call["model"], usage["input_tokens"], usage["output_tokens"]) if known else None
        return await self._finish(call, amount, step_record=step_record)

    async def refund(self, call):
        return await self._finish(call, None)

    async def _finish(self, call, charge, *, step_record=None):
        return await self._drain(self._finish_transaction(call, charge, step_record=step_record))

    async def _finish_transaction(self, call, charge, *, step_record=None):
        import database
        async with self._lock:
            async with aiosqlite.connect(database.DB_PATH, timeout=database.SQLITE_BUSY_TIMEOUT) as db:
                await db.execute("BEGIN IMMEDIATE")
                await self._active(db)
                cursor = await db.execute("SELECT strawberries_reserved,billing_status FROM novel_steps "
                                          "WHERE novel_id=? AND username=? AND step_key=?",
                                          (self.novel_id, self.username, call["step_key"]))
                row = await cursor.fetchone()
                if row is None or row["billing_status"] != "reserved":
                    return 0
                reserved = row["strawberries_reserved"]
                charged = 0 if charge is None else min(reserved, charge)
                await db.execute("UPDATE users SET strawberry_balance=strawberry_balance+? WHERE username=?",
                                 (reserved - charged, self.username))
                await db.execute("UPDATE novels SET reserved_strawberries=MAX(0,reserved_strawberries-?),"
                                 "spent_strawberries=spent_strawberries+?,updated_at=? WHERE id=? AND username=?",
                                 (reserved, charged, utc_now(), self.novel_id, self.username))
                await db.execute("UPDATE novel_steps SET billing_status=?,strawberries_charged=strawberries_charged+?,"
                                 "updated_at=? WHERE novel_id=? AND username=? AND step_key=?",
                                 ("refunded" if charge is None else "settled", charged, utc_now(),
                                  self.novel_id, self.username, call["step_key"]))
                if step_record is not None:
                    # A validated paid result becomes reusable in the exact
                    # transaction that charges it. No paid-but-incomplete gap.
                    from .store_db import DbStepStore
                    await DbStepStore.write_step_on_connection(db, self.username, self.novel_id,
                                                               call["step_key"], step_record)
                await db.commit()
                return charged

    async def refund_reserved(self):
        """Recover all outstanding attempts once, including a killed process."""
        return await self._drain(self._refund_reserved_transaction())

    async def _refund_reserved_transaction(self):
        import database
        async with self._lock:
            async with aiosqlite.connect(database.DB_PATH, timeout=database.SQLITE_BUSY_TIMEOUT) as db:
                await db.execute("BEGIN IMMEDIATE")
                db.row_factory = aiosqlite.Row
                cursor = await db.execute("SELECT COALESCE(SUM(strawberries_reserved),0) AS amount FROM novel_steps "
                                          "WHERE novel_id=? AND username=? AND billing_status='reserved'",
                                          (self.novel_id, self.username))
                amount = (await cursor.fetchone())["amount"]
                await db.execute("UPDATE users SET strawberry_balance=strawberry_balance+? WHERE username=?",
                                 (amount, self.username))
                await db.execute("UPDATE novels SET reserved_strawberries=MAX(0,reserved_strawberries-?) "
                                 "WHERE id=? AND username=?", (amount, self.novel_id, self.username))
                await db.execute("UPDATE novel_steps SET billing_status='refunded',status='interrupted',updated_at=? "
                                 "WHERE novel_id=? AND username=? AND billing_status='reserved'",
                                 (utc_now(), self.novel_id, self.username))
                await db.commit()
        return amount
