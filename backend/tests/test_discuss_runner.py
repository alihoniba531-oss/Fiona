# -*- coding: utf-8 -*-
"""讨论群后台任务：重启恢复与删号取消（场景 14、18）。

不经过 HTTP：需要直接控制事件循环，让 ``runner.start_group`` /
``recover_interrupted_groups`` 与轮询在同一个循环里完成。
"""
import asyncio
from contextlib import asynccontextmanager
import threading
import time

import aiosqlite
import pytest

import database
from discuss import config as discuss_config
from discuss import research, runner
from discuss import store as discuss_store
from novel.billing import RunNoLongerActive
from novel.byok_bridge import ByokUnavailable
from novel.fake_llm import FakeLLM
from novel.llm_router import LLMRouter

USER = "discuss_runner_user"

PLAN = {
    "title": "讨论群测试方案",
    "goal": "把这件事查清楚并给出可执行建议",
    "deliverable": {"kind": "report", "outline": ["背景", "发现", "建议"]},
    "criteria": ["每个结论有来源", "覆盖两个调研方向", "给出明确建议"],
    "picks": [{"role": "market", "focus": "查市场"},
              {"role": "tech", "focus": "查技术"}],
    "questions": [],
}
QUERIES = {"queries": ["问题一"]}
NOTE = {
    "note": "市场与技术的初步结论 [S1]",
    "key_points": [{"text": "结论一 [S1]", "refs": ["S1"]},
                   {"text": "结论二 [S1]", "refs": ["S1"]}],
    "gaps": [],
}
CRITIQUE = {
    "objections": [{"target": "market", "type": "missing",
                    "problem": "缺少竞品对比", "suggestion": "补查竞品"}],
    "counter_view": "还需要更多证据",
}
DECIDE = {
    "responses": [{"id": "O1", "action": "accept", "reason": "接受"}],
    "note_responses": [],
    "decision": "draft",
    "assignments": [],
    "brief_for_writer": "按调研要点写",
    "summary": "本轮进展",
}
DRAFT = "# 讨论群成果\n\n" + "这是根据调研要点写成的成果正文，结论都有来源支撑。" * 20 + "\n\n引用 [S1]。"
ACCEPT_PASS = {
    "verdicts": [{"id": "C1", "pass": True, "evidence": "有来源"},
                 {"id": "C2", "pass": True, "evidence": "覆盖两个方向"},
                 {"id": "C3", "pass": True, "evidence": "建议明确"}],
    "citation_issues": [],
    "rework": [],
}
BRIEF = {"context": "主人关心成本与落地", "answers": [], "ask_owner": []}
VIEW = {"comment": "对主人有用", "must_fix": []}

RESPONSES = {
    "plan": PLAN,
    "queries": QUERIES,
    "note": NOTE,
    "critique": CRITIQUE,
    "decide": DECIDE,
    "draft": DRAFT,
    "accept": ACCEPT_PASS,
    "rework": {"assignments": [], "note_responses": [],
               "brief_for_writer": "按意见修改", "summary": "返工"},
    "brief": BRIEF,
    "view": VIEW,
}


def search_once(query, context):
    return {
        "query": query,
        "data": {"findings": [{"fact": "一条可核实的事实", "refs": [1]}]},
        "sources": [{"title": "来源一", "url": "https://example.com/a",
                     "site_name": "站点", "index": 1}],
        "error": None,
    }


@pytest.fixture
def world(monkeypatch, tmp_path):
    monkeypatch.setenv("DEV_MODE", "1")
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "discuss_runner.db"))
    asyncio.run(database.init_db())
    asyncio.run(database.get_or_create_user(USER))
    fake = FakeLLM(dict(RESPONSES))
    monkeypatch.setattr(
        runner, "router_factory",
        lambda store, username, group_id, run_token: LLMRouter(
            store, dry_run=True, fake=fake))
    monkeypatch.setattr(research, "search_once", search_once)
    yield fake


def _new_group_id():
    return discuss_store.new_group_id()


async def _create_group(group_id, max_rounds=2, avatar=False, config=None):
    await discuss_store.create_group(
        USER, group_id=group_id, request="帮我研究一下这个方向", materials="",
        budget_strawberries=500, max_rounds=max_rounds,
        config=config if config is not None else {"avatar": avatar},
        created_day=discuss_config.today_beijing(),
    )


