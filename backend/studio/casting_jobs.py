"""定妆出图（image）与声线试听（tts）任务的后台执行、预留与结算。

付费安全（继承 WO1/WO3a 规则）：
- 付费调用只发一次，绝不自动重试；超时、断连、5xx、2xx 但解析失败 → ``uncertain``
  （保留预留，只能由作者手动释放）；明确 4xx / 429 → ``rejected``（释放预留）；
  内容审核拒绝 → ``failed``（按 0 结算）。
- ``running`` / ``submitting`` 的任务在重启后转 ``uncertain``；``queued`` 由调度器补发，
  绝不重发（见 ``recovery.py``）。
- 参考图只在执行期合并一次：已选定版本（derived 说明）排第一，再跟显式参考图，
  重复的同一 asset id 只保留一次（保留 derived 那张）；合并后 > 4 张即预检失败。

块 B / 块 C 的函数一律延迟导入（在函数体内 import），并通过本模块的薄封装调用，
这样它们尚不存在时本模块仍可导入，测试里只需 monkeypatch 这些封装。
"""
from __future__ import annotations

import asyncio
from decimal import Decimal
import hashlib
import json
import os
import re
import uuid
import weakref

from . import pricing, spend, store
from utils.background_tasks import create_background_task


UNCERTAIN_MESSAGE = "请求可能已发出，正在等待作者核对或手动释放"
SHEET_SIZE = "2560x1440"
INFLIGHT_IMAGE_ENV = "FIONA_STUDIO_MAX_INFLIGHT_IMAGE"
INFLIGHT_TTS_ENV = "FIONA_STUDIO_MAX_INFLIGHT_TTS"
DEFAULT_INFLIGHT_IMAGE = 3
DEFAULT_INFLIGHT_TTS = 2

_ACTIVE: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()
_SEMAPHORES: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()
_LIMIT_WARNED: set[str] = set()

# 允许的定妆任务状态转换；uncertain 不是终态，保留预留等作者处理。
_ALLOWED_TRANSITIONS = {
    "queued": {"running", "cancelled", "rejected"},
    "submitting": {"uncertain", "rejected", "failed"},
    "submitted": {"uncertain"},
    "running": {"succeeded", "failed", "rejected", "uncertain"},
    "uncertain": {"released"},
}
_PERMITTED_FIELDS = {
    "status", "error_code", "error_message", "run_token", "result_asset_id", "usage_json",
    "reserved_amount", "reserved_cny", "actual_amount", "actual_cny",
    "finished_at", "updated_at", "needs_recheck", "next_poll_at",
}
_SETTLING = {"succeeded", "failed", "rejected", "released", "cancelled"}


class PreflightError(Exception):
    """付费请求发出之前的失败；一律按 rejected 释放预留。"""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


# ---------------------------------------------------------------------------
# 块 B / 块 C 的薄封装（延迟导入，测试里 monkeypatch 这些名字）
# ---------------------------------------------------------------------------

async def _generate_sheet(prompt: str, *, size: str, reference_images: list):
    from .providers.image_seedream import generate_sheet
    return await generate_sheet(prompt, size=size, reference_images=reference_images)


async def _synthesize_cosy(text: str, *, voice: str, rate: float, pitch: float):
    from .providers.tts_cosy import synthesize_cosy
    return await synthesize_cosy(text, voice=voice, rate=rate, pitch=pitch)


async def _synthesize_edge(text: str, *, voice: str, rate: str, pitch: str):
    from .providers.tts_edge import synthesize_edge
    return await synthesize_edge(text, voice=voice, rate=rate, pitch=pitch)


async def _process_voice(raw: bytes, *, input_format: str, fx, target_lufs: float):
    from .audio import process_voice
    return await process_voice(raw, input_format=input_format, fx=fx, target_lufs=target_lufs, true_peak=-1.5)


def _build_sheet_prompt(**kwargs) -> str:
    from .casting_prompts import build_sheet_prompt
    return build_sheet_prompt(**kwargs)


def _reference_note(kind: str, derived: bool) -> str:
    from .casting_prompts import reference_note
    return reference_note(kind, derived)


