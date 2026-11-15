# -*- coding: utf-8 -*-
"""取消点扫描辅助模块（测试用，不依赖 pytest fixture，可直接 import）。

用途
====
给定一个「造出被测协程」的工厂函数 ``make_coroutine``，把取消依次落在该协程
第 k 次 aiosqlite 调用上（k = 1、2、3……），等任务结束后在**任务对象仍被引用**
的状态下调用检查函数。扫描只在第 k 次调用根本没有发生，或 anyio 取消落在最后
一次调用上且没有被取消域捕获时结束；注入的取消被吞掉时会记一条
``cancelled=False`` 并继续扫 k+1。

两种取消落点（``mode``）：

``"delivered"``
    该次 aiosqlite 调用的结果已经写进 Future、任务还没被唤醒时调用取消。
    实现方式是临时替换 ``aiosqlite.core.set_result``：原函数把结果写进 Future
    之后，立刻取消（原生取消用 ``task.cancel()``，anyio 用 ``CancelScope.cancel()``）。
    这是真实故障的窗口。

``"queued"``
    该次 aiosqlite 调用刚入队、还没有结果时取消（包装
    ``aiosqlite.core.Connection._execute``，在调用原方法之前取消）。

两种取消方式（``cancel``）：

``"task"``
    ``asyncio.Task.cancel()``（原生取消）。记录里的 ``cancelled`` 表示任务以
    ``CancelledError`` 结束；第 k 次调用确实发生但取消被吞掉时记 ``False``。

``"anyio"``
    被测协程放在 ``anyio.CancelScope`` 里运行，注入器调用 ``scope.cancel()``。
    anyio 的取消会在任务每次等待时重新送达，所以检查函数在宿主任务的
    ``finally`` 里、``CancelScope`` 退出之前运行（用
    ``anyio.CancelScope(shield=True)`` 包住）。记录里的 ``cancelled`` 表示
    ``CancelScope`` 捕获到了取消（``scope.cancelled_caught``）。任务本身不会以
    ``CancelledError`` 结束（异常被取消域吞掉），这是 anyio 的正常行为。

对外 API
========
``async def sweep_cancel_points(make_coroutine, *, check, prepare=None,
                                mode="delivered", cancel="task",
                                max_points=200) -> list[CancelPoint]``

参数
----
make_coroutine : ``Callable[[], Awaitable[Any]]``
    无参可调用对象，每次调用返回一个**新的**被测协程。扫描会对每个 k 调用一次。
    协程里应自己打开连接（``async with aiosqlite.connect(...)`` 或
    ``async with db_txn.connect(...)``），连接关闭语句也会被当作普通 aiosqlite
    调用计数；但通常扫描在事务体结束后、k 超过调用数时就自然停止了。
check : ``Callable[[CancelPointContext], Awaitable[Any]]``
    取消点检查函数，必须是 async 可调用对象。原生取消下它在等到任务结束之后、
    任务对象（``context.task``）仍被本模块引用时运行；``anyio`` 模式下它在宿主
    任务内部、被测协程抛出取消之后、``CancelScope`` 退出之前运行，并用
    ``anyio.CancelScope(shield=True)`` 包住（此时 ``context.task`` 是宿主任务
    本身）。返回值原样存进 ``CancelPoint.check_result``。检查函数抛出的普通异常
    会向外传播。检查函数返回后不要继续保存 ``context.task``（模块会把
    ``context.task`` 置空并释放任务引用，僵尸连接才会真正关闭）。
prepare : ``Callable[[], Awaitable[None]] | None``
    可选准备函数，在**每个**取消点（包括 k=1）之前运行一次，用来把数据恢复成
    初始状态。准备函数里的 aiosqlite 调用不计入取消点。
mode : ``"delivered" | "queued"``，默认 ``"delivered"``
cancel : ``"task" | "anyio"``，默认 ``"task"``
max_points : ``int``，默认 200
    安全上限。正常业务函数远小于它；达到上限仍未自然结束说明被测协程可能在
    无限地做数据库调用，此时抛 ``ScanLimitExceeded``，不静默截断。

返回值
------
``list[CancelPoint]``，按 k 升序，每个取消点一条记录。``CancelPoint`` 字段：

``k``
    第 k 次 aiosqlite 调用（从 1 开始）。
``label``
    调用标签：底层函数名 + SQL 开头一段，例如 ``"execute SELECT v FROM t"``。
``cancelled``
    原生取消：任务是否以 ``CancelledError`` 结束；第 k 次调用确实发生但取消被
    吞掉时是 ``False``。anyio 取消：``CancelScope`` 是否捕获到取消；取消被吞掉
    但注入之后还有 aiosqlite 调用时也是 ``False``。
``check_result``
    检查函数的返回值。
``check_completed``
    检查函数是否真的跑完。anyio 模式下如果检查函数被取消穿透而中断，这里是
    ``False``；扫描结束后若存在 ``False``，会抛 ``CheckNotCompleted``，保证不会
    被当成通过。
``mode`` / ``cancel``
    本次扫描使用的落点与取消方式。

终止条件：第 k 次调用没有发生（注入器的 ``fired`` 为空）；或 anyio 取消落在最后
一次 aiosqlite 调用上、取消域没有捕获到取消（属于自然结束）。取消被吞掉但之后
还有调用时记一条 ``cancelled=False`` 并继续扫描。自然结束的那一次不计入返回值，
也不调用 ``check``；但它的 ``prepare`` 已经先运行过（因此 ``prepare`` 的调用次数
通常等于记录数加一）。

``CancelPointContext`` 字段：``k``、``label``、``mode``、``cancel``、
``cancelled``、``task``（原生取消是被测任务对象；anyio 取消是宿主任务本身；
检查函数返回后置为 ``None``）。

异常
----
``NoCancelPointsFound``
    一个取消点都没扫到（没有任何一次调用被取消），不返回空列表让断言空转。
``CheckNotCompleted``
    某个取消点上检查函数没跑完；异常的 ``records`` 是全部已扫记录，
    ``incomplete`` 是未跑完的那些。
``ScanLimitExceeded``
    达到 ``max_points`` 仍未自然结束。
``ScanTimeout``
    等被测任务、``prepare``、``check`` 或写锁超过上限仍未结束；用于避免测试
    进程被挂死。

另外提供
========
``async def write_lock_is_free(db_path, *, busy_timeout=0.2) -> bool``
    新开一条忙等待 ``busy_timeout`` 秒的连接执行 ``BEGIN IMMEDIATE``；成功拿到
    写锁后回滚并返回 ``True``，遇到 ``database is locked``、超时或其他连接错误
    返回 ``False``。用于在取消点上判断有没有残留写锁。

用法示例
========
::

    import asyncio
    import aiosqlite
    from cancel_sweep import sweep_cancel_points, write_lock_is_free

    DB = "/tmp/example.db"

    async def make_coroutine():
        async with aiosqlite.connect(DB, timeout=0.2) as db:
            await db.execute("BEGIN IMMEDIATE")
            cursor = await db.execute("SELECT v FROM t WHERE id = 1")
            await cursor.fetchone()
            await db.execute("UPDATE t SET v = v + 1 WHERE id = 1")
            await db.commit()

    async def check(point):
        # 仍在任务对象被引用时运行；这里检查写锁是否空闲。
        return await write_lock_is_free(DB)

    points = await sweep_cancel_points(make_coroutine, check=check,
                                       mode="delivered")
    for point in points:
        print(point.k, point.label, point.cancelled, point.check_result)

    # queued 落点、anyio 取消、准备函数：
    points = await sweep_cancel_points(
        make_coroutine, check=check, prepare=reset_db,
        mode="queued", cancel="anyio")

约束
====
- 扫描器会临时替换 ``aiosqlite.core.Connection._execute`` 与
  ``aiosqlite.core.set_result``，并在 ``try/finally`` 里还原成进入扫描前的
  属性；不在扫描期间安装/卸载（不可重入、不可并发）。
- 每个取消点结束后会丢掉任务、等待结果等引用并调用一次 ``gc.collect()``，
  让被取消任务遗留的 aiosqlite 连接真正关闭；检查函数运行时任务对象仍被引用。
- 只能从同一个事件循环里调用；``anyio`` 模式使用 anyio 的 asyncio 后端，
  可以在 ``asyncio.run`` 下直接使用。
"""
from __future__ import annotations

