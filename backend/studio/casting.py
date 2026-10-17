"""定妆（G1）与声线的业务编排：条目同步、CastingState 组装、报价与条目操作。

本模块只依赖块 A 的文件与 `store` / `spend` / `pricing` / `brain_jobs` / `breakdown_plan`；
块 B（出图、合成、音频处理）与块 C（提示词）的函数一律延迟导入，见 `casting_jobs`。
"""
from __future__ import annotations

from datetime import timedelta
import hashlib
import json
import logging
import re
import shutil
import uuid

from fastapi import HTTPException

from . import brain_jobs, breakdown_plan, casting_jobs, pricing, spend, store


STYLE_TASK = "style_proposals"
LOOK_TASK = "casting_look"
PROPOSAL_FIELDS = ("name", "visual_style", "palette", "camera", "lighting", "rationale")
STYLE_FIELDS = (*PROPOSAL_FIELDS,)
REALISMS = ("photoreal", "anime", "3d")
VIDEO_MODELS = ("wan", "seedance")
RESOLUTIONS = ("480P", "720P", "1080P")
LANGUAGES = ("zh", "en")
SHEET_SIZE = "2560x1440"
ENGINES = ("doubao", "cosyvoice", "edge-tts")
ROLES = ("dialogue", "narration")

MAX_SHEET_ITEMS = 30
MAX_SHEET_VERSIONS = 60
MAX_ITEM_VERSIONS = 4
MAX_EXTRA_PROMPT = 500
MAX_LOCKED_FEATURES = 600
MAX_REFERENCES = 4
MAX_LOOK_ITEMS = 30
LOOK_BATCH_SIZE = 4
MAX_AUDITION_VARIANTS = 3
MAX_AUDITION_TEXT = 120
MAX_DIRECTION = 200
# CosyVoice 的原始音频必须经 ffmpeg/ffprobe 处理；付费前先确认工具在位。
AUDIO_TOOLS = ("ffmpeg", "ffprobe")

_EDGE_RATE = re.compile(r"^[+-]([0-9]{1,3})%$")
_EDGE_PITCH = re.compile(r"^[+-]([0-9]{1,3})Hz$")

_log = logging.getLogger(__name__)


def _load(value, default):
    if isinstance(value, str):
        return json.loads(value or json.dumps(default))
    return value if value is not None else default


# ---------------------------------------------------------------------------
# 前置门禁
# ---------------------------------------------------------------------------

async def _require_g0(pid: str, owner: str) -> dict:
    episodes = await breakdown_plan.get_episodes(pid, owner)
    if not episodes.get("g0_approved"):
        raise HTTPException(409, "请先在①拆解批准分集方案")
    return episodes


def _setup_json(project: dict) -> dict | None:
    return _load(project.get("setup_json"), None)


def _require_setup(project: dict) -> dict:
    if not project.get("setup_confirmed_at"):
        raise HTTPException(409, "请先确认开工设置")
    return _setup_json(project) or {}


def _require_style(project: dict) -> dict:
    chosen = _load(project.get("style_json"), None)
    if not chosen:
        raise HTTPException(409, "请先选定风格")
    return chosen


# ---------------------------------------------------------------------------
# 条目同步与 CastingItem 组装
# ---------------------------------------------------------------------------

async def _current_breakdown_id(pid: str, owner: str) -> str | None:
    episodes = await breakdown_plan.get_episodes(pid, owner)
    return episodes.get("breakdown_id")


async def _sync_items(db, project: dict, owner: str, breakdown_id: str | None) -> None:
    """为当前拆解总表里未归档、未合并的条目补建 ``studio_items`` 行（幂等）。"""
    if not breakdown_id:
        return
    rows = await store._many(db, """SELECT id,kind,name FROM studio_bible
        WHERE breakdown_id=? AND owner=? AND archived=0 AND merged_into IS NULL ORDER BY id""",
                             (breakdown_id, owner))
    stamp = store.utcnow()
    for row in rows:
        await db.execute("""INSERT OR IGNORE INTO studio_items
            (id,project_id,owner,bible_id,kind,name,status,spec_json,created_at,updated_at)
            VALUES(?,?,?,?,?,?,'pending','{}',?,?)""",
                         (str(uuid.uuid4()), project["id"], owner, row["id"], row["kind"], row["name"],
                          stamp, stamp))


def _bible_map(rows) -> dict:
    return {row["id"]: row for row in rows}


def _asset_public(asset: dict, *, role: str) -> dict:
    meta = _load(asset.get("meta"), {}) or {}
    base = {"asset_id": asset["id"], "version_no": asset.get("version_no") or 0,
            "created_at": asset["created_at"], "archived": bool(asset.get("archived"))}
    if role == "sheet":
        return {**base, "prompt": meta.get("prompt") or ""}
    # §8.3：试听条目只暴露 asset_id / spec / text / duration_s / measured_lufs / created_at / archived。
    return {"asset_id": asset["id"], "spec": meta.get("spec"), "text": meta.get("text") or "",
            "duration_s": asset.get("duration_s"), "measured_lufs": meta.get("measured_lufs"),
            "created_at": asset["created_at"], "archived": bool(asset.get("archived"))}


def is_orphaned(bible: dict | None, breakdown_id: str | None) -> bool:
    """总表条目已归档 / 已合并 / 不属于当前拆解 → 孤儿（不删条目，只标记）。"""
    if bible is None or bible.get("archived") or bible.get("merged_into"):
        return True
    return bool(breakdown_id) and bible.get("breakdown_id") != breakdown_id


def _item_public(item: dict, bible: dict | None, sheets: list[dict], auditions: list[dict],
                 breakdown_id: str | None) -> dict:
    spec = _load(item.get("spec_json"), {}) or {}
    orphaned = is_orphaned(bible, breakdown_id)
    voice = None
    if item["kind"] == "character":
        voice = {"spec": spec.get("voice"), "approved_asset_id": item.get("voice_asset_id"),
                 "auditions": [_asset_public(asset, role="audition") for asset in auditions]}
    return {
        "id": item["id"],
        "bible_id": item["bible_id"],
        "kind": item["kind"],
        "name": (bible or {}).get("name") or item.get("name") or "",
        "role": (bible or {}).get("role") or "",
        "appearance": (bible or {}).get("appearance") or "",
        "description": (bible or {}).get("description") or "",
        "needs_author": bool((bible or {}).get("needs_author")),
        "orphaned": orphaned,
        "status": item["status"],
        "locked_features": spec.get("locked_features") or "",
        "extra_prompt": spec.get("extra_prompt") or "",
        "look": spec.get("look") or None,
        "look_source": spec.get("look_source") or None,
        "reference_asset_ids": list(spec.get("reference_asset_ids") or []),
        "approved_asset_id": item.get("approved_asset_id"),
        "versions": [_asset_public(asset, role="sheet") for asset in sheets
                     if not asset.get("archived")],
        "voice": voice,
    }


