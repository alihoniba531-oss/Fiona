"""导演调用的预检、独立账本与后台执行；付费重试仅限一次显式输出修正。"""
from __future__ import annotations

import asyncio
from contextvars import ContextVar
from decimal import Decimal
import hashlib
import json
import uuid
import weakref

from fastapi import HTTPException

from . import pricing, spend, store
from utils.background_tasks import create_background_task

PROVIDERS = ("claude", "qwen", "deepseek")
TRIAL_TASKS = ("read_through", "style_proposals", "bible_extract")
_ACTIVE: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()
_SEMAPHORES: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()
_BOUND_JOB: ContextVar[str | None] = ContextVar("studio_brain_job", default=None)
_CALL_JOB: ContextVar[str | None] = ContextVar("studio_brain_call", default=None)


def _state():
    loop = asyncio.get_running_loop()
    return _ACTIVE.setdefault(loop, {}), _SEMAPHORES.setdefault(loop, {})


def _totals(items):
    result = {"CNY": Decimal(0), "USD": Decimal(0)}
    for item in items:
        result[item["currency"]] += pricing.money(item["amount"])
    return {currency: float(pricing.money(value)) for currency, value in result.items()}


async def patch_project(pid, owner, provider):
    if provider not in PROVIDERS:
        raise HTTPException(422, "导演模型必须为 claude、qwen 或 deepseek")
    async with store.connection(transaction=True) as db:
        await store._project(db, pid, owner)
        await db.execute("UPDATE studio_projects SET brain_provider=?,updated_at=? WHERE id=? AND owner=?",
                         (provider, store.utcnow(), pid, owner))
        return await store._project(db, pid, owner)


def _input_chars(task, inputs):
    # 完整 schema 与提示指令也占输入；序列化后的转义字符纳入预留。
    from .brain import estimate_input_chars
    return estimate_input_chars(task, inputs)


def _quote_item(provider, model, task, inputs, *, images=None):
    from .brain_tasks import get_task
    spec = get_task(task)
    chars = _input_chars(task, inputs)
    vision = 16384 * _image_count(images)
    first = pricing.estimate_brain(model, chars, spec.max_tokens, image_tokens=vision)
    repair = pricing.estimate_brain_repair(model, chars, spec.max_tokens, image_tokens=vision)
    return {"provider": provider, "task": task, "model": model, **first,
            "input_chars": chars, "repair_max": repair["amount"],
            "amount": float(pricing.money(first["amount"]) + pricing.money(repair["amount"])),
            "first_max": first["amount"]}


def _image_count(images):
    return len(images) if isinstance(images, (list, tuple)) else int(images is not None)


async def trial_plan(pid, owner, text, tasks, providers):
    from .brain import provider_options
    project = await store.get_project(pid, owner)
    if not isinstance(text, str) or not text.strip() or not 1 <= len(text) <= 20000:
        raise HTTPException(422, "素材须为 1–20000 字")
    if not tasks or len(tasks) != len(set(tasks)) or any(task not in TRIAL_TASKS for task in tasks):
        raise HTTPException(422, "请选择不重复的剧本试读任务")
    if providers not in {"current", "all"}:
        raise HTTPException(422, "提供方选项须为 current 或 all")
    choices = PROVIDERS if providers == "all" else (project["brain_provider"],)
    options = {option["id"]: option for option in await provider_options(owner)}
    errors, items = [], []
    for provider in choices:
        option = options[provider]
        for task in tasks:
            if not option["available"]:
                errors.append(f"{option['label']} / {task}：{option.get('reason', '不可用')}")
                continue
            try:
                items.append(_quote_item(provider, option["model"], task, {"text": text}))
            except HTTPException as exc:
                errors.append(f"{option['label']} / {task}：{exc.detail}")
    if errors:
        raise HTTPException(409, "；".join(errors))
    return items


async def quote_trial(pid, owner, text, tasks, providers):
    items = await trial_plan(pid, owner, text, tasks, providers)
    async with store.connection(transaction=True) as db:
        await store._project(db, pid, owner)
        await spend.check_brain_budget(db, owner, _totals(items))
    return {"items": items, "totals": _totals(items)}


