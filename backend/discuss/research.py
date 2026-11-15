"""联网搜索步骤与来源登记。

搜索是一次同步的 ``grounded_search`` 调用，包在线程里执行；同一事件循环里
最多同时跑 4 个搜索。费用按次固定预扣，失败全额退还且不缓存结果，续跑会重查。
来源编号只在 ``grounded_search`` 返回的 ``sources`` 上分配，模型写的网址不登记。
"""

from __future__ import annotations

import asyncio
import json
from weakref import WeakKeyDictionary

from tools.native_search import grounded_search

from . import config, roles
from . import store as discuss_store


SEARCH_CONCURRENCY = 4
_NO_SOURCES = "no_sources"

_search_semaphores: WeakKeyDictionary = WeakKeyDictionary()


def _search_semaphore() -> asyncio.Semaphore:
    """Keep one search semaphore per event loop, like novel.runner._semaphores."""
    loop = asyncio.get_running_loop()
    semaphore = _search_semaphores.get(loop)
    if semaphore is None:
        semaphore = asyncio.Semaphore(SEARCH_CONCURRENCY)
        _search_semaphores[loop] = semaphore
    return semaphore


def search_once(query: str, context: str) -> dict:
    """Run one grounded search. Tests replace this module attribute for offline runs."""
    messages = [
        {"role": "system",
         "content": roles.SEARCH_SYSTEM.format(today=config.today_beijing())},
        {"role": "user",
         "content": json.dumps({"问题": query, "背景": context}, ensure_ascii=False)},
    ]
    result = grounded_search(messages, max_tokens=1200, max_sources=8)
    return {"query": query, "data": result.get("data"), "sources": result.get("sources") or [],
            "error": result.get("error")}


def _empty_result(query: str, error: str) -> dict:
    return {"query": query, "data": None, "sources": [], "error": error}


def _error_code(result) -> str | None:
    """Return the fixed failure code, never the query or provider response text."""
    if not isinstance(result, dict):
        return "bad_response"
    error = result.get("error")
    if isinstance(error, str) and error.strip():
        return error.strip()
    if error:
        return type(error).__name__
    sources = result.get("sources")
    if not isinstance(sources, list) or not sources:
        return _NO_SOURCES
    return None


async def run_search(store, billing, step_key, role, query, context) -> dict:
    """Execute one billed search step, reusing a previously successful result."""
    record = await store.read_step(step_key)
    if record is not None and record.get("status") == "ok":
        return record.get("result")

    await billing.reserve_fixed(step_key, role, config.search_strawberries())

    async with _search_semaphore():
        # Resolve the module global at call time so tests can replace search_once.
        result = await asyncio.to_thread(search_once, query, context)

    error = _error_code(result)
    if error is not None:
        await billing.refund_fixed(step_key)
        await store.write_step(step_key, {
            "step_key": step_key,
            "role": role,
            "model": "search",
            "status": "failed",
            "errors": [error],
            "result": None,
        })
        return _empty_result(query, error)

    step_record = {
        "step_key": step_key,
        "role": role,
        "model": "search",
        "status": "ok",
        "result": result,
        "errors": [],
        "usage": {"input_tokens": 0, "output_tokens": 0, "cached_tokens": 0},
    }
    await billing.settle_fixed(step_key, step_record)
    return result


def collect_findings(results, register) -> list:
    """Register sources in order and map each finding's result indexes to S ids."""
    facts = []
    for result in results:
        sources = result.get("sources") if isinstance(result, dict) else None
        index_map = {}
        for source in sources or []:
            index_map[source.get("index")] = register(source)
        data = result.get("data") if isinstance(result, dict) else None
        data = data if isinstance(data, dict) else {}
        for item in data.get("findings") or []:
            if not isinstance(item, dict) or not isinstance(item.get("fact"), str):
                continue
            refs = sorted(
                {index_map[ref] for ref in item.get("refs") or [] if ref in index_map},
                key=lambda value: int(value[1:]),
            )
            if refs:
                facts.append({"fact": item["fact"][:160], "refs": refs})
    return facts


def _flatten_sources(results) -> list:
    flat = []
    for result in results:
        sources = result.get("sources") if isinstance(result, dict) else None
        for source in sources or []:
            flat.append(source)
    return flat


async def register_findings(store, results) -> list:
    """Register every search source for this group, then return numbered findings."""
    sids = await discuss_store.register_sources(store, _flatten_sources(results))
    remaining = iter(sids)

    def register(source):
        return f"S{next(remaining)}"

    return collect_findings(results, register)
