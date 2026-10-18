# -*- coding: utf-8 -*-
"""写歌版本状态机、火山任务提交与轮询。

状态流转：

    queued -> submitting -> submitted -> running -> downloading -> succeeded
                                   \\-> rejected
                                   \\-> uncertain
    submitted/running -> failed / expired

计费约束：创建时在一个 ``BEGIN IMMEDIATE`` 事务里预扣草莓并把
``billing_state`` 置为 ``reserved``；退款只由 :func:`refund_version` 执行，
它在同一事务里先把 ``billing_state`` 从 ``reserved`` 改成 ``refunded``，
只有确实改到 1 行才给用户加回草莓，所以并发退款只会回一次。

本模块不记录密钥、歌词正文、上游响应正文或音频 URL；日志只打印固定错误码。
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime, timezone
from uuid import uuid4

import aiosqlite

import database
from song import config, media, volc
from song import store
from utils.background_tasks import create_background_task


# 在途状态：算并发上限。
INFLIGHT_STATUSES: frozenset[str] = frozenset(
    {"queued", "submitting", "submitted", "running", "downloading"}
)

# 终态。
TERMINAL_STATUSES: frozenset[str] = frozenset(
    {"succeeded", "failed", "rejected", "uncertain", "expired"}
)

POLL_ACTIVE_STATUSES = ("submitted", "running")

# 需要退款对账的终态：这些状态本应已经退过款，只补偿「已标终态但事务没走完」
# 的崩溃/锁超时窗口。succeeded 与在途状态一律不碰。
REFUNDABLE_TERMINAL_STATUSES = ("failed", "rejected", "uncertain", "expired")

GENERIC_FAILURE_MESSAGE = "生成失败，请稍后再试"
PLAGIARISM_FAILURE_MESSAGE = "歌词疑似与已有作品重复，请改写后再试"

_SUBMIT_LABEL = "song-submit"

# 状态机内部错误码（只用于 failure_code / 日志，不含用户内容）。
_CODE_UNKNOWN_SUBMIT = "submit_unknown"
_CODE_RECOVERED_SUBMITTING = "recovered_submitting"
_CODE_EXPIRED = "expired"
_CODE_MISSING_TASK = "missing_task"
_CODE_MEDIA_EMPTY = "invalid_audio"
_CODE_DOWNLOAD_UNEXPECTED = "download_unexpected"


class SongError(Exception):
    """路由可转成 HTTPException 的业务错误；detail 是给人看的中文短句。"""

    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


# ------------------------------------------------------------------ 通用工具
def _dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _load_params(raw) -> dict | None:
    try:
        value = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _today_shanghai() -> str:
    """上海自然日（与 database._today_shanghai 同一规则）。"""
    try:
        from zoneinfo import ZoneInfo

        tz = ZoneInfo("Asia/Shanghai")
    except Exception:  # pragma: no cover - 极端环境没有时区库
        from datetime import timedelta

        tz = timezone(timedelta(hours=8))
    return datetime.now(tz).date().isoformat()


def _finite_number(value) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and abs(number) != float("inf") else None


def _created_epoch(raw) -> float | None:
    """把 SQLite 的 ``created_at`` 解析成 epoch；只用于轮询间隔。"""
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return float(raw)
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            return float(text)
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def _int_progress(value) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    number = int(value)
    return min(100, max(0, number))


def _captions_text(value) -> str | None:
    """Captions 原样保存；P0 不解析，只保证落库是文本。"""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        return None


def _public_version(row) -> dict:
    def _get(key, default=None):
        try:
            return row[key]
        except (KeyError, IndexError, TypeError):
            return default

    return {
        "id": _get("id"),
        "project_id": _get("project_id"),
        "lyrics_revision": _get("lyrics_revision"),
        "status": _get("status"),
        "progress": _get("progress"),
        "failure_message": _get("failure_message"),
        "duration_s": _get("duration_s"),
        "created_at": _get("created_at"),
    }


def _exists_user_clause() -> str:
    return (
        "EXISTS (SELECT 1 FROM users WHERE username = song_versions.owner_username)"
    )


# ---------------------------------------------------------------- 读取辅助
async def usage_counts(user: str) -> tuple[int, int]:
    """返回 (在途版本数, 今天非 rejected 版本数)；供路由算 can_generate。"""
    inflight_marks = ",".join("?" for _ in INFLIGHT_STATUSES)
    parameters = [user, *sorted(INFLIGHT_STATUSES)]
    async with aiosqlite.connect(
        database.DB_PATH, timeout=database.SQLITE_BUSY_TIMEOUT
    ) as db:
        async with db.execute(
            f"""SELECT COUNT(*) FROM song_versions
                 WHERE owner_username = ? AND status IN ({inflight_marks})""",
            parameters,
        ) as cursor:
            inflight = (await cursor.fetchone())[0]
        async with db.execute(
            """SELECT COUNT(*) FROM song_versions
                WHERE owner_username = ? AND created_day = ? AND status != 'rejected'""",
            (user, _today_shanghai()),
        ) as cursor:
            today = (await cursor.fetchone())[0]
    return int(inflight or 0), int(today or 0)


async def get_version(version_id: str, *, owner_username: str) -> dict | None:
    """按 owner 读取版本行（含项目标题），不存在与无权都返回 None。"""
    if not isinstance(version_id, str) or not version_id:
        return None
    async with aiosqlite.connect(
        database.DB_PATH, timeout=database.SQLITE_BUSY_TIMEOUT
    ) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT v.*, p.title AS project_title
                 FROM song_versions AS v
                 LEFT JOIN song_projects AS p ON p.id = v.project_id
                WHERE v.id = ? AND v.owner_username = ?""",
            (version_id, owner_username),
        ) as cursor:
            row = await cursor.fetchone()
    return dict(row) if row is not None else None