def fx_levels() -> dict:
    """``{"robot": ["A", ...], ...}``；不含滤镜字符串。"""
    from .audio import FX_PRESETS
    return {kind: sorted(levels) for kind, levels in FX_PRESETS.items()}


def valid_fx(fx) -> bool:
    if fx is None:
        return True
    from .audio import parse_fx
    try:
        parse_fx(fx)
    except (ValueError, TypeError):
        return False
    return True


def lookup_voice(engine: str, voice: str) -> dict | None:
    from .voices import lookup_voice as _lookup
    return _lookup(engine, voice)


def voice_catalog() -> list:
    """块 B 的音色目录；延迟导入，测试里 monkeypatch 本函数。"""
    from .voices import VOICE_CATALOG
    return VOICE_CATALOG


def style_inputs(**kwargs) -> dict:
    """块 C 的风格输入组装；延迟导入，测试里 monkeypatch 本函数。"""
    from .casting_prompts import style_inputs as _build
    return _build(**kwargs)


async def _save_image(project_id: str, data: bytes, metadata: dict) -> dict:
    from . import storage
    return await asyncio.to_thread(storage.save_image, project_id, data, metadata)


async def _save_audio(project_id: str, data: bytes) -> dict:
    from . import storage
    return await asyncio.to_thread(storage.save_audio, project_id, data)


async def _inspect_image(data: bytes) -> dict:
    from . import storage
    return await asyncio.to_thread(storage.inspect_image, data)


async def _discard_file(rel_path: str) -> None:
    from . import storage
    try:
        await asyncio.to_thread(storage.discard_file, rel_path)
    except Exception:
        pass


async def _reference_bytes(asset: dict) -> bytes:
    """读取参考图字节并把长边缩到 ≤1536，统一输出 PNG；全程在线程里做。"""
    from . import storage
    return await asyncio.to_thread(_reference_bytes_sync, storage.resolve_asset_path(asset))


def _reference_errors() -> tuple:
    """参考图查库 / 读取 / 解码可能抛出的异常；解码口径与 ``storage.inspect_image`` 一致。"""
    from fastapi import HTTPException
    from PIL import Image, UnidentifiedImageError
    return (HTTPException, UnidentifiedImageError, OSError, ValueError, SyntaxError,
            Image.DecompressionBombError, Image.DecompressionBombWarning)


def _reference_bytes_sync(path: str) -> bytes:
    import io
    from PIL import Image
    with Image.open(path) as image:
        image.load()
        if max(image.size) > 1536:
            scale = 1536 / max(image.size)
            image = image.resize((max(1, round(image.width * scale)), max(1, round(image.height * scale))))
        buffer = io.BytesIO()
        # 上游一律按 data:image/png 标注参考图，所以任何输入都输出 PNG 字节。
        image.convert("RGBA" if image.mode in {"RGBA", "LA", "P"} else "RGB").save(buffer, "PNG")
        return buffer.getvalue()


# ---------------------------------------------------------------------------
# 在途上限（每个 media_provider 一个 Semaphore）
# ---------------------------------------------------------------------------

def _limit(env: str, default: int) -> int:
    raw = os.getenv(env)
    if raw is None:
        return default
    if re.fullmatch(r"[0-9]+", raw):
        value = int(raw)
        if 1 <= value <= 10:
            return value
    if env not in _LIMIT_WARNED:
        print(f"[studio] {env} 无效，使用默认值")
        _LIMIT_WARNED.add(env)
    return default


def inflight_limit(media_provider: str) -> int:
    if media_provider == "seedream":
        return _limit(INFLIGHT_IMAGE_ENV, DEFAULT_INFLIGHT_IMAGE)
    return _limit(INFLIGHT_TTS_ENV, DEFAULT_INFLIGHT_TTS)


def _semaphore(media_provider: str):
    loop = asyncio.get_running_loop()
    table = _SEMAPHORES.setdefault(loop, {})
    if media_provider not in table:
        table[media_provider] = asyncio.Semaphore(inflight_limit(media_provider))
    return table[media_provider]


