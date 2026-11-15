# -*- coding: utf-8 -*-
"""在真实项目代码上复现「写事务被取消后残留写锁」（只用临时库，不碰真实数据）。

用法：在某个代码副本的 backend/ 目录下运行
    .venv/bin/python -B <本文件路径>

对每条路径：把取消依次落在被测写函数的每一次 aiosqlite 调用上（落点 = 结果已交回事件循环、
任务还没被唤醒，即真实故障的窗口），像真实代码那样用 gather(return_exceptions=True) 等任务结束，
然后在任务对象仍被引用的情况下执行真实的「收尾写库」，看它是否报 database is locked。
忙等待被调成 0.3 秒，只为跑得快；真实配置是 5 秒，表现为收尾卡 5 秒后报错。
"""
import os
import sys
import tempfile

_tmp = tempfile.mkdtemp(prefix="fiona-cancel-repro-")
os.environ["PYTHON_DOTENV_DISABLED"] = "1"
os.environ["FIONA_DB_PATH"] = os.path.join(_tmp, "repro.db")
os.environ["FIONA_UPLOADS_DIR"] = os.path.join(_tmp, "uploads")
os.environ["FIONA_STUDIO_DIR"] = os.path.join(_tmp, "studio")
os.makedirs(os.environ["FIONA_STUDIO_DIR"], exist_ok=True)
os.environ.setdefault("FIONA_STUDIO_OWNERS", "")
os.environ.setdefault("JWT_SECRET", "placeholder-secret-for-local-probe-0123456789")
os.environ.setdefault("DASHSCOPE_API_KEY", "sk-placeholder-not-real")
sys.path.insert(0, os.getcwd())

import asyncio  # noqa: E402
import gc  # noqa: E402

import aiosqlite  # noqa: E402
import aiosqlite.core as core  # noqa: E402

import database  # noqa: E402


class Injector:
    def __init__(self):
        self.reset(None)

    def reset(self, k):
        self.task, self.active, self.k = None, False, k
        self.n, self.fired, self._arm = 0, None, False


INJ = Injector()
_orig_execute = core.Connection._execute
_orig_set_result = core.set_result


def _label(fn, args):
    name = getattr(fn, "__name__", repr(fn))
    sql = " " + " ".join(args[0].split())[:46] if args and isinstance(args[0], str) else ""
    return f"{name}{sql}"


async def _patched_execute(self, fn, *args, **kwargs):
    if INJ.active and asyncio.current_task() is INJ.task:
        INJ.n += 1
        if INJ.n == INJ.k:
            INJ.fired = _label(fn, args)
            INJ._arm = True
    return await _orig_execute(self, fn, *args, **kwargs)


def _patched_set_result(fut, result):
    _orig_set_result(fut, result)
    if INJ._arm:
        INJ._arm = False
        INJ.active = False
        INJ.task.cancel()


core.Connection._execute = _patched_execute
core.set_result = _patched_set_result


async def sweep(name, victim, follow_up, follow_up_name, prepare=None):
    rows = []
    k = 1
    while k <= 60:
        if prepare is not None:
            await prepare()
        INJ.reset(k)

        async def run():
            INJ.active = True
            try:
                await victim()
            finally:
                INJ.active = False

        task = asyncio.create_task(run())
        INJ.task = task
        results = await asyncio.gather(task, return_exceptions=True)
        if INJ.fired is None:
            del task, results
            break
        cancelled = isinstance(results[0], asyncio.CancelledError)
        # 此刻任务对象仍被本函数引用，与 cancel_novel / _wait_task 的处境相同。
        try:
            await follow_up()
            state = "ok"
        except Exception as error:  # noqa: BLE001
            state = f"FAILED {type(error).__name__}: {error}"
        rows.append((k, INJ.fired, cancelled, state))
        # 放掉对已取消任务的全部引用（包括注入器里那一份），僵尸连接才会真正关闭。
        INJ.task = None
        del task, results
        gc.collect()
        k += 1
    failed = [row for row in rows if row[3] != "ok"]
    print(f"\n## {name}")
    print(f"   取消点 {len(rows)} 个；之后执行 {follow_up_name}：失败 {len(failed)} 个")
    for k, fired, cancelled, state in rows:
        mark = "  <== " + state if state != "ok" else ""
        print(f"   k={k:<2d} [{fired:<60s}] 取消送达={cancelled!s:<5s} 收尾写库={'ok' if state == 'ok' else '失败'}{mark}")
    return len(rows), len(failed)