async def _wait_for(group_id, states, timeout=8.0):
    deadline = time.monotonic() + timeout
    group = None
    while time.monotonic() < deadline:
        group = await discuss_store.get_group(USER, group_id)
        if group is None:
            pytest.fail("群不存在：" + group_id)
        if group["status"] in states:
            return group
        if group["status"] in ("failed",):
            pytest.fail("群进入失败状态：" + str(group))
        await asyncio.sleep(0.01)
    pytest.fail("等待超时：" + str(group))


def test_recover_interrupted_running_group_completes(world):
    """场景 14：running 群在 TASKS 清空后恢复并跑完。"""
    group_id = _new_group_id()

    async def flow():
        await _create_group(group_id, max_rounds=2)
        await runner.start_group(group_id, USER)
        await _wait_for(group_id, ("awaiting_start",))
        for _ in range(300):
            task = runner.TASKS.get(group_id)
            if task is None or task.done():
                break
            await asyncio.sleep(0.01)
        # 模拟进程重启：数据库里仍是 running，带一个上一进程的令牌，内存里没有任务。
        async with discuss_store.get_db() as db:
            await db.execute(
                "UPDATE discuss_groups SET status='running',stop_reason=NULL,"
                "run_token='dead-worker-token',round=0 WHERE id=? AND username=?",
                (group_id, USER))
            await db.commit()
        runner.TASKS.clear()
        await runner.recover_interrupted_groups()
        return await _wait_for(group_id, ("done", "awaiting_user"))

    group = asyncio.run(flow())
    assert group["status"] == "done"
    assert group["stop_reason"] == "accepted"
    assert group["run_token"] is None
    assert group["reserved_strawberries"] == 0
    assert group["round"] == 1


def test_recover_without_discuss_table_returns(world, monkeypatch, tmp_path):
    """场景 14：discuss_groups 表不存在时恢复函数直接返回、不抛错。"""
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "no_discuss.db"))
    asyncio.run(runner.recover_interrupted_groups())


def test_delete_account_cancels_running_task_and_removes_rows(world, monkeypatch):
    """场景 18：删号取消在跑的任务，五张表里不留该用户的行。"""
    entered = threading.Event()
    release = threading.Event()

    async def blocking_script(request, index):
        task = request.get("task")
        if task == "plan":
            entered.set()
            while not release.is_set():
                await asyncio.sleep(0.01)
        return RESPONSES[task]

    async def counts_by_username():
        counts = {}
        async with discuss_store.get_db() as db:
            for table in ("discuss_groups", "discuss_messages", "discuss_sources",
                          "discuss_steps", "discuss_outputs"):
                async with db.execute(
                        f"SELECT COUNT(*) FROM {table} WHERE username=?", (USER,)) as cursor:
                    counts[table] = (await cursor.fetchone())[0]
        return counts

    async def flow():
        fake = FakeLLM(dict(RESPONSES))
        monkeypatch.setattr(
            runner, "router_factory",
            lambda store, username, gid, token: LLMRouter(store, dry_run=True, fake=fake))
        done_id = _new_group_id()
        await _create_group(done_id)
        await runner.start_group(done_id, USER)
        await _wait_for(done_id, ("awaiting_start",))
        for _ in range(300):
            if done_id not in runner.TASKS:
                break
            await asyncio.sleep(0.01)
        await discuss_store.update_group(USER, done_id, status="running")
        await runner.start_group(done_id, USER)
        await _wait_for(done_id, ("done",))
        for _ in range(300):
            if done_id not in runner.TASKS:
                break
            await asyncio.sleep(0.01)
        before = await counts_by_username()
        assert before["discuss_groups"] == 1
        assert before["discuss_messages"] > 0
        assert before["discuss_sources"] > 0
        assert before["discuss_steps"] > 0
        assert before["discuss_outputs"] == 1

        # 第二个群的规划步骤卡住，制造一个真正持有令牌的任务再删号。
        fake.script = blocking_script
        blocked_id = _new_group_id()
        await _create_group(blocked_id)
        await runner.start_group(blocked_id, USER)
        for _ in range(500):
            if entered.is_set():
                break
            await asyncio.sleep(0.01)
        assert entered.is_set(), "规划步骤没有开始，无法验证取消"
        running = await discuss_store.get_group(USER, blocked_id)
        assert running["run_token"], "任务应在运行中持有令牌"

        result = await database.delete_account_data(USER)
        assert result["deleted"] is True
        for _ in range(100):
            if blocked_id not in runner.TASKS and done_id not in runner.TASKS:
                break
            await asyncio.sleep(0.01)
        assert blocked_id not in runner.TASKS
        assert done_id not in runner.TASKS
        return blocked_id, before, await counts_by_username()

    blocked_id, before, after = asyncio.run(flow())
    release.set()
    assert blocked_id
    assert set(before) == set(after)
    assert after == {table: 0 for table in after}


