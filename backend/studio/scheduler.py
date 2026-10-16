"""单进程后台调度；付费请求只允许从抢占成功的 queued 任务发出。"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import json
import logging
import math
from urllib.parse import urlsplit
import uuid
import weakref

from fastapi import HTTPException

from . import spend, storage, store
from .config import get_settings
from .providers import ProviderError, get_provider
from .providers.base import UNCERTAIN_MESSAGE


logger = logging.getLogger(__name__)
_LOOP_LOCKS: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()


def _tick_lock() -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    if loop not in _LOOP_LOCKS:
        _LOOP_LOCKS[loop] = asyncio.Lock()
    return _LOOP_LOCKS[loop]


def _json(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _params(job: dict) -> dict:
    params = job.get("params")
    return params if isinstance(params, dict) else json.loads(job["params_json"])


class StudioScheduler:
    def __init__(self, *, transport=None, download_transport=None, now=None):
        self.transport = transport
        self.download_transport = transport if download_transport is None else download_transport
        self.now = now or (lambda: datetime.now(timezone.utc))
        self._tasks: dict[str, asyncio.Task] = {}

    def _time(self) -> datetime:
        value = self.now()
        return store.parse_time(value) if isinstance(value, str) else value.astimezone(timezone.utc)

    def _provider(self, job: dict):
        return get_provider(job["provider"], transport=self.transport)

    @staticmethod
    def _age(job: dict, now: datetime) -> float:
        return max(0, (now - store.parse_time(job.get("submitted_at") or job["created_at"])).total_seconds())

    def _poll_updates(self, job: dict, now: datetime, timeout_minutes: float) -> dict:
        age = self._age(job, now)
        stopped = age > timeout_minutes * 60
        return {
            "needs_recheck": int(stopped), "poll_requested": 0,
            "next_poll_at": None if stopped else (now + timedelta(seconds=15 if age < 120 else 30)).isoformat(),
        }

    async def _guard(self, callback, job: dict, *args) -> None:
        try:
            await callback(job, *args)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            # 异常正文可能含签名 URL、提示词或密钥；只记录错误码、任务 ID 和异常类型。
            logger.warning("studio code=job_tick_error id=%s error=%s", job["id"], type(error).__name__)

    async def _dispatch(self, callback, jobs: list[dict], *args, wait: bool) -> None:
        tasks = []
        for job in jobs:
            if job["id"] in self._tasks:
                continue
            task = asyncio.create_task(self._guard(callback, job, *args), name=f"studio-{job['id']}")
            self._tasks[job["id"]] = task
            task.add_done_callback(lambda done, job_id=job["id"]: self._tasks.pop(job_id, None))
            tasks.append(task)
        if wait:
            await asyncio.gather(*tasks)

    async def close(self) -> None:
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def tick(self, *, wait: bool = True) -> None:
        """测试默认等待本 tick 的工作；生产派发后立即返回，保持两秒节奏。"""
        if not get_settings().enabled:
            return
        async with _tick_lock():
            settings = get_settings()
            if not settings.enabled:
                return
            now = self._time()
            jobs = await store.list_due_jobs(now)
            await self._dispatch(self._poll, jobs, now, settings.poll_timeout_min, wait=wait)
            downloads = await store.list_pending_downloads(now)
            await self._dispatch(self._download, downloads, now, wait=wait)
            claimed = []
            for provider in ("wan", "seedance"):
                # 在途计数和抢占同属一个数据库事务；不同供应商各用自己的上限。
                for _ in range(settings.inflight_limit(provider)):
                    if not get_settings().enabled:
                        break
                    job = await store.claim_next_job(provider, settings.inflight_limit(provider), uuid.uuid4().hex)
                    if job is None:
                        break
                    claimed.append(job)
            await self._dispatch(self._submit, claimed, now, wait=wait)

    async def _submit(self, job: dict, now: datetime) -> None:
        token = job["run_token"]
        result = None
        try:
            params = _params(job)
            try:
                asset = await store.get_asset(params["first_frame_asset_id"], job["owner"])
            except HTTPException:
                raise ProviderError("failed", "missing_first_frame", "首帧素材不可用，没有提交生成请求") from None
            if not asset or asset["project_id"] != job["project_id"] or asset["kind"] != "image":
                raise ProviderError("failed", "missing_first_frame", "首帧素材不可用，没有提交生成请求")
            try:
                path = storage.resolve_asset_path(asset)
            except Exception:
                raise ProviderError("failed", "missing_first_frame", "首帧文件不可用，没有提交生成请求") from None
            result = await self._provider(job).submit(params, path)
            await store.cas_job(job["id"], "submitting", {
                "status": "submitted", "task_id": result.task_id, "submitted_at": now.isoformat(),
                "next_poll_at": (now + timedelta(seconds=15)).isoformat(), "usage_json": _json(result.usage),
                "error_code": None, "error_message": None, "needs_recheck": 0,
            }, run_token=token)
        except asyncio.CancelledError:
            # 即使取消恰好落在 POST 之前，也从严保留预留，不允许自动重发。
            await asyncio.shield(store.cas_job(job["id"], "submitting", {
                "status": "uncertain", "error_code": "submission_interrupted",
                "error_message": UNCERTAIN_MESSAGE, "next_poll_at": None, "needs_recheck": 1,
                **({"task_id": result.task_id} if result is not None else {}),
            }, run_token=token))
            raise
        except ProviderError as exc:
            updates = {"error_code": exc.code, "error_message": exc.message,
                       "next_poll_at": None, "needs_recheck": int(exc.status == "uncertain")}
            if exc.status in {"rejected", "failed"}:
                await spend.settle_job(job["id"], "submitting", exc.status, usage={}, run_token=token, **updates)
            else:
                await store.cas_job(job["id"], "submitting", {"status": "uncertain", **updates}, run_token=token)
        except Exception:
            await store.cas_job(job["id"], "submitting", {
                "status": "uncertain", "error_code": "submission_error", "error_message": UNCERTAIN_MESSAGE,
                "next_poll_at": None, "needs_recheck": 1,
                **({"task_id": result.task_id} if result is not None else {}),
            }, run_token=token)

    async def _poll(self, job: dict, now: datetime, timeout_minutes: float) -> None:
        following = self._poll_updates(job, now, timeout_minutes)
        if following["needs_recheck"] and not job.get("poll_requested"):
            await store.cas_job(job["id"], job["status"], {
                **following, "error_code": "poll_timeout", "error_message": "自动轮询已超时，请手动核对任务状态",
            }, run_token=job.get("run_token"))
            return
        token = uuid.uuid4().hex
        if not await store.cas_job(job["id"], job["status"], {
            "run_token": token, **following,
        }, run_token=job.get("run_token")):
            return
        try:
            result = await self._provider(job).poll(job["task_id"])
        except ProviderError as exc:
            await store.cas_job(job["id"], job["status"], {
                **following, "error_code": exc.code, "error_message": exc.message,
            }, run_token=token)
            return
        updates = {"usage_json": _json(result.usage), "error_code": result.error_code,
                   "error_message": result.error_message, **following}
        if result.status in {"failed", "filtered", "expired"}:
            await spend.settle_job(job["id"], job["status"], result.status, usage=result.usage,
                                   run_token=token, error_code=result.error_code, error_message=result.error_message,
                                   next_poll_at=None, poll_requested=0, needs_recheck=0)
        elif result.status == "succeeded":
            await store.cas_job(job["id"], job["status"], {
                **updates, "status": "succeeded", "result_url": result.result_url,
                "result_host": urlsplit(result.result_url).hostname if result.result_url else None,
                "next_poll_at": now.isoformat(), "needs_recheck": 0,
            }, run_token=token)
        else:
            await store.cas_job(job["id"], job["status"], {**updates, "status": "running"}, run_token=token)

    async def _download(self, job: dict, now: datetime) -> None:
        later = (now + timedelta(seconds=30)).isoformat()
        url = job.get("result_url")
        following = self._poll_updates(job, now, get_settings().poll_timeout_min) if not url else {
            "next_poll_at": later, "poll_requested": 0,
        }
        if not url and following["needs_recheck"] and not job.get("poll_requested"):
            await store.cas_job(job["id"], "succeeded", {
                **following, "error_code": "poll_timeout", "error_message": "自动轮询已超时，请手动核对任务状态",
            }, run_token=job.get("run_token"))
            return
        token = uuid.uuid4().hex
        if not await store.cas_job(job["id"], "succeeded", {
            "run_token": token, **following,
        }, run_token=job.get("run_token")):
            return
        if not url:
            # 重启留下的 succeeded 任务可能还没有保存地址；仍然只查 GET。
            try:
                result = await self._provider(job).poll(job["task_id"])
            except ProviderError as exc:
                await store.cas_job(job["id"], "succeeded", {
                    "error_code": exc.code, "error_message": exc.message, **following,
                }, run_token=token)
                return
            if result.status in {"failed", "filtered", "expired"}:
                await spend.settle_job(job["id"], "succeeded", result.status, usage=result.usage,
                                       run_token=token, error_code=result.error_code, error_message=result.error_message)
                return
            url = result.result_url
            if not url:
                await store.cas_job(job["id"], "succeeded", {
                    **following,
                    "error_code": "poll_timeout" if following["needs_recheck"] else "missing_result_url",
                    "error_message": "自动轮询已超时，请手动核对任务状态" if following["needs_recheck"] else "上游尚未返回成片地址，稍后重查",
                }, run_token=token)
                return
            if not await store.cas_job(job["id"], "succeeded", {
                "result_url": url, "result_host": urlsplit(url).hostname, "usage_json": _json(result.usage),
                "needs_recheck": 0,
            }, run_token=token):
                return
        try:
            for attempt in range(3):
                try:
                    media = await storage.download_video(url, job["project_id"], job["id"], transport=self.download_transport)
                    break
                except storage.DownloadError as exc:
                    if not exc.retryable or attempt == 2:
                        raise
            duration = float(media["duration_s"])
            requested = _params(job)["duration"]
            minimum = (2 if job["provider"] == "wan" else 4) if requested == -1 else requested
            if not math.isfinite(duration) or duration < minimum - 0.2:
                await self._discard_media(media)
                await spend.settle_job(job["id"], "succeeded", "failed", run_token=token,
                                       error_code="short_output", error_message="成片时长短于请求时长", next_poll_at=None)
                return
            if not await store.finish_download(job["id"], media, run_token=token):
                await self._discard_media(media)
        except storage.DownloadError as exc:
            if exc.expired or not exc.retryable:
                await spend.settle_job(job["id"], "succeeded", "expired" if exc.expired else "failed", run_token=token,
                                       error_code=exc.code, error_message=exc.message, next_poll_at=None)
            else:
                await store.cas_job(job["id"], "succeeded", {
                    "error_code": exc.code, "error_message": exc.message, "next_poll_at": later,
                }, run_token=token)

    @staticmethod
    async def _discard_media(media: dict) -> None:
        try:
            await asyncio.to_thread(storage.discard_file, media["rel_path"])
        except Exception:
            logger.warning("studio code=result_cleanup_error")


async def scheduler_tick(*, transport=None, download_transport=None, now=None) -> None:
    await StudioScheduler(transport=transport, download_transport=download_transport, now=now).tick()


async def run_scheduler(*, transport=None, download_transport=None) -> None:
    scheduler = StudioScheduler(transport=transport, download_transport=download_transport)
    try:
        while True:
            started = asyncio.get_running_loop().time()
            try:
                await scheduler.tick(wait=False)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning("studio code=scheduler_tick_error")
            await asyncio.sleep(max(0, 2 - (asyncio.get_running_loop().time() - started)))
    finally:
        # 这些子任务与调度循环共生；应用取消循环时先处理提交的不确定状态，再退出。
        await scheduler.close()
