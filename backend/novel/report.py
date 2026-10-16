"""Deterministic author-facing reports, blind reading files and usage tables."""

from __future__ import annotations

import json
import math
import random
from collections import defaultdict
from pathlib import Path


def _json(path: Path, default=None):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def _write_json(path: Path, value) -> None:
    _write(path, json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def read_usage(out) -> list[dict]:
    path = Path(out) / "usage.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] if path.exists() else []


def load_prices(path) -> dict:
    """Prices are user input only; there are no built-in prices."""
    if path is None:
        return {}
    value = _json(Path(path)) if not isinstance(path, dict) else path
    if not isinstance(value, dict):
        raise ValueError("价格文件必须为 JSON 对象")
    for model, price in value.items():
        if not isinstance(model, str) or not isinstance(price, dict):
            raise ValueError("价格条目格式错误")
        for field in ("input_per_mtok", "output_per_mtok"):
            number = price.get(field)
            if type(number) not in (int, float) or number < 0 or not math.isfinite(number):
                raise ValueError("价格必须为非负有限数字")
        if price.get("currency") not in ("USD", "CNY"):
            raise ValueError("价格币种必须为 USD 或 CNY")
    return value


def _cell(value) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _table(headers, rows) -> str:
    return "\n".join([
        "| " + " | ".join(map(_cell, headers)) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
        *("| " + " | ".join(map(_cell, row)) + " |" for row in rows),
    ])


def cost_report(out, prices=None) -> str:
    prices = load_prices(prices)
    usage = read_usage(out)
    groups = defaultdict(list)
    chapters = defaultdict(list)
    for item in usage:
        groups[(item.get("experiment", ""), item.get("role", ""), item.get("model", ""))].append(item)
        chapters[(item.get("experiment", ""), item.get("arm", ""), item.get("chapter", 0))].append(item)

    def row(key, items):
        attempts = sum(item.get("attempts", 1) for item in items)
        values = [*key, attempts, sum(item.get("input_tokens", 0) for item in items), sum(item.get("output_tokens", 0) for item in items), round(sum(item.get("duration_ms", 0) for item in items) / max(attempts, 1), 2)]
        if prices:
            totals = defaultdict(float)
            missing = False
            for item in items:
                price = prices.get(item.get("model"))
                if price is None:
                    missing = True
                    continue
                totals[price["currency"]] += (item.get("input_tokens", 0) * price["input_per_mtok"] + item.get("output_tokens", 0) * price["output_per_mtok"]) / 1_000_000
            amounts = [f"{currency} {amount:.6f}" for currency, amount in sorted(totals.items())]
            if missing:
                amounts.append("部分模型未提供价格")
            values.append("；".join(amounts) or "未提供价格")
        return values

    suffix = ["金额"] if prices else []
    text = "# 用量与成本\n\n调用次数包含重试；输入、输出和缓存用量取提供方报告。fake 的 token 单位为字符。\n\n"
    text += _table(["实验", "角色", "模型", "调用次数", "输入 token", "输出 token", "平均耗时 ms", *suffix], [row(key, items) for key, items in sorted(groups.items())])
    text += "\n\n" + _table(["实验", "组别", "章节", "调用次数", "输入 token", "输出 token", "平均耗时 ms", *suffix], [row(key, items) for key, items in sorted(chapters.items())]) + "\n"
    _write(Path(out) / "cost.md", text)
    return text


def estimate_report(out) -> str:
    """Estimate the observed dry-run call trace at real-model output ceilings."""
    groups = defaultdict(list)
    for item in read_usage(out):
        groups[(item.get("experiment", ""), item.get("role", ""))].append(item)
    rows = []
    for key, items in sorted(groups.items()):
        rows.append([*key, sum(item.get("attempts", 1) for item in items), sum(item.get("input_chars", item.get("input_tokens", 0)) for item in items), sum(item.get("max_tokens", 0) * item.get("attempts", 1) for item in items)])
    text = "真实运行 token 上界估算（按本次 dry-run 调用轨迹）\n\n估算口径：输入按 1 字符 = 1 token，输出每次调用取该角色 max_tokens；调用次数包含已执行重试。真实模型若触发更多修订或不同章节数，需另计。Claude 对中文约 1–1.35 token/字，anthropic 角色的输入上界可能偏低。\n\n"
    text += _table(["实验", "角色", "调用次数", "输入 token 上界", "输出 token 上界"], rows) + "\n"
    _write(Path(out) / "estimate.md", text)
    return text


def generate_blind(out) -> None:
    out = Path(out)
    blind = out / "blind"
    key_path = blind / "key.json"
    key = _json(key_path)
    if key is None:
        arms = ["solo", "panel"]
        random.SystemRandom().shuffle(arms)
        key = {"版本甲": arms[0], "版本乙": arms[1]}
        _write_json(key_path, key)
    labels = ("版本甲", "版本乙")
    if not isinstance(key, dict) or any(key.get(label) not in ("solo", "panel") for label in labels) or {key[label] for label in labels} != {"solo", "panel"}:
        raise ValueError("盲读映射必须将版本甲、版本乙分别对应 solo 和 panel")
    for label in labels:
        arm = key[label]
        bodies = [path.read_text(encoding="utf-8").rstrip() for path in sorted((out / f"arm-{arm}").glob("ch[0-9][0-9][0-9]/chapter.md"))]
        _write(blind / f"{label}.md", "\n\n".join(bodies) + "\n")
    _write(blind / "阅读说明.md", "请分别阅读版本甲和版本乙，独立评价以下四点：\n\n1. 剧情走向是否更有意思。\n2. 人物是否可信。\n3. 是否有意外又合理的发展。\n4. 前后是否连贯。\n")


def _critique_summary(meeting, decision) -> list[str]:
    plan = meeting["plan"]
    initial, final = plan["beat_sheet"], decision["beat_sheet"]
    lines = ["", "推演模式：critique", "", "初案要点：", "",
             f"- 章名：{initial['title']}；本章目标：{initial['chapter_goal']}",
             "- 节拍：" + "；".join(initial["beats"]),
             f"- 开头钩子：{initial['opening_hook']}；结尾钩子：{initial['ending_hook']}",
             f"- 初案理由：{plan['rationale']}；ending_status：{plan['ending_status']}"]
    for critique in meeting.get("critiques", []):
        lines += ["", f"顾问 {critique.get('author_name', critique['author'])} 保留建议：{critique['keep']}"]
    replies = {item["objection_id"]: item["response"] for item in decision["objection_responses"]}
    for objection in meeting.get("objections", []):
        author = objection.get("author_name", objection["author"])
        if objection["id"].startswith("A"):
            lines += ["", f"替代走向 {objection['id']}（{author}）：{objection['alternative']}；主编回应：{replies.get(objection['id'], '')}"]
        else:
            lines += ["", f"意见 {objection['id']}（{author}，{objection['severity']}）：针对{objection['target']}；问题：{objection['problem']}；改法：{objection['suggestion']}；主编回应：{replies.get(objection['id'], '')}"]
    fields = ("title", "chapter_goal", "beats", "scenes", "opening_hook", "ending_hook",
              "foreshadowing_plant", "foreshadowing_resolve")
    display = lambda value: json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    rows = [[field, "是" if initial[field] != final[field] else "否",
             display(initial[field]), display(final[field])] for field in fields]
    lines += ["", "定稿相对初案的改动：", "", _table(["字段", "是否变化", "初案", "定稿"], rows),
              "", "定稿理由：" + decision["rationale"], "", "定稿说明：" + decision["merge_note"]]
    if decision.get("warnings"):
        lines += ["", "裁决警告：", "", _table(["字段", "ID", "原因"], [[item["field"], item["id"], item["reason"]] for item in decision["warnings"]])]
    return lines


def generate_report(out, prices=None) -> str:
    out = Path(out)
    manifest = _json(out / "manifest.json", {})
    config = manifest.get("config", {})
    experiment = manifest.get("experiment", config.get("experiment", ""))
    lines = [f"# 实验 {experiment} 报告", "", f"状态：{manifest.get('status', 'unknown')}", ""]
    if manifest.get("failed_step"):
        lines += [f"失败步骤：{manifest['failed_step']}", ""]
    for path in sorted(out.glob("arm-*/ch[0-9][0-9][0-9]/chapter_record.json")):
        record = _json(path)
        meeting = record["meeting"]
        decision = meeting["decision"]
        lines += [f"## {path.parent.parent.name} 第 {record['chapter']} 章：{record['title']}", "", "推演会摘要："]
        if meeting.get("mode") == "critique":
            lines += _critique_summary(meeting, decision)
        else:
            averages = meeting.get("scores", {})
            if isinstance(averages, list):
                averages = {item.get("proposal_id", item.get("id")): item for item in averages}
            for proposal in meeting.get("proposals", []):
                score = averages.get(proposal["id"], {})
                mean = score.get("total_mean", score.get("mean", score.get("overall", "—"))) if isinstance(score, dict) else score
                lines.append(f"- {proposal['id']} / {proposal.get('author_name', proposal.get('author', ''))}：{proposal['direction']}；均分 {mean}")
            if not meeting.get("proposals"):
                lines.append("- 主编独自构思。")
            lines += ["", "选中提案：" + ("、".join(decision["chosen_proposal_ids"]) or "独自构思"), "", "理由：" + decision["rationale"], "", "合并说明：" + decision["merge_note"]]
            if decision.get("warnings"):
                lines += ["", "裁决警告：", "", _table(["字段", "ID", "原因"], [[item["field"], item["id"], item["reason"]] for item in decision["warnings"]])]
            replies = {item["objection_id"]: item["response"] for item in decision["objection_responses"]}
            for objection in meeting.get("objections", []):
                lines += ["", f"反对意见 {objection['id']}（{objection['proposal_id']}）：{objection['objection']}；回应：{replies.get(objection['id'], '')}"]
        for reply in decision["user_note_responses"]:
            lines += ["", f"用户留言 {reply['note_id']}：采纳={reply['adopted']}；回应：{reply['response']}"]
        lines += ["", f"ending_status：{decision['ending_status']}", "", f"审校轮数：{record.get('review_rounds', 0)}；修订轮数：{record.get('revision_rounds', 0)}；标记：{'、'.join(record.get('flags', [])) or '无'}", "", f"被丢弃的 issue 条数：{record.get('review_dropped_issues', 0)}；blocking_defaulted 条数：{record.get('review_blocking_defaulted', 0)}", "", "摘要：" + record["summary"], ""]
    if experiment == "A":
        lines += ["盲读文件：blind/版本甲.md、blind/版本乙.md；阅读说明：blind/阅读说明.md。对应关系仅保存在 blind/key.json。", ""]
    elif experiment == "B":
        metrics = manifest.get("completion", {})
        lines += ["## 完结指标", "", f"完结章号：{metrics.get('chapter', '尚未完结')}", "", f"在目标范围内：{metrics.get('within_target', False)}", "", "ending_status 序列：" + " → ".join(metrics.get("ending_statuses", [])), "", "完结后仍为 open 的 major 伏笔：", ""]
        lines += [f"- {item['id']}：{item['description']}" for item in metrics.get("open_major_foreshadowing", [])] or ["无。"]
        for reply in metrics.get("user_note_responses", []):
            lines += ["", f"第{reply['chapter']}章 {reply['note_id']}：采纳={reply['adopted']}；{reply['response']}"]
    elif experiment == "C":
        results = _json(out / "comparison.json", [])
        lines += ["## 审校正控结果", "", "原稿阻断问题数为误报基线；抓到数以证据与插入句至少 8 字的公共连续子串计算。", "", _table(["审校模型", "抓到数（满分3）", "原稿误报数"], [[item["model"], item["caught_count"], item["false_positives"]] for item in results]), ""]
        insertions = _json(out / "control/insertions.json", [])
        lines += ["## 插入引文核对记录", "", "以至少8字公共连续子串记录匹配类别；不匹配不阻止实验，匹配也不代表已证明语义矛盾。", "", _table(["插入序号", "原稿锚点", "contradicts", "citation_check 匹配类别"], [[index, item["after_anchor"], item["contradicts"], "、".join(item.get("citation_check", {}).get("matched_categories", [])) or "未匹配（仅记录）"] for index, item in enumerate(insertions, 1)]), ""]
    text = "\n".join(lines).rstrip() + "\n"
    _write(out / "report.md", text)
    cost_report(out, prices)
    if manifest.get("dry_run"):
        estimate_report(out)
    return text