import asyncio
import gc
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

import aiosqlite
import aiosqlite.core as _core
import anyio

__all__ = [
    "CancelPoint",
    "CancelPointContext",
    "CheckNotCompleted",
    "NoCancelPointsFound",
    "ScanLimitExceeded",
    "ScanTimeout",
    "sweep_cancel_points",
    "write_lock_is_free",
]

# 等任务、prepare、check、写锁的上限；超过就抛 ScanTimeout，避免挂死测试进程。
_OPERATION_TIMEOUT_SECONDS = 60.0
# 超时后给任务最后一次退出的宽限时间。
_CANCEL_GRACE_SECONDS = 5.0


@dataclass
class CancelPoint:
    """一个取消点的扫描记录，字段含义见模块文档字符串。"""

    k: int
    label: str
    cancelled: bool
    check_result: Any
    check_completed: bool
    mode: str
    cancel: str


@dataclass
class CancelPointContext:
    """传给检查函数的取消点上下文。

    ``task`` 只在检查函数运行期间有效；检查函数返回后本模块会把它置为
    ``None`` 并释放任务引用，不要把它保存到别处继续使用。
    """

    k: int
    label: str
    mode: str
    cancel: str
    cancelled: bool
    task: asyncio.Task | None


class NoCancelPointsFound(AssertionError):
    """一个取消点都没扫到：扫描器没有测到任何东西，不能当成通过。"""