async def _insert_job(db, pid, owner, item, inputs, group_id, *, quote_id, parent=None, images=None, chunk_id=None):
    from database import WatchPrivateText
    stamp, jid = store.utcnow(), str(uuid.uuid4())
    amount = item["first_max"]
    # 旧库的 provider CHECK 不能用 ADD COLUMN 扩充，原列仅留兼容占位；
    # kind=brain 时新增 brain_provider 为权威提供方，_row 对外统一 provider。
    fields = {
        "id": jid, "project_id": pid, "owner": owner, "kind": "brain", "provider": "wan",
        "brain_provider": item["provider"], "model": item["model"], "task": item["task"],
        "params_json": WatchPrivateText(await asyncio.to_thread(store._json, {"inputs": inputs, **({"breakdown_chunk": chunk_id} if chunk_id else {})})),
        "fingerprint": hashlib.sha256(jid.encode()).hexdigest(),
        "quote_id": quote_id, "quote_item_id": jid, "group_id": group_id, "status": "queued",
        "currency": item["currency"], "reserved_amount": str(pricing.money(amount)),
        "reserved_cny": str(pricing.money(amount if item["currency"] == "CNY" else 0)),
        "est_min_cny": "0", "est_max_cny": str(pricing.money(amount if item["currency"] == "CNY" else 0)),
        "input_chars": len(inputs.get("text", "")) if isinstance(inputs, dict) else len(inputs),
        "created_at": stamp, "updated_at": stamp,
        "confirmed_day": spend.shanghai_day(stamp), "confirmed_month": spend.shanghai_month(stamp),
        "attempt": 2 if parent else 1, "parent_job_id": parent,
    }
    columns = ",".join(fields)
    await db.execute(f"INSERT INTO studio_jobs({columns}) VALUES({','.join('?' for _ in fields)})", tuple(fields.values()))
    if parent:
        # A schema repair remains the same logical chunk, with a new paid attempt.
        await db.execute("UPDATE studio_chunks SET job_id=?,updated_at=? WHERE job_id=?",
                         (jid, stamp, parent))
    return await store._get_job(db, jid, owner)


async def _new_quote(db, pid, owner, group_id):
    stamp = store.utcnow()
    await db.execute("""INSERT INTO studio_quotes(id,project_id,owner,items_json,total_min_cny,total_max_cny,
        params_hash,status,created_at,expires_at,confirmed_at) VALUES(?,?,?,'[]','0','0',?,'confirmed',?,?,?)""",
                     (group_id, pid, owner, group_id, stamp, stamp, stamp))


async def start_trial(pid, owner, text, tasks, providers):
    items = await trial_plan(pid, owner, text, tasks, providers)
    gid = str(uuid.uuid4())
    async with store.connection(transaction=True) as db:
        await store._project(db, pid, owner)
        await spend.check_brain_budget(db, owner, _totals(items))
        await _new_quote(db, pid, owner, gid)
        jobs = [await _insert_job(db, pid, owner, item, {"text": text}, gid, quote_id=gid) for item in items]
    for job in jobs:
        _schedule(job["id"])
    return {"group_id": gid, "jobs": jobs}


async def group(pid, owner, gid):
    async with store.connection() as db:
        await store._project(db, pid, owner)
        jobs = await store._many(db, """SELECT * FROM studio_jobs WHERE project_id=? AND owner=?
            AND kind='brain' AND group_id=? ORDER BY created_at,id""", (pid, owner, gid))
    if not jobs:
        raise HTTPException(404, "Not Found")
    billed = [{"currency": job["currency"], "amount": job["cost"]["amount"] or 0} for job in jobs]
    return {"group_id": gid, "jobs": jobs, "totals": _totals(billed)}