def test_start_group_with_existing_token_does_not_start_second_task(world):
    """T10 / N1：群里已有 run_token 时不再起第二个任务，令牌保持原值。"""
    group_id = _new_group_id()
    original_token = "existing-run-token"

    async def flow():
        await _create_group(group_id)
        await discuss_store.update_group(
            USER, group_id, status="running", run_token=original_token)
        assert runner.TASKS.get(group_id) is None

        started = await runner.start_group(group_id, USER)
        spawned = runner.TASKS.get(group_id)
        if started is not None:
            # 被改坏时会拿到新任务：先取消并等它退出，避免遗留后台任务。
            started.cancel()
            await asyncio.gather(started, return_exceptions=True)
        if spawned is not None and spawned is not started:
            spawned.cancel()
            await asyncio.gather(spawned, return_exceptions=True)
        for _ in range(300):
            if group_id not in runner.TASKS:
                break
            await asyncio.sleep(0.01)

        assert started is None
        assert runner.TASKS.get(group_id) is None
        group = await discuss_store.get_group(USER, group_id)
        assert group["status"] == "running"
        assert group["run_token"] == original_token
        return group

    group = asyncio.run(flow())
    assert group["run_token"] == original_token


def test_recover_returns_with_users_but_no_discuss_groups_table(
        world, monkeypatch, tmp_path):
    """T11 / N2：users 在而 discuss_groups 不在时，恢复直接返回、不抛错。"""
    monkeypatch.setattr(
        database, "DB_PATH", str(tmp_path / "users_without_discuss.db"))

    async def flow():
        await database.init_db()
        async with discuss_store.get_db() as db:
            async with db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
            ) as cursor:
                assert await cursor.fetchone() is not None
            await db.execute("DROP TABLE discuss_groups")
            await db.commit()
            async with db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name='discuss_groups'"
            ) as cursor:
                assert await cursor.fetchone() is None
        assert await runner.recover_interrupted_groups() is None

    asyncio.run(flow())


def test_byok_unavailable_pauses_with_fixed_error(world, monkeypatch):
    """T13 / N7：自带模型不可用后群暂停，原因与固定文案都写进群。"""
    def unavailable(*args, **kwargs):
        raise ByokUnavailable("自带的模型配置不可用")

    monkeypatch.setattr(runner, "router_factory", unavailable)
    group_id = _new_group_id()

    async def flow():
        await _create_group(group_id)
        task = await runner.start_group(group_id, USER)
        assert task is not None
        await _wait_for(group_id, ("paused",))
        await asyncio.gather(task, return_exceptions=True)
        for _ in range(300):
            if group_id not in runner.TASKS:
                break
            await asyncio.sleep(0.01)
        return await discuss_store.get_group(USER, group_id)

    group = asyncio.run(flow())
    assert group["status"] == "paused"
    assert group["stop_reason"] == "byok_unavailable"
    assert group["last_error"] == "自带模型当前不可用，请到设置里检查后再继续"
    assert group["run_token"] is None


def test_stale_token_store_cannot_write_message_status_or_output(world):
    """T17 / T1：令牌换掉后，旧令牌的 store 三类写操作都不生效。"""
    group_id = _new_group_id()
    new_token = "new-run-token"

    async def flow():
        await _create_group(group_id)
        await discuss_store.update_group(
            USER, group_id, status="running", run_token=new_token)
        before = await discuss_store.get_group(USER, group_id)
        assert before["status"] == "running" and before["round"] == 0
        assert before["run_token"] == new_token
        assert before["output_version"] == 0
        before_messages = await discuss_store.list_messages(USER, group_id)
        assert before_messages == []
        assert await discuss_store.get_output(USER, group_id) is None

        stale = discuss_store.DiscussStepStore(USER, group_id, "old-run-token")
        with pytest.raises(RunNoLongerActive):
            await stale.post_message(0, "host", "message", "旧任务追加的消息")
        with pytest.raises(RunNoLongerActive):
            await stale.save_output(0, "r01/50-draft-writer", "旧任务写下的成果")
        with pytest.raises(RunNoLongerActive):
            await stale.update_group(status="paused", round=9)

        after = await discuss_store.get_group(USER, group_id)
        assert (after["status"], after["round"]) == ("running", 0)
        assert after["run_token"] == new_token
        assert after["output_version"] == 0
        assert await discuss_store.list_messages(USER, group_id) == before_messages
        assert await discuss_store.get_output(USER, group_id) is None
        return after

    group = asyncio.run(flow())
    assert group["status"] == "running"