async def _load_items(db, project: dict, owner: str, breakdown_id: str | None) -> list[dict]:
    bible = _bible_map(await store._many(db, "SELECT * FROM studio_bible WHERE project_id=? AND owner=?",
                                         (project["id"], owner)))
    items = await store._many(db, """SELECT * FROM studio_items WHERE project_id=? AND owner=?
        ORDER BY kind,name,id""", (project["id"], owner))
    assets = await store._many(db, """SELECT * FROM studio_assets WHERE project_id=? AND owner=?
        AND item_id IS NOT NULL AND role IN ('sheet','audition') ORDER BY item_id,version_no,created_at""",
                               (project["id"], owner))
    sheets, auditions = {}, {}
    for asset in assets:
        target = sheets if asset["role"] == "sheet" else auditions
        target.setdefault(asset["item_id"], []).append(asset)
    return [_item_public(item, bible.get(item["bible_id"]), sheets.get(item["id"], []),
                         auditions.get(item["id"], []), breakdown_id) for item in items]


def _g1(items: list[dict]) -> dict:
    active = [item for item in items if not item["orphaned"]]
    approved = sum(1 for item in active if item["status"] == "approved")
    skipped = sum(1 for item in active if item["status"] == "skipped")
    done = len(active) - sum(1 for item in active if item["status"] == "pending")
    return {"approved": bool(active) and approved >= 1 and done == len(active),
            "total": len(active), "done": done, "skipped": skipped}


def _job_item_ids(row: dict) -> list[str]:
    params = row.get("params") or {}
    raw = params.get("item_ids")
    if isinstance(raw, list):
        return [value for value in raw if isinstance(value, str) and value]
    inputs = params.get("inputs") if isinstance(params, dict) else None
    items = inputs.get("items") if isinstance(inputs, dict) else None
    return [entry["item_id"] for entry in items or []
            if isinstance(entry, dict) and isinstance(entry.get("item_id"), str)]


def _casting_job(row: dict) -> dict:
    actual = row.get("actual_amount")
    result = {"id": row["id"], "kind": row["kind"], "task": row.get("task"),
              "item_id": row.get("item_id"), "status": row["status"],
              "error_code": row.get("error_code"), "error_message": row.get("error_message"),
              "reserved_amount": float(pricing.money(row.get("reserved_amount") or 0)),
              "actual_amount": None if actual is None else float(pricing.money(actual)),
              "currency": row.get("currency") or "CNY", "created_at": row["created_at"]}
    if row.get("task") == LOOK_TASK:
        result["item_ids"] = _job_item_ids(row)
    return result


_JOBS_FILTER = "(kind IN ('image','tts') OR (kind='brain' AND task IN (?,?)))"
_INFLIGHT = ("queued", "submitting", "submitted", "running", "uncertain")


async def _project_jobs(db, project_id: str, owner: str) -> list[dict]:
    inflight = await store._many(db, f"""SELECT * FROM studio_jobs WHERE project_id=? AND owner=?
        AND {_JOBS_FILTER} AND status IN ('queued','submitting','submitted','running','uncertain')
        ORDER BY created_at,id""", (project_id, owner, STYLE_TASK, LOOK_TASK))
    finished = await store._many(db, f"""SELECT * FROM studio_jobs WHERE project_id=? AND owner=?
        AND {_JOBS_FILTER} AND status NOT IN ('queued','submitting','submitted','running','uncertain')
        ORDER BY COALESCE(finished_at,updated_at) DESC, id DESC LIMIT 50""",
                              (project_id, owner, STYLE_TASK, LOOK_TASK))
    return [_casting_job(row) for row in [*inflight, *finished]]


async def _style_rows(db, project: dict, owner: str) -> list[dict]:
    if not project.get("style_group_id"):
        return []
    return await store._many(db, """SELECT * FROM studio_jobs WHERE project_id=? AND owner=?
        AND kind='brain' AND task=? AND group_id=? ORDER BY created_at,id""",
                             (project["id"], owner, STYLE_TASK, project["style_group_id"]))


def _proposals(output) -> list[dict]:
    raw = output.get("proposals") if isinstance(output, dict) else None
    result = []
    for entry in raw or []:
        if not isinstance(entry, dict):
            continue
        result.append({key: str(entry.get(key) or "") for key in PROPOSAL_FIELDS})
    return result


async def _style_block(db, project: dict, owner: str) -> dict:
    rows = await _style_rows(db, project, owner)
    proposals, job = [], None
    for row in rows:
        job = _casting_job(row)
        if row["status"] == "succeeded":
            found = _proposals(row.get("output"))
            if found:
                proposals = found
    return {"chosen": _load(project.get("style_json"), None), "proposals": proposals, "proposal_job": job}


def _look_fields(kind: str) -> tuple[str, ...]:
    from .casting_prompts import LOOK_FIELDS
    return tuple(key for key, _label in LOOK_FIELDS.get(kind, ()))


def _clean_look(kind: str, value) -> dict:
    """只保留该条目 kind 的已知字段；空串与超长值按上限截断。"""
    from .casting_prompts import LOOK_MAX_CHARS
    if not isinstance(value, dict):
        return {}
    result = {}
    for key in _look_fields(kind):
        text = value.get(key)
        if isinstance(text, str) and text.strip():
            result[key] = text.strip()[:LOOK_MAX_CHARS]
    return result


async def _apply_look_results(db, project_id: str, owner: str, breakdown_id: str | None) -> None:
    """按任务 created_at 的水位写回造型说明。

    每个条目在 ``spec_json["look_job_created_at"]`` 记下已写回任务的时间，只有更晚创建的
    任务才能覆盖；已应用的任务不会反复写库。单个条目的结果损坏只记一条 warning 并跳过，
    不影响 ``GET /casting`` 的其余内容。
    """
    jobs = await store._many(db, """SELECT * FROM studio_jobs WHERE project_id=? AND owner=?
        AND kind='brain' AND task=? AND status='succeeded'
        ORDER BY created_at,id""", (project_id, owner, LOOK_TASK))
    for job in jobs:
        output = job.get("output")
        if not isinstance(output, dict) or not isinstance(output.get("looks"), list):
            continue
        requested = set(_job_item_ids(job))
        created_at = job["created_at"]
        created = store.parse_time(created_at)
        for entry in output["looks"]:
            if not isinstance(entry, dict):
                continue
            item_id = entry.get("item_id")
            if item_id not in requested:
                continue
            try:
                item = await store._one(db, "SELECT * FROM studio_items WHERE id=? AND project_id=? AND owner=?",
                                        (item_id, project_id, owner))
                if item is None or item["kind"] not in ("character", "prop"):
                    continue
                if entry.get("kind") != item["kind"]:
                    continue
                spec = _load(item.get("spec_json"), {}) or {}
                applied_at = spec.get("look_job_created_at")
                if applied_at and store.parse_time(applied_at) >= created:
                    continue
                if spec.get("look_source") == "author":
                    continue
                bible = await store._one(db, "SELECT * FROM studio_bible WHERE id=? AND owner=?",
                                         (item["bible_id"], owner))
                if is_orphaned(bible, breakdown_id):
                    continue
                look = _clean_look(item["kind"], entry.get("look"))
                if not look:
                    continue
                spec["look"] = look
                spec["look_source"] = "director"
                spec["look_job_created_at"] = created_at
                spec.pop("look_job_ids", None)
                await db.execute("UPDATE studio_items SET spec_json=?,updated_at=? WHERE id=? AND owner=?",
                                 (store._json(spec), store.utcnow(), item_id, owner))
            except Exception as exc:  # 结果损坏或字段异常时不能拖垮整个状态接口。
                _log.warning("造型说明任务 %s 的条目 %s 结果损坏，已跳过：%s", job["id"], item_id, exc)