# ---------------------------------------------------------------------------
# 状态转换与结算
# ---------------------------------------------------------------------------

async def transition(db, job, expected_status, updates: dict, *, run_token=None) -> bool:
    expected = {expected_status} if isinstance(expected_status, str) else set(expected_status)
    if job["status"] not in expected or (run_token is not None and job.get("run_token") != run_token):
        return False
    if await store._one(db, "SELECT id FROM studio_projects WHERE id=? AND owner=? AND archived=0",
                        (job["project_id"], job["owner"])) is None:
        return False
    updates = dict(updates)
    if set(updates) - _PERMITTED_FIELDS:
        raise ValueError("未知定妆任务更新字段")
    target = updates.get("status", job["status"])
    if target != job["status"] and target not in _ALLOWED_TRANSITIONS.get(job["status"], set()):
        raise ValueError("不允许的定妆任务状态转换")
    if target in _SETTLING:
        reserved = pricing.money(job.get("reserved_amount") or 0)
        actual = reserved if target == "succeeded" else pricing.money(0)
        updates["actual_amount"] = str(pricing.money(actual))
        updates["actual_cny"] = str(pricing.money(actual))
        # 声线（edge-tts）预留为 0，成功也按 0 结算。
        updates["reserved_amount"] = "0"
        updates["reserved_cny"] = "0"
        updates.setdefault("finished_at", store.utcnow())
        if target != "succeeded":
            updates.setdefault("needs_recheck", 0)
            updates.setdefault("next_poll_at", None)
    if isinstance(updates.get("usage_json"), (dict, list)):
        updates["usage_json"] = store._json(updates["usage_json"])
    updates["updated_at"] = store.utcnow()
    assignments = ",".join(f"{key}=?" for key in updates)
    sql = f"UPDATE studio_jobs SET {assignments} WHERE id=? AND status=?"
    values = [*updates.values(), job["id"], job["status"]]
    if run_token is not None:
        sql += " AND run_token=?"
        values.append(run_token)
    async with db.execute(sql, values) as cursor:
        return cursor.rowcount == 1


# ---------------------------------------------------------------------------
# 建任务（预留）与派发
# ---------------------------------------------------------------------------

async def _synthetic_quote(db, project_id: str, owner: str, tag: str) -> str:
    qid, stamp = str(uuid.uuid4()), store.utcnow()
    await db.execute(
        """INSERT INTO studio_quotes(id,project_id,owner,items_json,total_min_cny,total_max_cny,
           params_hash,status,created_at,expires_at,confirmed_at) VALUES(?,?,?,'[]','0','0',?,'confirmed',?,?,?)""",
        (qid, project_id, owner, tag, stamp, stamp, stamp))
    return qid


async def prepare_jobs(db, project: dict, owner: str, *, kind: str, media_provider: str | None,
                       quote_id: str | None, entries: list[dict]) -> list[dict]:
    """在调用方已开启的写事务里为每一张图 / 每个声线变体建一条任务并预留。

    ``entries`` 形如 ``[{"item_id":..., "media_provider":..., "params": {...}, "reserved_amount": Decimal}]``；
    ``entry["media_provider"]`` 优先于调用级的 ``media_provider``；``quote_id`` 为空时自动建一张
    合成报价以满足外键与唯一约束。这里不新开事务、不派发，提交与排程由调用方决定
    （``create_jobs`` 或需要「确认报价 + 建任务」同事务的调用方）。
    """
    if kind not in store.CASTING_JOB_KINDS:
        raise ValueError("未知的定妆任务类型")
    if not entries:
        return []
    stamp = store.utcnow()
    jobs = []
    await store._project(db, project["id"], owner)
    total = sum((pricing.money(entry.get("reserved_amount") or 0) for entry in entries), Decimal(0))
    await spend.check_reservation(db, total, now=stamp)
    qid = quote_id or await _synthetic_quote(db, project["id"], owner, f"casting-{kind}")
    for entry in entries:
        job_id = str(uuid.uuid4())
        amount = str(pricing.money(entry.get("reserved_amount") or 0))
        provider = entry.get("media_provider") or media_provider
        fields = {
            "id": job_id, "project_id": project["id"], "owner": owner, "kind": kind,
            "provider": "wan", "media_provider": provider,
            "item_id": entry.get("item_id"), "model": provider or "media",
            "params_json": store._json(entry.get("params") or {}),
            "fingerprint": hashlib.sha256(job_id.encode()).hexdigest(),
            "quote_id": qid, "quote_item_id": job_id, "status": "queued",
            "currency": "CNY", "reserved_amount": amount, "reserved_cny": amount,
            "est_min_cny": amount, "est_max_cny": amount,
            "created_at": stamp, "updated_at": stamp,
            "confirmed_day": spend.shanghai_day(stamp),
        }
        columns = ",".join(fields)
        await db.execute(f"INSERT INTO studio_jobs({columns}) VALUES({','.join('?' for _ in fields)})",
                         tuple(fields.values()))
        jobs.append(await store._get_job(db, job_id, owner))
    return jobs