def test_cancel_group_detaches_task_on_closed_loop_and_clears_token(world):
    """第三节：TASKS 里残留已关闭事件循环的任务时，关停不再等待死循环。"""
    group_id = _new_group_id()

    async def flow():
        await _create_group(group_id)
        await discuss_store.update_group(
            USER, group_id, status="running", run_token="closed-loop-token")
        loop = asyncio.new_event_loop()
        task = loop.create_task(asyncio.sleep(3600))
        loop.close()
        runner.TASKS[group_id] = task
        runner._owners[group_id] = USER
        try:
            await asyncio.wait_for(runner.shutdown_discuss_tasks(), timeout=2)
            # The stale entry must be purged, not merely detached.
            assert group_id not in runner.TASKS
            assert group_id not in runner._owners
        finally:
            task.cancel()
            # The loop never ran the coroutine; close it explicitly so the
            # pending task does not emit an un-awaited-coroutine warning.
            task.get_coro().close()
            runner.TASKS.pop(group_id, None)
            runner._owners.pop(group_id, None)
        group = await discuss_store.get_group(USER, group_id)
        assert group["run_token"] is None

    asyncio.run(flow())


# ── R3：写事务取消保护与注册表清理 ─────────────────────────

def _gate_next_commit(monkeypatch, marks=None):
    """Replace get_db so the next unprotected commit waits for release.

    The setup writes run before this helper is installed.  The protected
    transaction must finish the commit (and close the connection) before the
    caller's CancelledError is delivered.
    """
    import discuss.store as store_module

    original = store_module.get_db
    entered, release = asyncio.Event(), asyncio.Event()

    @asynccontextmanager
    async def gated():
        async with original() as db:
            real_commit = db.commit

            async def commit():
                entered.set()
                await release.wait()
                await real_commit()
                if marks is not None:
                    marks.append("committed")

            db.commit = commit
            yield db

    monkeypatch.setattr(store_module, "get_db", gated)
    return entered, release


async def _assert_write_lock_free():
    connection = await aiosqlite.connect(database.DB_PATH, timeout=0.2)
    try:
        await connection.execute("BEGIN IMMEDIATE")
        await connection.rollback()
    finally:
        await connection.close()


def test_cancelled_store_transaction_finishes_and_releases_lock(world, monkeypatch):
    """R3：事务提交途中取消，事务仍提交并释放锁；新连接 0.2 秒内拿到写锁。"""
    group_id = _new_group_id()
    marks = []

    async def flow():
        await _create_group(group_id)
        await discuss_store.update_group(
            USER, group_id, status="running", run_token="cancel-token")
        entered, release = _gate_next_commit(monkeypatch, marks)
        store = discuss_store.DiscussStepStore(USER, group_id, "cancel-token")

        async def operation(db):
            await db.execute(
                "UPDATE discuss_groups SET title='取消保护' WHERE id=?", (group_id,))
            return "done"

        task = asyncio.create_task(store.transaction(operation))
        await entered.wait()
        task.cancel()
        await asyncio.sleep(0.05)
        assert not task.done(), "取消不应在事务收尾前生效"
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert marks == ["committed"]
        group = await discuss_store.get_group(USER, group_id)
        assert group["title"] == "取消保护"
        await _assert_write_lock_free()

    asyncio.run(flow())


def test_cancelled_store_transaction_twice_finishes_and_releases_lock(world, monkeypatch):
    """R3：同一个事务任务连续取消两次，仍只等事务跑完再交还取消。"""
    group_id = _new_group_id()
    marks = []

    async def flow():
        await _create_group(group_id)
        await discuss_store.update_group(
            USER, group_id, status="running", run_token="cancel-token")
        entered, release = _gate_next_commit(monkeypatch, marks)
        store = discuss_store.DiscussStepStore(USER, group_id, "cancel-token")

        async def operation(db):
            await db.execute(
                "UPDATE discuss_groups SET title='两次取消' WHERE id=?", (group_id,))
            return "done"

        task = asyncio.create_task(store.transaction(operation))
        await entered.wait()
        task.cancel()
        await asyncio.sleep(0.02)
        assert not task.done()
        task.cancel()
        await asyncio.sleep(0.02)
        assert not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert marks == ["committed"]
        await _assert_write_lock_free()

    asyncio.run(flow())