# ---------------------------------------------------------------------------
# CASTING STATE
# ---------------------------------------------------------------------------

async def state(pid: str, owner: str) -> dict:
    project = await store.get_project(pid, owner)
    episodes = await breakdown_plan.get_episodes(pid, owner)
    # 按需补建条目必须先落库，否则只读连接关闭时会被回滚。
    async with store.connection(transaction=True) as db:
        await _sync_items(db, project, owner, episodes.get("breakdown_id"))
        await _apply_look_results(db, project["id"], owner, episodes.get("breakdown_id"))
    async with store.connection() as db:
        items = await _load_items(db, project, owner, episodes.get("breakdown_id"))
        style = await _style_block(db, project, owner)
        jobs = await _project_jobs(db, project["id"], owner)
    setup = _setup_json(project)
    if project.get("setup_confirmed_at") and setup is not None:
        setup = {"aspect": project["aspect"], **setup, "sheet_size": SHEET_SIZE,
                 "confirmed_at": project["setup_confirmed_at"]}
    else:
        setup = None
    return {"g0_approved": bool(episodes.get("g0_approved")), "setup": setup, "style": style,
            "items": items, "g1": _g1(items), "jobs": jobs,
            "prices": {"seedream_cny": float(pricing.seedream_price()),
                       "cosyvoice_cny_per_10k_chars": float(pricing.cosyvoice_price_per_10k_chars()),
                       "doubao_cny_per_10k_chars": float(pricing.doubao_price_per_10k_chars())}}


# ---------------------------------------------------------------------------
# §4 开工确认与风格
# ---------------------------------------------------------------------------

async def put_setup(pid: str, owner: str, *, resolution: str, video_model: str, language: str) -> dict:
    if resolution not in RESOLUTIONS:
        raise HTTPException(422, "视频分辨率必须为 480P / 720P / 1080P")
    if video_model not in VIDEO_MODELS:
        raise HTTPException(422, "默认视频模型必须为 wan 或 seedance")
    if language not in LANGUAGES:
        raise HTTPException(422, "语言必须为 zh 或 en")
    await _require_g0(pid, owner)
    stamp = store.utcnow()
    payload = store._json({"resolution": resolution, "video_model": video_model, "language": language})
    async with store.connection(transaction=True) as db:
        await store._project(db, pid, owner)
        await db.execute("""UPDATE studio_projects SET setup_json=?,setup_confirmed_at=?,updated_at=?
            WHERE id=? AND owner=?""", (payload, stamp, stamp, pid, owner))
    return await state(pid, owner)


async def _brain_option(provider: str, owner: str) -> dict:
    from .brain import provider_options
    if provider not in brain_jobs.PROVIDERS:
        raise HTTPException(422, "导演模型必须为 claude、qwen 或 deepseek")
    option = next(item for item in await provider_options(owner) if item["id"] == provider)
    if not option["available"]:
        raise HTTPException(409, option.get("reason", "导演模型不可用，请先配置密钥"))
    return option


async def _style_inputs(project: dict, episodes: dict, pid: str, owner: str) -> dict:
    breakdown = None
    if episodes.get("breakdown_id"):
        async with store.connection() as db:
            breakdown = await store._one(db, "SELECT * FROM studio_breakdowns WHERE id=? AND owner=?",
                                         (episodes["breakdown_id"], owner))
    synopsis = json.loads((breakdown or {}).get("synopsis_json") or "{}")
    bible = await breakdown_plan.list_bible(pid, owner)
    language = (_setup_json(project) or {}).get("language") or "zh"
    return casting_jobs.style_inputs(synopsis=synopsis, bible=bible,
                                     episodes=episodes.get("episodes") or [], language=language)


def _style_quote_public(row_id: str, expires: str, currency: str, amount) -> dict:
    value = float(pricing.money(amount))
    return {"id": row_id, "kind": "casting_style",
            "items": [{"item_id": None, "name": "风格提案", "versions": 1, "unit": value, "est": value}],
            "total": value, "currency": currency, "expires_at": expires}


async def quote_style(pid: str, owner: str) -> dict:
    project = await store.get_project(pid, owner)
    episodes = await _require_g0(pid, owner)
    _require_setup(project)
    inputs = await _style_inputs(project, episodes, pid, owner)
    option = await _brain_option(project["brain_provider"], owner)
    item = brain_jobs._quote_item(project["brain_provider"], option["model"], STYLE_TASK, inputs)
    payload = {"kind": "casting_style", "items": [item], "inputs": inputs,
               "provider": project["brain_provider"]}
    qid, stamp = str(uuid.uuid4()), store.utcnow()
    expires = (store.parse_time(stamp) + timedelta(minutes=15)).isoformat()
    async with store.connection(transaction=True) as db:
        await store._project(db, pid, owner)
        await spend.check_brain_budget(db, owner, brain_jobs._totals([item]))
        await db.execute("""INSERT INTO studio_quotes(id,project_id,owner,items_json,total_min_cny,
            total_max_cny,params_hash,status,created_at,expires_at) VALUES(?,?,?,?,?,?,?,'open',?,?)""",
                         (qid, pid, owner, store._json(payload), "0", str(pricing.money(item["amount"])),
                          hashlib.sha256(store._json(item).encode()).hexdigest(), stamp, expires))
    return _style_quote_public(qid, expires, item["currency"], item["amount"])


async def start_style(pid: str, owner: str, quote_id: str) -> dict:
    project = await store.get_project(pid, owner)
    await _require_g0(pid, owner)
    _require_setup(project)
    async with store.connection(transaction=True) as db:
        await store._project(db, pid, owner)
        row = await store._one(db, "SELECT * FROM studio_quotes WHERE id=? AND project_id=? AND owner=?",
                               (quote_id, pid, owner))
        if row is None:
            raise HTTPException(404, "Not Found")
        payload = row.get("items")
        if not isinstance(payload, dict) or payload.get("kind") != "casting_style":
            raise HTTPException(409, "报价用途不匹配")
        if row["status"] != "open":
            raise HTTPException(409, "报价只能确认一次")
        if store.parse_time(row["expires_at"]) <= store.parse_time(store.utcnow()):
            raise HTTPException(409, "报价已过期，请重新报价")
        await spend.check_brain_budget(db, owner, brain_jobs._totals(payload["items"]))
        stamp = store.utcnow()
        await db.execute("UPDATE studio_quotes SET status='confirmed',confirmed_at=? WHERE id=? AND status='open'",
                         (stamp, quote_id))
        group_id = str(uuid.uuid4())
        await db.execute("UPDATE studio_projects SET style_group_id=?,updated_at=? WHERE id=? AND owner=?",
                         (group_id, stamp, pid, owner))
        job = await brain_jobs._insert_job(db, pid, owner, payload["items"][0], payload["inputs"], group_id,
                                          quote_id=quote_id)
    brain_jobs._schedule(job["id"])
    return await state(pid, owner)


