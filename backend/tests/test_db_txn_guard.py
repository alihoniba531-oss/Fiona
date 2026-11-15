# -*- coding: utf-8 -*-
"""``utils.db_txn`` 的取消安全测试。

只用临时库和自建小表 ``t (id INTEGER PRIMARY KEY, v INTEGER)``，不依赖业务代码。
覆盖规格 4.2：

* 9 种事务写法各做取消点扫描：``delivered``/``queued`` 两种落点 + 原生取消，
  以及 ``delivered`` + ``anyio.CancelScope`` 取消；每个取消点上断言任务对象仍
  被引用时写锁空闲、任务以取消结束、表数据只会是事务前或事务完成后的值。
* 同样 9 种写法用裸 ``aiosqlite.connect`` 做对照，至少一个取消点写锁不空闲。
* ``connect`` 的其余行为：普通异常回滚、正常退出、回滚自身异常、回滚等待时
  再次被取消、参数透传、交出对象同一性。
* ``drain`` 规格 3.1 表格五行 + 连续取消三次，外加已在运行的 Task / Future
  两种可等待对象。

同步 test 函数里用 ``asyncio.run`` / ``anyio.run`` 组织，不用 pytest 的
asyncio 插件标记。
"""
import asyncio
import sqlite3
import time

import aiosqlite
import anyio
import pytest

from cancel_sweep import sweep_cancel_points, write_lock_is_free
from utils import db_txn


INITIAL_ROWS = [(1, 10), (2, 20)]


# ---------------------------------------------------------------------------
# 建表 / 重置 / 读表
# ---------------------------------------------------------------------------


def _create_db(path):
    """建自建小表并准备两行初始数据（放在测试自己的临时目录里）。"""
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v INTEGER)")
        db.executemany("INSERT INTO t (id, v) VALUES (?, ?)", INITIAL_ROWS)


async def _prepare_db(path):
    """把表恢复成初始数据；每个取消点之前都跑一次。

    裸连接对照组的僵尸连接可能还占着写锁一小会儿（要等 gc 让它关闭），所以
    这里对 ``database is locked`` 做有限重试。准备函数的数据库调用发生在
    ``cancel_sweep`` 安装注入器之后、``injector.reset`` 之前，不计入取消点。
    """
    deadline = time.monotonic() + 5.0
    while True:
        try:
            async with aiosqlite.connect(path, timeout=0.2) as db:
                await db.execute("DELETE FROM t")
                await db.executemany(
                    "INSERT INTO t (id, v) VALUES (?, ?)", INITIAL_ROWS
                )
                await db.commit()
            return
        except sqlite3.OperationalError:
            if time.monotonic() >= deadline:
                raise
            await asyncio.sleep(0.05)


async def _read_rows(path):
    """用一条新连接读当前表值；读不会被写事务挡住。"""
    async with aiosqlite.connect(path, timeout=0.2) as db:
        rows = await db.execute_fetchall("SELECT id, v FROM t ORDER BY id")
    return [tuple(row) for row in rows]


async def _check_point(path, _point):
    """取消点检查：写锁是否空闲 + 当前表值，两者都交给测试逐点断言。"""
    return (await write_lock_is_free(path), await _read_rows(path))


async def _sweep(open_connection, path, body, mode, cancel):
    """对一种事务写法做一遍取消点扫描。"""

    async def make_coroutine():
        async with open_connection(path, timeout=0.2) as db:
            await body(db)

    return await sweep_cancel_points(
        make_coroutine,
        check=lambda point: _check_point(path, point),
        prepare=lambda: _prepare_db(path),
        mode=mode,
        cancel=cancel,
    )


# ---------------------------------------------------------------------------
# 等事件 / 等任务 / 等 gather 的上限
# ---------------------------------------------------------------------------
#
# 实现被改坏时（例如回滚被删掉），裸的 Event.wait()/await task/gather 会永远
# 等下去，把整个测试进程挂死；这里统一加几秒上限，超时转换成 pytest.fail。

_WAIT_TIMEOUT_SECONDS = 5.0
_CANCEL_GRACE_SECONDS = 1.0


def _discard_task_exception(task):
    """取走已结束任务的异常，避免 asyncio 报「exception was never retrieved」。"""
    if task.done() and not task.cancelled():
        task.exception()


