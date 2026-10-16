"""终态通知与付费状态分开提交，失败由后续 tick 补写。"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import weakref

from . import pricing, store


logger = logging.getLogger(__name__)
NOTICE_STATUSES = frozenset({"downloaded", "failed", "rejected", "filtered", "expired", "uncertain"})
_LOOP_LOCKS: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()
_PENDING_NOTICES: dict[tuple[str, str], dict] = {}
_STATUS_LABELS = {
    "failed": "失败", "rejected": "被拒绝（未扣费）", "filtered": "被内容审核拦截（未扣费）",
    "expired": "结果已过期",
}
_ERROR_LABELS = {
    "restart_during_submission": "提交时服务重启", "submission_interrupted": "提交被中断",
    "submission_error": "提交发生错误", "poll_timeout": "查询已超时",
    "short_output": "成片时长短于请求时长", "not_charged": "已确认未扣费",
    "missing_first_frame": "首帧素材不可用",
}


def _account_lock(username: str) -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    locks = _LOOP_LOCKS.setdefault(loop, weakref.WeakValueDictionary())
    return locks.setdefault(username, asyncio.Lock())


def discard_pending_notices(username: str) -> None:
    """删号在事务提交后清除该账号尚未补写的内存快照。"""
    import database
    for key, pending in list(_PENDING_NOTICES.items()):
        if key[0] == str(database.DB_PATH) and pending["owner"] == username:
            _PENDING_NOTICES.pop(key, None)


def notice_content(job: dict, title: str) -> str:
    """只取项目名、白名单标签和已结算字段，绝不拼接上游错误正文。"""
    title = re.sub(r"(?:https?://|www\.)\S+", "", title, flags=re.IGNORECASE)
    title = re.sub(r"(?:sk-[A-Za-z0-9_-]+|Bearer\s+\S+)", "", title, flags=re.IGNORECASE)
    for name in ("ARK_API_KEY", "DASHSCOPE_API_KEY", "DASHSCOPE_WORKSPACE_ID"):
        secret = os.getenv(name, "").strip()
        if secret:
            title = title.replace(secret, "")
    if job.get("task_id"):
        title = title.replace(job["task_id"], "")
    title = " ".join(title.split()) or "未命名项目"
    prefix = f"【短片工作室】《{title}》镜头"
    if job["status"] == "uncertain":
        return prefix + "提交结果不确定，可能已扣费，请到工作室核对。"
    if job["status"] == "downloaded":
        params = job["params"]
        model = "万相 3.0" if job["provider"] == "wan" else "Seedance 2.5"
        duration = params["duration"]
        if duration == -1:
            # 自适应时长优先使用素材实长，避免向用户显示 -1 秒。
            duration = job.get("result_duration_s") or params["duration_max_s"]
        duration_text = f"{float(duration):g}"
        if job.get("actual_cny") is None:
            # 上游用量不合法时 WO1 保留预留，不能把未结算误写为实付零元。
            return prefix + f"已生成：{model} {params['resolution'].upper()} {duration_text} 秒，费用待核对。"
        return prefix + (f"已生成：{model} {params['resolution'].upper()} {duration_text} 秒，"
                         f"实付 ¥{pricing.money(job['actual_cny']):.2f}。")
    content = prefix + f"未生成：{_STATUS_LABELS[job['status']]}"
    reason = _ERROR_LABELS.get(job.get("error_code"))
    if reason:
        content += f"，原因：{reason}"
    content += "。"
    if (job.get("actual_cny") is not None and pricing.money(job["reserved_cny"]) == 0
            and pricing.money(job["actual_cny"]) < pricing.money(job["est_max_cny"])):
        content += "未扣费的部分已释放。"
    return content


async def write_job_notice(job_id: str) -> None:
    """通知异常只能记固定错误码，不能冒泡到调度和结算路径。"""
    import database
    pending_key = (str(database.DB_PATH), job_id)
    try:
        async with store.connection() as db:
            owner = await store._one(db, """SELECT j.owner FROM studio_jobs j
                JOIN users u ON u.username=j.owner WHERE j.id=?""", (job_id,))
        if owner is None:
            _PENDING_NOTICES.pop(pending_key, None)
            return
        # 与本机监控相同：同账号写入串行，避免相同正文被两个任务误认领。
        async with _account_lock(owner["owner"]):
            async with store.connection() as db:
                job = await store._one(db, """SELECT j.*,p.title AS project_title,
                        a.duration_s AS result_duration_s
                    FROM studio_jobs j JOIN studio_projects p ON p.id=j.project_id AND p.owner=j.owner
                    LEFT JOIN studio_assets a ON a.id=j.result_asset_id AND a.owner=j.owner
                    WHERE j.id=? AND j.kind='i2v' AND p.archived=0
                        AND NOT EXISTS(SELECT 1 FROM studio_notices n WHERE n.job_id=j.id)
                        AND NOT EXISTS(SELECT 1 FROM studio_notice_historical h WHERE h.job_id=j.id)""", (job_id,))
            if job is None:
                _PENDING_NOTICES.pop(pending_key, None)
                return
            pending = _PENDING_NOTICES.get(pending_key)
            if pending is None:
                async with store.connection() as db:
                    durable = await store._one(db, "SELECT content FROM studio_notice_pending WHERE job_id=? AND username=?",
                                               (job_id, job["owner"]))
                if durable is None and job["status"] not in NOTICE_STATUSES:
                    return
                content = durable["content"] if durable else notice_content(job, job["project_title"])
                pending = {"owner": job["owner"], "content": database.WatchPrivateText(content)}
                _PENDING_NOTICES[pending_key] = pending
            content = pending["content"]
            if await database.save_studio_notice(job["owner"], job, content[:200], content) is not None:
                _PENDING_NOTICES.pop(pending_key, None)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.warning("studio code=notice_write_error")


async def initialize_notice_cutoff() -> str:
    """Atomically mark pre-deployment terminals and the first scheduler start.

    Historical job IDs remain excluded if an old uncertain task later changes
    updated_at during recheck. Already-attempted notifications retain their
    durable retry records and are never mistaken for a historical backfill.
    """
    import database
    async with store.connection(transaction=True) as db:
        row = await store._one(db, "SELECT value FROM studio_notice_meta WHERE key='started_at'")
        if row is not None:
            return row["value"]
        await db.execute("""INSERT OR IGNORE INTO studio_notice_historical(job_id)
            SELECT j.id FROM studio_jobs j
            WHERE j.kind='i2v'
                AND j.status IN ('downloaded','failed','rejected','filtered','expired','uncertain')
                AND NOT EXISTS(SELECT 1 FROM studio_notice_pending d WHERE d.job_id=j.id)""")
        for key in list(_PENDING_NOTICES):
            if key[0] == str(database.DB_PATH):
                await db.execute("DELETE FROM studio_notice_historical WHERE job_id=?", (key[1],))
        now = store.utcnow()
        await db.execute("INSERT INTO studio_notice_meta(key,value) VALUES('started_at',?)", (now,))
        return now


async def retry_pending_notices() -> None:
    try:
        import database
        cutoff = await initialize_notice_cutoff()
        pending_ids = [key[1] for key in _PENDING_NOTICES if key[0] == str(database.DB_PATH)]
        async with store.connection() as db:
            # This expression matches idx_studio_jobs_notice_terminal. Uncertain
            # submissions may not have finished_at, so their transition time is
            # updated_at. Old completed jobs are excluded before joining notices.
            jobs = await store._many(db, """SELECT j.id FROM studio_jobs AS j INDEXED BY idx_studio_jobs_notice_terminal
                JOIN studio_projects p ON p.id=j.project_id AND p.owner=j.owner AND p.archived=0
                JOIN users u ON u.username=j.owner
                WHERE j.kind='i2v'
                    AND j.status IN ('downloaded','failed','rejected','filtered','expired','uncertain')
                    AND COALESCE(j.finished_at,j.updated_at)>=?
                    AND NOT EXISTS(SELECT 1 FROM studio_notices n WHERE n.job_id=j.id)
                    AND NOT EXISTS(SELECT 1 FROM studio_notice_historical h WHERE h.job_id=j.id)
                ORDER BY COALESCE(j.finished_at,j.updated_at),j.id""", (cutoff,))
            persisted = await store._many(db, """SELECT d.job_id AS id FROM studio_notice_pending d
                JOIN studio_jobs j ON j.id=d.job_id AND j.owner=d.username AND j.kind='i2v'
                JOIN studio_projects p ON p.id=j.project_id AND p.owner=j.owner AND p.archived=0
                JOIN users u ON u.username=j.owner
                WHERE NOT EXISTS(SELECT 1 FROM studio_notices n WHERE n.job_id=j.id)""")
        # Durable snapshots survive a restart even if the author linked the job
        # and its status is no longer terminal. Memory snapshots cover a failure
        # before save_studio_notice had an opportunity to persist its marker.
        for job_id in dict.fromkeys([job["id"] for job in jobs + persisted] + pending_ids):
            await write_job_notice(job_id)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.warning("studio code=notice_retry_error")