def _clean_fields(value: dict, fields) -> dict:
    result = {}
    for key in fields:
        entry = value.get(key)
        if entry is None:
            entry = ""
        if not isinstance(entry, str) or len(entry) > 2000:
            raise HTTPException(422, "风格字段须为不超过 2000 字的文本")
        result[key] = entry.strip()
    return result


async def put_style(pid: str, owner: str, *, realism: str, proposal_index=None, custom=None) -> dict:
    if realism not in REALISMS:
        raise HTTPException(422, "写实度必须为 photoreal / anime / 3d")
    if (proposal_index is None) == (custom is None):
        raise HTTPException(422, "请从提案中选一项，或提供自定义风格")
    project = await store.get_project(pid, owner)
    await _require_g0(pid, owner)
    _require_setup(project)
    if proposal_index is not None:
        if isinstance(proposal_index, bool) or not isinstance(proposal_index, int) or proposal_index < 0:
            raise HTTPException(422, "提案序号无效")
        async with store.connection() as db:
            proposals = (await _style_block(db, project, owner))["proposals"]
        if proposal_index >= len(proposals):
            raise HTTPException(422, "提案序号超出范围")
        chosen = {**proposals[proposal_index], "realism": realism, "source": "proposal",
                  "proposal_index": proposal_index}
    else:
        if not isinstance(custom, dict):
            raise HTTPException(422, "自定义风格格式无效")
        fields = _clean_fields(custom, STYLE_FIELDS)
        if not fields["name"] or not fields["visual_style"]:
            raise HTTPException(422, "自定义风格的名称与视觉风格不能为空")
        chosen = {**fields, "realism": realism, "source": "custom", "proposal_index": None}
    async with store.connection(transaction=True) as db:
        await store._project(db, pid, owner)
        await db.execute("UPDATE studio_projects SET style_json=?,updated_at=? WHERE id=? AND owner=?",
                         (store._json(chosen), store.utcnow(), pid, owner))
    return await state(pid, owner)


# ---------------------------------------------------------------------------
# §5 造型说明（导演补全）
# ---------------------------------------------------------------------------

async def _synopsis_json(episodes: dict, owner: str):
    if not episodes.get("breakdown_id"):
        return {}
    async with store.connection() as db:
        breakdown = await store._one(db, "SELECT * FROM studio_breakdowns WHERE id=? AND owner=?",
                                     (episodes["breakdown_id"], owner))
    try:
        value = json.loads((breakdown or {}).get("synopsis_json") or "{}")
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, (dict, str)) else {}


def _looks_quote_public(qid: str, expires: str, items: list[dict], total) -> dict:
    currency = items[0]["currency"] if items else "CNY"
    return {"id": qid, "kind": "casting_looks",
            "items": [{"item_id": None, "name": item["name"], "versions": 1,
                       "item_count": item.get("item_count", len(item.get("item_ids") or [])),
                       "unit": float(pricing.money(item["amount"])),
                       "est": float(pricing.money(item["amount"]))} for item in items],
            "total": float(pricing.money(total)), "currency": currency, "expires_at": expires}


async def _look_inflight_ids(db, project_id: str, owner: str) -> set[str]:
    rows = await store._many(db, """SELECT * FROM studio_jobs WHERE project_id=? AND owner=?
        AND kind='brain' AND task=? AND status IN ('queued','submitting','submitted','running')""",
                             (project_id, owner, LOOK_TASK))
    result: set[str] = set()
    for row in rows:
        result.update(_job_item_ids(row))
    return result


async def quote_looks(pid: str, owner: str, item_ids) -> dict:
    from .casting_prompts import look_inputs

    project = await store.get_project(pid, owner)
    episodes = await _require_g0(pid, owner)
    breakdown_id = episodes.get("breakdown_id")
    _require_setup(project)
    style = _require_style(project)
    if not isinstance(item_ids, list) or not item_ids:
        raise HTTPException(422, f"请选择 1–{MAX_LOOK_ITEMS} 个条目")
    if any(not isinstance(item_id, str) or not item_id for item_id in item_ids):
        raise HTTPException(422, "条目 ID 无效")
    ids = list(dict.fromkeys(item_ids))
    if len(ids) > MAX_LOOK_ITEMS:
        raise HTTPException(422, f"一次最多为 {MAX_LOOK_ITEMS} 个条目补全造型说明")
    language = (_setup_json(project) or {}).get("language") or "zh"
    synopsis = await _synopsis_json(episodes, owner)
    entries = []
    inflight_excluded = 0
    async with store.connection() as db:
        inflight = await _look_inflight_ids(db, project["id"], owner)
        for item_id in ids:
            item, bible = await _item_with_bible(db, item_id, owner, pid)
            name = (bible or {}).get("name") or item.get("name") or ""
            if is_orphaned(bible, breakdown_id):
                raise HTTPException(409, f"{name} 已不在当前总表，不能补全造型说明")
            if item["kind"] not in ("character", "prop"):
                raise HTTPException(409, f"{name} 是场景条目，不需要造型说明")
            if item_id in inflight:
                inflight_excluded += 1
                continue
            spec = _load(item.get("spec_json"), {}) or {}
            if spec.get("look_source") == "author":
                continue
            entries.append({"item_id": item["id"], "kind": item["kind"], "name": name,
                            "appearance": (bible or {}).get("appearance") or "",
                            "description": (bible or {}).get("description") or "",
                            "locked_features": spec.get("locked_features") or ""})
    if not entries:
        if inflight_excluded:
            raise HTTPException(409, "这些条目正在补全造型")
        raise HTTPException(409, "这些条目的造型说明已由作者修改")
    option = await _brain_option(project["brain_provider"], owner)
    quote_items = []
    for batch, start in enumerate(range(0, len(entries), LOOK_BATCH_SIZE), 1):
        chunk = entries[start:start + LOOK_BATCH_SIZE]
        inputs = look_inputs(items=chunk, style=style, synopsis=synopsis, language=language)
        item = brain_jobs._quote_item(project["brain_provider"], option["model"], LOOK_TASK, inputs)
        item.update({"name": f"造型说明 第 {batch} 批（{len(chunk)} 个条目）",
                     "item_ids": [entry["item_id"] for entry in chunk], "item_count": len(chunk),
                     "locked_features": {entry["item_id"]: entry["locked_features"] for entry in chunk},
                     "inputs": inputs})
        quote_items.append(item)
    total = pricing.money(sum(pricing.money(item["amount"]) for item in quote_items))
    payload = {"kind": "casting_looks", "items": quote_items, "provider": project["brain_provider"]}
    qid, stamp = str(uuid.uuid4()), store.utcnow()
    expires = (store.parse_time(stamp) + timedelta(minutes=15)).isoformat()
    async with store.connection(transaction=True) as db:
        await store._project(db, pid, owner)
        await spend.check_brain_budget(db, owner, brain_jobs._totals(quote_items), now=stamp)
        await db.execute("""INSERT INTO studio_quotes(id,project_id,owner,items_json,total_min_cny,
            total_max_cny,params_hash,status,created_at,expires_at) VALUES(?,?,?,?,?,?,?,'open',?,?)""",
                         (qid, pid, owner, store._json(payload), "0", str(total),
                          hashlib.sha256(store._json(payload).encode()).hexdigest(), stamp, expires))
    return _looks_quote_public(qid, expires, quote_items, total)