def test_cancelled_pause_write_finishes_and_releases_lock(world, monkeypatch):
    """R3：runner._pause 写入被取消时仍提交，并释放写锁。"""
    group_id = _new_group_id()

    async def flow():
        await _create_group(group_id)
        await discuss_store.update_group(
            USER, group_id, status="running", run_token="cancel-token")
        entered, release = _gate_next_commit(monkeypatch)
        store = discuss_store.DiscussStepStore(USER, group_id, "cancel-token")
        task = asyncio.create_task(runner._pause(store, "budget"))
        await entered.wait()
        task.cancel()
        await asyncio.sleep(0.05)
        assert not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        group = await discuss_store.get_group(USER, group_id)
        assert (group["status"], group["stop_reason"]) == ("paused", "budget")
        await _assert_write_lock_free()

    asyncio.run(flow())


def test_cancelled_cancel_group_token_clear_finishes_and_releases_lock(world, monkeypatch):
    """R3：cancel_group 清令牌被取消时仍提交，并释放写锁。"""
    group_id = _new_group_id()

    async def flow():
        await _create_group(group_id)
        await discuss_store.update_group(
            USER, group_id, status="running", run_token="cancel-token")
        entered, release = _gate_next_commit(monkeypatch)
        task = asyncio.create_task(runner.cancel_group(group_id, USER))
        await entered.wait()
        task.cancel()
        await asyncio.sleep(0.05)
        assert not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        group = await discuss_store.get_group(USER, group_id)
        assert group["run_token"] is None
        await _assert_write_lock_free()

    asyncio.run(flow())


def test_cancel_group_purges_done_task_from_registries(world):
    """N9：cancel_group 处理后，已结束任务也从 TASKS 与 _owners 移除。"""
    group_id = _new_group_id()

    async def flow():
        await _create_group(group_id)
        await discuss_store.update_group(
            USER, group_id, status="running", run_token="done-token")
        task = asyncio.create_task(asyncio.sleep(0))
        await task
        runner.TASKS[group_id] = task
        runner._owners[group_id] = USER
        await runner.cancel_group(group_id, USER)
        assert group_id not in runner.TASKS
        assert group_id not in runner._owners
        group = await discuss_store.get_group(USER, group_id)
        assert group["run_token"] is None

    asyncio.run(flow())


# ── R3 门禁后由规格作者补充 ─────────────────────────────────

def test_stale_worker_pause_writes_nothing_and_returns_quietly(world):
    """过期任务（令牌已被替换）写终态时什么都不写，也不抛异常。"""
    group_id = _new_group_id()

    async def flow():
        await _create_group(group_id)
        await discuss_store.update_group(
            USER, group_id, status="running", run_token="current-token")
        stale = discuss_store.DiscussStepStore(USER, group_id, "stale-token")
        assert await runner._pause(stale, "budget") is None
        group = await discuss_store.get_group(USER, group_id)
        assert (group["status"], group["stop_reason"], group["run_token"]) == (
            "running", None, "current-token")

    asyncio.run(flow())


def _hold_cursor_after_token_check(monkeypatch):
    """Let the guarded transaction's token query run, then hold its unconsumed cursor."""
    import discuss.store as store_module

    original = store_module.get_db
    entered, release = asyncio.Event(), asyncio.Event()
    fired = [False]

    @asynccontextmanager
    async def gated():
        async with original() as db:
            real_execute = db._execute

            async def execute(fn, *args, **kwargs):
                result = await real_execute(fn, *args, **kwargs)
                if (not fired[0] and args and isinstance(args[0], str)
                        and "run_token=?" in args[0]):
                    fired[0] = True
                    entered.set()
                    await release.wait()
                return result

            db._execute = execute
            yield db

    monkeypatch.setattr(store_module, "get_db", gated)
    return entered, release


def test_cancel_with_unconsumed_cursor_leaves_no_write_lock_during_cleanup(world, monkeypatch):
    """取消落在「查询已执行、游标未取走」时，收尾代码仍能立刻拿到写锁。

    这是偶发 database is locked 的真实机制：没有取消保护时，那个没人关的游标会让
    已经关闭的连接继续占着写锁，而收尾代码正拿着取消异常去写库。
    """
    group_id = _new_group_id()
    seen = {}

    async def flow():
        await _create_group(group_id)
        await discuss_store.update_group(
            USER, group_id, status="running", run_token="cancel-token")
        entered, release = _hold_cursor_after_token_check(monkeypatch)
        store = discuss_store.DiscussStepStore(USER, group_id, "cancel-token")

        async def worker():
            try:
                await store.post_message(1, "host", "note", "收尾前的最后一条")
            finally:
                # 与 runner._cleanup 相同的处境：取消异常还在传播时去拿写锁。
                await _assert_write_lock_free()
                seen["cleanup_got_lock"] = True

        task = asyncio.create_task(worker())
        await asyncio.wait_for(entered.wait(), timeout=5)
        task.cancel()
        await asyncio.sleep(0.05)
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert seen == {"cleanup_got_lock": True}

    asyncio.run(flow())