# ---------------------------------------------------------------- 创建
async def create_generation(
    user: str, project_id: str, lyrics_revision: int, idempotency_key: str
) -> dict:
    """创建一次生成：校验、限流、预扣草莓、插入 queued 版本并调度提交。"""
    price = config.song_price_strawberries()
    max_inflight = config.song_max_inflight()
    daily_limit = config.song_daily_limit()
    created_day = _today_shanghai()
    version_id = uuid4().hex

    async with aiosqlite.connect(
        database.DB_PATH, timeout=database.SQLITE_BUSY_TIMEOUT
    ) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("BEGIN IMMEDIATE")
        try:
            project = await store.fetch_project(
                db, project_id, owner_username=user
            )
            if project is None:
                raise SongError(404, "找不到这个写歌项目")

            # 幂等优先于歌词校验：同一用户重复提交同一把钥匙时，即使歌词
            # 已经更新或配置临时缺失，也直接返回第一次创建的那一版。
            async with db.execute(
                """SELECT * FROM song_versions
                    WHERE owner_username = ? AND idempotency_key = ?""",
                (user, idempotency_key),
            ) as cursor:
                existing = await cursor.fetchone()
            if existing is not None:
                result = _public_version(existing)
                await db.commit()
                return result

            lyrics = await store.fetch_latest_lyrics(db, project["id"])
            if (
                not isinstance(lyrics_revision, int)
                or isinstance(lyrics_revision, bool)
                or lyrics_revision != project["lyrics_revision"]
            ):
                raise SongError(409, "歌词已更新，请刷新")
            if lyrics is None or lyrics.get("revision") != project["lyrics_revision"]:
                raise SongError(409, "歌词有未解决的问题")
            check = lyrics.get("check") or {}
            if not isinstance(check, dict) or check.get("ok") is not True:
                raise SongError(409, "歌词有未解决的问题")

            if not config.song_configured():
                raise SongError(409, "写歌服务未配置")

            inflight_marks = ",".join("?" for _ in INFLIGHT_STATUSES)
            async with db.execute(
                f"""SELECT COUNT(*) FROM song_versions
                     WHERE owner_username = ? AND status IN ({inflight_marks})""",
                (user, *sorted(INFLIGHT_STATUSES)),
            ) as cursor:
                inflight = (await cursor.fetchone())[0]
            if int(inflight or 0) >= max_inflight:
                raise SongError(429, "同时在途的歌曲太多，请稍后再试")

            async with db.execute(
                """SELECT COUNT(*) FROM song_versions
                    WHERE owner_username = ? AND created_day = ?
                      AND status != 'rejected'""",
                (user, created_day),
            ) as cursor:
                today_count = (await cursor.fetchone())[0]
            if int(today_count or 0) >= daily_limit:
                raise SongError(429, "今天生成歌曲的次数已用完，明天再来吧")

            dev_mode = os.getenv("DEV_MODE", "0") == "1"
            if dev_mode:
                billing_state = "none"
            else:
                await database._apply_daily_refill(
                    db, user, database.strawberry_daily_refill()
                )
                async with db.execute(
                    """UPDATE users SET strawberry_balance = strawberry_balance - ?
                        WHERE username = ? AND strawberry_balance >= ?""",
                    (price, user, price),
                ) as cursor:
                    if cursor.rowcount != 1:
                        raise SongError(402, database.strawberry_insufficient_message())
                billing_state = "reserved"

            params = volc.build_params(project, check, version_id)
            await db.execute(
                """INSERT INTO song_versions
                       (id, project_id, owner_username, lyrics_revision, provider,
                        params_json, status, progress, strawberries, billing_state,
                        idempotency_key, created_day)
                   VALUES (?, ?, ?, ?, 'volc', ?, 'queued', 0, ?, ?, ?, ?)""",
                (
                    version_id,
                    project["id"],
                    user,
                    lyrics_revision,
                    _dumps(params),
                    price,
                    billing_state,
                    idempotency_key,
                    created_day,
                ),
            )
            async with db.execute(
                "SELECT * FROM song_versions WHERE id = ?", (version_id,)
            ) as cursor:
                row = await cursor.fetchone()
            result = _public_version(row)
            await db.commit()
        except BaseException:
            await db.rollback()
            raise

    create_background_task(submit_version(version_id), label=_SUBMIT_LABEL)
    return result