async def _revalidate_look_item(db, item_id: str, quoted_features: str, owner: str, pid: str,
                                 breakdown_id: str | None) -> None:
    """执行前复核报价条目：仍可用、未由作者改写、锁定特征与报价时一致。"""
    try:
        item, bible = await _item_with_bible(db, item_id, owner, pid)
    except HTTPException as exc:
        if exc.status_code == 404:
            raise HTTPException(409, "条目已不存在，请重新报价") from exc
        raise
    name = (bible or {}).get("name") or item.get("name") or ""
    if is_orphaned(bible, breakdown_id):
        raise HTTPException(409, f"{name} 已不在当前总表，请重新报价")
    if item["kind"] not in ("character", "prop"):
        raise HTTPException(409, f"{name} 是场景条目，不需要造型说明")
    spec = _load(item.get("spec_json"), {}) or {}
    if spec.get("look_source") == "author":
        raise HTTPException(409, f"{name} 的造型说明已由作者修改，请重新报价")
    if (spec.get("locked_features") or "") != (quoted_features or ""):
        raise HTTPException(409, f"{name} 的锁定特征已修改，请重新报价")


async def start_looks(pid: str, owner: str, quote_id: str) -> dict:
    project = await store.get_project(pid, owner)
    episodes = await _require_g0(pid, owner)
    breakdown_id = episodes.get("breakdown_id")
    _require_setup(project)
    _require_style(project)
    async with store.connection(transaction=True) as db:
        await store._project(db, pid, owner)
        row = await store._one(db, "SELECT * FROM studio_quotes WHERE id=? AND project_id=? AND owner=?",
                               (quote_id, pid, owner))
        if row is None:
            raise HTTPException(404, "Not Found")
        payload = row.get("items")
        if not isinstance(payload, dict) or payload.get("kind") != "casting_looks":
            raise HTTPException(409, "报价用途不匹配")
        if row["status"] != "open":
            raise HTTPException(409, "报价只能确认一次")
        if store.parse_time(row["expires_at"]) <= store.parse_time(store.utcnow()):
            raise HTTPException(409, "报价已过期，请重新报价")
        quoted_ids = {item_id for item in payload.get("items") or []
                      for item_id in (item.get("item_ids") or [])}
        inflight_ids = await _look_inflight_ids(db, pid, owner)
        if quoted_ids & inflight_ids:
            raise HTTPException(409, "这些条目正在补全造型，请等完成后再报价")
        await spend.check_brain_budget(db, owner, brain_jobs._totals(payload["items"]))
        for item in payload["items"]:
            quoted = item.get("locked_features") or {}
            if not isinstance(quoted, dict):
                quoted = {}
            for item_id in item.get("item_ids") or []:
                await _revalidate_look_item(db, item_id, quoted.get(item_id, ""), owner, pid, breakdown_id)
        stamp = store.utcnow()
        await db.execute("UPDATE studio_quotes SET status='confirmed',confirmed_at=? WHERE id=? AND status='open'",
                         (stamp, quote_id))
        group_id = str(uuid.uuid4())
        jobs = []
        for item in payload["items"]:
            inputs = item.get("inputs") or {}
            job = await brain_jobs._insert_job(db, pid, owner, item, inputs, group_id, quote_id=quote_id)
            item_ids = list(item.get("item_ids") or [])
            if item_ids:
                await db.execute("UPDATE studio_jobs SET params_json=? WHERE id=? AND owner=?",
                                 (store._json({"inputs": inputs, "item_ids": item_ids}), job["id"], owner))
                job = await store._get_job(db, job["id"], owner)
            jobs.append(job)
    for job in jobs:
        brain_jobs._schedule(job["id"])
    return await state(pid, owner)


# ---------------------------------------------------------------------------
# §5 定妆出图
# ---------------------------------------------------------------------------

async def _item_or_404(db, item_id: str, owner: str) -> dict:
    item = await store._one(db, "SELECT * FROM studio_items WHERE id=? AND owner=?", (item_id, owner))
    if item is None:
        raise HTTPException(404, "Not Found")
    return item


async def _item_with_bible(db, item_id: str, owner: str, pid: str) -> tuple[dict, dict]:
    item = await _item_or_404(db, item_id, owner)
    if item["project_id"] != pid:
        raise HTTPException(404, "Not Found")
    bible = await store._one(db, "SELECT * FROM studio_bible WHERE id=? AND owner=?", (item["bible_id"], owner))
    return item, bible or {}


async def _reference_assets(db, ids, owner: str, pid: str) -> list[str]:
    result = []
    for asset_id in ids:
        asset = await store._one(db, "SELECT * FROM studio_assets WHERE id=? AND owner=? AND archived=0",
                                 (asset_id, owner))
        if asset is None or asset["project_id"] != pid or asset["kind"] != "image":
            raise HTTPException(404, "Not Found")
        result.append(asset_id)
    return result


def _dedupe(ids) -> list[str]:
    return list(dict.fromkeys(ids))


async def _sheet_plan(db, item: dict, bible: dict, owner: str, pid: str, *, breakdown_id: str | None,
                      extra_prompt, reference_asset_ids, derive_from_approved) -> dict:
    """把条目级常驻默认与本次批量栏输入合并成报价/执行用的显式参考图与补充提示词。

    定妆出图只需付费前的三次校验：条目可用（非孤儿、不缺外形）、参考图归属本项目、
    合并后（含派生的已选定版本）不超过 4 张。
    """
    name = item["name"]
    if is_orphaned(bible, breakdown_id):
        raise HTTPException(409, f"{name} 已不在当前总表，不能出图")
    if item["kind"] == "character" and bible.get("needs_author"):
        raise HTTPException(409, f"{name} 还缺外形描述，请先补写外形再出图")
    spec = _load(item.get("spec_json"), {}) or {}
    defaults = _dedupe(spec.get("reference_asset_ids") or [])
    batch = list(reference_asset_ids or [])
    if len(batch) > MAX_REFERENCES:
        raise HTTPException(422, f"每个条目最多 {MAX_REFERENCES} 张参考图")
    explicit = await _reference_assets(db, _dedupe([*defaults, *batch]), owner, pid)
    derive = bool(derive_from_approved)
    approved = item.get("approved_asset_id")
    if derive and not approved:
        raise HTTPException(409, f"{name} 还没有已选定版本，不能派生，请先选定版本")
    merged = _dedupe([approved, *explicit]) if derive else explicit
    if len(merged) > MAX_REFERENCES:
        raise HTTPException(422, f"每个条目最多 {MAX_REFERENCES} 张参考图")
    saved_prompt = (spec.get("extra_prompt") or "").strip()
    batch_prompt = (extra_prompt or "").strip()
    return {"extra_prompt": " ".join(part for part in (saved_prompt, batch_prompt) if part),
            "reference_asset_ids": explicit, "derive_from_approved": derive}


