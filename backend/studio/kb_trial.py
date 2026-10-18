"""导演知识库试拆：报价、确认、两模式执行、查询。

审核任务先以占位行预留额度，等对应模式的 shot_plan 成功后才转成 brain 任务执行，
避免调度器在分镜尚未产出时提前发出审核请求。
"""
from __future__ import annotations

import asyncio
from datetime import timedelta
from decimal import Decimal
import hashlib
import inspect
import json
import uuid

from fastapi import HTTPException

from . import brain_jobs, cross_review, pricing, spend, store
from .config import get_settings
from utils.background_tasks import create_background_task


MODES = ("with_kb", "without_kb")
REVIEW_PROVIDERS = ("claude", "qwen", "deepseek", "off")
CONTENT_SCENE_TYPES = (
    "dialogue", "confrontation", "fight", "chase", "reveal", "monologue", "flashback",
    "ensemble", "montage", "establishing", "twist", "intimacy", "phone-call",
    "process-closeup", "explainer", "scare", "investigation",
)
POSITION_SCENE_TYPES = ("opening-hook", "cliffhanger")
PACES = ("fast", "mid", "slow")
REALISMS = ("photoreal", "anime", "3d")
SETTINGS = ("interior", "exterior", "mixed")
SENSITIVE = ("face_closeup", "structure", "material", "giant_offscreen", "ip_risk")
CARD_TYPES = ("grammar", "scene", "model", "negative")
EXEMPLAR_KINDS = ("good", "bad")
DEFAULT_REVIEW_PROVIDER = "qwen"
DEFAULT_MODEL = {"qwen": "qwen3.8-max"}


def _default_model(provider: str) -> str | None:
    if provider == "deepseek":
        return get_settings().deepseek_model
    return DEFAULT_MODEL.get(provider)
ROLE_NAMES = {
    ("with_kb", "shot_plan"): "导演拆镜（带知识库）",
    ("without_kb", "shot_plan"): "导演拆镜（不带知识库）",
    ("with_kb", "cross_review"): "交叉审核（带知识库）",
    ("without_kb", "cross_review"): "交叉审核（不带知识库）",
}


# ---------------------------------------------------------------------------
# 跨块适配：A 的 loader / retrieval / lint / stats 与 store 读接口
# ---------------------------------------------------------------------------

async def _maybe_await(value):
    return await value if inspect.isawaitable(value) else value


def _cards_result(value) -> list[dict]:
    if isinstance(value, tuple):
        value = value[0]
    if isinstance(value, dict):
        if "id" in value and "type" in value:
            return [value]
        if isinstance(value.get("cards"), (list, tuple, dict)):
            return _cards_result(value["cards"])
        return [card for card in value.values() if isinstance(card, dict)]
    if isinstance(value, (list, tuple)):
        return [card for card in value if isinstance(card, dict)]
    return []


def _fallback_cards() -> list[dict]:
    """仅为兼容 A 尚未落盘的并行期；A 的 loader 存在时永远优先使用它。"""
    import yaml
    from pathlib import Path
    root = Path(__file__).with_name("director_kb") / "cards"
    cards = []
    for path in sorted(root.glob("*/*.yaml")):
        try:
            card = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(card, dict):
            card.setdefault("id", path.stem)
            cards.append(card)
    return cards


async def _all_cards() -> list[dict]:
    try:
        from .director_kb import loader
    except ImportError:
        return _fallback_cards()
    for name in ("load_cards", "load_all", "all_cards", "cards"):
        value = getattr(loader, name, None)
        if callable(value):
            value = await _maybe_await(value())
            cards = _cards_result(value)
            if cards:
                return cards
        elif isinstance(value, (list, tuple, dict)):
            cards = _cards_result(value)
            if cards:
                return cards
    cards = _fallback_cards()
    return cards


def _card_public(card: dict) -> dict:
    tags = card.get("tags")
    return {"id": card.get("id"), "type": card.get("type"), "title": card.get("title"),
            "summary": card.get("summary"), "tags": list(tags) if isinstance(tags, (list, tuple)) else []}


