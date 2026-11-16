"""界面验收用的造数脚本：往一个临时库里写入各种状态的讨论群。

用法：python3 -I seed_groups.py <临时库路径> <用户名> <走查目录>
走查目录是 docs/tasks/2026-11-14-agent-group/verify/walk-final（含 transcript.md 与 report.md）。
只写 discuss_* 五张表里属于该用户、且 id 以 seed- 开头的行；重复运行会先删掉旧的 seed- 行。
不调用任何模型，不访问网络。
"""
import json
import re
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB, USER, WALK = sys.argv[1], sys.argv[2], Path(sys.argv[3])
BASE = datetime(2026, 11, 15, 1, 0, 0, tzinfo=timezone.utc)
SENDERS = {
    "阿衡": "host", "小满": "avatar", "市场与行业": "market", "十年投资人": "custom1",
    "政策与合规": "policy", "你": "user", "唱反调的老张": "critic", "撰稿人": "writer", "验收人": "acceptor",
}
CITE = re.compile(r"\[S(\d{1,4})\]")


def stamp(minutes):
    return (BASE + timedelta(minutes=minutes)).isoformat()


def parse_transcript(text):
    """按「### 第 N 轮 · 名字（kind）」切成消息。"""
    messages, current = [], None
    for line in text.splitlines():
        match = re.match(r"^### 第 (\d+) 轮 · (.+?)（([a-z]+)）\s*$", line)
        if match:
            if current:
                messages.append(current)
            current = {"round": int(match.group(1)), "name": match.group(2), "kind": match.group(3), "lines": []}
        elif current is not None:
            current["lines"].append(line)
    if current:
        messages.append(current)
    for item in messages:
        item["content"] = "\n".join(item.pop("lines")).strip()
        item["sender"] = SENDERS[item["name"]]
    return messages


TRANSCRIPT = parse_transcript((WALK / "transcript.md").read_text(encoding="utf-8"))
REPORT = (WALK / "report.md").read_text(encoding="utf-8")
assert len(TRANSCRIPT) >= 20, len(TRANSCRIPT)
assert REPORT.count("\n|") >= 10, "report.md 里应该有表格"

PLAN = {
    "title": "东南亚AI短剧出海可行性调研",
    "goal": "调研面向东南亚市场的AI短剧出海是否值得做，给出明确结论和起步方案。",
    "deliverable": {"kind": "report", "outline": [
        "东南亚短剧市场现状与AI应用趋势", "主流平台与分发渠道盘点", "AI短剧制作流程与成本拆解",
        "变现模式与收入水平", "合规与版权风险", "结论与起步方案"]},
    "criteria": [
        {"id": "C1", "text": "列出至少3个东南亚可用的短剧分发平台或渠道及其接入方式"},
        {"id": "C2", "text": "给出单集AI短剧的制作成本区间，注明所用工具与假设前提"},
        {"id": "C3", "text": "列出至少2种已跑通的变现模式，有公开收入数据则引用，无则注明查不到"},
        {"id": "C4", "text": "列出印尼、泰国、越南中至少2国的内容审核或版权关键限制"},
        {"id": "C5", "text": "必须给出明确做或不做的结论，并写明依据和适用前提"},
        {"id": "C6", "text": "起步方案须包含前3个月的具体动作清单"},
    ],
    "picks": [
        {"role": "market", "name": "市场与行业", "does": "查市场规模、增长、格局与趋势",
         "focus": "查东南亚短剧市场规模、增速、用户偏好；梳理出海平台及本地渠道的分发规则。"},
        {"role": "custom1", "name": "十年投资人", "does": "做过十年早期投资，只看投入产出比和回本周期",
         "focus": "从投入产出比角度测算AI短剧单部制作成本；调研各类变现方式的实际收入。"},
        {"role": "policy", "name": "政策与合规", "does": "查监管政策、合规要求与风险事件",
         "focus": "查印尼、泰国、越南的内容审核、AI生成内容标注与版权要求。"},
    ],
    "questions": [
        "目标国家是聚焦某几个还是覆盖整个东南亚？不同国家的合规与渠道差异很大。",
        "团队现有AI视频生成能力处于什么水平，是从零开始还是已有工作流？",
        "启动预算大致在什么量级，以便判断适合的起步规模？",
    ],
}
CONFIG = {
    "models": {}, "avatar": True, "revisions": [], "answers": "",
    "identities": {"host": {"name": "阿衡", "persona": "说话直接，先给结论再讲依据"},
                   "critic": {"name": "唱反调的老张", "persona": ""}},
    "fixed_members": [],
}
REQUEST = "帮我查清楚面向东南亚市场做AI短剧出海值不值得做，给出明确的结论和起步方案。我们是三个人的小团队，预算二十万以内。"

