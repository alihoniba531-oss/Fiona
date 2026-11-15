#!/usr/bin/env python3
"""讨论群第一期的真实模型走查（验证工具）。

从 backend/ 目录运行：
    python ../docs/tasks/2026-11-14-agent-group/verify/walk_discuss.py <输出目录>

在临时库里用进程内客户端走一遍真实接口：作者组队建群 → 看方案 → 改身份与成员 → 开工 →
插话 → 暂停 → 继续 → 等到停下 → 取成果、来源、导出。模型与搜索都是真实调用，会花钱。
DEV_MODE=1 下不扣草莓，脚本按步骤记录的 token 折算应扣的草莓数。平台 Key 只从环境读取。
"""
import asyncio
import json
import os
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

out = Path(sys.argv[1]).resolve()
out.mkdir(parents=True, exist_ok=True)
scratch = Path(tempfile.mkdtemp(prefix="discuss-walk-"))
os.environ.update({
    "PYTHON_DOTENV_DISABLED": "1", "DEV_MODE": "1",
    "FIONA_DB_PATH": str(scratch / "walk.db"), "FIONA_UPLOADS_DIR": str(scratch / "uploads"),
    "FIONA_STUDIO_DIR": str(scratch / "studio"), "FIONA_STUDIO": "0",
    "FIONA_DISCUSS": "1", "FIONA_DISCUSS_USERS": "walker",
})
os.environ.setdefault("JWT_SECRET", "discuss-walk-placeholder-secret-0123456789")
os.environ.pop("ANTHROPIC_BASE_URL", None)
(scratch / "studio").mkdir()
sys.path.insert(0, os.getcwd())

import main  # noqa: E402
import agent_store  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from novel.billing import calculate_cost  # noqa: E402
from rate_limit import limiter  # noqa: E402

limiter.enabled = False
H = {"X-Dev-User": "walker"}
checks = []


def check(name, ok, detail=""):
    checks.append({"name": name, "ok": bool(ok), "detail": str(detail)[:300]})
    print(("通过 " if ok else "失败 ") + name + (f"  {detail}" if detail and not ok else ""), flush=True)


def wait(client, gid, states, seconds=900, on_tick=None):
    deadline = time.monotonic() + seconds
    data = None
    while time.monotonic() < deadline:
        data = client.get(f"/discuss/groups/{gid}", headers=H).json()
        if on_tick:
            on_tick(data)
        if data["status"] in states:
            return data
        time.sleep(2)
    return data