async def _wait_event_or_fail(event, description, *, task=None):
    """等事件，超过上限就 pytest.fail，不无限等。

    超时若给了 ``task``，先取消并短暂等它退出，再取走异常，避免留下
    「Task exception was never retrieved」的噪声。
    """
    try:
        await asyncio.wait_for(event.wait(), timeout=_WAIT_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        if task is not None:
            task.cancel()
            await asyncio.wait({task}, timeout=_CANCEL_GRACE_SECONDS)
            _discard_task_exception(task)
        pytest.fail(
            f"{description}：等待超过 {_WAIT_TIMEOUT_SECONDS:g} 秒仍未发生"
        )


async def _wait_task_or_fail(task, description):
    """等任务结束，超过上限就取消并 pytest.fail。

    不用 ``asyncio.wait_for(task)``：任务若一直吞掉取消，wait_for 会陪着它
    挂住；分两步 ``asyncio.wait`` 保证一定在有限时间内返回。任务必须正常
    结束且没有异常；被取消或带着异常结束时用 pytest.fail 报出实际结局，
    不让 ``task.result()`` 把那个异常直接漏出用例。
    """
    _done, pending = await asyncio.wait(
        {task}, timeout=_WAIT_TIMEOUT_SECONDS
    )
    if pending:
        task.cancel()
        await asyncio.wait({task}, timeout=_CANCEL_GRACE_SECONDS)
        if task.done():
            _discard_task_exception(task)
        pytest.fail(
            f"{description}：任务超过 {_WAIT_TIMEOUT_SECONDS:g} 秒仍未结束"
        )
    if task.cancelled():
        pytest.fail(f"{description}：任务被取消，预期正常结束")
    error = task.exception()
    if error is not None:
        pytest.fail(
            f"{description}：任务以 {type(error).__name__}: {error} 结束，"
            f"预期正常结束"
        )


async def _gather_or_fail(*tasks, description):
    """等价于 ``gather(*tasks, return_exceptions=True)``，但整体有上限。"""
    _done, pending = await asyncio.wait(
        set(tasks), timeout=_WAIT_TIMEOUT_SECONDS
    )
    if pending:
        for task in pending:
            task.cancel()
        await asyncio.wait(pending, timeout=_CANCEL_GRACE_SECONDS)
        pytest.fail(
            f"{description}：等待超过 {_WAIT_TIMEOUT_SECONDS:g} 秒仍未结束"
        )
    outcomes = []
    for task in tasks:
        if task.cancelled():
            outcomes.append(asyncio.CancelledError())
        else:
            outcomes.append(task.exception())
    return outcomes


async def _bounded_or_fail(awaitable, description):
    """给一次普通 await 加同样的上限。

    超时、被意外取消或抛出非断言异常都转成 pytest.fail，并带上上下文。
    """
    try:
        return await asyncio.wait_for(
            awaitable, timeout=_WAIT_TIMEOUT_SECONDS
        )
    except asyncio.TimeoutError:
        pytest.fail(
            f"{description}：超过 {_WAIT_TIMEOUT_SECONDS:g} 秒仍未完成"
        )
    except asyncio.CancelledError:
        pytest.fail(f"{description}：等待被意外取消", pytrace=False)
    except Exception as error:
        pytest.fail(
            f"{description}：意外抛出 {type(error).__name__}: {error}",
            pytrace=False,
        )


def _run_or_fail(awaitable, description):
    """同步测试里跑一个协程，把实现漏出的非断言异常转成 pytest.fail。"""
    try:
        return asyncio.run(awaitable)
    except AssertionError:
        raise
    except asyncio.CancelledError:
        pytest.fail(f"{description}：任务被意外取消", pytrace=False)
    except Exception as error:
        pytest.fail(
            f"{description}：意外抛出 {type(error).__name__}: {error}",
            pytrace=False,
        )


def _anyio_run_or_fail(async_fn, description, *args):
    """同步测试里跑 anyio；实现漏出的非断言异常转成 pytest.fail。"""
    try:
        return anyio.run(async_fn, *args)
    except AssertionError:
        raise
    except asyncio.CancelledError:
        pytest.fail(f"{description}：任务被意外取消", pytrace=False)
    except Exception as error:
        pytest.fail(
            f"{description}：意外抛出 {type(error).__name__}: {error}",
            pytrace=False,
        )


def _read_rows_or_fail(path, description):
    """同步读表；连接或读取失败也转成带上下文的断言失败。"""
    return _run_or_fail(_read_rows(path), description)


# ---------------------------------------------------------------------------
# 规格 4.2 的 9 种事务写法
# ---------------------------------------------------------------------------


async def _form_1(db):
    await db.execute("BEGIN IMMEDIATE")
    cursor = await db.execute("SELECT v FROM t WHERE id = 1")
    await cursor.fetchone()
    await db.execute("UPDATE t SET v = v + 1 WHERE id = 1")
    await db.commit()


async def _form_2(db):
    await db.execute("BEGIN IMMEDIATE")
    async with db.execute("SELECT v FROM t WHERE id = 1") as cursor:
        await cursor.fetchone()
    await db.execute("UPDATE t SET v = v + 1 WHERE id = 1")
    await db.commit()


async def _form_3(db):
    await db.execute("BEGIN IMMEDIATE")
    # 只取一行，不关游标；剩余未取完的语句是残留写锁的条件之一。
    cursor = await db.execute("SELECT id, v FROM t ORDER BY id")
    await cursor.fetchone()
    await db.execute("UPDATE t SET v = v + 1 WHERE id = 1")
    await db.commit()


async def _form_4(db):
    await db.execute("BEGIN IMMEDIATE")
    await db.execute("UPDATE t SET v = v + 1 WHERE id = 1")
    await db.execute("UPDATE t SET v = v + 10 WHERE id = 2")
    await db.commit()


async def _form_5(db):
    await db.execute("UPDATE t SET v = v + 5 WHERE id = 2")
    await db.execute("SELECT v FROM t WHERE id = 2")
    await db.commit()


async def _form_6(db):
    cursor = await db.execute("SELECT v FROM t WHERE id = 1")
    await cursor.fetchone()


async def _form_7(db):
    await db.execute("BEGIN IMMEDIATE")
    cursor = await db.execute(
        "UPDATE t SET v = v + 2 WHERE id = 1 RETURNING v"
    )
    await cursor.fetchone()
    await db.commit()


async def _form_8(db):
    await db.execute("BEGIN IMMEDIATE")
    await db.execute_fetchall("SELECT id, v FROM t ORDER BY id")
    await db.execute("UPDATE t SET v = v + 100 WHERE id = 1")
    await db.commit()


async def _form_9(db):
    cursor = await db.execute("SELECT v FROM t WHERE id = 1")
    await cursor.fetchone()
    await db.execute("UPDATE t SET v = v + 1 WHERE id = 1")
    await db.commit()


# (名称, 事务体, 完整执行后的表值)
FORMS = [
    ("f1_begin_select_fetchone_update", _form_1, [(1, 11), (2, 20)]),
    ("f2_begin_async_with_select_update", _form_2, [(1, 11), (2, 20)]),
    ("f3_begin_multi_select_open_cursor", _form_3, [(1, 11), (2, 20)]),
    ("f4_begin_two_updates", _form_4, [(1, 11), (2, 30)]),
    ("f5_update_select_commit", _form_5, [(1, 10), (2, 25)]),
    ("f6_select_only", _form_6, [(1, 10), (2, 20)]),
    ("f7_begin_update_returning", _form_7, [(1, 12), (2, 20)]),
    ("f8_begin_execute_fetchall", _form_8, [(1, 110), (2, 20)]),
    ("f9_select_fetchone_update", _form_9, [(1, 11), (2, 20)]),
]

FORM_IDS = [form[0] for form in FORMS]


def _assert_points(records, form_name, mode, cancel, final_rows):
    """逐点断言：取消真的发生、写锁空闲、数据是事务前或事务后的值。"""
    assert records, f"{form_name} {mode}/{cancel} 没有扫到任何取消点"
    for point in records:
        where = (
            f"{form_name} mode={mode} cancel={cancel} "
            f"k={point.k} label={point.label!r}"
        )
        assert point.cancelled, f"任务没有以取消结束: {where}"
        assert point.check_completed, f"检查函数没有跑完: {where}"
        lock_free, rows = point.check_result
        assert lock_free is True, f"任务对象仍被引用时写锁不空闲: {where}"
        assert rows in (INITIAL_ROWS, final_rows), (
            f"取消点的数据既不是事务前也不是事务完整执行后的值: "
            f"{where} rows={rows!r}"
        )


@pytest.mark.parametrize("form_name,body,final_rows", FORMS, ids=FORM_IDS)
def test_db_txn_connect_cancel_points_leave_no_lock(
    tmp_path, form_name, body, final_rows
):
    """9 种写法在 delivered/queued 两种落点、原生取消下都不残留写锁。"""
    db_path = tmp_path / f"{form_name}-native.db"
    _create_db(db_path)

    for mode in ("delivered", "queued"):
        records = _run_or_fail(
            _sweep(db_txn.connect, db_path, body, mode, "task"),
            f"{form_name} {mode}/task 取消点扫描",
        )
        _assert_points(records, form_name, mode, "task", final_rows)


@pytest.mark.parametrize("form_name,body,final_rows", FORMS, ids=FORM_IDS)
def test_db_txn_connect_anyio_cancel_points_leave_no_lock(
    tmp_path, form_name, body, final_rows
):
    """9 种写法在 delivered 落点、anyio.CancelScope 取消下都不残留写锁。"""
    db_path = tmp_path / f"{form_name}-anyio.db"
    _create_db(db_path)

    records = _anyio_run_or_fail(
        _sweep,
        f"{form_name} delivered/anyio 取消点扫描",
        db_txn.connect,
        db_path,
        body,
        "delivered",
        "anyio",
    )
    _assert_points(records, form_name, "delivered", "anyio", final_rows)


def test_bare_aiosqlite_control_group_can_hold_write_lock(tmp_path):
    """对照组：裸 aiosqlite.connect 至少一个取消点写锁不空闲。

    证明扫描器确实能测出「取消后残留写锁」，上面两组断言不是空转。
    """
    db_path = tmp_path / "bare-control.db"
    _create_db(db_path)

    locked = []
    for form_name, body, _final_rows in FORMS:
        records = _run_or_fail(
            _sweep(aiosqlite.connect, db_path, body, "delivered", "task"),
            f"裸连接对照组 {form_name} 取消点扫描",
        )
        assert records, f"对照组 {form_name} 没有扫到任何取消点"
        for point in records:
            assert point.cancelled, (
                f"对照组 {form_name} k={point.k} 任务没有以取消结束"
            )
            assert point.check_completed
            lock_free, _rows = point.check_result
            if not lock_free:
                locked.append((form_name, point.k, point.label))

    assert locked, (
        "裸 aiosqlite.connect 对照组没有任何取消点写锁不空闲，"
        "取消点扫描器可能没有在测真正的问题"
    )


def test_sweep_reports_swallowed_cancellation(tmp_path):
    """协程吞掉取消时，扫描要记 ``cancelled=False`` 并继续扫后面的取消点。

    被测协程一共 5 次 aiosqlite 调用（含关闭）：第 2 次上的取消被吞掉，
    扫描应返回 5 条记录，只有第 2 条 ``cancelled`` 为假。
    """
    db_path = tmp_path / "swallowed-cancel.db"
    _create_db(db_path)

    async def swallowing_victim():
        async with aiosqlite.connect(db_path, timeout=0.2) as db:
            await db.execute("BEGIN IMMEDIATE")  # 第 1 次调用
            try:
                # 第 2 次调用：取消在这里被吞掉。
                await db.execute("UPDATE t SET v = v + 1 WHERE id = 1")
            except asyncio.CancelledError:
                pass
            await db.execute("UPDATE t SET v = v + 1 WHERE id = 1")  # 第 3 次
            await db.commit()  # 第 4 次
        # 退出 async with 时关闭连接是第 5 次调用。

    async def check(_point):
        return await write_lock_is_free(db_path)

    async def scenario():
        return await sweep_cancel_points(
            swallowing_victim,
            check=check,
            mode="delivered",
            cancel="task",
        )

    records = _run_or_fail(scenario(), "吞掉取消的扫描")

    summary = [(point.k, point.label, point.cancelled) for point in records]
    assert len(records) == 5, (
        f"应扫到 5 条记录（含关闭连接），实际 {len(records)} 条: {summary}"
    )
    assert [point.cancelled for point in records] == [
        True,
        False,
        True,
        True,
        True,
    ], f"只有第 2 个取消点应记 cancelled=False，实际: {summary}"
    assert all(point.check_completed for point in records), (
        f"有取消点的检查函数没有跑完: {summary}"
    )


def test_bare_aiosqlite_anyio_control_group_can_hold_write_lock(tmp_path):
    """anyio 对照组：裸 ``aiosqlite.connect`` 的第 3 种写法至少一处锁不空闲。

    证明 anyio 这一组检查确实在取消传播途中运行，不是空转。
    """
    db_path = tmp_path / "bare-anyio-control.db"
    _create_db(db_path)

    records = _anyio_run_or_fail(
        _sweep,
        "裸连接 anyio 对照组取消点扫描",
        aiosqlite.connect,
        db_path,
        _form_3,
        "delivered",
        "anyio",
    )

    assert records, "anyio 对照组没有扫到任何取消点"
    locked = []
    for point in records:
        assert point.check_completed, (
            f"anyio 对照组 k={point.k} 的检查函数没有跑完"
        )
        lock_free, _rows = point.check_result
        if not lock_free:
            locked.append((point.k, point.label))

    assert locked, (
        "裸 aiosqlite.connect 的 anyio 对照组没有任何取消点写锁不空闲，"
        "anyio 这组断言可能在空转"
    )


# ---------------------------------------------------------------------------
# connect 的其余行为
# ---------------------------------------------------------------------------


def test_connect_rolls_back_and_closes_on_plain_exception(tmp_path):
    """作用域内抛普通异常：写入回滚、连接关闭、向外是原异常。"""
    db_path = tmp_path / "plain-exception.db"
    _create_db(db_path)
    original = RuntimeError("original failure")
    connections = []

    async def scenario():
        async with db_txn.connect(db_path, timeout=0.2) as db:
            connections.append(db)
            await db.execute("BEGIN IMMEDIATE")
            await db.execute("UPDATE t SET v = 777 WHERE id = 1")
            raise original

    caught = None
    try:
        asyncio.run(scenario())
    except BaseException as error:
        caught = error

    assert caught is original, (
        f"向外抛的应是原异常对象，实际是 {type(caught).__name__}: {caught!r}"
    )
    assert len(connections) == 1
    assert connections[0]._connection is None
    assert _read_rows_or_fail(
        db_path, "普通异常回滚后读取表数据"
    ) == INITIAL_ROWS


def test_plain_exception_rollback_releases_lock_before_close(tmp_path):
    """普通异常离开时也要先回滚：持有异常对象期间写锁已空闲。

    写法与规格 4.2 要求的第 3 种事务一致：``BEGIN IMMEDIATE``、多行 SELECT
    只取一行且不关游标、UPDATE，然后抛普通异常。裸 ``aiosqlite.connect``
    对照组在同样条件下（异常对象仍被引用）写锁不空闲，证明本用例能区分
    「回滚」与「只是关闭」。
    """
    wrapped_path = tmp_path / "plain-exception-lock-wrapped.db"
    bare_path = tmp_path / "plain-exception-lock-bare.db"
    _create_db(wrapped_path)
    _create_db(bare_path)
    original = RuntimeError("original failure")
    wrapped_connections = []
    bare_connections = []

    async def scenario(open_connection, path, connections):
        async with open_connection(path, timeout=0.2) as db:
            connections.append(db)
            await db.execute("BEGIN IMMEDIATE")
            cursor = await db.execute("SELECT id, v FROM t ORDER BY id")
            await cursor.fetchone()  # 只取一行，不关游标
            await db.execute("UPDATE t SET v = 777 WHERE id = 1")
            raise original

    caught = None
    try:
        asyncio.run(
            scenario(db_txn.connect, wrapped_path, wrapped_connections)
        )
    except BaseException as error:
        caught = error

    assert caught is original, (
        f"db_txn.connect 向外抛的应是原异常对象，实际是 "
        f"{type(caught).__name__}: {caught!r}"
    )
    assert len(wrapped_connections) == 1
    assert (
        _run_or_fail(
            write_lock_is_free(str(wrapped_path)),
            "db_txn.connect 普通异常回滚后检查写锁",
        )
        is True
    ), "db_txn.connect 在普通异常后、异常对象仍被引用时写锁不空闲"
    assert _read_rows_or_fail(
        wrapped_path, "db_txn.connect 普通异常回滚后读取表数据"
    ) == INITIAL_ROWS
    assert wrapped_connections[0]._connection is None

    # 对照：裸连接只关闭、不回滚；异常对象还活着时写锁仍被占。
    bare_caught = None
    try:
        asyncio.run(scenario(aiosqlite.connect, bare_path, bare_connections))
    except BaseException as error:
        bare_caught = error

    assert bare_caught is original, (
        f"裸 aiosqlite.connect 对照组向外抛的应是原异常对象，实际是 "
        f"{type(bare_caught).__name__}: {bare_caught!r}"
    )
    assert len(bare_connections) == 1
    assert (
        _run_or_fail(
            write_lock_is_free(str(bare_path)),
            "裸 aiosqlite.connect 对照组检查写锁",
        )
        is False
    ), (
        "对照组（裸 aiosqlite.connect）在异常对象仍被引用时写锁却空闲，"
        "本用例无法区分「回滚」与「只是关闭」"
    )


def test_connect_without_exception_matches_bare_connection(tmp_path):
    """作用域内无异常：与裸 aiosqlite.connect 相同，已提交留下、未提交丢弃。"""
    wrapped_path = tmp_path / "wrapped.db"
    bare_path = tmp_path / "bare.db"
    _create_db(wrapped_path)
    _create_db(bare_path)

    async def scenario(open_connection, path):
        async with open_connection(path, timeout=0.2) as db:
            await db.execute("UPDATE t SET v = 999 WHERE id = 1")
            await db.commit()
            # 第二个写入不提交；正常退出时应被丢弃。
            await db.execute("UPDATE t SET v = 777 WHERE id = 2")

    async def run_both():
        await scenario(db_txn.connect, wrapped_path)
        await scenario(aiosqlite.connect, bare_path)

    _run_or_fail(run_both(), "无异常退出 connect 应与裸连接行为一致")

    wrapped_rows = _read_rows_or_fail(wrapped_path, "读取封装连接提交后的表数据")
    bare_rows = _read_rows_or_fail(bare_path, "读取裸连接提交后的表数据")
    assert wrapped_rows == [(1, 999), (2, 20)]
    assert bare_rows == [(1, 999), (2, 20)]
    assert wrapped_rows == bare_rows


def test_connect_swallows_rollback_error_and_keeps_original_exception(tmp_path):
    """回滚自己抛 sqlite3.OperationalError：吞掉，仍关闭，向外仍是原异常。"""
    db_path = tmp_path / "rollback-error.db"
    _create_db(db_path)
    original = RuntimeError("original failure")
    connections = []
    rollback_called = []

    async def scenario():
        async with db_txn.connect(db_path, timeout=0.2) as db:
            connections.append(db)

            async def failing_rollback():
                rollback_called.append(True)
                raise sqlite3.OperationalError("rollback failed")

            db.rollback = failing_rollback
            await db.execute("BEGIN IMMEDIATE")
            await db.execute("UPDATE t SET v = 555 WHERE id = 1")
            raise original

    caught = None
    try:
        asyncio.run(scenario())
    except BaseException as error:
        caught = error

    assert caught is original, (
        f"向外抛的应是原异常对象，实际是 {type(caught).__name__}: {caught!r}"
    )
    assert rollback_called == [True]
    assert len(connections) == 1
    assert connections[0]._connection is None
    assert _read_rows_or_fail(
        db_path, "回滚自身异常后读取表数据"
    ) == INITIAL_ROWS


def test_connect_closes_when_rollback_is_cancelled_again(tmp_path):
    """回滚等待时再次被取消：连接最终关闭、工作线程退出、写锁空闲。"""
    db_path = tmp_path / "recancel-rollback.db"
    _create_db(db_path)
    connections = []
    rollback_started = anyio.Event()
    rollback_finished = []

    async def scenario():
        scope = anyio.CancelScope()

        async def victim():
            with scope:
                async with db_txn.connect(db_path, timeout=0.2) as db:
                    connections.append(db)

                    async def slow_rollback():
                        rollback_started.set()
                        await anyio.sleep(30)
                        rollback_finished.append(True)

                    db.rollback = slow_rollback
                    await db.execute("BEGIN IMMEDIATE")
                    await db.execute("UPDATE t SET v = 888 WHERE id = 1")
                    raise RuntimeError("original failure")

        task = asyncio.create_task(victim())
        await _wait_event_or_fail(
            rollback_started,
            "db_txn.connect 没有调用 rollback（等待 rollback_started）",
            task=task,
        )
        # 让回滚真正停在 anyio.sleep 上，再把取消送进去。
        await asyncio.sleep(0.05)
        scope.cancel()
        await _wait_task_or_fail(
            task, "db_txn.connect 的取消收尾（回滚后关闭连接）"
        )

        assert len(connections) == 1
        db = connections[0]
        deadline = time.monotonic() + 3.0
        while db._thread.is_alive() and time.monotonic() < deadline:
            await asyncio.sleep(0.01)

        assert db._connection is None
        assert not db._thread.is_alive()
        assert rollback_finished == []
        lock_free = await _bounded_or_fail(
            write_lock_is_free(db_path), "取消收尾后检查写锁"
        )
        assert lock_free is True
        rows = await _bounded_or_fail(
            _read_rows(db_path), "取消收尾后读取表数据"
        )
        assert rows == INITIAL_ROWS

    _anyio_run_or_fail(
        scenario, "回滚等待时再次取消的 connect 收尾"
    )


class _FakeConnection:
    """参数透传用例的伪连接，只实现 async with。"""

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


def test_connect_passes_arguments_through_unchanged(tmp_path, monkeypatch):
    """参数透传：位置参数和关键字参数原样交给 aiosqlite.connect。"""
    path = tmp_path / "passthrough.db"
    fake = _FakeConnection()
    recorded = {}

    def fake_connect(*args, **kwargs):
        recorded["args"] = args
        recorded["kwargs"] = kwargs
        return fake

    monkeypatch.setattr(aiosqlite, "connect", fake_connect)

    async def scenario():
        async with db_txn.connect(path, uri=True, timeout=1.0) as db:
            assert db is fake

    _run_or_fail(scenario(), "参数透传用例的 connect 调用")

    assert recorded["args"] == (path,)
    assert recorded["kwargs"] == {"uri": True, "timeout": 1.0}


def test_connect_yields_the_connection_object_from_aiosqlite(tmp_path, monkeypatch):
    """async with 交出的就是 aiosqlite.connect(...) 返回的那个连接对象。"""
    db_path = tmp_path / "same-object.db"
    _create_db(db_path)
    captured = []
    original_connect = aiosqlite.connect

    def tracking_connect(*args, **kwargs):
        connection = original_connect(*args, **kwargs)
        captured.append(connection)
        return connection

    monkeypatch.setattr(aiosqlite, "connect", tracking_connect)

    async def scenario():
        async with db_txn.connect(db_path, timeout=0.2) as db:
            assert len(captured) == 1
            assert db is captured[0]
            rows = await db.execute_fetchall("SELECT id, v FROM t ORDER BY id")
            assert [tuple(row) for row in rows] == INITIAL_ROWS

    _run_or_fail(scenario(), "交出的连接对象应与 aiosqlite.connect 返回的一致")

    assert len(captured) == 1
    assert captured[0]._connection is None


# ---------------------------------------------------------------------------
# drain
# ---------------------------------------------------------------------------


def test_drain_returns_inner_result_when_not_cancelled():
    """drain 表格第一行：调用方没被取消，内层正常返回，返回同一个值。"""
    value = object()

    async def operation():
        await asyncio.sleep(0.01)
        return value

    async def scenario():
        return await db_txn.drain(operation())

    assert _run_or_fail(scenario(), "drain 未取消时返回内层结果") is value


def test_drain_propagates_inner_exception_when_not_cancelled():
    """drain 表格第二行：调用方没被取消，内层异常原样抛出同一个异常。"""
    inner_error = ValueError("inner failure")

    async def operation():
        await asyncio.sleep(0.01)
        raise inner_error

    async def scenario():
        try:
            await db_txn.drain(operation())
        except BaseException as caught:
            return caught
        raise AssertionError("drain 没有抛出内层异常")

    assert asyncio.run(scenario()) is inner_error


def test_drain_raises_cancelled_error_when_inner_task_cancels_itself():
    """drain 表格第三行：内层任务自己取消，drain 抛 CancelledError。"""
    observed = []

    async def operation():
        asyncio.current_task().cancel()
        await asyncio.sleep(1)

    async def scenario():
        try:
            await db_txn.drain(operation())
        except asyncio.CancelledError:
            observed.append("cancelled")
            return
        observed.append("returned")

    _run_or_fail(scenario(), "drain 内层任务自己取消")
    assert observed == ["cancelled"]


def test_drain_waits_for_inner_then_raises_when_caller_cancelled():
    """drain 表格第四行：调用方取消、内层正常返回，等内层结束后抛取消。"""
    operation_started = asyncio.Event()
    inner_finished = []
    finished_at_raise = []

    async def operation():
        operation_started.set()
        await asyncio.sleep(0.1)
        inner_finished.append(True)
        return "inner result"

    async def caller():
        try:
            await db_txn.drain(operation())
        except asyncio.CancelledError:
            # 这个记录点就在 drain 抛出取消的同一时刻：此刻内层必须已结束。
            finished_at_raise.append(inner_finished == [True])
            raise

    async def scenario():
        task = asyncio.create_task(caller())
        await _wait_event_or_fail(
            operation_started, "drain 的内层操作没有开始", task=task
        )
        task.cancel()
        outcome = await _gather_or_fail(
            task, description="等待 drain 的调用方任务结束"
        )
        return task, outcome

    task, outcome = _run_or_fail(scenario(), "drain 等待内层时取消调用方")

    assert isinstance(outcome[0], asyncio.CancelledError)
    assert task.cancelled()
    assert finished_at_raise == [True]


def test_drain_waits_for_inner_error_then_raises_cancelled_with_cause():
    """drain 表格第五行：等内层抛异常结束之后抛取消，__cause__ 是内层异常。"""
    inner_started = asyncio.Event()
    inner_finished = []
    finished_at_raise = []
    causes = []
    inner_error = ValueError("inner failure")

    async def operation():
        inner_started.set()
        await asyncio.sleep(0.1)
        inner_finished.append(True)
        raise inner_error

    async def caller():
        try:
            await db_txn.drain(operation())
        except asyncio.CancelledError as caught:
            # drain 抛出时内层已经结束：这里在 except 里读取完成标记和 cause。
            finished_at_raise.append(inner_finished == [True])
            causes.append(caught.__cause__)
            raise

    async def scenario():
        task = asyncio.create_task(caller())
        await _wait_event_or_fail(
            inner_started, "drain 的内层操作没有开始", task=task
        )
        task.cancel()
        outcome = await _gather_or_fail(
            task, description="等待 drain 的调用方任务结束"
        )
        return task, outcome

    task, outcome = _run_or_fail(
        scenario(), "drain 等待内层异常时取消调用方"
    )

    assert isinstance(outcome[0], asyncio.CancelledError)
    assert task.cancelled()
    assert inner_finished == [True]
    assert finished_at_raise == [True]
    assert causes == [inner_error]


def test_drain_three_consecutive_cancels_run_inner_once():
    """等待期间连续取消三次：内层只执行一遍，最终抛 CancelledError。"""
    count = 0
    operation_done = asyncio.Event()
    started = asyncio.Event()

    async def operation():
        nonlocal count
        count += 1
        started.set()
        await asyncio.sleep(0.3)
        operation_done.set()
        return "once"

    async def caller():
        return await db_txn.drain(operation())

    async def scenario():
        task = asyncio.create_task(caller())
        await _wait_event_or_fail(
            started, "drain 的内层操作没有开始", task=task
        )
        for _ in range(3):
            task.cancel()
            await asyncio.sleep(0.05)
        outcome = await _gather_or_fail(
            task, description="等待 drain 的调用方任务结束"
        )
        return task, outcome

    task, outcome = _run_or_fail(scenario(), "drain 等待期间连续取消三次")

    assert count == 1
    assert operation_done.is_set()
    assert isinstance(outcome[0], asyncio.CancelledError)
    assert task.cancelled()


# ---------------------------------------------------------------------------
# drain 的可等待对象：已在运行的 Task 与 Future
# ---------------------------------------------------------------------------


def test_drain_accepts_already_running_task():
    """drain 接受已经在跑的 Task：调用方不取消时返回它的结果。"""
    value = object()
    started = asyncio.Event()
    release = asyncio.Event()

    async def operation():
        started.set()
        await asyncio.wait_for(
            release.wait(), timeout=_WAIT_TIMEOUT_SECONDS
        )
        return value

    async def scenario():
        inner = asyncio.create_task(operation())
        await _wait_event_or_fail(started, "内层 Task 没有开始", task=inner)
        assert not inner.done(), "内层 Task 在传给 drain 之前不应已经结束"
        release.set()
        result = await _bounded_or_fail(
            db_txn.drain(inner), "等待 drain 返回已在运行的 Task 结果"
        )
        return inner, result

    inner, result = _run_or_fail(scenario(), "drain 传入已在运行的 Task")

    assert result is value
    assert inner.done()
    assert inner.result() is value


def test_drain_accepts_future_and_returns_its_result():
    """drain 接受 Future：调用方不取消时返回 Future 的结果。"""
    value = object()

    async def scenario():
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        loop.call_soon(future.set_result, value)
        result = await _bounded_or_fail(
            db_txn.drain(future), "等待 drain 返回 Future 结果"
        )
        return future, result

    future, result = _run_or_fail(scenario(), "drain 传入 Future")

    assert result is value
    assert future.done()
    assert future.result() is value


def test_drain_waits_for_running_task_then_raises_when_caller_cancelled():
    """在跑的 Task 等待期间取消调用方：内层正常完成后 drain 再抛取消。"""
    caller_entered = asyncio.Event()
    inner_started = asyncio.Event()
    release_inner = asyncio.Event()
    inner_finished = []
    outcomes = []

    async def operation():
        inner_started.set()
        await asyncio.wait_for(
            release_inner.wait(), timeout=_WAIT_TIMEOUT_SECONDS
        )
        inner_finished.append(True)
        return "inner result"

    async def caller(inner):
        caller_entered.set()
        try:
            await db_txn.drain(inner)
        except asyncio.CancelledError:
            outcomes.append(("cancelled", inner_finished == [True]))
            raise
        else:
            outcomes.append(("returned", inner_finished == [True]))

    async def scenario():
        inner = asyncio.create_task(operation())
        await _wait_event_or_fail(
            inner_started, "内层 Task 没有开始", task=inner
        )
        task = asyncio.create_task(caller(inner))
        await _wait_event_or_fail(
            caller_entered, "drain 调用方没有开始", task=task
        )
        task.cancel()
        # 让取消先送到 drain 的 shield 上；内层仍停在 release_inner 上。
        await asyncio.sleep(0)
        assert inner_finished == [], "取消送达前内层不应已经结束"
        release_inner.set()
        outcome = await _gather_or_fail(
            task, description="等待 drain 调用方结束"
        )
        # 断言内层正常结束；实现若没等内层，这里会等到它结束再核对结局。
        await _wait_task_or_fail(inner, "drain 内层 Task 的结局")
        return inner, task, outcome

    inner, task, outcome = _run_or_fail(
        scenario(), "drain 等待已在运行的 Task 时取消调用方"
    )

    assert outcomes == [("cancelled", True)], (
        f"drain 应在内层结束后抛 CancelledError，实际结局: {outcomes!r}"
    )
    assert task.cancelled()
    assert isinstance(outcome[0], asyncio.CancelledError)
    assert inner.done()
    assert inner.result() == "inner result"


def test_drain_waits_for_future_then_raises_when_caller_cancelled():
    """Future 等待期间取消调用方：Future 完成、结果保留后 drain 再抛取消。"""
    value = object()
    caller_entered = asyncio.Event()
    outcomes = []

    async def caller(future):
        caller_entered.set()
        try:
            await db_txn.drain(future)
        except asyncio.CancelledError:
            outcomes.append(("cancelled", future.done()))
            raise
        else:
            outcomes.append(("returned", future.done()))

    async def scenario():
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        task = asyncio.create_task(caller(future))
        await _wait_event_or_fail(
            caller_entered, "drain 调用方没有开始", task=task
        )
        task.cancel()
        # 让取消先送到 drain 对 Future 的 shield 上，再让 Future 完成。
        await asyncio.sleep(0)
        assert not future.done(), "Future 应在调用方取消之后才完成"
        future.set_result(value)
        outcome = await _gather_or_fail(
            task, description="等待 drain 调用方结束"
        )
        return future, task, outcome

    future, task, outcome = _run_or_fail(
        scenario(), "drain 等待 Future 时取消调用方"
    )

    assert outcomes == [("cancelled", True)], (
        f"drain 应在 Future 完成后抛 CancelledError，实际结局: {outcomes!r}"
    )
    assert task.cancelled()
    assert isinstance(outcome[0], asyncio.CancelledError)
    assert future.done()
    assert future.result() is value