async def list_cards(*, type: str | None = None, q: str | None = None) -> list[dict]:
    type = type or None
    if type is not None and type not in CARD_TYPES:
        raise HTTPException(422, "卡片类型必须为 grammar、scene、model 或 negative")
    cards = await _all_cards()
    if type is not None:
        cards = [card for card in cards if card.get("type") == type]
    query = (q or "").strip().lower()
    if query:
        def matches(card):
            tags = card.get("tags") if isinstance(card.get("tags"), (list, tuple)) else []
            haystack = " ".join(str(value) for value in (
                card.get("id", ""), card.get("title", ""), card.get("summary", ""), *tags))
            return query in haystack.lower()
        cards = [card for card in cards if matches(card)]
    cards.sort(key=lambda card: (str(card.get("type") or ""), str(card.get("id") or "")))
    return [_card_public(card) for card in cards]


async def get_card(card_id: str) -> dict:
    if not isinstance(card_id, str) or not card_id:
        raise HTTPException(404, "Not Found")
    try:
        from .director_kb import loader
        finder = getattr(loader, "get_card", None) or getattr(loader, "find_card", None)
        if callable(finder):
            card = await _maybe_await(finder(card_id))
            if isinstance(card, dict) and card:
                return card
    except ImportError:
        pass
    for card in await _all_cards():
        if card.get("id") == card_id:
            return card
    raise HTTPException(404, "Not Found")


def _decode_json(value, default):
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str) or not value:
        return default
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return default


def _exemplar_public(row: dict) -> dict:
    return {
        "id": row.get("id"), "project_id": row.get("project_id"), "source": row.get("source"),
        "scene_type": row.get("scene_type"), "kind": row.get("kind"), "reason": row.get("reason") or "",
        "shot": _decode_json(row.get("shot_json"), {}),
        "keyframe_asset_id": row.get("keyframe_asset_id"), "video_model": row.get("video_model"),
        "qc": _decode_json(row.get("qc_json"), {}), "cost_cny": row.get("cost_cny"),
        "tags": _decode_json(row.get("tags_json"), []), "created_at": row.get("created_at"),
        "archived": bool(row.get("archived")),
    }


async def list_exemplars(owner: str, *, scene_type: str | None = None,
                         kind: str | None = None) -> list[dict]:
    scene_type, kind = scene_type or None, kind or None
    if scene_type is not None and scene_type not in CONTENT_SCENE_TYPES:
        raise HTTPException(422, "场景类型必须为 17 类内容卡之一")
    if kind is not None and kind not in EXEMPLAR_KINDS:
        raise HTTPException(422, "案例类型必须为 good 或 bad")
    reader = getattr(store, "list_exemplars", None)
    if callable(reader):
        return await _maybe_await(reader(owner, scene_type=scene_type, kind=kind))
    sql = "SELECT * FROM studio_exemplars WHERE owner=? AND archived=0"
    args = [owner]
    if scene_type is not None:
        sql += " AND scene_type=?"
        args.append(scene_type)
    if kind is not None:
        sql += " AND kind=?"
        args.append(kind)
    sql += " ORDER BY created_at DESC,id DESC"
    async with store.connection() as db:
        return [_exemplar_public(row) for row in await store._many(db, sql, tuple(args))]


async def patch_exemplar(owner: str, exemplar_id: str, fields: dict) -> dict:
    allowed = {"kind", "reason", "archived"}
    if set(fields) - allowed:
        raise HTTPException(422, "只能修改 kind、reason 或归档状态")
    if not fields:
        raise HTTPException(422, "至少需要修改一项")
    updater = getattr(store, "update_exemplar", None)
    if callable(updater):
        return await _maybe_await(updater(owner, exemplar_id, **fields))
    if "kind" in fields and fields["kind"] not in EXEMPLAR_KINDS:
        raise HTTPException(422, "案例类型必须为 good 或 bad")
    if "reason" in fields:
        reason = fields["reason"]
        if not isinstance(reason, str) or len(reason) > 2000:
            raise HTTPException(422, "案例原因须为不超过 2000 字的文本")
    if "archived" in fields and not isinstance(fields["archived"], bool):
        raise HTTPException(422, "归档状态必须为布尔值")
    async with store.connection(transaction=True) as db:
        row = await store._one(db, "SELECT * FROM studio_exemplars WHERE id=? AND owner=?",
                               (exemplar_id, owner))
        if row is None:
            raise HTTPException(404, "Not Found")
        updates = dict(fields)
        if "archived" in updates:
            updates["archived"] = int(updates["archived"])
        await db.execute(f"UPDATE studio_exemplars SET {','.join(key+'=?' for key in updates)} WHERE id=? AND owner=?",
                         (*updates.values(), exemplar_id, owner))
        row = await store._one(db, "SELECT * FROM studio_exemplars WHERE id=? AND owner=?",
                               (exemplar_id, owner))
    return _exemplar_public(row)


