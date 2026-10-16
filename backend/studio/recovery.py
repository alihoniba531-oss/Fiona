"""启动恢复只调整数据库状态，绝不提交或查询上游。"""
from . import store
from .providers.base import UNCERTAIN_MESSAGE


async def recover_studio_jobs() -> None:
    # 部分既有启动测试会替换 init_db；尚未建表时和小说恢复保持一致。
    async with store.connection() as db:
        async with db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='studio_jobs'") as cursor:
            if await cursor.fetchone() is None:
                return
    now = store.utcnow()
    for job in await store.list_jobs_by_status(("submitting", "submitted", "running", "succeeded")):
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