def schedule_jobs(jobs: list[dict]) -> None:
    """把已建好的任务逐个排程；必须在写事务提交之后调用。"""
    for job in jobs:
        _schedule(job["id"])


async def create_jobs(project: dict, owner: str, *, kind: str, media_provider: str | None,
                      quote_id: str | None, entries: list[dict]) -> list[dict]:
    """一个写事务里建任务并预留，提交之后再派发；签名与外部行为保持不变。"""
    if kind not in store.CASTING_JOB_KINDS:
        raise ValueError("未知的定妆任务类型")
    if not entries:
        return []
    async with store.connection(transaction=True) as db:
        jobs = await prepare_jobs(db, project, owner, kind=kind, media_provider=media_provider,
                                  quote_id=quote_id, entries=entries)
    schedule_jobs(jobs)
    return jobs


def _schedule(job_id: str) -> None:
    loop = asyncio.get_running_loop()
    active = _ACTIVE.setdefault(loop, {})
    if job_id in active:
        return
    task = create_background_task(execute(job_id), label=f"studio-casting-{job_id}")
    active[job_id] = task
    task.add_done_callback(lambda done: active.pop(job_id, None))


async def dispatch_queued() -> list[str]:
    """调度器 tick 补发遗留的 queued 定妆任务；只排程，不在这里发请求。"""
    async with store.connection() as db:
        rows = await store._many(db, """SELECT id FROM studio_jobs
            WHERE kind IN ('image','tts') AND status='queued' ORDER BY created_at,id""")
    for row in rows:
        _schedule(row["id"])
    return [row["id"] for row in rows]


# ---------------------------------------------------------------------------
# 执行
# ---------------------------------------------------------------------------

async def execute(job_id: str) -> bool:
    """执行一条 queued 的定妆任务；可被测试直接 await。"""
    job = await store.get_job(job_id)
    if job is None or job.get("kind") not in store.CASTING_JOB_KINDS or job["status"] != "queued":
        return False
    async with _semaphore(job.get("media_provider")):
        token = uuid.uuid4().hex
        # cas_job 自带 queued 条件，不再多余地预读一次。
        if not await store.cas_job(job_id, "queued", {"status": "running", "run_token": token}):
            return False
        try:
            # 置为 running 之后的任何异常都必须把任务结算掉，不能停在 running。
            job = await store.get_job(job_id)
            if job is None:
                return await _fail(job_id, token, "uncertain", "job_missing", UNCERTAIN_MESSAGE)
            if job["kind"] == "image":
                return await _run_image(job, token)
            return await _run_tts(job, token)
        except asyncio.CancelledError:
            await asyncio.shield(_fail(job_id, token, "uncertain", "submission_interrupted", UNCERTAIN_MESSAGE))
            raise
        except BaseException as exc:  # noqa: BLE001 - 任何未归类异常都按不确定保留预留
            status, code, message = _classify(exc)
            return await _fail(job_id, token, status, code, message)


def _classify(exc: BaseException) -> tuple[str, str, str]:
    from .providers.media_errors import MediaCallError
    if isinstance(exc, MediaCallError):
        return exc.status, exc.code, exc.message
    if isinstance(exc, PreflightError):
        return "rejected", exc.code, exc.message
    return "uncertain", "media_error", UNCERTAIN_MESSAGE