async def get_stats(owner: str) -> dict:
    try:
        from .director_kb import stats as stats_module
        reader = (getattr(stats_module, "read_stats", None) or getattr(stats_module, "get_stats", None)
                  or getattr(stats_module, "read", None) or getattr(stats_module, "summary", None))
        if callable(reader):
            result = await _maybe_await(reader(owner))
            if isinstance(result, dict) and "ready" in result:
                return result
    except ImportError:
        pass
    lister = getattr(store, "list_stats", None)
    if callable(lister):
        rows = await _maybe_await(lister(owner))
    else:
        async with store.connection() as db:
            rows = await store._many(db, "SELECT * FROM studio_stats WHERE owner=?", (owner,))
    if not rows:
        return {"ready": False, "episodes": 0}
    episodes = max(int(row.get("episodes") or 0) for row in rows)
    if episodes < 5:
        return {"ready": False, "episodes": episodes}
    entries = []
    for row in sorted(rows, key=lambda item: str(item.get("scene_type") or "")):
        entries.append({
            "scene_type": row.get("scene_type"), "episodes": int(row.get("episodes") or 0),
            "shots": int(row.get("shots") or 0), "avg_shot_s": row.get("avg_shot_s"),
            "shot_size": _decode_json(row.get("shot_size"), _decode_json(row.get("shot_size_json"), {})),
            "camera": _decode_json(row.get("camera"), _decode_json(row.get("camera_json"), {})),
            "updated_at": row.get("updated_at"),
        })
    return {"ready": True, "episodes": episodes, "stats": entries}


async def get_review_provider(pid: str, owner: str) -> str:
    try:
        getter = getattr(store, "get_review_provider", None)
        if callable(getter):
            value = await _maybe_await(getter(pid, owner))
            return value if value in REVIEW_PROVIDERS else DEFAULT_REVIEW_PROVIDER
    except ImportError:
        pass
    async with store.connection() as db:
        project = await store._project(db, pid, owner)
    value = project.get("review_provider")
    return value if value in REVIEW_PROVIDERS else DEFAULT_REVIEW_PROVIDER


async def set_review_provider(pid: str, owner: str, value: str) -> str:
    if value not in REVIEW_PROVIDERS:
        raise HTTPException(422, "审核模型必须为 claude、qwen、deepseek 或 off")
    setter = getattr(store, "set_review_provider", None)
    if callable(setter):
        await _maybe_await(setter(pid, owner, value))
        return value
    async with store.connection(transaction=True) as db:
        await store._project(db, pid, owner)
        async with db.execute("PRAGMA table_info(studio_projects)") as cursor:
            columns = {row[1] for row in await cursor.fetchall()}
        if "review_provider" not in columns:
            raise HTTPException(409, "审核模型字段尚未迁移")
        await db.execute("UPDATE studio_projects SET review_provider=?,updated_at=? WHERE id=? AND owner=?",
                         (value, store.utcnow(), pid, owner))
    return value


def normalize_tags(tags) -> dict:
    if not isinstance(tags, dict):
        raise HTTPException(422, "tags 必须为对象")
    scene_type = tags.get("scene_type")
    if scene_type in POSITION_SCENE_TYPES:
        raise HTTPException(422, "位置卡不能作为主场景类型；请用 17 类内容卡之一")
    if scene_type not in CONTENT_SCENE_TYPES:
        raise HTTPException(422, "场景类型必须为 17 类内容卡之一")
    position = tags.get("position", "body")
    if position not in ("opening", "body", "ending"):
        raise HTTPException(422, "位置必须为 opening、body 或 ending")
    pace = tags.get("pace", "mid")
    if pace not in PACES:
        raise HTTPException(422, "节奏必须为 fast、mid 或 slow")
    emotion = tags.get("emotion", "")
    if not isinstance(emotion, str) or len(emotion) > 20:
        raise HTTPException(422, "情绪须为不超过 20 字的文本")
    cast_count = tags.get("cast_count", 1)
    if isinstance(cast_count, bool) or not isinstance(cast_count, int) or not 1 <= cast_count <= 6:
        raise HTTPException(422, "同场人数必须为 1–6 的整数")
    realism = tags.get("realism", "photoreal")
    if realism not in REALISMS:
        raise HTTPException(422, "写实度必须为 photoreal、anime 或 3d")
    setting = tags.get("setting", "interior")
    if setting not in SETTINGS:
        raise HTTPException(422, "场景环境必须为 interior、exterior 或 mixed")
    sensitive = tags.get("sensitive", [])
    if not isinstance(sensitive, list) or any(item not in SENSITIVE for item in sensitive):
        raise HTTPException(422, "敏感标记只能取 face_closeup / structure / material / giant_offscreen / ip_risk")
    return {"scene_type": scene_type, "position": position, "pace": pace, "emotion": emotion,
            "cast_count": cast_count, "realism": realism, "setting": setting,
            "sensitive": list(dict.fromkeys(sensitive))}