# ── 复核第 6 节 B/E、第 4 节 X17–X20 补充 ───────────────────

def _hold_after(monkeypatch, marker):
    """让匹配的查询执行完、游标还没被取走时停住。

    与 ``04-review.md`` 第 6 节 B 的探针一致：这是 ``agent_store`` 的写事务
    留下僵尸连接、继续占着写锁的机制。
    """
    entered, release = asyncio.Event(), asyncio.Event()
    fired = [False]
    original = aiosqlite.Connection._execute

    async def hooked(self, fn, *args, **kwargs):
        result = await original(self, fn, *args, **kwargs)
        if (not fired[0] and args and isinstance(args[0], str)
                and marker in args[0]):
            fired[0] = True
            entered.set()
            await release.wait()
        return result

    monkeypatch.setattr(aiosqlite.Connection, "_execute", hooked)
    return entered, release


def test_cancelled_avatar_system_for_leaves_no_write_lock_during_cleanup(
        world, monkeypatch):
    """M1：取消 avatar.system_for 时，收尾代码仍能立刻拿到写锁。"""
    import agent_store
    from discuss import avatar

    seen = {}

    async def flow():
        # 先建好 agents 行，避免建行本身的查询被钩子拦下。
        await agent_store.get_my_agent(USER)
        entered, release = _hold_after(
            monkeypatch, "FROM agents WHERE owner_username")

        async def worker():
            try:
                await avatar.system_for(USER, "brief")
            finally:
                await _assert_write_lock_free()
                seen["cleanup_got_lock"] = True

        task = asyncio.create_task(worker())
        await asyncio.wait_for(entered.wait(), timeout=5)
        task.cancel()
        await asyncio.sleep(0.05)
        assert not task.done(), "取消不应在写事务收尾前生效"
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(flow())
    assert seen == {"cleanup_got_lock": True}


def test_cancelled_avatar_display_name_leaves_no_write_lock_during_cleanup(
        world, monkeypatch):
    """M1：取消 avatar.display_name 时，收尾代码仍能立刻拿到写锁。"""
    import agent_store
    from discuss import avatar

    seen = {}

    async def flow():
        await agent_store.get_my_agent(USER)
        entered, release = _hold_after(
            monkeypatch, "FROM agents WHERE owner_username")

        async def worker():
            try:
                await avatar.display_name(USER)
            finally:
                await _assert_write_lock_free()
                seen["cleanup_got_lock"] = True

        task = asyncio.create_task(worker())
        await asyncio.wait_for(entered.wait(), timeout=5)
        task.cancel()
        await asyncio.sleep(0.05)
        assert not task.done(), "取消不应在写事务收尾前生效"
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(flow())
    assert seen == {"cleanup_got_lock": True}


def test_cancelled_start_group_claim_clears_token_and_leaves_no_task(
        world, monkeypatch):
    """E：认领令牌的提交被取消时，补偿清令牌，不留有令牌没任务的群。"""
    group_id = _new_group_id()

    async def flow():
        await _create_group(group_id)
        entered, release = _gate_next_commit(monkeypatch)
        task = asyncio.create_task(runner.start_group(group_id, USER))
        await asyncio.wait_for(entered.wait(), timeout=5)
        task.cancel()
        await asyncio.sleep(0.05)
        assert not task.done(), "取消不应在认领事务收尾前生效"
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        group = await discuss_store.get_group(USER, group_id)
        assert group["status"] == "planning"
        assert group["run_token"] is None
        assert group_id not in runner.TASKS
        assert group_id not in runner._owners
        await _assert_write_lock_free()

    asyncio.run(flow())


def test_recovering_step_failure_pauses_with_server_restart_failed(
        world, monkeypatch):
    """X17 / 规格 4.12：恢复模式下的 StepFailed 记 paused/server_restart_failed。"""
    from discuss import engine
    from novel.llm_router import StepFailed

    group_id = _new_group_id()

    async def failing(*args, **kwargs):
        raise StepFailed("规划步骤失败")

    monkeypatch.setattr(engine, "run_planning", failing)

    async def flow():
        await _create_group(group_id)
        task = await runner.start_group(group_id, USER, recovering=True)
        assert task is not None
        await _wait_for(group_id, ("paused",))
        await asyncio.gather(task, return_exceptions=True)
        for _ in range(300):
            if group_id not in runner.TASKS:
                break
            await asyncio.sleep(0.01)
        return await discuss_store.get_group(USER, group_id)

    group = asyncio.run(flow())
    assert group["status"] == "paused"
    assert group["stop_reason"] == "server_restart_failed"
    assert group["run_token"] is None


