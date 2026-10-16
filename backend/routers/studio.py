"""仅向工作室作者开放的作品接入、导演拆解与视频 API。"""
import asyncio
from urllib.parse import quote
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, field_validator

from studio import brain_jobs, breakdown_plan, pricing, sources, spend, storage, store
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


class NovelProjectBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    book_id: str = Field(min_length=1, max_length=100)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    aspect: Literal["16:9", "9:16"] = "16:9"


class ExchangeProjectBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    exchange_id: str = Field(min_length=1, max_length=100)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    aspect: Literal["16:9", "9:16"] = "16:9"


class SourceSyncBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_no: StrictInt


class TextProjectBody(ProjectBody):
    kind: Literal["upload", "paste"]
    text: str | None = Field(default=None, max_length=2_000_000)


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
    brain_provider: Literal["claude", "qwen", "deepseek"] | None = None
    episode_seconds_min: StrictInt | None = Field(default=None, ge=60, le=900)
    episode_seconds_max: StrictInt | None = Field(default=None, ge=60, le=900)


class BreakdownQuoteBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_episodes: StrictInt | None = Field(default=None, ge=1, le=300)
    episode_seconds_min: StrictInt | None = Field(default=None, ge=60, le=900)
    episode_seconds_max: StrictInt | None = Field(default=None, ge=60, le=900)


class BreakdownStartBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    quote_id: str = Field(min_length=1, max_length=100)


class BreakdownRetryQuoteBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: Literal["claude", "qwen", "deepseek"]


class SynopsisBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    synopsis: dict


class BibleFields(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=200)
    aliases: list[str] | None = Field(default=None, max_length=100)
    role: str | None = Field(default=None, max_length=2000)
    description: str | None = Field(default=None, max_length=10000)
    appearance: str | None = Field(default=None, max_length=10000)
    needs_author: StrictBool | None = None

    @field_validator("name")
    @classmethod
    def nonempty_name(cls, value):
        if value is not None and not value.strip():
            raise ValueError("名字不能为空")
        return value.strip() if value is not None else value

    @field_validator("aliases")
    @classmethod
    def valid_aliases(cls, value):
        if value is not None and any(not item.strip() or len(item) > 200 for item in value):
            raise ValueError("别名须为 1–200 字")
        return [item.strip() for item in value] if value is not None else value


class BibleCreateBody(BibleFields):
    project_id: str = Field(min_length=1, max_length=100)
    kind: Literal["character", "location", "prop"]
    name: str = Field(min_length=1, max_length=200)


class BibleMergeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    keep_id: str = Field(min_length=1, max_length=100)
    merge_ids: list[str] = Field(min_length=1, max_length=100)


class EpisodeFields(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, min_length=1, max_length=500)
    change: str | None = Field(default=None, max_length=10000)
    hook: str | None = Field(default=None, max_length=10000)
    notes: str | None = Field(default=None, max_length=10000)
    target_min: StrictInt | None = Field(default=None, ge=60, le=900)
    target_max: StrictInt | None = Field(default=None, ge=60, le=900)


class EpisodeOperationBody(EpisodeFields):
    expected_revision: StrictInt = Field(ge=0)
    op: Literal["edit", "merge", "split", "move_boundary", "delete", "insert"]
    no: StrictInt | None = Field(default=None, ge=1)
    at_unit: StrictInt | None = Field(default=None, ge=1)
    delta: StrictInt | None = Field(default=None, ge=-1, le=1)
    unit_from: StrictInt | None = Field(default=None, ge=1)
    unit_to: StrictInt | None = Field(default=None, ge=1)
    fields: EpisodeFields | None = None

    @field_validator("delta")
    @classmethod
    def valid_delta(cls, value):
        if value is not None and value not in (-1, 1):
            raise ValueError("边界只能移动 -1 或 +1 场")
        return value


class PlanApproveBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: StrictInt = Field(ge=0)


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
    return await breakdown_plan.patch_project(pid, user, body.model_dump(exclude_unset=True, exclude_none=True))


@router.post("/projects/{pid}/breakdown/quote")
async def quote_breakdown(pid: str, body: BreakdownQuoteBody, user: str = Depends(studio_user)):
    from studio import breakdown
    return await breakdown.quote(pid, user, body.target_episodes,
                                 episode_seconds_min=body.episode_seconds_min,
                                 episode_seconds_max=body.episode_seconds_max)


@router.post("/projects/{pid}/breakdown/start")
async def start_breakdown(pid: str, body: BreakdownStartBody, user: str = Depends(studio_user)):
    from studio import breakdown
    return await breakdown.start(pid, user, body.quote_id)


@router.get("/projects/{pid}/breakdown")
async def current_breakdown(pid: str, user: str = Depends(studio_user)):
    from studio import breakdown
    return await breakdown.get_current(pid, user)


@router.patch("/projects/{pid}/breakdown")
@router.patch("/projects/{pid}/breakdown/synopsis")
async def patch_breakdown(pid: str, body: SynopsisBody, user: str = Depends(studio_user)):
    return await breakdown_plan.patch_synopsis(pid, user, body.synopsis)


@router.post("/breakdowns/{bid}/chunks/{cid}/retry/quote")
async def quote_retry_breakdown(bid: str, cid: str, body: BreakdownRetryQuoteBody, user: str = Depends(studio_user)):
    from studio import breakdown
    return await breakdown.retry_quote(bid, cid, user, body.provider)