def _select_materials(tags: dict, video_model: str, owner: str) -> dict:
    from .director_kb.retrieval import select_materials
    return select_materials(tags, video_model, owner=owner)


def _lint_shots(shots: list[dict], *, video_model: str, tags: dict) -> list[dict]:
    from .director_kb.lint import lint_shots
    return lint_shots(shots, video_model=video_model, tags=tags)


async def _materials(tags: dict, video_model: str, owner: str) -> dict:
    result = await _maybe_await(_select_materials(tags, video_model, owner))
    if not isinstance(result, dict):
        raise HTTPException(409, "知识库取材料失败")
    text = result.get("text") if isinstance(result.get("text"), str) else ""
    card_ids = result.get("card_ids") if isinstance(result.get("card_ids"), list) else []
    chars = result.get("chars")
    if isinstance(chars, bool) or not isinstance(chars, int):
        chars = len(text)
    return {"text": text, "card_ids": [str(card_id) for card_id in card_ids], "chars": chars}


def _quote_item(provider: str, model: str, task: str, inputs: dict, *, mode: str) -> dict:
    item = brain_jobs._quote_item(provider, model, task, inputs)
    item["mode"], item["role"] = mode, task
    return item


# 审核输入里系统提示、JSON 键名与转义的保守余量；导演输出本身按 shot_plan
# 的 token 上限整额计入，避免把 JSON 结构开销漏在预留之外。
_REVIEW_PACKAGING_CHARS = 512


def _review_quote_item(provider: str, model: str, scene_text: str, *, mode: str) -> dict:
    """审核报价按「原文 + 导演输出上限 + 包装」估输入 token。

    审核时 shots 已知，但报价时模型还没输出；用 shot_plan.max_tokens 作为
    shots 部分的 token 上界，不把 JSON 字符数再乘 1.5 重复放大。
    """
    from math import ceil

    from .brain import estimate_input_chars, system_prompt
    from .brain_tasks import get_task

    review_max = get_task("cross_review").max_tokens
    shot_max = get_task("shot_plan").max_tokens
    packaging_tokens = ceil((len(system_prompt("cross_review"))
                             + _REVIEW_PACKAGING_CHARS) * 1.5)
    input_tokens = ceil(len(scene_text) * 1.5) + shot_max + packaging_tokens
    first = pricing.estimate_brain_tokens(model, input_tokens, review_max)
    repair = pricing.estimate_brain_tokens(
        model, input_tokens + review_max + pricing.REPAIR_OVERHEAD_TOKENS, review_max)
    placeholder = "镜" * max(1, ceil(shot_max / 1.5))
    input_chars = estimate_input_chars(
        "cross_review", cross_review.build_inputs(scene_text, placeholder))
    return {"provider": provider, "task": "cross_review", "model": model,
            "currency": first["currency"], "input_chars": input_chars,
            "amount": float(pricing.money(first["amount"]) + pricing.money(repair["amount"])),
            "first_max": first["amount"], "repair_max": repair["amount"],
            "mode": mode, "role": "cross_review"}


def _public_quote(quote_id: str, expires: str, payload: dict) -> dict:
    lines = []
    sums = {"CNY": Decimal(0), "USD": Decimal(0)}
    for item in payload["items"]:
        amount = pricing.money(item["amount"])
        currency = item.get("currency") if item.get("currency") in {"CNY", "USD"} else "CNY"
        sums[currency] += amount
        lines.append({"item_id": f'{item["mode"]}:{item["role"]}',
                      "name": ROLE_NAMES[(item["mode"], item["role"])],
                      "versions": 1, "currency": currency,
                      "unit": float(amount), "est": float(amount)})
    totals = {currency: float(pricing.money(value)) for currency, value in sums.items()}
    currencies = {line["currency"] for line in lines}
    if len(currencies) == 1:
        currency = next(iter(currencies))
        total = totals[currency]
    else:
        # 混合币种没有可用的换算率：明细逐行带币种，合计只给分币种金额。
        currency, total = "mixed", None
    return {"id": quote_id, "kind": "kb_trial", "items": lines,
            "total": total, "currency": currency, "expires_at": expires,
            "totals": totals}