class CheckNotCompleted(AssertionError):
    """检查函数在某个取消点上没有跑完（例如取消穿透了 shield）。"""

    def __init__(self, records: list[CancelPoint], incomplete: list[CancelPoint]):
        self.records = records
        self.incomplete = incomplete
        details = ", ".join(
            f"k={point.k} [{point.label}]" for point in incomplete
        )
        super().__init__(
            f"检查函数在 {len(incomplete)} 个取消点上没有跑完: {details}"
        )


class ScanLimitExceeded(RuntimeError):
    """达到扫描上限仍未自然结束，可能是被测协程在无限地做数据库调用。"""


class ScanTimeout(RuntimeError):
    """等待任务、准备函数、检查函数或写锁超过上限仍未结束。"""


async def _with_timeout(awaitable: Awaitable[Any], description: str) -> Any:
    """给一次 await 加明确上限；超时抛 ``ScanTimeout``，不改变正常路径。"""
    try:
        return await asyncio.wait_for(
            awaitable, timeout=_OPERATION_TIMEOUT_SECONDS
        )
    except asyncio.TimeoutError:
        raise ScanTimeout(
            f"{description}超过 {_OPERATION_TIMEOUT_SECONDS:g} 秒仍未完成"
        ) from None


async def _wait_for_task(task: asyncio.Task, description: str) -> None:
    """等任务结束，超过上限时取消并抛 ``ScanTimeout``。

    这里不用 ``asyncio.wait_for(gather(...))``：``wait_for`` 在任务吞掉取消时
    会一直等它退出；分两步 ``asyncio.wait`` 可以保证一定在有限时间内返回。
    """
    _done, pending = await asyncio.wait(
        {task}, timeout=_OPERATION_TIMEOUT_SECONDS
    )
    if not pending:
        return
    task.cancel()
    _done, still_pending = await asyncio.wait(
        {task}, timeout=_CANCEL_GRACE_SECONDS
    )
    if still_pending:
        raise ScanTimeout(
            f"{description}超过 {_OPERATION_TIMEOUT_SECONDS:g} 秒仍未结束，"
            f"取消后 {_CANCEL_GRACE_SECONDS:g} 秒仍未退出"
        )
    raise ScanTimeout(
        f"{description}超过 {_OPERATION_TIMEOUT_SECONDS:g} 秒仍未结束，已取消"
    )


# ---------------------------------------------------------------------------
# 注入器
# ---------------------------------------------------------------------------


def _format_label(fn: Any, args: tuple[Any, ...]) -> str:
    """方法名 + SQL 开头一段。"""
    name = getattr(fn, "__name__", repr(fn))
    sql = ""
    if args and isinstance(args[0], str):
        sql = " " + " ".join(args[0].split())[:60]
    return f"{name}{sql}"


