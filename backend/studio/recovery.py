"""启动恢复只调整数据库状态，绝不提交或查询上游。"""
import logging

from . import store
from .providers.base import UNCERTAIN_MESSAGE

logger = logging.getLogger(__name__)


async def _recover_kb_trials() -> None:
    """续跑已确认但还没跑完的试拆；归档项目只清占位，不调度付费调用。"""
    from . import kb_trial
    from .config import get_settings

    async with store.connection() as db:
        for table in ("studio_quotes", "studio_projects"):
            async with db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                                  (table,)) as cursor:
                if await cursor.fetchone() is None:
                    return
        rows = await store._many(db, """SELECT q.id,q.owner,q.items_json,q.project_id,
                p.id AS project_exists,p.archived AS project_archived
            FROM studio_quotes q
            LEFT JOIN studio_projects p ON p.id=q.project_id AND p.owner=q.owner
            WHERE q.status='confirmed' AND EXISTS (
                SELECT 1 FROM studio_jobs j WHERE j.quote_id=q.id
                AND j.kind IN ('kb_shot','kb_review') AND j.status='queued')
            ORDER BY q.created_at,q.id""")
    enabled = get_settings().enabled
    for row in rows:
        payload = row.get("items")
        if not isinstance(payload, dict) or payload.get("kind") != "kb_trial":
            continue
        if row.get("project_exists") is None or row.get("project_archived"):
            await kb_trial._cancel_quote_placeholders(row["id"])
            continue
        if not enabled:
            continue
        kb_trial._schedule(row["id"])


async def recover_studio_jobs() -> None:
    # 部分既有启动测试会替换 init_db；尚未建表时和小说恢复保持一致。
    async with store.connection() as db:
        async with db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='studio_jobs'") as cursor:
            if await cursor.fetchone() is None:
                return
    now = store.utcnow()
    from . import notices
    await notices.initialize_notice_cutoff()
    async with store.connection() as db:
        # 恢复只需要导演任务的状态，不读取、解析其大文本素材与输出。
        async with db.execute('''SELECT id,kind,task,status,run_token FROM studio_jobs
            WHERE kind='brain' AND status IN ('submitting','submitted','running','succeeded')
            ORDER BY created_at,id''') as cursor:
            jobs = [dict(row) for row in await cursor.fetchall()]
        jobs.extend(await store._many(db, '''SELECT * FROM studio_jobs WHERE kind!='brain'
            AND status IN ('submitting','submitted','running','succeeded') ORDER BY created_at,id'''))
    for job in jobs:
        if job.get("kind") == "brain":
            if job["status"] in {"submitting", "running"}:
                try:
                    await store.cas_job(job["id"], job["status"], {
                        "status": "uncertain", "error_code": "restart_during_submission",
                        "error_message": "服务重启时请求可能已发出；" + UNCERTAIN_MESSAGE,
                    }, run_token=job.get("run_token"))
                except Exception as exc:
                    if job.get('task') not in {'novel_complete', 'text_map', 'synopsis', 'episode_plan'}:
                        raise
                    # 一个损坏的拆解任务不能阻断其它任务或应用启动；不记录素材。
                    logger.error('Could not recover breakdown job %s (%s)', job['id'], type(exc).__name__)
            continue
        if job.get("kind") in store.CASTING_JOB_KINDS:
            # 定妆出图与声线试听：与导演任务相同，running / submitting 转 uncertain
            # （保留预留，只能手动释放）；queued 交给调度器补发，绝不重发。
            if job["status"] in {"submitting", "running"}:
                await store.cas_job(job["id"], job["status"], {
                    "status": "uncertain", "error_code": "restart_during_submission",
                    "error_message": "服务重启时请求可能已发出；" + UNCERTAIN_MESSAGE,
                    "needs_recheck": 1, "next_poll_at": None,
                })
            continue
        if job["status"] == "submitting":
            updates = {
                "status": "uncertain", "error_code": "restart_during_submission",
                "error_message": "服务重启时请求可能已发出；" + UNCERTAIN_MESSAGE,
                "needs_recheck": 1, "next_poll_at": None, "poll_requested": 0,
            }
        elif job["status"] == "succeeded":
            if job.get("result_asset_id"):
                continue
            updates = {"next_poll_at": now}
        else:
            # 已超时暂停的任务仍须作者手动 recheck；重启不绕过这一限制。
            updates = {"next_poll_at": now} if not job.get("needs_recheck") else {}
        if updates:
            await store.cas_job(job["id"], job["status"], updates, run_token=job.get("run_token"))

    from .breakdown import recover
    await recover()
    await _recover_kb_trials()