def _validate_request(scene_text, tags, target_seconds, video_model, modes):
    if not isinstance(scene_text, str) or not scene_text.strip() or len(scene_text) > 3000:
        raise HTTPException(422, "试拆原文须为 1–3000 字")
    clean_tags = normalize_tags(tags)
    if isinstance(target_seconds, bool) or not isinstance(target_seconds, int) or not 10 <= target_seconds <= 120:
        raise HTTPException(422, "目标时长必须为 10–120 的整数秒")
    if video_model not in ("wan", "seedance"):
        raise HTTPException(422, "视频模型必须为 wan 或 seedance")
    if not isinstance(modes, (list, tuple)) or not modes or len(modes) != len(set(modes)):
        raise HTTPException(422, "模式必须是不重复的 with_kb / without_kb")
    if any(mode not in MODES for mode in modes):
        raise HTTPException(422, "模式必须是不重复的 with_kb / without_kb")
    return scene_text, clean_tags, list(modes)


async def _options(owner: str) -> dict:
    from .brain import provider_options
    return {option["id"]: option for option in await provider_options(owner)}


def _require_option(options: dict, provider: str) -> dict:
    option = options.get(provider)
    if option is None:
        raise HTTPException(409, f"导演模型 {provider} 不可用")
    if not option.get("available"):
        raise HTTPException(409, f"{option.get('label', provider)}：{option.get('reason', '不可用')}")
    model = option.get("model")
    if not isinstance(model, str) or not model:
        model = _default_model(provider)
    return {**option, "model": model}


async def quote(pid: str, owner: str, scene_text: str, tags: dict, target_seconds: int,
                video_model: str, modes) -> dict:
    scene_text, clean_tags, modes = _validate_request(scene_text, tags, target_seconds, video_model, modes)
    project = await store.get_project(pid, owner)
    review_provider = await get_review_provider(pid, owner)
    options = await _options(owner)
    director = _require_option(options, project["brain_provider"])
    reviewer = None if review_provider == "off" else _require_option(options, review_provider)

    materials = ({"with_kb": await _materials(clean_tags, video_model, owner)}
                 if "with_kb" in modes else {})
    payload = {
        "kind": "kb_trial", "scene_text": scene_text, "tags": clean_tags,
        "target_seconds": target_seconds, "video_model": video_model, "modes": modes,
        "director_provider": project["brain_provider"], "review_provider": review_provider,
        "materials": materials, "inputs": {},
    }
    items = []
    for mode in modes:
        inputs = {"scene_text": scene_text, "tags": clean_tags,
                  "target_seconds": target_seconds, "video_model": video_model}
        if mode == "with_kb":
            inputs["kb_text"] = materials["with_kb"]["text"]
        payload["inputs"][mode] = inputs
        items.append(_quote_item(project["brain_provider"], director["model"], "shot_plan",
                                 inputs, mode=mode))
        if reviewer is not None:
            # 审核输入还包含该模式的分镜；按导演输出上限估上界，避免预留低于实际。
            items.append(_review_quote_item(review_provider, reviewer["model"], scene_text,
                                            mode=mode))
    payload["items"] = items
    payload["totals"] = brain_jobs._totals(items)

    qid, stamp = str(uuid.uuid4()), store.utcnow()
    expires = (store.parse_time(stamp) + timedelta(minutes=15)).isoformat()
    async with store.connection(transaction=True) as db:
        await store._project(db, pid, owner)
        await spend.check_brain_budget(db, owner, payload["totals"], now=stamp)
        await db.execute("""INSERT INTO studio_quotes(id,project_id,owner,items_json,total_min_cny,
            total_max_cny,params_hash,status,created_at,expires_at) VALUES(?,?,?,?,?,?,?,'open',?,?)""",
                         (qid, pid, owner, store._json(payload), "0",
                          str(pricing.money(payload["totals"].get("CNY", 0))),
                          hashlib.sha256(store._json(payload).encode()).hexdigest(), stamp, expires))
    return _public_quote(qid, expires, payload)