async def quote_sheets(pid: str, owner: str, entries: list[dict]) -> dict:
    project = await store.get_project(pid, owner)
    episodes = await _require_g0(pid, owner)
    breakdown_id = episodes.get("breakdown_id")
    _require_setup(project)
    _require_style(project)
    if not entries or len(entries) > MAX_SHEET_ITEMS:
        raise HTTPException(422, f"一次最多为 {MAX_SHEET_ITEMS} 个条目出图")
    unit = pricing.seedream_price()
    qid, stamp = str(uuid.uuid4()), store.utcnow()
    expires = (store.parse_time(stamp) + timedelta(minutes=15)).isoformat()
    # 报价和执行前都先回放造型结果，避免同一事务里读到旧 look。
    async with store.connection(transaction=True) as db:
        await store._project(db, pid, owner)
        await _apply_look_results(db, project["id"], owner, breakdown_id)
        quote_items, total_versions = [], 0
        for entry in entries:
            item, bible = await _item_with_bible(db, entry["item_id"], owner, pid)
            versions = entry["versions"]
            plan = await _sheet_plan(db, item, bible, owner, pid, breakdown_id=breakdown_id,
                                     extra_prompt=entry.get("extra_prompt"),
                                     reference_asset_ids=entry.get("reference_asset_ids"),
                                     derive_from_approved=entry.get("derive_from_approved"))
            total_versions += versions
            quote_items.append({"item_id": item["id"], "name": item["name"], "versions": versions,
                                "unit": float(pricing.money(unit)),
                                "est": float(pricing.money(unit * versions)), **plan})
        if total_versions > MAX_SHEET_VERSIONS:
            raise HTTPException(422, f"单次出图合计不得超过 {MAX_SHEET_VERSIONS} 张")
        total = pricing.money(unit * total_versions)
        payload = {"kind": "casting_sheets", "items": quote_items, "total": float(total), "currency": "CNY"}
        await spend.check_quote_budget(db, total, now=stamp)
        await db.execute("""INSERT INTO studio_quotes(id,project_id,owner,items_json,total_min_cny,
            total_max_cny,params_hash,status,created_at,expires_at) VALUES(?,?,?,?,?,?,?,'open',?,?)""",
                         (qid, pid, owner, store._json(payload), "0", str(total),
                          hashlib.sha256(store._json(quote_items).encode()).hexdigest(), stamp, expires))
    return _sheets_quote_public(qid, expires, quote_items, total)


def _sheets_quote_public(qid: str, expires: str, items: list[dict], total) -> dict:
    return {"id": qid, "kind": "casting_sheets",
            "items": [{key: item[key] for key in ("item_id", "name", "versions", "unit", "est")}
                      for item in items],
            "total": float(pricing.money(total)), "currency": "CNY", "expires_at": expires}


async def _revalidate_sheet_item(db, quote_item: dict, owner: str, pid: str, breakdown_id: str | None) -> dict:
    """执行前按当前库状态复核报价条目：条目仍可用、参考图仍在、派生前提仍成立。"""
    item, bible = await _item_with_bible(db, quote_item["item_id"], owner, pid)
    if is_orphaned(bible, breakdown_id):
        raise HTTPException(409, f"{item['name']} 已不在当前总表，请重新报价")
    if item["kind"] == "character" and bible.get("needs_author"):
        raise HTTPException(409, f"{item['name']} 还缺外形描述，请先补写外形再出图")
    explicit = await _reference_assets(db, list(quote_item.get("reference_asset_ids") or []), owner, pid)
    derive = bool(quote_item.get("derive_from_approved"))
    approved = item.get("approved_asset_id")
    if derive and not approved:
        raise HTTPException(409, f"{item['name']} 还没有已选定版本，不能派生，请重新报价")
    merged = _dedupe([approved, *explicit]) if derive else explicit
    if len(merged) > MAX_REFERENCES:
        raise HTTPException(422, f"每个条目最多 {MAX_REFERENCES} 张参考图")
    return {"extra_prompt": quote_item.get("extra_prompt") or "", "reference_asset_ids": explicit,
            "derive_from_approved": derive}


async def start_sheets(pid: str, owner: str, quote_id: str) -> dict:
    project = await store.get_project(pid, owner)
    episodes = await _require_g0(pid, owner)
    breakdown_id = episodes.get("breakdown_id")
    _require_setup(project)
    _require_style(project)
    # 复核、确认报价、预留与建任务同属一个 BEGIN IMMEDIATE：撞日上限或中途失败时
    # 报价保持 open，不会被白烧掉。
    async with store.connection(transaction=True) as db:
        await store._project(db, pid, owner)
        await _apply_look_results(db, project["id"], owner, breakdown_id)
        row = await store._one(db, "SELECT * FROM studio_quotes WHERE id=? AND project_id=? AND owner=?",
                               (quote_id, pid, owner))
        if row is None:
            raise HTTPException(404, "Not Found")
        payload = row.get("items")
        if not isinstance(payload, dict) or payload.get("kind") != "casting_sheets":
            raise HTTPException(409, "报价用途不匹配")
        if row["status"] != "open":
            raise HTTPException(409, "报价只能确认一次")
        if store.parse_time(row["expires_at"]) <= store.parse_time(store.utcnow()):
            raise HTTPException(409, "报价已过期，请重新报价")
        await spend.check_quote_budget(db, pricing.money(row["total_max_cny"]))
        entries = []
        for item in payload["items"]:
            plan = await _revalidate_sheet_item(db, item, owner, pid, breakdown_id)
            for _ in range(item["versions"]):
                entries.append({"item_id": item["item_id"], "reserved_amount": pricing.money(item["unit"]),
                                "params": {"item_id": item["item_id"], **plan}})
        await db.execute("UPDATE studio_quotes SET status='confirmed',confirmed_at=? WHERE id=? AND status='open'",
                         (store.utcnow(), quote_id))
        jobs = await casting_jobs.prepare_jobs(db, project, owner, kind="image", media_provider="seedream",
                                              quote_id=quote_id, entries=entries)
    casting_jobs.schedule_jobs(jobs)
    return await state(pid, owner)