def test_recovering_unexpected_error_pauses_with_server_restart_failed(
        world, monkeypatch):
    """X18 / 规格 4.12：恢复模式下的其他异常记 paused，不是 failed/error。"""
    from discuss import engine

    group_id = _new_group_id()

    async def failing(*args, **kwargs):
        raise RuntimeError("意外的规划错误")

    monkeypatch.setattr(engine, "run_planning", failing)

    async def flow():
        await _create_group(group_id)
        task = await runner.start_group(group_id, USER, recovering=True)
        assert task is not None
        await _wait_for(group_id, ("paused",))
        await asyncio.gather(task, return_exceptions=True)
        for _ in range(300):
            if group_id not in runner.TASKS:
                break
            await asyncio.sleep(0.01)
        return await discuss_store.get_group(USER, group_id)

    group = asyncio.run(flow())
    assert group["status"] == "paused"
    assert group["stop_reason"] == "server_restart_failed"
    assert group["run_token"] is None


def test_step_failure_without_recovery_pauses_with_step_failed(world, monkeypatch):
    """X19 / 规格 4.12：非恢复模式的 StepFailed 记 paused/step_failed，不是 failed/error。"""
    from discuss import engine
    from novel.llm_router import StepFailed

    group_id = _new_group_id()

    async def failing(*args, **kwargs):
        raise StepFailed("规划步骤失败")

    monkeypatch.setattr(engine, "run_planning", failing)

    async def flow():
        await _create_group(group_id)
        task = await runner.start_group(group_id, USER)
        assert task is not None
        await _wait_for(group_id, ("paused",))
        await asyncio.gather(task, return_exceptions=True)
        for _ in range(300):
            if group_id not in runner.TASKS:
                break
            await asyncio.sleep(0.01)
        return await discuss_store.get_group(USER, group_id)

    group = asyncio.run(flow())
    assert group["status"] == "paused"
    assert group["stop_reason"] == "step_failed"
    assert group["run_token"] is None


def test_max_running_limits_concurrent_planning(world, monkeypatch):
    """X20 / 规格 4.2、4.12：FIONA_DISCUSS_MAX_RUNNING=1 时第二个群等槽位。"""
    from discuss import engine

    monkeypatch.setenv("FIONA_DISCUSS_MAX_RUNNING", "1")
    entered = []
    first_entered, second_entered = asyncio.Event(), asyncio.Event()
    release = asyncio.Event()

    async def fake_planning(store, router):
        entered.append(store.group_id)
        if len(entered) == 1:
            first_entered.set()
        elif len(entered) == 2:
            second_entered.set()
        await release.wait()
        await discuss_store.update_group(
            USER, store.group_id, status="awaiting_start", run_token=None)

    monkeypatch.setattr(engine, "run_planning", fake_planning)
    first_id, second_id = _new_group_id(), _new_group_id()

    async def flow():
        await _create_group(first_id)
        await _create_group(second_id)
        first_task = await runner.start_group(first_id, USER)
        second_task = await runner.start_group(second_id, USER)
        assert first_task is not None and second_task is not None
        await asyncio.wait_for(first_entered.wait(), timeout=5)
        try:
            await asyncio.wait_for(second_entered.wait(), timeout=0.3)
        except asyncio.TimeoutError:
            pass
        else:
            pytest.fail("全站并发上限没有生效：第一个群还在跑，第二个群已进入规划")
        assert entered == [first_id]
        assert not first_task.done() and not second_task.done()

        release.set()
        await asyncio.wait_for(
            asyncio.gather(first_task, second_task), timeout=5)
        assert entered == [first_id, second_id]
        for _ in range(300):
            if first_id not in runner.TASKS and second_id not in runner.TASKS:
                break
            await asyncio.sleep(0.01)
        assert first_id not in runner.TASKS
        assert second_id not in runner.TASKS
        return (await discuss_store.get_group(USER, first_id),
                await discuss_store.get_group(USER, second_id))

    first_group, second_group = asyncio.run(flow())
    for group in (first_group, second_group):
        assert group["status"] == "awaiting_start"
        assert group["run_token"] is None