async def transition(db, job, expected_status, updates, *, run_token=None):
    expected = {expected_status} if isinstance(expected_status, str) else set(expected_status)
    if job["status"] not in expected or (run_token is not None and job.get("run_token") != run_token):
        return False
    if await store._one(db, "SELECT id FROM studio_projects WHERE id=? AND owner=? AND archived=0",
                        (job["project_id"], job["owner"])) is None:
        return False
    updates = dict(updates)
    allowed = {"queued": {"running", "cancelled", "rejected"},
               "running": {"succeeded", "failed", "invalid_output", "uncertain", "rejected"},
               "submitting": {"uncertain"}, "uncertain": {"released"}}
    target = updates.get("status", job["status"])
    if target != job["status"] and target not in allowed.get(job["status"], set()):
        raise ValueError("不允许的导演任务状态转换")
    permitted = {"status", "error_code", "error_message", "run_token", "submitted_at", "usage_json",
                 "result_json", "warnings_json", "actual_amount", "latency_s", "stop_reason", "repaired",
                 "finished_at", "updated_at", "needs_recheck", "next_poll_at", "poll_requested", "model"}
    if set(updates) - permitted:
        raise ValueError("未知导演任务更新字段")
    if target in {"succeeded", "failed", "invalid_output", "rejected", "cancelled", "released"}:
        actual = updates.get("actual_amount", job.get("actual_amount"))
        if target in spend.ZERO_STATUSES:
            actual = 0
        updates["actual_amount"] = None if actual is None else str(pricing.money(actual))
        updates["actual_cny"] = (str(pricing.money(actual)) if job["currency"] == "CNY" and actual is not None else None)
        updates["reserved_amount"] = str(pricing.money(0 if actual is not None else job["reserved_amount"]))
        updates["reserved_cny"] = str(pricing.money(0 if actual is not None else job["reserved_cny"]))
        updates.setdefault("finished_at", store.utcnow())
    if target == "invalid_output":
        updates["status"] = "failed"
        updates.setdefault("error_code", "invalid_output")
    for key in ("usage_json", "result_json", "warnings_json"):
        if key in updates and updates[key] is not None and not isinstance(updates[key], str):
            updates[key] = await asyncio.to_thread(store._json, updates[key])
        if key in updates and updates[key] is not None:
            from database import WatchPrivateText
            updates[key] = WatchPrivateText(updates[key])
    updates["updated_at"] = store.utcnow()
    raw_status = "failed" if job["status"] == "invalid_output" else job["status"]
    async with db.execute(f"UPDATE studio_jobs SET {','.join(key+'=?' for key in updates)} WHERE id=? AND status=?",
                          (*updates.values(), job["id"], raw_status)) as cursor:
        return cursor.rowcount == 1


def _schedule(jid):
    active, _ = _state()
    if jid not in active:
        task = create_background_task(_background(jid), label=f"studio-brain-{jid}")
        active[jid] = task
        task.add_done_callback(lambda done: active.pop(jid, None))


async def dispatch_queued():
    async with store.connection() as db:
        jobs = await store._many(db, """SELECT j.id FROM studio_jobs j LEFT JOIN studio_chunks c ON c.job_id=j.id
            WHERE j.kind='brain' AND j.status='queued' AND (c.id IS NULL OR c.status='queued') ORDER BY j.created_at,j.id""")
    for job in jobs:
        _schedule(job["id"])


async def _background(jid):
    from .brain import BrainProviderError
    from .breakdown import prepare_job, refresh_for_job
    job = await store.get_job(jid)
    token = _BOUND_JOB.set(jid)
    try:
        inputs = (await prepare_job(jid, job['owner']) if job.get('params', {}).get('breakdown_chunk')
                  else job['params']['inputs'])
        await run_brain(job["task"], inputs, provider=job["provider"], username=job["owner"])
    except (BrainProviderError, HTTPException):
        # Preparation failures occur before a request and can release their hold.
        # A submitted/running job has already been settled by run_brain.
        await store.cas_job(jid, 'queued', {'status': 'rejected', 'error_code': 'input_unavailable',
            'error_message': '拆解输入无法读取或批次已更新，未发起付费请求'})
    except Exception:
        await store.cas_job(jid, 'queued', {'status': 'rejected', 'error_code': 'input_unavailable',
            'error_message': '拆解输入无法读取，未发起付费请求'})
    finally:
        _BOUND_JOB.reset(token)
        await refresh_for_job(jid)


async def run_brain(task, inputs, *, provider, username, images=None):
    from .brain_tasks import get_task
    get_task(task)
    _, semaphores = _state()
    lane = "qwen" if images and provider != "claude" else provider
    token = _CALL_JOB.set(None)
    try:
        async with semaphores.setdefault(lane, asyncio.Semaphore(3)):
            return await _execute_brain(task, inputs, provider=provider, username=username, images=images)
    except BaseException as exc:
        jid = _CALL_JOB.get()
        if jid is not None:
            await store.cas_job(jid, "running", {"status": "uncertain",
                "error_code": "submission_interrupted" if isinstance(exc, asyncio.CancelledError) else "submission_error",
                "error_message": "调用结果不确定，可能已扣费，请核对账单后手动释放"})
        raise
    finally:
        _CALL_JOB.reset(token)