async def patch_item(item_id: str, owner: str, fields: dict) -> dict:
    if not fields:
        raise HTTPException(422, "请填写要修改的条目字段")
    async with store.connection(transaction=True) as db:
        item = await _item_or_404(db, item_id, owner)
        if "look" in fields:
            # 先回放已完成的导演结果，再在它之上合并作者修改。
            project = await store._one(db, "SELECT breakdown_id FROM studio_projects WHERE id=? AND owner=?",
                                       (item["project_id"], owner))
            await _apply_look_results(db, item["project_id"], owner, (project or {}).get("breakdown_id"))
            item = await _item_or_404(db, item_id, owner)
        spec = _load(item.get("spec_json"), {}) or {}
        if "locked_features" in fields:
            value = fields["locked_features"]
            if not isinstance(value, str) or len(value) > MAX_LOCKED_FEATURES:
                raise HTTPException(422, f"锁定特征不能超过 {MAX_LOCKED_FEATURES} 字")
            spec["locked_features"] = value.strip()
        if "extra_prompt" in fields:
            value = fields["extra_prompt"]
            if not isinstance(value, str) or len(value) > MAX_EXTRA_PROMPT:
                raise HTTPException(422, f"补充提示词不能超过 {MAX_EXTRA_PROMPT} 字")
            spec["extra_prompt"] = value.strip()
        if "look" in fields:
            from .casting_prompts import LOOK_MAX_CHARS
            value = fields["look"]
            if item["kind"] not in ("character", "prop"):
                raise HTTPException(422, "场景条目不需要造型说明")
            if not isinstance(value, dict):
                raise HTTPException(422, "造型说明格式无效")
            if not value:
                raise HTTPException(422, "造型说明不能为空")
            allowed = set(_look_fields(item["kind"]))
            incoming = {}
            for key, text in value.items():
                if key not in allowed:
                    raise HTTPException(422, f"未知的造型字段：{key}")
                if not isinstance(text, str):
                    raise HTTPException(422, "造型说明的每个字段须为文本")
                if len(text) > LOOK_MAX_CHARS:
                    raise HTTPException(422, f"造型说明的每个字段不能超过 {LOOK_MAX_CHARS} 字")
                incoming[key] = text.strip()
            merged = dict(spec.get("look") or {})
            merged.update(incoming)
            if any(text.strip() for text in merged.values() if isinstance(text, str)):
                spec["look"] = merged
                spec["look_source"] = "author"
            else:
                # 全部字段都清空后允许重新交给导演补全。
                spec.pop("look", None)
                spec.pop("look_source", None)
        if "reference_asset_ids" in fields:
            ids = fields["reference_asset_ids"]
            if not isinstance(ids, list) or len(ids) > MAX_REFERENCES:
                raise HTTPException(422, f"每个条目最多 {MAX_REFERENCES} 张参考图")
            spec["reference_asset_ids"] = await _reference_assets(db, ids, owner, item["project_id"])
        await db.execute("UPDATE studio_items SET spec_json=?,updated_at=? WHERE id=? AND owner=?",
                         (store._json(spec), store.utcnow(), item_id, owner))
        item = await _item_or_404(db, item_id, owner)
        return await _single_item(db, item, owner)


async def _single_item(db, item: dict, owner: str) -> dict:
    bible = await store._one(db, "SELECT * FROM studio_bible WHERE id=? AND owner=?", (item["bible_id"], owner))
    project = await store._one(db, "SELECT breakdown_id FROM studio_projects WHERE id=? AND owner=?",
                               (item["project_id"], owner))
    assets = await store._many(db, """SELECT * FROM studio_assets WHERE owner=? AND item_id=?
        AND role IN ('sheet','audition') ORDER BY version_no,created_at""", (owner, item["id"]))
    # 与 GET /casting 一致：单条目接口也只返回未归档的版本。
    sheets = [asset for asset in assets if asset["role"] == "sheet" and not asset.get("archived")]
    auditions = [asset for asset in assets if asset["role"] == "audition"]
    return _item_public(item, bible, sheets, auditions, (project or {}).get("breakdown_id"))


async def approve_item(item_id: str, owner: str, asset_id: str) -> dict:
    async with store.connection(transaction=True) as db:
        item = await _item_or_404(db, item_id, owner)
        asset = await store._one(db, "SELECT * FROM studio_assets WHERE id=? AND owner=? AND archived=0",
                                 (asset_id, owner))
        if asset is None or asset["item_id"] != item_id or asset["role"] != "sheet" or asset["kind"] != "image":
            raise HTTPException(404, "Not Found")
        await db.execute("""UPDATE studio_items SET approved_asset_id=?,status='approved',updated_at=?
            WHERE id=? AND owner=?""", (asset_id, store.utcnow(), item_id, owner))
        item = await _item_or_404(db, item_id, owner)
        return await _single_item(db, item, owner)


async def set_status(item_id: str, owner: str, status: str) -> dict:
    async with store.connection(transaction=True) as db:
        item = await _item_or_404(db, item_id, owner)
        # skip / reopen 都取消选定，作者才有退路；已定档的声线保留不动。
        await db.execute("""UPDATE studio_items SET status=?,approved_asset_id=NULL,updated_at=?
            WHERE id=? AND owner=?""", (status, store.utcnow(), item_id, owner))
        item = await _item_or_404(db, item_id, owner)
        return await _single_item(db, item, owner)


async def archive_asset(asset_id: str, owner: str) -> dict:
    async with store.connection(transaction=True) as db:
        asset = await store._one(db, "SELECT * FROM studio_assets WHERE id=? AND owner=?", (asset_id, owner))
        if asset is None:
            raise HTTPException(404, "Not Found")
        # 只有条目级定妆版本与试听可以归档；上传图 / i2v 首帧等不属于本流程。
        if not asset.get("item_id") or asset.get("role") not in ("sheet", "audition"):
            raise HTTPException(409, "只能归档条目下的定妆版本或试听")
        item = await store._one(db, "SELECT * FROM studio_items WHERE id=? AND owner=?",
                                (asset["item_id"], owner))
        if item is not None and asset_id in (item.get("approved_asset_id"), item.get("voice_asset_id")):
            raise HTTPException(409, "已选定（定档）的版本不能归档，请先换选定")
        await db.execute("UPDATE studio_assets SET archived=1 WHERE id=? AND owner=?", (asset_id, owner))
    return {"ok": True}


# ---------------------------------------------------------------------------
# §6 声线
# ---------------------------------------------------------------------------