VERDICT_FAIL = {
    "verdicts": [
        {"id": "C1", "pass": True, "evidence": "列出TikTok、YouTube Shorts、ReelShort/DramaBox四个渠道及发布、入驻或供货路径"},
        {"id": "C2", "pass": False, "evidence": "给出单集50至200元及整剧成本区间、假设，但未列出具体AI工具名称"},
        {"id": "C3", "pass": True, "evidence": "列出流量分成、小额订阅两种模式；缺失数据已注明"},
        {"id": "C4", "pass": True, "evidence": "列出印尼AI标注、PT PMA、税务限制及泰国计算机犯罪法、PDPA"},
        {"id": "C5", "pass": True, "evidence": "明确不建议常规做，仅1至3万元小范围验证"},
        {"id": "C6", "pass": True, "evidence": "起步方案包含第1至第3个月的动作和止损点"},
    ],
    "citation_issues": [
        {"quote": "首月自然播放总量若不过万，立即停止", "problem": "止损阈值未说明测算依据"},
    ],
    "rework": ["补上所用AI工具的具体名称与订阅价格", "两处止损阈值注明是推断并写出依据"],
}
VERDICT_PASS = {
    "verdicts": [{"id": item["id"], "pass": True, "evidence": "已满足"} for item in PLAN["criteria"]],
    "citation_issues": [], "rework": [],
}


def insert_group(db, group_id, *, status, stop_reason=None, last_error=None, round=0, max_rounds=3,
                 plan=None, plan_revision=0, config=None, budget=500, spent=0, output_version=0,
                 title="", request=REQUEST, minutes=0, token=None):
    db.execute(
        "INSERT INTO discuss_groups(id,username,title,request,materials,status,stop_reason,last_error,round,"
        "max_rounds,plan_json,plan_revision,config_json,budget_strawberries,spent_strawberries,"
        "reserved_strawberries,output_version,run_token,created_day,created_at,updated_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (group_id, USER, title, request, "", status, stop_reason, last_error, round, max_rounds,
         json.dumps(plan or {}, ensure_ascii=False), plan_revision,
         json.dumps(config or CONFIG, ensure_ascii=False), budget, spent, 0, output_version, token,
         "2026-11-15", stamp(0), stamp(minutes)))


def insert_messages(db, group_id, items, *, start_minute=1, unread_last=0):
    """items 是 parse_transcript 的结果；user 的消息里最后 unread_last 条保持未读。"""
    notes = [index for index, item in enumerate(items) if item["sender"] == "user"]
    unread = set(notes[len(notes) - unread_last:]) if unread_last else set()
    versions = 0
    for index, item in enumerate(items):
        payload = {}
        if item["kind"] == "draft":
            versions += 1
            payload = {"version": versions}
        step_key = None if item["sender"] == "user" else f"seed/{index:03d}-{item['kind']}-{item['sender']}"
        consumed = None
        if item["sender"] == "user" and index not in unread:
            consumed = "start"
        db.execute(
            "INSERT INTO discuss_messages(group_id,username,round,sender,kind,content,payload_json,step_key,"
            "consumed_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (group_id, USER, item["round"], item["sender"], item["kind"], item["content"],
             json.dumps(payload, ensure_ascii=False), step_key, consumed, stamp(start_minute + index)))