async def main():
    database.SQLITE_BUSY_TIMEOUT = 0.3
    await database.init_db()
    await database.get_or_create_user("probe")
    async with aiosqlite.connect(database.DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO novels (id, username, seed_idea, status, config_json, "
            "budget_strawberries, run_token) VALUES ('novel-1','probe','seed','running','{}',1000,'tok')")
        # 不用 INSERT OR IGNORE：约束不满足时要当场报错，而不是静默没插进去。
        await db.execute(
            "INSERT INTO agent_exchanges (id, initiator_username, recipient_username, "
            "initiator_agent_id, recipient_agent_id, pair_key, initiator_json, recipient_json, "
            "topic, max_turns, token_budget, status, run_token) VALUES ('exchange-1','probe',"
            "'probe-peer','agent-a','agent-b','agent-a:agent-b','{}','{}','话题',4,100000,'running','tok')")
        await db.commit()
        async with db.execute("SELECT COUNT(*) FROM novels") as cursor:
            assert (await cursor.fetchone())[0] == 1, "书斋测试数据没有插进去"
        async with db.execute("SELECT COUNT(*) FROM agent_exchanges") as cursor:
            assert (await cursor.fetchone())[0] == 1, "分身交流测试数据没有插进去"

    async def reset_exchange():
        async with aiosqlite.connect(database.DB_PATH) as db:
            await db.execute("UPDATE agent_exchanges SET status='running', run_token='tok', "
                             "inflight_call_id=NULL WHERE id='exchange-1'")
            await db.commit()

    import agent_store
    import exchange_store
    import trace
    from novel.billing import NovelBilling
    from novel.store_db import DbStepStore

    store = DbStepStore("probe", "novel-1", "tok")
    usage = {"step_key": "probe-step", "role": "writer", "model": "fake:probe",
             "input_tokens": 1, "output_tokens": 1, "cached_tokens": 0, "duration_ms": 1}

    async def refund_novel():
        await NovelBilling("probe", "novel-1").refund_reserved()

    async def settle_exchange():
        await exchange_store.stop_and_discard_reserved_calls("exchange-1", "tok", "stopped")

    async def refund_chat():
        await database.refund_strawberries("probe", 1)

    total = failed = 0
    for name, victim, follow_up, follow_name, prepare in (
        ("书斋：写作任务正在记步骤用量（DbStepStore.append_usage），此时被暂停/删除",
         lambda: store.append_usage(dict(usage)), refund_novel,
         "cancel_novel 的下一步 NovelBilling.refund_reserved", None),
        ("分身交流：任务正在预留一次模型调用（exchange_store.reserve_model_call），此时被停止",
         lambda: exchange_store.reserve_model_call("exchange-1", "tok", 0, "turn", 10, 10),
         settle_exchange, "取消后的结算 stop_and_discard_reserved_calls", reset_exchange),
        ("聊天（Claude 智能体）：正在确认会话（agent_store.resolve_chat_conversation），客户端断开",
         lambda: agent_store.resolve_chat_conversation("probe"), refund_chat,
         "run_chat 收尾里的 refund_strawberries", None),
        ("聊天后处理/讨论群分身：读取私有记忆（agent_store.get_memory_snapshot）",
         lambda: agent_store.get_memory_snapshot("probe"), refund_chat, "refund_strawberries", None),
        ("保存消息（database.save_message）",
         lambda: database.save_message("probe", "user", "你好"), refund_chat, "refund_strawberries", None),
        ("写埋点（trace.log_event）",
         lambda: trace.log_event("probe", "chat"), refund_chat, "refund_strawberries", None),
    ):
        points, bad = await sweep(name, victim, follow_up, follow_name, prepare)
        total += points
        failed += bad
    print(f"\nREAL_CODE_REPRO cancel_points={total} follow_up_failed={failed}")
    return failed


if __name__ == "__main__":
    sys.exit(1 if asyncio.run(main()) else 0)