# ---------------------------------------------------------------- 提交
async def submit_version(version_id: str) -> None:
    """把 queued 版本提交给火山；仅当原子改到 submitting 时才发请求。"""
    params = None
    changed = 0
    async with aiosqlite.connect(
        database.DB_PATH, timeout=database.SQLITE_BUSY_TIMEOUT
    ) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("BEGIN IMMEDIATE")
        try:
            async with db.execute(
                f"""SELECT params_json FROM song_versions
                     WHERE id = ? AND status = 'queued' AND {_exists_user_clause()}""",
                (version_id,),
            ) as cursor:
                row = await cursor.fetchone()
            if row is not None:
                params = _load_params(row["params_json"])
                async with db.execute(
                    f"""UPDATE song_versions SET status = 'submitting',
                            updated_at = CURRENT_TIMESTAMP
                         WHERE id = ? AND status = 'queued'
                           AND {_exists_user_clause()}""",
                    (version_id,),
                ) as cursor:
                    changed = cursor.rowcount
            await db.commit()
        except BaseException:
            await db.rollback()
            raise
    if changed != 1:
        return
    if params is None:
        await _mark_submit_terminal(version_id, "uncertain", _CODE_UNKNOWN_SUBMIT)
        await refund_version(version_id)
        print("[song] code=submit_invalid_params")
        return

    try:
        task_id = await get_provider().submit(params)
    except volc.SubmitRejected as exc:
        await _mark_submit_terminal(version_id, "rejected", exc.code)
        await refund_version(version_id)
        return
    except volc.SubmitUncertain as exc:
        await _mark_submit_terminal(version_id, "uncertain", exc.code)
        await refund_version(version_id)
        return
    except Exception:
        # 付费 POST 的结果未知：不重试，按 uncertain 退款，只打印固定错误码。
        await _mark_submit_terminal(version_id, "uncertain", _CODE_UNKNOWN_SUBMIT)
        await refund_version(version_id)
        print("[song] code=submit_unknown")
        return

    now = time.time()
    await _execute_guarded(
        """UPDATE song_versions
              SET status = 'submitted', provider_task_id = ?,
                  next_poll_at = ?, deadline_at = ?,
                  updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND status = 'submitting'""",
        (task_id, now + 5, now + 900, version_id),
    )


async def _mark_submit_terminal(version_id: str, status: str, code) -> None:
    await _execute_guarded(
        """UPDATE song_versions
              SET status = ?, failure_code = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND status = 'submitting'""",
        (status, str(code) if code is not None else None, version_id),
    )