with TestClient(main.app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000)) as client:
    check("准入", client.get("/discuss/access", headers=H).json() == {"allowed": True})
    catalog = client.get("/discuss/catalog", headers=H).json()
    check("目录有 8 个调研角色与隐私说明",
          sum(1 for role in catalog["roles"] if role["kind"] == "lens") == 8 and "阿里云百炼" in catalog["notice"])

    asyncio.run(agent_store.get_my_agent("walker"))
    asyncio.run(agent_store.update_my_agent("walker", {"display_name": "小满", "personality": "说话直接，先讲结论"}))
    asyncio.run(agent_store.update_memory("walker", {
        "职业": "给中小企业做 AI 智能体的创业者", "偏好": "预算紧，喜欢先小范围验证再放大",
        "顾虑": "团队只有三个人，做不了重运营", "体检记录": "去年查出轻度脂肪肝"}))

    created = client.post("/discuss/groups", headers=H, json={
        "request": "我想做面向东南亚市场的 AI 短剧出海，请调研值不值得做：平台与分发渠道、制作成本、变现方式与收入水平、合规风险，最后给一个做或不做的判断和起步方案。",
        "budget_strawberries": 600, "max_rounds": 3, "avatar": True,
        "members": [{"role": "market"},
                    {"name": "十年投资人", "does": "从投入产出和退出路径的角度查资料，判断这件事值不值得投"}],
        "identities": {"critic": {"name": "唱反调的老张", "persona": "说话直接，不留情面，专挑最薄弱的一环"}},
    })
    check("作者组队建群返回 201", created.status_code == 201, created.text)
    gid = created.json()["id"]
    data = wait(client, gid, {"awaiting_start", "paused", "failed"}, 300)
    check("立项后进入等开工", data["status"] == "awaiting_start", data.get("stop_reason"))
    plan = data["plan"]
    picks = {pick["role"]: pick for pick in plan["picks"]}
    check("主持人只给作者定的两位成员写分工", set(picks) == {"market", "custom1"}, list(picks))
    check("自定义成员保留作者写的名字", picks.get("custom1", {}).get("name") == "十年投资人")
    kinds = [message["kind"] for message in data["messages"]]
    check("立项消息与分身发言都在", "plan" in kinds and "brief" in kinds, kinds)
    brief = next((m for m in data["messages"] if m["kind"] == "brief"), None)
    check("分身发言里没有与任务无关的体检信息", brief is not None and "脂肪肝" not in brief["content"])
    check("分身的名字取自分身设定", brief is not None and brief["sender_name"] == "小满", brief and brief["sender_name"])

    patched = client.patch(f"/discuss/groups/{gid}/plan", headers=H, json={
        "expected_revision": data["plan_revision"],
        "picks": [*[{"role": pick["role"], "focus": pick["focus"]} for pick in plan["picks"]],
                  {"role": "policy", "focus": "查东南亚主要国家对短剧内容、支付和数据的监管要求与近两年的处罚案例"}],
        "identities": {"host": {"name": "阿衡", "persona": "讲话干脆，先下结论再给理由"}},
        "answers": "先只看印尼和泰国；团队三个人，预算二十万元以内。",
    })
    check("开工前改方案成功", patched.status_code == 200, patched.text)
    stale = client.patch(f"/discuss/groups/{gid}/plan", headers=H,
                         json={"expected_revision": data["plan_revision"], "title": "过期的修改"})
    check("用旧版本号再改被拒", stale.status_code == 409, stale.status_code)
    data = patched.json()
    names = {member["role"]: member["name"] for member in data["members"]}
    check("成员名字按作者设定显示", names.get("host") == "阿衡" and names.get("critic") == "唱反调的老张", names)
    check("新增的政策成员在群里", "policy" in names)

    started = client.post(f"/discuss/groups/{gid}/start", headers=H, json={"expected_revision": data["plan_revision"]})
    check("开工", started.status_code == 200, started.text)
    second = client.post("/discuss/groups", headers=H, json={"request": "另一个诉求，测试同时只能跑一个群"})
    check("已有在跑的群时不能再建", second.status_code == 409, second.status_code)

    state = {"noted": False, "paused": False}

    def tick(detail):
        if not state["noted"] and any(m["kind"] == "note" for m in detail["messages"]):
            state["noted"] = True
            response = client.post(f"/discuss/groups/{gid}/notes", headers=H,
                                   json={"text": "重点看印尼，泰国一笔带过；起步方案要写清头三个月每个月做什么。"})
            check("运行中插话成功", response.status_code == 200, response.text)
            paused = client.post(f"/discuss/groups/{gid}/pause", headers=H)
            state["paused"] = paused.status_code == 200
            check("运行中暂停成功", state["paused"], paused.text)

    data = wait(client, gid, {"paused", "done", "awaiting_user", "failed"}, 600, tick)
    if data["status"] == "paused" and data.get("stop_reason") == "user":
        check("暂停后预扣清零", data["reserved_strawberries"] == 0)
        before = len(client.get(f"/discuss/groups/{gid}", headers=H).json()["messages"])
        resumed = client.post(f"/discuss/groups/{gid}/resume", headers=H, json={})
        check("继续", resumed.status_code == 200, resumed.text)
        data = wait(client, gid, {"paused", "done", "awaiting_user", "failed"}, 900)
        after = client.get(f"/discuss/groups/{gid}", headers=H).json()["messages"]
        keys = [(m["sender"], m["kind"], m["round"], m["content"][:40]) for m in after]
        check("继续后没有重复消息", len(keys) == len(set(keys)) and len(after) >= before)
    check("最终停在完成或等作者决定", data["status"] in {"done", "awaiting_user"},
          f"{data['status']} / {data.get('stop_reason')} / {data.get('last_error')}")

    messages = client.get(f"/discuss/groups/{gid}", headers=H).json()["messages"]
    host_replies = [m for m in messages if m["sender"] == "host" and m["kind"] in {"decision", "rework"}
                    and (m["payload"].get("note_responses") or [])]
    check("主持人回应了插话", bool(host_replies))
    check("插话已被读到", all(m.get("consumed") for m in messages if m["kind"] == "user"))
    check("自定义成员与政策成员都发过言",
          {"custom1", "policy"} <= {m["sender"] for m in messages if m["kind"] in {"note", "notice"}})
    check("分身看过稿", any(m["kind"] in {"view", "notice"} and m["sender"] == "avatar" and m["round"] >= 1 for m in messages))

    sources = client.get(f"/discuss/groups/{gid}/sources", headers=H).json()
    output = client.get(f"/discuss/groups/{gid}/output", headers=H)
    export = client.get(f"/discuss/groups/{gid}/export", headers=H)
    check("有来源登记", len(sources) > 0, len(sources))
    check("有成果", output.status_code == 200, output.status_code)
    check("导出为 Markdown 附件且含来源清单",
          export.status_code == 200 and "attachment" in export.headers.get("content-disposition", "")
          and "## 来源" in export.text)
    if output.status_code == 200:
        text = output.json()["content"]
        check("成果里没有模型自己写的网址", "http://" not in text and "https://" not in text)
        urls = {source["url"] for source in sources}
        exported = [line.rsplit("）", 1)[-1].strip() for line in export.text.split("## 来源")[-1].splitlines()
                    if line.startswith("- S")]
        check("导出的网址都来自来源登记", bool(exported) and set(exported) <= urls, exported[:2])

    transcript = [f"# 走查讨论记录\n\n状态：{data['status']} / {data.get('stop_reason')}，轮次 {data['round']} / {data['max_rounds']}\n"]
    for message in messages:
        transcript.append(f"### 第 {message['round']} 轮 · {message['sender_name']}（{message['kind']}）\n\n{message['content']}\n")
    (out / "transcript.md").write_text("\n".join(transcript), encoding="utf-8")
    if export.status_code == 200:
        (out / "report.md").write_text(export.text, encoding="utf-8")

    db = sqlite3.connect(scratch / "walk.db")
    db.row_factory = sqlite3.Row
    steps = [dict(row) for row in db.execute(
        "SELECT step_key, role, model, status, attempts, input_tokens, output_tokens FROM discuss_steps WHERE group_id=?", (gid,))]
    db.close()
    searches = [step for step in steps if "/11-search-" in step["step_key"]]
    calls = [step for step in steps if "/11-search-" not in step["step_key"]]
    model_cost = sum(calculate_cost(step["model"], step["input_tokens"] or 0, step["output_tokens"] or 0)
                     for step in calls if step["model"] and ":" in step["model"])
    summary = {
        "status": data["status"], "stop_reason": data.get("stop_reason"), "round": data["round"],
        "output_version": data["output_version"], "sources": len(sources),
        "model_steps": len(calls), "repaired_steps": [step["step_key"] for step in calls if (step["attempts"] or 0) > 1],
        "failed_steps": [step["step_key"] for step in steps if step["status"] != "ok"],
        "searches": len(searches), "input_tokens": sum(step["input_tokens"] or 0 for step in calls),
        "output_tokens": sum(step["output_tokens"] or 0 for step in calls),
        "model_strawberries": model_cost, "search_strawberries": 2 * sum(1 for step in searches if step["status"] == "ok"),
        "checks_passed": sum(1 for item in checks if item["ok"]), "checks_total": len(checks),
        "failed_checks": [item for item in checks if not item["ok"]],
    }
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