async def _execute_brain(task, inputs, *, provider, username, images=None):
    from .brain import BrainProviderError, BrainResult, InvalidBrainOutput, get_provider, validate_reply
    from .brain_tasks import get_task
    jid = _BOUND_JOB.get()
    adapter = None
    if jid is None:
        adapter = await get_provider(provider, username, images=images)
        item = _quote_item(provider, adapter.model, task, inputs, images=images)
        project = await store.create_project(username, "导演模型", "16:9")
        gid = str(uuid.uuid4())
        async with store.connection(transaction=True) as db:
            await spend.check_brain_budget(db, username, _totals([item]))
            await _new_quote(db, project["id"], username, gid)
            job = await _insert_job(db, project["id"], username, item, inputs, gid, quote_id=gid)
        jid = job["id"]
    job = await store.get_job(jid, username)
    requested_model = job["model"]
    if not await store.cas_job(jid, "queued", {"status": "running", "run_token": uuid.uuid4().hex,
                                              "submitted_at": store.utcnow()}):
        raise HTTPException(409, "导演任务已被处理")
    _CALL_JOB.set(jid)
    first_jid, repair, all_usage, all_cost, total_latency = jid, None, {}, Decimal(0), 0.0
    unknown_cost, all_warnings = False, []
    for attempt in (1, 2):
        if attempt == 2 and job.get('params', {}).get('breakdown_chunk'):
            async with store.connection(transaction=True) as db:
                current = await store._one(db, """SELECT b.status FROM studio_chunks c
                    JOIN studio_breakdowns b ON b.id=c.breakdown_id WHERE c.job_id=?""", (jid,))
                if current and current['status'] == 'cancelled':
                    await transition(db, await store._get_job(db, jid, username), 'running', {
                        'status': 'rejected', 'error_code': 'breakdown_cancelled',
                        'error_message': '拆解已取消，修正请求未发出'})
                    raise BrainProviderError('rejected', 'breakdown_cancelled', '拆解已取消，修正请求未发出')
        try:
            if adapter is None:
                adapter = await get_provider(provider, username, images=images)
                adapter.model = job["model"]  # 排队后改默认模型不改变已经确认的调用。
            if images and provider != "claude" and hasattr(adapter, "pin_vision_model"):
                # 已完成报价的调用锁定视觉模型；下次新调用再读取最新配置。
                adapter.pin_vision_model(requested_model)
            reply = await adapter.call(task, inputs, images=images, repair=repair)
        except HTTPException as exc:
            if exc.status_code == 409:
                # 视觉价目在预检后被移除时，适配层仍在 SDK 前拒绝，不能记为可能扣费。
                await store.cas_job(jid, "running", {"status": "rejected", "error_code": "vision_price_unavailable",
                    "error_message": str(exc.detail)})
            raise
        except BrainProviderError as exc:
            failure = {"status": exc.status, "error_code": exc.code, "error_message": exc.message}
            if exc.status == "failed" and getattr(exc, "usage", None) is not None:
                actual_model = getattr(exc, "model", None) or requested_model
                cost, warnings = pricing.settle_brain_response(actual_model, exc.usage,
                    currency=job["currency"], reserved_amount=job["reserved_amount"])
                failure.update(usage_json=exc.usage, actual_amount=cost["amount"], model=actual_model,
                    warnings_json=warnings, stop_reason=getattr(exc, "stop_reason", None),
                    latency_s=getattr(exc, "latency_s", None), repaired=attempt == 2)
            await store.cas_job(jid, "running", failure)
            raise
        actual_model = reply.model or requested_model
        cost, price_warnings = pricing.settle_brain_response(actual_model, reply.usage,
            currency=job["currency"], reserved_amount=job["reserved_amount"])
        all_warnings = list(dict.fromkeys([*all_warnings, *reply.warnings, *price_warnings]))
        total_latency += reply.latency_s
        for key, value in reply.usage.items():
            if isinstance(value, int):
                all_usage[key] = all_usage.get(key, 0) + value
        if cost["amount"] is not None:
            all_cost += pricing.money(cost["amount"])
        else:
            unknown_cost = True
        updates = {"usage_json": reply.usage, "actual_amount": cost["amount"], "latency_s": reply.latency_s,
                   "stop_reason": reply.stop_reason, "repaired": attempt == 2, "model": actual_model,
                   "warnings_json": list(dict.fromkeys([*reply.warnings, *price_warnings]))}
        if reply.stop_reason in {"max_tokens", "length"}:
            message = "输出超长被截断，请缩短素材或减少勾选的任务"
            await store.cas_job(jid, "running", {**updates, "status": "invalid_output",
                                                "error_code": "max_tokens", "error_message": message})
            raise BrainProviderError("invalid_output", "max_tokens", message)
        try:
            output, warnings = await asyncio.to_thread(validate_reply, task, reply, inputs)
        except InvalidBrainOutput as exc:
            invalid = {**updates, "status": "invalid_output",
                "error_message": "导演输出未通过校验" + ("，修正后仍不合格" if attempt == 2 else "，将尝试一次单独计费修正")}
            if attempt == 2:
                await store.cas_job(jid, "running", invalid)
                raise
            repair = {"output": reply.text, "errors": exc.errors}
            quote = pricing.estimate_brain_repair(requested_model,
                await asyncio.to_thread(_input_chars, task, inputs),
                get_task(task).max_tokens, image_tokens=16384 * _image_count(images))
            item = {"provider": provider, "model": requested_model, "task": task, **quote, "first_max": quote["amount"]}
            bound_chunk = job.get("params", {}).get("breakdown_chunk")
            cancelled_breakdown = False
            try:
                async with store.connection(transaction=True) as db:
                    # WO3c confirmation already authorized and reserved this correction.
                    # Transfer its hold atomically; another quote cannot take the gap.
                    current_job = await store._get_job(db, jid, username)
                    if bound_chunk:
                        chunk = await store._one(db, """SELECT c.source_json,b.status AS breakdown_status
                            FROM studio_chunks c JOIN studio_breakdowns b ON b.id=c.breakdown_id WHERE c.id=?""", (bound_chunk,))
                        cancelled_breakdown = chunk['breakdown_status'] == 'cancelled'
                        if not cancelled_breakdown:
                            source = await asyncio.to_thread(json.loads, chunk['source_json'])
                            authorized = source['_item']
                            item['amount'] = item['first_max'] = authorized['repair_max']
                            if invalid.get('actual_amount') is None:
                                # Unknown first usage retains only the first-call hold.
                                first_hold = pricing.money(authorized['first_max'])
                                await db.execute('UPDATE studio_jobs SET reserved_amount=?,reserved_cny=? WHERE id=?',
                                    (str(first_hold), str(first_hold if current_job['currency'] == 'CNY' else 0), jid))
                                current_job = await store._get_job(db, jid, username)
                    if cancelled_breakdown:
                        invalid['error_message'] = '拆解已取消；当前响应不合格，未发起修正'
                    await transition(db, current_job, "running", invalid)
                    if not cancelled_breakdown:
                        if not bound_chunk:
                            await spend.check_brain_budget(db, username, _totals([item]))
                        job = await _insert_job(db, job["project_id"], username, item, inputs, job["group_id"],
                                                quote_id=job["quote_id"], parent=first_jid, chunk_id=bound_chunk)
                        jid = job["id"]
                        _CALL_JOB.set(jid)
                        await transition(db, job, "queued", {"status": "running", "submitted_at": store.utcnow(),
                                                             "run_token": uuid.uuid4().hex})
            except HTTPException as budget_error:
                await store.cas_job(first_jid, "running", invalid)
                await store.cas_job(first_jid, "invalid_output", {
                    "error_message": "导演输出不合格，修正未执行：" + str(budget_error.detail)})
                raise
            if cancelled_breakdown:
                raise exc
            continue
        if images and provider != "claude":
            from .brain import VISION_WARNING
            vision_warning = VISION_WARNING.format(model=actual_model)
            if vision_warning not in warnings:
                warnings = [*warnings, vision_warning]
        warnings = list(dict.fromkeys([*all_warnings, *warnings]))
        await store.cas_job(jid, "running", {**updates, "status": "succeeded", "result_json": output,
                                             "warnings_json": warnings})
        return BrainResult(output=output, warnings=warnings, usage=all_usage,
                           cost={"currency": cost["currency"], "amount": None if unknown_cost else float(all_cost)},
                           model=reply.model, stop_reason=reply.stop_reason, latency_s=total_latency, repaired=attempt == 2)