# ---------------------------------------------------------------- 退款
async def refund_version(version_id: str) -> bool:
    """退款一次：标记 refunded 与加回草莓在同一事务；返回是否真的退回。"""
    async with aiosqlite.connect(
        database.DB_PATH, timeout=database.SQLITE_BUSY_TIMEOUT
    ) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("BEGIN IMMEDIATE")
        try:
            async with db.execute(
                "SELECT owner_username, strawberries FROM song_versions WHERE id = ?",
                (version_id,),
            ) as cursor:
                row = await cursor.fetchone()
            if row is None:
                await db.rollback()
                return False
            async with db.execute(
                """UPDATE song_versions SET billing_state = 'refunded',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND billing_state = 'reserved'""",
                (version_id,),
            ) as cursor:
                if cursor.rowcount != 1:
                    await db.commit()
                    return False
            amount = row["strawberries"]
            if isinstance(amount, int) and not isinstance(amount, bool) and amount > 0:
                await db.execute(
                    """UPDATE users SET strawberry_balance = strawberry_balance + ?
                        WHERE username = ?""",
                    (amount, row["owner_username"]),
                )
            await db.commit()
            return True
        except BaseException:
            await db.rollback()
            raise


async def reconcile_refunds() -> int:
    """退回「已标终态但 billing_state 仍是 reserved」的版本，返回实际退回数。

    覆盖「状态已写成 failed/rejected/uncertain/expired、退款事务却没走完」的
    崩溃或锁超时窗口。只处理用户仍存在的版本；``succeeded`` 与在途状态一律
    不碰。单个版本失败只打印固定错误码并继续，查询失败也不外抛。
    """
    refunded = 0
    marks = ",".join("?" for _ in REFUNDABLE_TERMINAL_STATUSES)
    try:
        async with aiosqlite.connect(
            database.DB_PATH, timeout=database.SQLITE_BUSY_TIMEOUT
        ) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                f"""SELECT id FROM song_versions
                     WHERE status IN ({marks})
                       AND billing_state = 'reserved'
                       AND {_exists_user_clause()}""",
                REFUNDABLE_TERMINAL_STATUSES,
            ) as cursor:
                rows = await cursor.fetchall()
    except Exception:
        print("[song] code=reconcile_failed")
        return refunded

    for row in rows:
        try:
            if await refund_version(row["id"]):
                refunded += 1
        except Exception:
            print("[song] code=reconcile_failed")
    return refunded


# ---------------------------------------------------------------- 轮询
async def _execute_guarded(sql: str, parameters: tuple) -> int:
    """带 ``users`` 存在检查的写库；返回影响行数。"""
    guarded_sql = sql + f" AND {_exists_user_clause()}" if "WHERE" in sql else sql
    async with aiosqlite.connect(
        database.DB_PATH, timeout=database.SQLITE_BUSY_TIMEOUT
    ) as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            async with db.execute(guarded_sql, parameters) as cursor:
                changed = cursor.rowcount
            await db.commit()
        except BaseException:
            await db.rollback()
            raise
    return int(changed or 0)