async def _fail(job_id: str, token: str, status: str, code: str, message: str) -> bool:
    """把 running 的任务结算到 status / code；只按 job_id 定位，读不到行也能结算。"""
    updates = {"error_code": code, "error_message": message}
    if status == "uncertain":
        updates["needs_recheck"] = 1
    return await store.cas_job(job_id, "running", {"status": status, **updates}, run_token=token)


async def _run_image(job: dict, token: str) -> bool:
    params = job.get("params") or {}
    item_id = params.get("item_id")
    if not item_id:
        raise PreflightError("missing_item", "定妆任务缺少条目")
    async with store.connection() as db:
        item = await store._one(db, "SELECT * FROM studio_items WHERE id=? AND owner=?", (item_id, job["owner"]))
        if item is None:
            raise PreflightError("item_unavailable", "定妆条目不存在")
        bible = await store._one(db, "SELECT * FROM studio_bible WHERE id=? AND project_id=? AND owner=?",
                                 (item["bible_id"], job["project_id"], job["owner"]))
        project = await store._one(db, "SELECT * FROM studio_projects WHERE id=? AND owner=?",
                                   (job["project_id"], job["owner"]))
    if project is None:
        raise PreflightError("project_unavailable", "项目不存在")
    spec = item.get("spec_json") or {}
    if isinstance(spec, str):
        spec = json.loads(spec or "{}")
    style = project.get("style_json") or {}
    if isinstance(style, str):
        style = json.loads(style or "{}")
    reference_ids, notes = await _reference_plan(job, item, params)
    images = []
    for asset_id in reference_ids:
        try:
            asset = await store.get_asset(asset_id, job["owner"])
        except _reference_errors() as exc:
            # 已归档、不存在或项目不可用的资产一律在付费请求之前判为预检失败。
            raise PreflightError("reference_unavailable", "参考图不可用") from exc
        if asset["project_id"] != job["project_id"] or asset["kind"] != "image":
            raise PreflightError("reference_unavailable", "参考图不可用")
        try:
            images.append(await _reference_bytes(asset))
        except _reference_errors() as exc:
            raise PreflightError("reference_unreadable", "参考图文件缺失或无法解码") from exc
    prompt = _build_sheet_prompt(
        kind=item["kind"], name=item["name"],
        appearance=(bible or {}).get("appearance") or "",
        description=(bible or {}).get("description") or "",
        locked_features=spec.get("locked_features") or "",
        style=style, extra_prompt=params.get("extra_prompt") or "",
        reference_notes=notes,
    )
    result = await _generate_sheet(prompt, size=SHEET_SIZE, reference_images=images)
    meta = {"prompt": prompt, "reference_asset_ids": reference_ids, "size": SHEET_SIZE,
            "provider": job.get("media_provider"), "model": getattr(result, "model", None)}
    asset = await _commit_image(job, result.png, meta)
    await store.cas_job(job["id"], "running", {"status": "succeeded", "result_asset_id": asset["id"]},
                        run_token=token)
    return True


async def _reference_plan(job: dict, item: dict, params: dict) -> tuple[list[str], list[str]]:
    """执行期唯一一次合并：已选定版本（derived）排第一，再跟显式参考图并去重。"""
    reference_ids: list[str] = []
    derived: list[bool] = []
    if params.get("derive_from_approved"):
        approved = item.get("approved_asset_id")
        if not approved:
            raise PreflightError("missing_approved", "条目缺少已选定版本，无法派生参考图")
        reference_ids.append(approved)
        derived.append(True)
    for asset_id in params.get("reference_asset_ids") or []:
        # 报价里可能已经含 approved；同一 asset id 只保留第一次出现的那张。
        if asset_id in reference_ids:
            continue
        reference_ids.append(asset_id)
        derived.append(False)
    if len(reference_ids) > 4:
        raise PreflightError("too_many_references", "参考图最多 4 张")
    notes = [_reference_note(item["kind"], flag) for flag in derived]
    return reference_ids, notes