def _validate_variant(variant: dict) -> dict:
    if not isinstance(variant, dict):
        raise HTTPException(422, "声线方案格式无效")
    engine = variant.get("engine")
    if engine not in ENGINES:
        raise HTTPException(422, "配音引擎必须为 doubao、cosyvoice 或 edge-tts")
    voice = variant.get("voice")
    if not isinstance(voice, str) or casting_jobs.lookup_voice(engine, voice) is None:
        raise HTTPException(422, "所选音色与引擎不匹配")
    fx = variant.get("fx")
    if not casting_jobs.valid_fx(fx):
        raise HTTPException(422, "声线特效档位无效")
    role = variant.get("role")
    if role not in ROLES:
        raise HTTPException(422, "角色类型必须为 dialogue 或 narration")
    direction = variant.get("direction")
    if direction is not None and not isinstance(direction, str):
        raise HTTPException(422, "表演指示格式无效")
    direction = (direction or "").strip() or None
    if engine == "doubao":
        if direction is not None and len(direction) > MAX_DIRECTION:
            raise HTTPException(422, f"表演指示最多 {MAX_DIRECTION} 字")
        rate = _bounded_float(variant.get("rate"), 0.5, 2.0, "语速")
        pitch = _bounded_int(variant.get("pitch"), -12, 12, "音高")
    elif engine == "cosyvoice":
        if direction:
            raise HTTPException(422, "该引擎不支持表演指示")
        rate = _bounded_float(variant.get("rate"), 0.5, 2.0, "语速")
        pitch = _bounded_float(variant.get("pitch"), 0.5, 2.0, "音高")
    else:
        if direction:
            raise HTTPException(422, "该引擎不支持表演指示")
        rate = _edge_value(variant.get("rate"), _EDGE_RATE, 50, "%", "语速")
        pitch = _edge_value(variant.get("pitch"), _EDGE_PITCH, 50, "Hz", "音高")
    return {"engine": engine, "voice": voice, "rate": rate, "pitch": pitch, "fx": fx or None,
            "role": role, "direction": direction}


def _bounded_float(value, minimum: float, maximum: float, label: str) -> float:
    if isinstance(value, bool):
        raise HTTPException(422, f"{label}须为 {minimum}–{maximum} 之间的数值")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise HTTPException(422, f"{label}须为 {minimum}–{maximum} 之间的数值") from None
    if not minimum <= number <= maximum:
        raise HTTPException(422, f"{label}须为 {minimum}–{maximum} 之间的数值")
    return round(number, 2)


def _bounded_int(value, minimum: int, maximum: int, label: str) -> int:
    """整数范围校验；值是整数的浮点（如 3.0）也接受，布尔值不算数字。"""
    if isinstance(value, bool):
        raise HTTPException(422, f"{label}须为 {minimum}–{maximum} 之间的整数")
    if isinstance(value, int):
        number = value
    elif isinstance(value, float) and value.is_integer():
        number = int(value)
    else:
        raise HTTPException(422, f"{label}须为 {minimum}–{maximum} 之间的整数")
    if not minimum <= number <= maximum:
        raise HTTPException(422, f"{label}须为 {minimum}–{maximum} 之间的整数")
    return number


def _edge_value(value, pattern, limit: int, suffix: str, label: str) -> str:
    if not isinstance(value, str):
        raise HTTPException(422, f"{label}须形如 +5{suffix}（-{limit}{suffix} 到 +{limit}{suffix}）")
    match = pattern.fullmatch(value.strip())
    if match is None or int(match.group(1)) > limit:
        raise HTTPException(422, f"{label}须形如 +5{suffix}（-{limit}{suffix} 到 +{limit}{suffix}）")
    return value.strip()


async def audition(pid: str, owner: str, *, item_id: str, text: str, variants: list[dict]) -> dict:
    project = await store.get_project(pid, owner)
    _require_setup(project)
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_AUDITION_TEXT:
        raise HTTPException(422, f"试听台词须为 1–{MAX_AUDITION_TEXT} 字")
    if not variants or len(variants) > MAX_AUDITION_VARIANTS:
        raise HTTPException(422, f"每次最多 {MAX_AUDITION_VARIANTS} 个声线方案")
    episodes = await breakdown_plan.get_episodes(pid, owner)
    async with store.connection() as db:
        item, bible = await _item_with_bible(db, item_id, owner, pid)
    if is_orphaned(bible, episodes.get("breakdown_id")):
        raise HTTPException(409, f"{item['name']} 已不在当前总表，不能试听")
    if item["kind"] != "character":
        raise HTTPException(409, "声线只针对人物条目")
    specs = [_validate_variant(variant) for variant in variants]
    engines = {spec["engine"] for spec in specs}
    # 豆包没配 Key 时直接 503；这两项预检都必须在任何付费请求之前完成。
    if "doubao" in engines and not casting_jobs.doubao_configured():
        raise HTTPException(503, "未配置 VOLC_SPEECH_API_KEY")
    # 豆包返回 mp3、CosyVoice 返回 wav，都必须经 ffmpeg / ffprobe 处理。
    if engines & {"cosyvoice", "doubao"}:
        missing = [name for name in AUDIO_TOOLS if shutil.which(name) is None]
        if missing:
            label = "豆包" if "doubao" in engines else "CosyVoice"
            raise HTTPException(503, f"服务器缺少 {'/'.join(missing)}，暂时无法合成 {label} 试听")
    entries = []
    for spec in specs:
        amount = pricing.money(pricing.estimate_speech(len(text.strip()), spec["engine"])["amount"])
        entries.append({"item_id": item_id, "media_provider": spec["engine"], "reserved_amount": amount,
                        "params": {"item_id": item_id, "text": text.strip(), "spec": spec}})
    await casting_jobs.create_jobs(project, owner, kind="tts", media_provider=None, quote_id=None, entries=entries)
    return await state(pid, owner)


async def approve_voice(item_id: str, owner: str, asset_id: str, *, baseline: str | None = None) -> dict:
    async with store.connection(transaction=True) as db:
        item = await _item_or_404(db, item_id, owner)
        asset = await store._one(db, "SELECT * FROM studio_assets WHERE id=? AND owner=? AND archived=0",
                                 (asset_id, owner))
        if asset is None or asset["item_id"] != item_id or asset["role"] != "audition" or asset["kind"] != "audio":
            raise HTTPException(404, "Not Found")
        spec = (_load(asset.get("meta"), {}) or {}).get("spec")
        if not isinstance(spec, dict) or not spec:
            raise HTTPException(409, "该试听没有可定档的声线方案")
        direction = spec.get("direction") or None
        if baseline is None or not str(baseline).strip():
            baseline = direction
        else:
            baseline = str(baseline).strip()
            if len(baseline) > MAX_DIRECTION:
                raise HTTPException(422, f"角色基调最多 {MAX_DIRECTION} 字")
        payload = _load(item.get("spec_json"), {}) or {}
        payload["voice"] = {**spec, "direction": direction, "baseline": baseline or None}
        await db.execute("UPDATE studio_items SET voice_asset_id=?,spec_json=?,updated_at=? WHERE id=? AND owner=?",
                         (asset_id, store._json(payload), store.utcnow(), item_id, owner))
        item = await _item_or_404(db, item_id, owner)
        return await _single_item(db, item, owner)


def voice_catalog() -> dict:
    return {"voices": casting_jobs.voice_catalog(), "fx": casting_jobs.fx_levels()}