# ── 复核门禁补单：V3 私有记忆查询取消保护 ─────────────────

def _hold_memory_cursor(monkeypatch):
    """Hold the cursor of get_memory_snapshot's private-memory query."""
    original = aiosqlite.Connection._execute
    entered, release = asyncio.Event(), asyncio.Event()
    marker = "SELECT private_memory_json, memory_revision FROM agents WHERE owner_username = ?"
    fired = [False]

    async def hooked(self, fn, *args, **kwargs):
        result = await original(self, fn, *args, **kwargs)
        if (not fired[0] and args and isinstance(args[0], str)
                and marker in args[0]):
            fired[0] = True
            entered.set()
            await release.wait()
        return result

    monkeypatch.setattr(aiosqlite.Connection, "_execute", hooked)
    return entered, release


def test_cancelled_avatar_system_for_memory_snapshot_leaves_no_write_lock(
        world, monkeypatch):
    """V3：取消 get_memory_snapshot 的未取走游标，收尾仍能立刻拿写锁。"""
    import agent_store
    from discuss import avatar

    async def flow():
        # Create the agents row before installing the cursor hook, so the
        # first get_my_agent call returns normally and only the memory query is
        # held.
        await agent_store.get_my_agent(USER)
        entered, release = _hold_memory_cursor(monkeypatch)

        async def worker():
            try:
                await avatar.system_for(USER, "brief")
            finally:
                await _assert_write_lock_free()

        task = asyncio.create_task(worker())
        await asyncio.wait_for(entered.wait(), timeout=5)
        task.cancel()
        await asyncio.sleep(0.05)
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(flow())


# ── 复核第 2 轮：M5 分身读库错误不得吞掉取消 ─────────────────

@pytest.mark.parametrize("stage", ["planning", "running"])
def test_pause_during_avatar_memory_error_keeps_cancellation(stage, world, monkeypatch):
    """M5：分身读私有记忆抛错时暂停仍生效，不继续扣费或往下跑。"""
    import sqlite3

    import agent_store
    from discuss import service as discuss_service

    group_id = _new_group_id()

    async def flow():
        await _create_group(group_id, avatar=True)
        if stage == "running":
            await runner.start_group(group_id, USER)
            await _wait_for(group_id, ("awaiting_start",))
            task0 = runner.TASKS.get(group_id)
            if task0 is not None:
                await asyncio.gather(task0, return_exceptions=True)

        entered, release = asyncio.Event(), asyncio.Event()
        original = agent_store.get_memory_snapshot
        fired = [False]

        async def failing(username, conversation_id=None):
            if not fired[0]:
                fired[0] = True
                entered.set()
                await release.wait()
                raise sqlite3.OperationalError("simulated memory read failure")
            return await original(username, conversation_id)

        monkeypatch.setattr(agent_store, "get_memory_snapshot", failing)

        if stage == "planning":
            task = await runner.start_group(group_id, USER)
        else:
            group = await discuss_store.get_group(USER, group_id)
            await discuss_service.start(
                USER, group_id,
                discuss_service.StartGroup(expected_revision=group["plan_revision"]))
            task = runner.TASKS.get(group_id)

        await asyncio.wait_for(entered.wait(), 5)
        pause_task = asyncio.create_task(discuss_service.pause(USER, group_id))
        await asyncio.sleep(0.05)
        release.set()
        result = await pause_task
        assert (result["status"], result["stop_reason"]) == ("paused", "user")
        if task is not None:
            await asyncio.gather(task, return_exceptions=True)

        messages = await discuss_store.list_messages(USER, group_id)
        kinds = [message["kind"] for message in messages]
        if stage == "planning":
            assert "notice" not in kinds
        else:
            assert "verdict" not in kinds

    asyncio.run(flow())


def test_cancelled_start_group_does_not_clear_other_token(world, monkeypatch):
    """Y1：认领被已有令牌拒绝并同时取消时，别人的令牌原样保留。"""
    group_id = _new_group_id()

    async def flow():
        await _create_group(group_id)
        await discuss_store.update_group(
            USER, group_id, status="running", run_token="other-token")
        entered, release = _gate_next_commit(monkeypatch)
        task = asyncio.create_task(runner.start_group(group_id, USER))
        await entered.wait()
        task.cancel()
        await asyncio.sleep(0.05)
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        group = await discuss_store.get_group(USER, group_id)
        assert group["run_token"] == "other-token"
        assert group_id not in runner.TASKS

    asyncio.run(flow())