def insert_sources(db, group_id, texts):
    ids = sorted({int(number) for text in texts for number in CITE.findall(text)})
    for sid in ids:
        url = f"https://example.com/source/{sid}"
        if sid == ids[0]:
            url = "javascript:alert('seed')"  # 反例：不安全的网址只能显示成文字
        db.execute(
            "INSERT INTO discuss_sources(group_id,username,sid,url,url_key,title,site_name,created_at) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (group_id, USER, sid, url, f"key-{sid}", f"示例来源 {sid}：东南亚短剧市场观察", "示例站点", stamp(2)))
    return ids


def insert_output(db, group_id, version, round, content, verdict, passed, minute):
    db.execute(
        "INSERT INTO discuss_outputs(group_id,username,version,round,step_key,content,verdict_json,passed,created_at) "
        "VALUES(?,?,?,?,?,?,?,?,?)",
        (group_id, USER, version, round, f"seed/output-{version}", content,
         None if verdict is None else json.dumps(verdict, ensure_ascii=False), 1 if passed else 0, stamp(minute)))


def main():
    db = sqlite3.connect(DB)
    assert db.execute("SELECT 1 FROM users WHERE username=?", (USER,)).fetchone(), "用户不存在，先登录一次"
    for table in ("discuss_messages", "discuss_sources", "discuss_steps", "discuss_outputs"):
        db.execute(f"DELETE FROM {table} WHERE username=? AND group_id LIKE 'seed-%'", (USER,))
    db.execute("DELETE FROM discuss_groups WHERE username=? AND id LIKE 'seed-%'", (USER,))

    until_round = lambda limit: [item for item in TRANSCRIPT if item["round"] <= limit]
    first_report = REPORT[: REPORT.index("\n## ", REPORT.index("\n## ") + 1)]  # 第一版只留开头两节

    # 1 轮数用尽、验收未过：完整的真实记录，两版成果，最后一条插话未读
    all_messages = TRANSCRIPT + [{"round": 3, "name": "你", "kind": "user", "sender": "user",
                                  "content": "成本那一节把工具名字和订阅价格补上。"}]
    insert_group(db, "seed-awaiting-user", status="awaiting_user", stop_reason="rounds_exhausted", round=3,
                 plan=PLAN, plan_revision=1, spent=296, output_version=2, title=PLAN["title"], minutes=40)
    insert_messages(db, "seed-awaiting-user", all_messages, unread_last=1)
    insert_sources(db, "seed-awaiting-user", [REPORT] + [item["content"] for item in TRANSCRIPT])
    insert_output(db, "seed-awaiting-user", 1, 2, first_report, VERDICT_FAIL, False, 20)
    insert_output(db, "seed-awaiting-user", 2, 3, REPORT, VERDICT_FAIL, False, 38)

    # 2 等开工：只有方案与分身背景
    insert_group(db, "seed-awaiting-start", status="awaiting_start", round=0, plan=PLAN, plan_revision=1,
                 spent=12, title=PLAN["title"] + "（待开工）", minutes=50)
    insert_messages(db, "seed-awaiting-start", until_round(0))

    # 3 预算用完暂停：第一轮做到一半
    insert_group(db, "seed-paused-budget", status="paused", stop_reason="budget", round=1, plan=PLAN,
                 plan_revision=1, budget=100, spent=100, title=PLAN["title"] + "（预算用完）", minutes=45)
    insert_messages(db, "seed-paused-budget", until_round(1)[:5])
    insert_sources(db, "seed-paused-budget", [item["content"] for item in until_round(1)[:5]])

    # 4 验收通过
    insert_group(db, "seed-done", status="done", stop_reason="accepted", round=2, plan=PLAN, plan_revision=1,
                 spent=180, output_version=1, title=PLAN["title"] + "（已通过）", minutes=30)
    insert_messages(db, "seed-done", until_round(2))
    insert_sources(db, "seed-done", [REPORT] + [item["content"] for item in until_round(2)])
    insert_output(db, "seed-done", 1, 2, REPORT, VERDICT_PASS, True, 25)

    # 5 已结束、没有成果
    insert_group(db, "seed-closed", status="closed", stop_reason="user", round=1, plan=PLAN, plan_revision=1,
                 spent=40, title=PLAN["title"] + "（已结束）", minutes=10)
    insert_messages(db, "seed-closed", until_round(1)[:3])

    # 6 出错
    insert_group(db, "seed-failed", status="failed", stop_reason="error", last_error="RuntimeError", round=1,
                 plan=PLAN, plan_revision=1, spent=60, title=PLAN["title"] + "（出错）", minutes=8)
    insert_messages(db, "seed-failed", until_round(1)[:4])

    # 7 还没有标题、成果在等验收（verdict 为空）
    insert_group(db, "seed-no-verdict", status="paused", stop_reason="user", round=2, plan=PLAN, plan_revision=1,
                 spent=150, output_version=1, title="", request="一个还没有标题的群：" + REQUEST, minutes=6)
    insert_messages(db, "seed-no-verdict", until_round(2)[:14])
    insert_output(db, "seed-no-verdict", 1, 2, first_report, None, False, 5)

    # 8 长记录：超过 200 条消息，验证分页读取
    insert_group(db, "seed-long", status="paused", stop_reason="user", round=4, max_rounds=6, plan=PLAN,
                 plan_revision=1, spent=420, budget=2000, title="长记录（230 条消息）", minutes=4)
    long_items = []
    for index in range(230):
        base = TRANSCRIPT[index % len(TRANSCRIPT)]
        long_items.append({**base, "round": 1 + index // 60,
                           "content": f"第 {index + 1} 条。" + base["content"][:120]})
    insert_messages(db, "seed-long", long_items)

    db.commit()
    counts = {row[0]: row[1] for row in db.execute(
        "SELECT group_id, COUNT(*) FROM discuss_messages WHERE username=? AND group_id LIKE 'seed-%' GROUP BY group_id",
        (USER,))}
    groups = db.execute("SELECT id,status,stop_reason,output_version FROM discuss_groups WHERE username=? "
                        "AND id LIKE 'seed-%' ORDER BY id", (USER,)).fetchall()
    print(json.dumps({"groups": groups, "messages": counts}, ensure_ascii=False))


if __name__ == "__main__":
    main()