async def _activate(job_id: str, owner: str, *, expected_kind: str) -> bool:
    async with store.connection(transaction=True) as db:
        job = await store._get_job(db, job_id, owner)
        if job is None or job.get("kind") != expected_kind or job.get("status") != "queued":
            return False
        await db.execute("UPDATE studio_jobs SET kind='brain',updated_at=? WHERE id=? AND kind=? AND status='queued'",
                         (store.utcnow(), job_id, expected_kind))
        return True


async def _activate_review(job_id: str, owner: str, inputs: dict, input_chars: int) -> bool:
    async with store.connection(transaction=True) as db:
        job = await store._get_job(db, job_id, owner)
        if job is None or job.get("kind") != "kb_review" or job.get("status") != "queued":
            return False
        await db.execute("""UPDATE studio_jobs SET kind='brain',task='cross_review',params_json=?,
            input_chars=?,updated_at=? WHERE id=? AND kind='kb_review' AND status='queued'""",
                         (store._json({"inputs": inputs}), input_chars, store.utcnow(), job_id))
        return True


async def _cancel_placeholder(job_id: str, owner: str) -> None:
    async with store.connection(transaction=True) as db:
        job = await store._get_job(db, job_id, owner)
        if job is not None and job.get("kind") == "kb_review" and job.get("status") == "queued":
            # brain 的终态结算会同时清掉 reserved_amount / reserved_cny。
            await brain_jobs.transition(db, job, "queued", {
                "status": "cancelled", "error_code": "review_not_needed",
                "error_message": "分镜没有成功产出，审核未发出"})


async def _cancel_quote_placeholders(quote_id: str) -> None:
    """项目已归档时只清排队中的占位任务及其预留，绝不发上游请求。

    归档项目的 brain_jobs.transition 会拒绝所有状态变化，所以这里用等价的安全写法：
    只匹配本报价下仍为 queued 的 kb_shot / kb_review。
    """
    stamp = store.utcnow()
    async with store.connection(transaction=True) as db:
        await db.execute("""UPDATE studio_jobs SET status='cancelled',
            error_code='project_archived', error_message='项目已归档，试拆未再发出',
            reserved_amount='0', reserved_cny='0', actual_amount='0',
            actual_cny=CASE WHEN currency='CNY' THEN '0' ELSE NULL END,
            finished_at=COALESCE(finished_at,?), updated_at=?
            WHERE quote_id=? AND kind IN ('kb_shot','kb_review') AND status='queued'""",
                         (stamp, stamp, quote_id))


async def _job_or_none(owner: str, job_id: str | None) -> dict | None:
    if not job_id:
        return None
    try:
        return await store.get_job(job_id, owner)
    except HTTPException:
        return None


async def _final_attempt(owner: str, job_id: str | None) -> dict | None:
    """沿 studio_jobs.parent_job_id 找到最新一次尝试，包括单独计费的修正。

    修正任务由 brain_jobs 创建为 parent_job_id=原任务、attempt+1 的子任务；
    原任务会先落成 invalid_output，因此判断结果与等待终态都必须看子任务。
    """
    if not job_id:
        return None
    async with store.connection() as db:
        job = await store._get_job(db, job_id, owner)
        if job is None:
            return None
        best, current, seen = job, job, {job["id"]}
        while True:
            children = await store._many(db, """SELECT * FROM studio_jobs
                WHERE parent_job_id=? AND owner=?
                ORDER BY attempt DESC,created_at DESC,id DESC""", (current["id"], owner))
            child = next((item for item in children if item.get("id") not in seen), None)
            if child is None:
                return best
            # attempt 可能因旧数据异常而缺失，链上的子任务仍算更新的一次尝试。
            seen.add(child["id"])
            best, current = child, child


async def _wait_terminal(job_id: str, owner: str) -> dict | None:
    """等任务及其修正尝试到终态；调度器可能同时持有，不能按墙钟放弃。"""
    while True:
        job = await _final_attempt(owner, job_id)
        if job is None:
            return None
        if job.get("status") not in {"queued", "running", "submitting"}:
            return job
        await asyncio.sleep(.25)