async def _run_tts(job: dict, token: str) -> bool:
    params = job.get("params") or {}
    spec = params.get("spec") or {}
    text = params.get("text") or ""
    if not spec or not text:
        raise PreflightError("missing_spec", "试听任务缺少声线方案或台词")
    engine = spec.get("engine")
    if engine == "cosyvoice":
        raw = await _synthesize_cosy(text, voice=spec["voice"], rate=float(spec["rate"]),
                                     pitch=float(spec["pitch"]))
    elif engine == "edge-tts":
        raw = await _synthesize_edge(text, voice=spec["voice"], rate=spec["rate"], pitch=spec["pitch"])
    else:
        raise PreflightError("unknown_engine", "未知的配音引擎")
    target_lufs = -16.0 if spec.get("role") == "dialogue" else -18.0
    processed = await _process_voice(raw.audio, input_format=raw.audio_format, fx=spec.get("fx"),
                                     target_lufs=target_lufs)
    meta = {"spec": spec, "text": text, "duration_s": processed.duration_s,
            "measured_lufs": processed.measured_lufs, "sample_rate": processed.sample_rate}
    asset = await _commit_audio(job, processed.wav, meta)
    await store.cas_job(job["id"], "running", {"status": "succeeded", "result_asset_id": asset["id"]},
                        run_token=token)
    return True


async def _commit_image(job: dict, data: bytes, meta: dict) -> dict:
    metadata = await _inspect_image(data)
    return await _commit_asset(job, data, meta, kind="image", role="sheet", metadata=metadata,
                               save=_save_image)


async def _commit_audio(job: dict, data: bytes, meta: dict) -> dict:
    metadata = {"duration_s": meta.get("duration_s"), "has_audio": 1}
    return await _commit_asset(job, data, meta, kind="audio", role="audition", metadata=metadata,
                               save=lambda project_id, payload, _m: _save_audio(project_id, payload))


async def _commit_asset(job: dict, data: bytes, meta: dict, *, kind: str, role: str, metadata: dict, save) -> dict:
    saved = None
    async with store.connection() as db:
        await db.execute("BEGIN IMMEDIATE")
        committed = False
        try:
            maximum = await store._one(db, """SELECT MAX(version_no) AS value FROM studio_assets
                WHERE owner=? AND item_id=? AND role=?""", (job["owner"], job["item_id"], role))
            version_no = int((maximum or {}).get("value") or 0) + 1
            saved = await save(job["project_id"], data, metadata)
            asset = await store._create_asset(db, job["owner"], job["project_id"], {
                **saved, "kind": kind, "source": "generated", "item_id": job["item_id"],
                "version_no": version_no, "role": role, "meta": meta,
                **({"width": metadata["width"], "height": metadata["height"]} if kind == "image" else {}),
                **({"duration_s": metadata.get("duration_s"), "has_audio": 1} if kind == "audio" else {}),
            })
            await db.commit()
            committed = True
        except BaseException:
            if not committed:
                await db.rollback()
                # 回滚后再查：同一文件可能仍被别的资产引用（例如逐字节一致的 edge-tts 输出）。
                if saved is not None and saved.get("rel_path") and not await _asset_path_referenced(saved["rel_path"]):
                    await _discard_file(saved["rel_path"])
            raise
        return asset


async def _asset_path_referenced(rel_path: str) -> bool:
    """是否有别的资产仍在引用这个文件；必须在回滚之后用新连接查（否则会查到自己）。"""
    try:
        async with store.connection() as db:
            row = await store._one(db, "SELECT id FROM studio_assets WHERE rel_path=? LIMIT 1", (rel_path,))
    except Exception:  # 查不出来就按仍有引用处理，宁可留下文件也不误删
        return True
    return row is not None


def price_for(media_provider: str, *, chars: int = 0) -> Decimal:
    """一条任务的预留/结算金额。"""
    if media_provider == "seedream":
        return pricing.seedream_price()
    if media_provider == "cosyvoice":
        return pricing.money(pricing.estimate_speech(chars, "cosyvoice")["amount"])
    return pricing.money(0)