class _Injector:
    """保存一次取消点扫描的可变状态。"""

    def __init__(self) -> None:
        self.task: asyncio.Task | None = None
        self.scope: Any = None
        # tracking 为真时统计目标任务的 aiosqlite 调用次数；fire 之后继续为真，
        # 用来判断 anyio 的取消是不是落在最后一次调用上。运行检查函数前置假，
        # 避免检查函数自己开的连接被算进来。
        self.tracking = False
        self.mode = "delivered"
        self.cancel = "task"
        self.k = 0
        self.n = 0
        self.fired: str | None = None
        self.arm = False

    def reset(self, *, mode: str, cancel: str, k: int) -> None:
        self.task = None
        self.scope = None
        self.tracking = False
        self.mode = mode
        self.cancel = cancel
        self.k = k
        self.n = 0
        self.fired = None
        self.arm = False

    def disarm(self) -> None:
        self.task = None
        self.scope = None
        self.tracking = False
        self.arm = False


_INJECTOR = _Injector()
_ORIGINAL_EXECUTE: Any = None
_ORIGINAL_SET_RESULT: Any = None
_INSTALLED = False


def _deliver_cancel(injector: _Injector) -> None:
    """在该取消落点上投递取消。"""
    if injector.cancel == "anyio":
        scope = injector.scope
        if scope is not None:
            scope.cancel()
        return
    task = injector.task
    if task is not None and not task.done():
        task.cancel()


async def _patched_execute(self: Any, fn: Any, *args: Any, **kwargs: Any) -> Any:
    """包装 ``aiosqlite.core.Connection._execute``，只统计被测任务的调用。"""
    injector = _INJECTOR
    if (
        injector.tracking
        and injector.task is not None
        and asyncio.current_task() is injector.task
    ):
        injector.n += 1
        label = _format_label(fn, args)
        if injector.n == injector.k:
            injector.fired = label
            if injector.mode == "queued":
                # 该次调用刚入队、还没有结果：先投递取消，再让原方法入队等待。
                _deliver_cancel(injector)
            else:
                # 结果由下面的 set_result 包装投递；那里再取消。
                injector.arm = True
    return await _ORIGINAL_EXECUTE(self, fn, *args, **kwargs)


def _patched_set_result(fut: asyncio.Future, result: Any) -> None:
    """包装 ``aiosqlite.core.set_result``，在结果写进 Future 之后立刻取消。"""
    _ORIGINAL_SET_RESULT(fut, result)
    injector = _INJECTOR
    if not injector.arm:
        return
    task = injector.task
    if task is None or task.done():
        return
    # 只对被测任务当前正在等待的那个 Future 生效；被丢弃的旧 Future 稍后到达时
    # 不能误取消新一轮扫描的任务。
    if fut is not getattr(task, "_fut_waiter", None):
        return
    injector.arm = False
    _deliver_cancel(injector)


def _install_injection() -> tuple[Any, Any]:
    """安装包装并返回进入前的原属性，供 ``finally`` 原样还原。"""
    global _ORIGINAL_EXECUTE, _ORIGINAL_SET_RESULT, _INSTALLED
    if _INSTALLED:
        raise RuntimeError("cancel_sweep 扫描器不可重入或并发使用")
    _ORIGINAL_EXECUTE = _core.Connection._execute
    _ORIGINAL_SET_RESULT = _core.set_result
    _core.Connection._execute = _patched_execute
    _core.set_result = _patched_set_result
    _INSTALLED = True
    return _ORIGINAL_EXECUTE, _ORIGINAL_SET_RESULT


def _restore_injection(saved: tuple[Any, Any]) -> None:
    """还原进入扫描前的属性；无论扫描成功、失败还是被取消都执行。"""
    global _ORIGINAL_EXECUTE, _ORIGINAL_SET_RESULT, _INSTALLED
    _core.Connection._execute = saved[0]
    _core.set_result = saved[1]
    _ORIGINAL_EXECUTE = saved[0]
    _ORIGINAL_SET_RESULT = saved[1]
    _INSTALLED = False


# ---------------------------------------------------------------------------
# 单个取消点
# ---------------------------------------------------------------------------


class _AnyioState:
    """anyio 取消域在宿主任务与扫描任务之间传递的状态。"""

    def __init__(self) -> None:
        self.scope: Any = None
        self.cancelled_caught = False
        self.check_completed = False
        self.check_result: Any = None