async def _run_trial(trial_id: str) -> None:
    async with store.connection() as db:
        row = await store._one(db, "SELECT * FROM studio_quotes WHERE id=?", (trial_id,))
        project = None
        if row is not None:
            project = await store._one(db, "SELECT id,archived FROM studio_projects WHERE id=? AND owner=?",
                                       (row["project_id"], row["owner"]))
    if row is None or row.get("status") != "confirmed" or not isinstance(row.get("items"), dict) \
            or row["items"].get("kind") != "kb_trial":
        return
    owner, payload = row["owner"], row["items"]
    if project is None or project.get("archived"):
        await _cancel_quote_placeholders(trial_id)
        return
    for mode in payload.get("modes") or []:
        shot_job_id = (payload.get("shot_jobs") or {}).get(mode)
        if not shot_job_id:
            continue
        review_job_id = (payload.get("review_jobs") or {}).get(mode)
        # 续跑：只有仍停在 kb_shot/queued 的占位任务才需要激活并执行；
        # 已经是 brain 的任务（排队、在途或终态）交给等待逻辑，绝不重发。
        shot_job = await _job_or_none(owner, shot_job_id)
        if shot_job is not None and shot_job.get("kind") == "kb_shot" \
                and shot_job.get("status") == "queued":
            if await _activate(shot_job_id, owner, expected_kind="kb_shot"):
                try:
                    await brain_jobs._background(shot_job_id)
                except Exception:
                    # _background 已经把失败/不确定写进任务行；这里只负责继续收尾。
                    pass
        shot_job = await _wait_terminal(shot_job_id, owner)
        if shot_job is None or shot_job.get("status") != "succeeded" or not review_job_id:
            if review_job_id:
                await _cancel_placeholder(review_job_id, owner)
            continue
        review_job = await _job_or_none(owner, review_job_id)
        if review_job is None:
            continue
        if review_job.get("kind") == "kb_review" and review_job.get("status") == "queued":
            output = shot_job.get("output") if isinstance(shot_job.get("output"), dict) else {}
            shots = output.get("shots") if isinstance(output.get("shots"), list) else []
            inputs = cross_review.build_inputs(payload["scene_text"], shots, adaptation_scale="适度")
            if not await _activate_review(review_job_id, owner, inputs, cross_review_input_chars(inputs)):
                # 并发续跑时另一方可能已激活；本次不重复发审核。
                continue
            try:
                await brain_jobs._background(review_job_id)
            except Exception:
                pass
        await _wait_terminal(review_job_id, owner)


def cross_review_input_chars(inputs: dict) -> int:
    from .brain import estimate_input_chars
    return estimate_input_chars("cross_review", inputs)


async def start(pid: str, owner: str, quote_id: str) -> dict:
    if not isinstance(quote_id, str) or not quote_id.strip() or len(quote_id) > 100:
        raise HTTPException(422, "请提供有效的报价编号")
    async with store.connection(transaction=True) as db:
        project = await store._project(db, pid, owner)
        row = await store._one(db, "SELECT * FROM studio_quotes WHERE id=? AND project_id=? AND owner=?",
                               (quote_id, pid, owner))
        if row is None:
            raise HTTPException(404, "Not Found")
        payload = row.get("items")
        if not isinstance(payload, dict) or payload.get("kind") != "kb_trial":
            raise HTTPException(409, "报价用途不匹配")
        if row["status"] != "open":
            raise HTTPException(409, "报价只能确认一次，不能重复确认")
        stamp = store.utcnow()
        if store.parse_time(row["expires_at"]) <= store.parse_time(stamp):
            raise HTTPException(409, "报价已过期，请重新报价")
        await spend.check_brain_budget(db, owner, payload["totals"], now=stamp)
        await db.execute("UPDATE studio_quotes SET status='confirmed',confirmed_at=? WHERE id=? AND status='open'",
                         (stamp, quote_id))
        shot_jobs, review_jobs = {}, {}
        mode_roles = {}
        for item in payload["items"]:
            mode_roles.setdefault(item["mode"], {})[item["role"]] = item
        for mode in payload["modes"]:
            item = mode_roles[mode]["shot_plan"]
            job = await brain_jobs._insert_job(db, pid, owner, item, payload["inputs"][mode],
                                              quote_id, quote_id=quote_id)
            shot_jobs[mode] = job["id"]
            await db.execute("UPDATE studio_jobs SET kind='kb_shot',input_chars=? WHERE id=?",
                             (item.get("input_chars") or 0, job["id"]))
            review_item = mode_roles[mode].get("cross_review")
            if review_item is not None:
                placeholder = cross_review.build_inputs(payload["scene_text"], [])
                review_job = await brain_jobs._insert_job(db, pid, owner, review_item, placeholder,
                                                          quote_id, quote_id=quote_id)
                review_jobs[mode] = review_job["id"]
                await db.execute("UPDATE studio_jobs SET kind='kb_review',input_chars=0 WHERE id=?",
                                 (review_job["id"],))
        payload["shot_jobs"], payload["review_jobs"] = shot_jobs, review_jobs
        payload["started_at"] = stamp
        await db.execute("UPDATE studio_quotes SET items_json=? WHERE id=? AND status='confirmed'",
                         (store._json(payload), quote_id))
    _schedule(quote_id)
    return {"id": quote_id, "trial_id": quote_id, "status": "queued", "modes": payload["modes"],
            "review_provider": payload.get("review_provider")}