@router.post("/breakdowns/{bid}/chunks/{cid}/retry")
async def retry_breakdown(bid: str, cid: str, body: BreakdownStartBody, user: str = Depends(studio_user)):
    from studio import breakdown
    return await breakdown.retry(bid, cid, user, body.quote_id)


@router.post("/breakdowns/{bid}/cancel")
async def cancel_breakdown(bid: str, user: str = Depends(studio_user)):
    from studio import breakdown
    return await breakdown.cancel(bid, user)


@router.get("/projects/{pid}/bible")
async def breakdown_bible(pid: str, kind: Literal["character", "location", "prop"] | None = None,
                          user: str = Depends(studio_user)):
    return await breakdown_plan.list_bible(pid, user, kind)


@router.patch("/bible/{item_id}")
async def patch_breakdown_bible(item_id: str, body: BibleFields, user: str = Depends(studio_user)):
    return await breakdown_plan.patch_bible(item_id, user, body.model_dump(exclude_unset=True, exclude_none=True))


@router.post("/bible/merge")
async def merge_breakdown_bible(body: BibleMergeBody, user: str = Depends(studio_user)):
    return await breakdown_plan.merge_bible(user, body.keep_id, body.merge_ids)


@router.post("/bible", status_code=201)
async def create_breakdown_bible(body: BibleCreateBody, user: str = Depends(studio_user)):
    return await breakdown_plan.create_bible(user, body.model_dump(exclude_none=True))


@router.delete("/bible/{item_id}")
async def archive_breakdown_bible(item_id: str, user: str = Depends(studio_user)):
    return await breakdown_plan.archive_bible(item_id, user)


@router.get("/projects/{pid}/episodes")
async def breakdown_episodes(pid: str, user: str = Depends(studio_user)):
    return await breakdown_plan.get_episodes(pid, user)


@router.post("/projects/{pid}/episodes/ops")
async def operate_breakdown_episodes(pid: str, body: EpisodeOperationBody, user: str = Depends(studio_user)):
    data = body.model_dump(exclude_unset=True)
    if body.fields is not None:
        data['fields'] = body.fields.model_dump(exclude_unset=True)
    return await breakdown_plan.operate_episodes(pid, user, data)


@router.post("/projects/{pid}/episodes/approve")
async def approve_breakdown_episodes(pid: str, body: PlanApproveBody, user: str = Depends(studio_user)):
    return await breakdown_plan.approve(pid, user, body.expected_revision)


@router.get("/projects/{pid}/breakdown/export")
async def export_breakdown(pid: str, user: str = Depends(studio_user)):
    title, markdown = await breakdown_plan.export_markdown(pid, user)
    return Response(markdown, media_type='text/markdown', headers={
        'Content-Disposition': "attachment; filename*=UTF-8''" + quote(title + '-拆解与分集.md', safe=''),
        'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff'})


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


@router.get("/sources/novels")
async def source_novels(user: str = Depends(studio_user)):
    return await sources.list_candidates(user)


@router.get("/sources/novels/search")
async def search_source_novels(q: str = Query(min_length=1, max_length=200), user: str = Depends(studio_user)):
    if not q.strip():
        raise HTTPException(422, "书名不能为空")
    return await sources.find_candidates(user, q)


@router.get("/sources/exchanges")
async def source_exchanges(user: str = Depends(studio_user)):
    return await sources.list_exchanges(user)


@router.post("/projects/from-novel", status_code=201)
async def project_from_novel(body: NovelProjectBody, user: str = Depends(studio_user)):
    return await sources.create_novel_project(user, body.book_id, body.title, body.aspect)


@router.post("/projects/from-text", status_code=201)
async def project_from_text(request: Request, user: str = Depends(studio_user)):
    # 先过作者门禁再解析表单；禁止未知字段，与 JSON 请求模型的 extra=forbid 一致。
    async with request.form(max_files=1, max_fields=5, max_part_size=8_000_000) as form:
        if set(form) - {"title", "aspect", "kind", "file", "text"} or any(len(form.getlist(key)) != 1 for key in form):
            raise HTTPException(422, "作品表单包含未知或重复字段")
        from pydantic import ValidationError
        try:
            body = TextProjectBody.model_validate({key: form[key] for key in ("title", "aspect", "kind", "text") if key in form})
        except ValidationError:
            raise HTTPException(422, "作品标题、画幅或来源格式无效") from None
        if body.kind == "upload":
            file = form.get("file")
            if not hasattr(file, "read") or body.text is not None:
                raise HTTPException(422, "请上传一个作品文件")
            raw = await file.read(sources.MAX_UPLOAD_BYTES + 1)
            filename = file.filename
        else:
            if "file" in form or body.text is None:
                raise HTTPException(422, "请粘贴作品文本")
            raw, filename = body.text, None
        return await sources.create_text_project(user, body.kind, body.title, raw, filename, body.aspect)


@router.post("/projects/from-exchange", status_code=201)
async def project_from_exchange(body: ExchangeProjectBody, user: str = Depends(studio_user)):
    return await sources.create_exchange_project(user, body.exchange_id, body.title, body.aspect)


@router.get("/projects/{pid}/source")
async def project_source(pid: str, user: str = Depends(studio_user)):
    return await sources.source_status(user, pid)


@router.post("/projects/{pid}/source/sync")
async def sync_project_source(pid: str, body: SourceSyncBody, user: str = Depends(studio_user)):
    return await sources.sync_source(user, pid, body.expected_no)


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