async def _run_asyncio_point(
    make_coroutine: Callable[[], Awaitable[Any]],
    check: Callable[[CancelPointContext], Awaitable[Any]],
    mode: str,
) -> CancelPoint | None:
    """原生 ``task.cancel()`` 的一个取消点；自然结束时返回 ``None``。"""
    injector = _INJECTOR
    injector.tracking = True
    task: asyncio.Task | None = None

    async def victim() -> None:
        try:
            await make_coroutine()
        finally:
            injector.tracking = False

    try:
        task = asyncio.create_task(victim(), name=f"cancel-sweep-k{injector.k}")
        injector.task = task
        # 与真实收尾代码一致：等任务结束；超时由 _wait_for_task 兜底。
        await _wait_for_task(task, f"等待第 {injector.k} 个取消点的被测任务")
        injector.tracking = False

        if task.cancelled():
            error: BaseException | None = None
            cancelled = True
        else:
            error = task.exception()
            cancelled = False
        if error is not None:
            # 以别的异常失败时保持向外抛，不能伪装成 cancelled=False。
            raise error

        fired = injector.fired
        if fired is None:
            # 第 k 次调用根本没有发生：扫描结束。
            return None

        # 第 k 次调用发生了。取消被吞掉时任务会正常完成，这里记
        # cancelled=False 并照常运行检查，然后继续扫 k+1。
        context = CancelPointContext(
            k=injector.k,
            label=fired,
            mode=mode,
            cancel="task",
            cancelled=cancelled,
            task=task,
        )
        try:
            check_result = await _with_timeout(
                check(context),
                f"检查函数 check()（k={injector.k}）",
            )
        finally:
            # 检查函数已经跑完；放掉它对任务对象的引用。
            context.task = None
        return CancelPoint(
            k=context.k,
            label=context.label,
            cancelled=cancelled,
            check_result=check_result,
            check_completed=True,
            mode=mode,
            cancel="task",
        )
    finally:
        injector.disarm()
        task = None
        gc.collect()


async def _run_anyio_point(
    make_coroutine: Callable[[], Awaitable[Any]],
    check: Callable[[CancelPointContext], Awaitable[Any]],
    mode: str,
) -> CancelPoint | None:
    """``anyio.CancelScope`` 的一个取消点；自然结束时返回 ``None``。"""
    injector = _INJECTOR
    state = _AnyioState()
    injector.tracking = True
    task: asyncio.Task | None = None

    async def host() -> None:
        # 取消域必须和被测协程在同一个任务里进入和退出。
        propagating_cancel = False
        failed_other = False
        with anyio.CancelScope() as scope:
            state.scope = scope
            injector.scope = scope
            try:
                await make_coroutine()
            except BaseException as error:
                propagating_cancel = isinstance(
                    error, anyio.get_cancelled_exc_class()
                )
                failed_other = not propagating_cancel
                raise
            finally:
                # 被测协程已经结束：先停止调用计数，再判断这次取消值不值得
                # 运行检查。检查函数自己开的连接不能计入调用次数。
                injector.tracking = False
                fired = injector.fired
                later_calls = injector.n > injector.k
                if (
                    fired is not None
                    and not failed_other
                    and (propagating_cancel or later_calls)
                ):
                    # 检查必须在宿主任务内部、CancelScope 退出之前运行，
                    # 且 shield 住，避免 anyio 在检查等待时再次投递取消。
                    context = CancelPointContext(
                        k=injector.k,
                        label=fired,
                        mode=mode,
                        cancel="anyio",
                        cancelled=propagating_cancel,
                        task=asyncio.current_task(),
                    )
                    try:
                        with anyio.CancelScope(shield=True):
                            state.check_result = await _with_timeout(
                                check(context),
                                f"检查函数 check()（k={injector.k}）",
                            )
                            state.check_completed = True
                    except asyncio.CancelledError:
                        # 检查函数没跑完：记录后由扫描结束处统一报错。
                        state.check_completed = False
                    finally:
                        context.task = None
        state.cancelled_caught = scope.cancelled_caught

    try:
        task = asyncio.create_task(host(), name=f"cancel-sweep-anyio-k{injector.k}")
        injector.task = task
        await _wait_for_task(
            task, f"等待第 {injector.k} 个 anyio 取消点的宿主任务"
        )
        injector.tracking = False

        if task.cancelled():
            error: BaseException | None = None
        else:
            error = task.exception()
        if error is not None:
            # 普通异常保持向外抛，不能伪装成 cancelled=False。
            raise error

        fired = injector.fired
        if fired is None:
            # 第 k 次调用根本没有发生：扫描结束。
            return None
        cancelled = bool(state.cancelled_caught)
        if not cancelled and injector.n <= injector.k:
            # 取消域没有捕获到取消，而且注入的是最后一次调用：自然结束。
            return None
        # 取消被吞掉但之后还有调用：记 cancelled=False，检查已在宿主任务
        # 的 finally 里跑过，继续扫 k+1。
        return CancelPoint(
            k=injector.k,
            label=fired,
            cancelled=cancelled,
            check_result=state.check_result,
            check_completed=state.check_completed,
            mode=mode,
            cancel="anyio",
        )
    finally:
        injector.disarm()
        task = None
        gc.collect()


