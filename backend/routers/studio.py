"""仅向工作室作者开放的单镜首帧视频 API。"""
import asyncio
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, field_validator

from studio import brain_jobs, pricing, spend, storage, store
from studio.config import get_settings
from studio.gate import PRIVATE_HEADERS, studio_user


router = APIRouter(prefix="/studio", tags=["studio"])


def _public_asset(asset: dict) -> dict:
    return {key: value for key, value in asset.items() if key != "rel_path"}


def _public_job(job: dict) -> dict:
    # 成片只通过素材 ID 访问；供应商签名地址和并发令牌不离开后端。
    return {key: value for key, value in job.items() if key not in {"result_url", "run_token"}}


class ProjectBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)
    aspect: Literal["16:9", "9:16"] = "16:9"

    @field_validator("title")
    @classmethod
    def nonempty_title(cls, value):
        if not value.strip():
            raise ValueError("项目名称不能为空")
        return value.strip()


class QuoteBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    first_frame_asset_id: str = Field(min_length=1, max_length=100)
    prompt: str = Field(min_length=1, max_length=2000)
    provider: Literal["wan", "seedance"] = "wan"
    model: str | None = None
    resolution: str = "480P"
    duration: StrictInt = 5
    audio: StrictBool = True

    @field_validator("prompt")
    @classmethod
    def nonempty_prompt(cls, value):
        if not value.strip():
            raise ValueError("提示词不能为空")
        return value


class LinkTaskBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_id: str = Field(min_length=1, max_length=512)

    @field_validator("task_id")
    @classmethod
    def nonempty_task_id(cls, value):
        if not value.strip():
            raise ValueError("任务编号不能为空")
        return value.strip()


class ReleaseBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    not_charged: StrictBool
    note: str | None = Field(default=None, max_length=2000)


class BrainProjectBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    brain_provider: Literal["claude", "qwen", "deepseek"]


class BrainTrialBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=20000)
    tasks: list[Literal["read_through", "style_proposals", "bible_extract"]] = Field(min_length=1, max_length=3)
    providers: Literal["current", "all"] = "current"


@router.get("/access")
async def access(user: str = Depends(studio_user)):
    settings = get_settings()
    return {"enabled": True, "caps": {"daily_cny": settings.daily_cny,
            "max_quote_cny": settings.max_quote_cny,
            "brain_monthly_usd": settings.brain_monthly_usd,
            "brain_month_used_usd": float(await spend.brain_month_used(user)),
            "inflight": {"wan": settings.max_inflight_wan, "seedance": settings.max_inflight_seedance}},
            "today": await spend.today()}


@router.get("/brain/providers")
async def brain_providers(user: str = Depends(studio_user)):
    from studio.brain import provider_options
    return await provider_options(user)


@router.patch("/projects/{pid}")
async def patch_project(pid: str, body: BrainProjectBody, user: str = Depends(studio_user)):
    return await brain_jobs.patch_project(pid, user, body.brain_provider)


@router.post("/projects/{pid}/brain/quote")
async def quote_brain(pid: str, body: BrainTrialBody, user: str = Depends(studio_user)):
    return await brain_jobs.quote_trial(pid, user, body.text, body.tasks, body.providers)


@router.post("/projects/{pid}/brain/trial")
async def trial_brain(pid: str, body: BrainTrialBody, user: str = Depends(studio_user)):
    result = await brain_jobs.start_trial(pid, user, body.text, body.tasks, body.providers)
    return {**result, "jobs": [_public_job(job) for job in result["jobs"]]}


@router.get("/projects/{pid}/brain/groups/{group_id}")
async def brain_group(pid: str, group_id: str, user: str = Depends(studio_user)):
    result = await brain_jobs.group(pid, user, group_id)
    return {**result, "jobs": [_public_job(job) for job in result["jobs"]]}


@router.post("/projects", status_code=201)
async def create_project(body: ProjectBody, user: str = Depends(studio_user)):
    return await store.create_project(user, body.title, body.aspect)


@router.get("/projects")
async def projects(user: str = Depends(studio_user)):
    return await store.list_projects(user)


@router.get("/projects/{pid}")
async def project_detail(pid: str, user: str = Depends(studio_user)):
    try:
        return await store.get_project(pid, user)
    except HTTPException as exc:
        raise HTTPException(exc.status_code, exc.detail, headers=PRIVATE_HEADERS) from None


@router.get("/projects/{pid}/assets")
async def project_assets(pid: str, user: str = Depends(studio_user)):
    try:
        return [_public_asset(asset) for asset in await store.list_assets(pid, user)]
    except HTTPException as exc:
        raise HTTPException(exc.status_code, exc.detail, headers=PRIVATE_HEADERS) from None


@router.get("/notices")
async def notices(after: int = Query(default=0, ge=0), user: str = Depends(studio_user)):
    import database
    return await database.list_studio_notices_with_content(user, after)


@router.post("/projects/{pid}/assets", status_code=201)
async def upload_asset(pid: str, file: UploadFile, user: str = Depends(studio_user)):
    await store.get_project(pid, user)
    try:
        data = await file.read(storage.MAX_IMAGE_BYTES + 1)
    finally:
        await file.close()
    metadata = await asyncio.to_thread(storage.inspect_image, data)
    return _public_asset(await store.save_uploaded_asset(user, pid, data, metadata))


@router.post("/projects/{pid}/clips/quote")
async def quote_clip(pid: str, body: QuoteBody, user: str = Depends(studio_user)):
    await store.get_project(pid, user)
    asset = await store.get_asset(body.first_frame_asset_id, user)
    if asset["project_id"] != pid or asset["kind"] != "image":
        raise HTTPException(404, "Not Found", headers=PRIVATE_HEADERS)
    params = pricing.normalize_params(body.model_dump(exclude_none=True))
    if params["provider"] == "wan":
        await asyncio.to_thread(storage.validate_wan_image, asset)
    return await store.create_quote(user, pid, params)


@router.post("/quotes/{qid}/confirm")
async def confirm_quote(qid: str, user: str = Depends(studio_user)):
    return [_public_job(job) for job in await store.confirm_quote(qid, user)]


@router.get("/projects/{pid}/jobs")
async def project_jobs(pid: str, user: str = Depends(studio_user)):
    await store.get_project(pid, user)
    return [_public_job(job) for job in await store.list_jobs(pid, user)]


@router.get("/jobs/{jid}")
async def job_detail(jid: str, user: str = Depends(studio_user)):
    return _public_job(await store.get_job(jid, user))


@router.post("/jobs/{jid}/cancel")
async def cancel_job(jid: str, user: str = Depends(studio_user)):
    return _public_job(await store.cancel_job(jid, user))


@router.post("/jobs/{jid}/recheck")
async def recheck_job(jid: str, user: str = Depends(studio_user)):
    return _public_job(await store.recheck_job(jid, user))


@router.post("/jobs/{jid}/link-task")
async def link_task(jid: str, body: LinkTaskBody, user: str = Depends(studio_user)):
    return _public_job(await store.link_task(jid, user, body.task_id))


@router.post("/jobs/{jid}/release")
async def release_job(jid: str, body: ReleaseBody, user: str = Depends(studio_user)):
    return _public_job(await store.release_job(jid, user, body.not_charged, body.note))


@router.get("/assets/{aid}/file")
async def asset_file(aid: str, user: str = Depends(studio_user)):
    asset = await store.get_asset(aid, user)
    return storage.asset_file_response(asset)