async def _due_versions(now: float) -> list[dict]:
    async with aiosqlite.connect(
        database.DB_PATH, timeout=database.SQLITE_BUSY_TIMEOUT
    ) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT v.*, p.title AS project_title
                 FROM song_versions AS v
                 LEFT JOIN song_projects AS p ON p.id = v.project_id
                WHERE v.status IN ('submitted', 'running')
                  AND v.next_poll_at IS NOT NULL
                  AND v.next_poll_at <= ?
                ORDER BY v.next_poll_at ASC, v.rowid ASC""",
            (now,),
        ) as cursor:
            rows = await cursor.fetchall()
    return [dict(row) for row in rows]


def _set_failed_sql(from_statuses: tuple[str, ...]) -> str:
    marks = ",".join("?" for _ in from_statuses)
    return f"""UPDATE song_versions
                  SET status = 'failed', failure_code = ?, failure_message = ?,
                      updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND status IN ({marks})"""


def _set_expired_sql() -> str:
    return """UPDATE song_versions
                 SET status = 'expired', failure_code = ?,
                     updated_at = CURRENT_TIMESTAMP
               WHERE id = ? AND status IN ('submitted', 'running')"""


async def _fail_version(
    version_id: str,
    code,
    message: str,
    from_statuses: tuple[str, ...],
) -> int:
    changed = await _execute_guarded(
        _set_failed_sql(from_statuses),
        (str(code) if code is not None else None, message, version_id, *from_statuses),
    )
    return changed


async def _expire_version(version_id: str) -> int:
    return await _execute_guarded(
        _set_expired_sql(), (_CODE_EXPIRED, version_id)
    )


async def _run_version(
    version_id: str, progress: int, next_poll_at: float
) -> int:
    return await _execute_guarded(
        """UPDATE song_versions
              SET status = 'running', progress = ?, next_poll_at = ?,
                  updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND status IN ('submitted', 'running')""",
        (progress, next_poll_at, version_id),
    )


async def _postpone_version(version_id: str, next_poll_at: float) -> int:
    return await _execute_guarded(
        """UPDATE song_versions SET next_poll_at = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND status IN ('submitted', 'running')""",
        (next_poll_at, version_id),
    )


async def _claim_downloading(version_id: str, progress: int) -> int:
    return await _execute_guarded(
        """UPDATE song_versions
              SET status = 'downloading', progress = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND status IN ('submitted', 'running')""",
        (progress, version_id),
    )


async def _mark_succeeded(
    version_id: str,
    *,
    audio_rel_path: str,
    duration_s,
    captions_raw,
) -> int:
    return await _execute_guarded(
        """UPDATE song_versions
              SET status = 'succeeded',
                  billing_state = CASE WHEN billing_state = 'reserved'
                                       THEN 'settled' ELSE billing_state END,
                  audio_rel_path = ?, duration_s = ?, captions_raw = ?,
                  progress = 100, updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND status = 'downloading'""",
        (audio_rel_path, duration_s, captions_raw, version_id),
    )


def _unlink_audio(audio_rel_path) -> None:
    path = media.safe_audio_path(audio_rel_path)
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _failure_message(code, message) -> str:
    if code == 300061 or str(code) == "300061" or message == "InputLyricsPlagiarized":
        return PLAGIARISM_FAILURE_MESSAGE
    return GENERIC_FAILURE_MESSAGE


async def _handle_succeeded(version: dict, result: dict, now: float) -> None:
    version_id = version["id"]
    progress = _int_progress(result.get("progress"))
    if progress <= 0:
        progress = 99
    if await _claim_downloading(version_id, progress) != 1:
        # 已被其它轮询处理，或用户已删号且行已不存在。
        return
    try:
        info = await media.download_and_store(
            result.get("audio_url"),
            version_id=version_id,
            title=version.get("project_title") or "",
        )
    except media.MediaError as exc:
        await _fail_version(
            version_id, exc.code, GENERIC_FAILURE_MESSAGE, ("downloading",)
        )
        await refund_version(version_id)
        return
    except Exception:
        # 下载/转码抛出 MediaError 以外的异常也要收口：标记 failed 并退款，
        # 不让单个版本把整轮 poll_once 打断。不打印异常正文。
        await _fail_version(
            version_id,
            _CODE_DOWNLOAD_UNEXPECTED,
            GENERIC_FAILURE_MESSAGE,
            ("downloading",),
        )
        await refund_version(version_id)
        return
    if (
        not isinstance(info, dict)
        or not isinstance(info.get("audio_rel_path"), str)
        or not info["audio_rel_path"]
    ):
        await _fail_version(
            version_id, _CODE_MEDIA_EMPTY, GENERIC_FAILURE_MESSAGE, ("downloading",)
        )
        await refund_version(version_id)
        return
    duration = info.get("duration_s")
    if not isinstance(duration, (int, float)) or isinstance(duration, bool):
        duration = result.get("duration")
    changed = await _mark_succeeded(
        version_id,
        audio_rel_path=info["audio_rel_path"],
        duration_s=duration,
        captions_raw=_captions_text(result.get("captions_raw")),
    )
    if changed != 1:
        # 删号与下载并发：行已被删掉，刚下载的文件不能留。
        _unlink_audio(info["audio_rel_path"])


async def _handle_failed(version: dict, result: dict) -> None:
    version_id = version["id"]
    code = result.get("failure_code")
    message = _failure_message(code, result.get("failure_msg"))
    await _fail_version(version_id, code, message, POLL_ACTIVE_STATUSES)
    await refund_version(version_id)


async def poll_once(now: float | None = None) -> None:
    """轮询一轮到期的 submitted/running 版本。"""
    current = time.time() if now is None else float(now)
    try:
        versions = await _due_versions(current)
    except Exception:
        # 查询待轮询版本本身失败也不能把整轮抛出；下一轮再试。
        print("[song] code=poll_unexpected")
        return
    provider = None
    for version in versions:
        version_id = version["id"]
        try:
            deadline = _finite_number(version.get("deadline_at"))
            if deadline is not None and current > deadline:
                await _expire_version(version_id)
                await refund_version(version_id)
                continue

            task_id = version.get("provider_task_id")
            if not isinstance(task_id, str) or not task_id:
                await _fail_version(
                    version_id, _CODE_MISSING_TASK, GENERIC_FAILURE_MESSAGE,
                    POLL_ACTIVE_STATUSES,
                )
                await refund_version(version_id)
                continue

            if provider is None:
                provider = get_provider()
            try:
                result = await provider.query(task_id)
            except volc.PollError:
                # PollError 是预期内的「下次再查」：只推迟，不打印错误码。
                await _postpone_version(version_id, current + 10)
                continue
            if not isinstance(result, dict):
                await _postpone_version(version_id, current + 10)
                continue

            state = result.get("state")
            if state in ("waiting", "running"):
                progress = _int_progress(result.get("progress"))
                created = _created_epoch(version.get("created_at"))
                recent = created is not None and current - created < 60
                await _run_version(
                    version_id, progress, current + (5 if recent else 10)
                )
            elif state == "succeeded":
                await _handle_succeeded(version, result, current)
            elif state == "failed":
                await _handle_failed(version, result)
            else:
                await _postpone_version(version_id, current + 10)
        except Exception:
            # 单版本兜底：供应商查询、取供应商或状态写库的任何非预期异常都
            # 只影响这一版，整轮 poll_once 不向外抛。不打印异常正文。
            print("[song] code=poll_unexpected")
            try:
                await _postpone_version(version_id, current + 10)
            except Exception:
                pass


# ---------------------------------------------------------------- 恢复与轮询器
async def recover_on_startup() -> None:
    """进程重启恢复；仅由 lifespan 在开关开启时调用。"""
    now = time.time()
    submitting: list[str] = []
    queued: list[str] = []
    async with aiosqlite.connect(
        database.DB_PATH, timeout=database.SQLITE_BUSY_TIMEOUT
    ) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("BEGIN IMMEDIATE")
        try:
            exists = _exists_user_clause()
            async with db.execute(
                f"""SELECT id FROM song_versions
                     WHERE status = 'submitting' AND {exists}"""
            ) as cursor:
                submitting = [row["id"] for row in await cursor.fetchall()]
            await db.execute(
                f"""UPDATE song_versions
                       SET status = 'uncertain', failure_code = ?,
                           updated_at = CURRENT_TIMESTAMP
                     WHERE status = 'submitting' AND {exists}""",
                (_CODE_RECOVERED_SUBMITTING,),
            )
            async with db.execute(
                f"""SELECT id FROM song_versions
                     WHERE status = 'queued' AND {exists}"""
            ) as cursor:
                queued = [row["id"] for row in await cursor.fetchall()]
            await db.execute(
                f"""UPDATE song_versions
                       SET status = 'running', next_poll_at = ?,
                           updated_at = CURRENT_TIMESTAMP
                     WHERE status = 'downloading' AND {exists}""",
                (now,),
            )
            await db.commit()
        except BaseException:
            await db.rollback()
            raise

    for version_id in submitting:
        await refund_version(version_id)
    for version_id in queued:
        create_background_task(submit_version(version_id), label=_SUBMIT_LABEL)


def get_provider():
    """供应商工厂；测试 monkeypatch 成假供应商。"""
    return volc.VolcMusicClient()


async def run_poller() -> None:
    """后台轮询器：每 5 秒一轮，每 60 秒清理待删音频并做一次退款对账。"""
    last_cleanup = time.monotonic()
    while True:
        try:
            await poll_once()
        except Exception:
            print("[song] code=poll_failed")
        if time.monotonic() - last_cleanup >= 60:
            # 两项各自兜底，互不影响；失败也要推进 last_cleanup，避免热循环。
            try:
                await media.drain_cleanup_queue()
            except Exception:
                print("[song] code=cleanup_failed")
            try:
                await reconcile_refunds()
            except Exception:
                print("[song] code=reconcile_failed")
            last_cleanup = time.monotonic()
        await asyncio.sleep(5)