def _schedule(trial_id: str) -> None:
    create_background_task(_run_trial(trial_id), label=f"studio-kb-trial-{trial_id}")


def _model_card_missing(tags: dict, video_model: str) -> bool:
    """该视频模型 + 写实度没有对应模型卡时为 True（目前只有 3d 会命中）。"""
    try:
        from .director_kb import loader
        cards = loader.load_cards_of_type("model")
    except Exception:
        # 卡片不可用时详情仍应可读；lint 的模型规则同样会自行跳过。
        return False
    family = [card for card in cards
              if str(card.get("model") or "").startswith(f"{video_model}-")]
    realism = tags.get("realism")
    if any(card.get("style") == realism for card in family):
        return False
    return not any(card.get("style") == "any" for card in family)


async def get_trial(pid: str, owner: str, trial_id: str) -> dict:
    async with store.connection() as db:
        await store._project(db, pid, owner)
        row = await store._one(db, "SELECT * FROM studio_quotes WHERE id=? AND project_id=? AND owner=?",
                               (trial_id, pid, owner))
        if row is None or not isinstance(row.get("items"), dict) or row["items"].get("kind") != "kb_trial":
            raise HTTPException(404, "Not Found")
        payload = row["items"]
    shot_jobs = {mode: await _final_attempt(owner, job_id)
                 for mode, job_id in (payload.get("shot_jobs") or {}).items()}
    review_jobs = {mode: await _final_attempt(owner, job_id)
                   for mode, job_id in (payload.get("review_jobs") or {}).items()}
    model_card_missing = _model_card_missing(payload.get("tags") or {}, payload.get("video_model"))
    entries, reviews = {}, {}
    for mode in MODES:
        if mode not in (payload.get("modes") or []):
            entries[mode] = None
            reviews[mode] = None
            continue
        job = shot_jobs.get(mode)
        status = job.get("status") if isinstance(job, dict) else "not_started"
        output = job.get("output") if isinstance(job, dict) and status == "succeeded" and isinstance(job.get("output"), dict) else {}
        shots = output.get("shots") if isinstance(output.get("shots"), list) else []
        material = (payload.get("materials") or {}).get(mode) or {}
        lint = []
        if shots:
            lint = await asyncio.to_thread(_lint_shots, shots, video_model=payload["video_model"],
                                           tags=payload["tags"])
        review = cross_review.review_record(review_jobs.get(mode))
        injected_chars = int(material.get("chars") or 0)
        entries[mode] = {
            "mode": mode, "status": status, "shots": shots,
            "template_id": output.get("template_id"), "deviations": output.get("deviations") or "",
            "card_ids": list(material.get("card_ids") or []),
            "injected_chars": injected_chars, "chars": injected_chars,
            "lint": lint, "review": review, "model_card_missing": model_card_missing,
            "error_code": job.get("error_code") if isinstance(job, dict) else None,
            "error_message": job.get("error_message") if isinstance(job, dict) else None,
        }
        reviews[mode] = review
    statuses = [entry["status"] for entry in entries.values() if entry]
    review_pending = any(
        isinstance(job, dict) and job.get("kind") in {"brain", "kb_review"}
        and job.get("status") in {"queued", "running", "submitting"}
        for job in review_jobs.values())
    if not (payload.get("shot_jobs") or {}):
        overall = "open"
    elif any(status in {"queued", "running", "not_started"} for status in statuses) or review_pending:
        overall = "running"
    elif statuses and all(status == "succeeded" for status in statuses):
        overall = "done"
    elif any(status == "succeeded" for status in statuses):
        overall = "partial"
    else:
        overall = "failed"
    return {"id": trial_id, "trial_id": trial_id, "kind": "kb_trial", "status": overall,
            "modes": payload.get("modes") or [], "tags": payload.get("tags"),
            "target_seconds": payload.get("target_seconds"), "video_model": payload.get("video_model"),
            "review_provider": payload.get("review_provider"), **entries, "review": reviews}