# ---------------------------------------------------------------------------
# 对外扫描入口
# ---------------------------------------------------------------------------


async def sweep_cancel_points(
    make_coroutine: Callable[[], Awaitable[Any]],
    *,
    check: Callable[[CancelPointContext], Awaitable[Any]],
    prepare: Callable[[], Awaitable[None]] | None = None,
    mode: str = "delivered",
    cancel: str = "task",
    max_points: int = 200,
) -> list[CancelPoint]:
    """逐 k 扫描取消点，返回记录列表；细节见模块文档字符串。

    在 ``try/finally`` 里安装并还原 aiosqlite 注入；扫描结束后如果一条记录也
    没有，抛 ``NoCancelPointsFound``；如果有检查函数没跑完，抛
    ``CheckNotCompleted``。
    """
    if mode not in ("delivered", "queued"):
        raise ValueError(f"未知的取消落点 mode={mode!r}，只支持 'delivered'/'queued'")
    if cancel not in ("task", "anyio"):
        raise ValueError(f"未知的取消方式 cancel={cancel!r}，只支持 'task'/'anyio'")
    if not isinstance(max_points, int) or max_points < 1:
        raise ValueError(f"max_points 必须是正整数，收到 {max_points!r}")

    records: list[CancelPoint] = []
    saved = _install_injection()
    try:
        for k in range(1, max_points + 1):
            if prepare is not None:
                await _with_timeout(
                    prepare(), f"准备函数 prepare()（取消点 k={k} 之前）"
                )
            _INJECTOR.reset(mode=mode, cancel=cancel, k=k)
            if cancel == "anyio":
                point = await _run_anyio_point(make_coroutine, check, mode)
            else:
                point = await _run_asyncio_point(make_coroutine, check, mode)
            if point is None:
                break
            records.append(point)
        else:
            raise ScanLimitExceeded(
                f"取消点扫描达到上限 max_points={max_points}（mode={mode}, "
                f"cancel={cancel}）仍未自然结束"
            )
    finally:
        _INJECTOR.disarm()
        _restore_injection(saved)

    if not records:
        raise NoCancelPointsFound(
            f"没有扫到任何取消点（mode={mode}, cancel={cancel}）："
            "被测协程没有发生可取消的 aiosqlite 调用"
        )
    incomplete = [point for point in records if not point.check_completed]
    if incomplete:
        raise CheckNotCompleted(records, incomplete)
    return records


# ---------------------------------------------------------------------------
# 写锁检查
# ---------------------------------------------------------------------------


async def write_lock_is_free(db_path: str, *, busy_timeout: float = 0.2) -> bool:
    """新开连接尝试 ``BEGIN IMMEDIATE``，成功拿到写锁并回滚则返回 ``True``。

    ``busy_timeout`` 是 SQLite 忙等待秒数（默认 0.2）。遇到写锁被占、超时或
    其他连接错误都返回 ``False``；任务被取消时 ``CancelledError`` 照常传播。
    整个检查超过上限仍未结束会抛 ``ScanTimeout``，不再无限等锁。
    """

    async def _attempt() -> bool:
        connection: aiosqlite.Connection | None = None
        try:
            connection = await aiosqlite.connect(db_path, timeout=busy_timeout)
            try:
                await connection.execute("BEGIN IMMEDIATE")
            except Exception:
                return False
            try:
                await connection.rollback()
            except Exception:
                return False
            return True
        except Exception:
            return False
        finally:
            if connection is not None:
                try:
                    await connection.close()
                except Exception:
                    pass

    return await _with_timeout(_attempt(), "write_lock_is_free 等锁")
