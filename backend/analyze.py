# -*- coding: utf-8 -*-
"""
菲欧娜使用数据分析。扫 events 表，按维度给出 CLI 报告。

设计原则：原始事件存在 events 表，本脚本只负责聚合 + 呈现，
不预设结论，方便随时加新维度。

用法：
    python analyze.py             # 默认看过去 30 天
    python analyze.py --days 7    # 看过去 7 天
    python analyze.py --raw       # 多打印一份原始事件抽样
"""
import argparse
import json
import os
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from statistics import mean, median

DB_PATH = os.path.join(os.path.dirname(__file__), "fiona.db")


def parse_args():
    ap = argparse.ArgumentParser(description="菲欧娜使用数据分析")
    ap.add_argument("--days", type=int, default=30, help="统计窗口（天），默认 30")
    ap.add_argument("--raw", action="store_true", help="额外打印原始事件抽样")
    ap.add_argument("--user", type=str, default=None, help="只看指定用户")
    return ap.parse_args()


def fetch_events(conn, since_ts: str, username: str | None) -> list[tuple]:
    sql = "SELECT ts, username, event_type, name, payload, duration_ms, success FROM events WHERE ts >= ?"
    params: list = [since_ts]
    if username:
        sql += " AND username = ?"
        params.append(username)
    sql += " ORDER BY ts ASC"
    return conn.execute(sql, params).fetchall()


def fmt_pct(n: int, total: int) -> str:
    if total == 0:
        return "  0.0%"
    return f"{n * 100 / total:5.1f}%"


def fmt_ms(values: list[int]) -> str:
    """耗时统计，返回 'avg=X med=Y p95=Z' 格式"""
    if not values:
        return "  -"
    s = sorted(values)
    p95 = s[max(0, int(len(s) * 0.95) - 1)]
    return f"avg={int(mean(values))}ms med={int(median(values))}ms p95={p95}ms"


def section(title: str, char: str = "─"):
    print()
    print(title)
    print(char * max(20, len(title)))


def print_table(headers: list[str], rows: list[list], widths: list[int] | None = None):
    if widths is None:
        widths = [max(len(str(h)), *(len(str(r[i])) for r in rows)) if rows else len(str(h))
                  for i, h in enumerate(headers)]
    line = "  ".join(str(h).ljust(w) for h, w in zip(headers, widths))
    print(line)
    print("  ".join("-" * w for w in widths))
    for r in rows:
        print("  ".join(str(c).ljust(w) for c, w in zip(r, widths)))


def main():
    args = parse_args()

    if not os.path.exists(DB_PATH):
        print(f"找不到数据库：{DB_PATH}")
        return

    since = datetime.now() - timedelta(days=args.days)
    since_ts = since.strftime("%Y-%m-%d %H:%M:%S")

    conn = sqlite3.connect(DB_PATH)
    # 兜底：events 表不存在时（后端还没启动过新版），给出明确提示
    has_events = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='events'"
    ).fetchone()
    if not has_events:
        print("events 表还不存在。说明后端还没用新版代码启动过——")
        print("启动一次 uvicorn 让 init_db 跑过即可（events 表会被自动创建）。")
        return
    rows = fetch_events(conn, since_ts, args.user)

    if not rows:
        print(f"窗口内（最近 {args.days} 天）没有事件。")
        if args.user:
            print(f"用户：{args.user}")
        print("如果 events 表是空的，说明后端还没跑过 chat 流量，或者埋点没生效。")
        return

    # ── 解析事件 ──────────────────────────────────────
    chats: list[dict] = []
    tool_calls: list[dict] = []
    match_events: list[dict] = []

    for ts, username, event_type, name, payload_json, duration_ms, success in rows:
        try:
            payload = json.loads(payload_json) if payload_json else {}
        except Exception:
            payload = {}
        rec = {
            "ts": ts,
            "username": username,
            "name": name,
            "payload": payload,
            "duration_ms": duration_ms,
            "success": bool(success),
        }
        if event_type == "chat":
            chats.append(rec)
        elif event_type == "tool_call":
            tool_calls.append(rec)
        elif event_type == "match_card":
            match_events.append(rec)

    # ── 总览 ──────────────────────────────────────────
    print(f"\n菲欧娜使用数据 · 最近 {args.days} 天")
    print(f"窗口起点：{since_ts}")
    if args.user:
        print(f"用户过滤：{args.user}")
    print("=" * 60)

    section("📊 总览")
    users = {c["username"] for c in chats if c["username"]}
    chat_errors = sum(1 for c in chats if not c["success"])
    print(f"活跃用户        : {len(users)}")
    print(f"chat 请求       : {len(chats)}")
    print(f"  ├─ 成功       : {len(chats) - chat_errors}")
    print(f"  └─ 失败       : {chat_errors}  ({fmt_pct(chat_errors, len(chats))})")
    print(f"工具调用        : {len(tool_calls)}")
    print(f"匹配命中        : {len(match_events)} 次（共保存 {sum(m['payload'].get('saved', 0) for m in match_events)} 张卡片）")

    # ── mode 分布 ─────────────────────────────────────
    section("🪞 模式分布（friend vs mirror）")
    mode_counter: Counter = Counter()
    for c in chats:
        mode = c["payload"].get("mode") or "(unknown)"
        mode_counter[mode] += 1
    total = sum(mode_counter.values())
    rows_out = [[m, n, fmt_pct(n, total)] for m, n in mode_counter.most_common()]
    print_table(["mode", "count", "pct"], rows_out)

    # ── model 路由分布 ────────────────────────────────
    section("🤖 模型路由（light vs main）")
    model_counter: Counter = Counter()
    for c in chats:
        model = c["payload"].get("model") or "(none)"  # 工具直接执行时不走 model
        model_counter[model] += 1
    total = sum(model_counter.values())
    rows_out = [[m, n, fmt_pct(n, total)] for m, n in model_counter.most_common()]
    print_table(["model", "count", "pct"], rows_out)

    # ── 意图识别命中率 ───────────────────────────────
    section("🎯 意图识别（intent != null 的比例 = 工具触发率）")
    intent_counter: Counter = Counter()
    for c in chats:
        i = c["payload"].get("intent")
        intent_counter[i if i else "(null/纯对话)"] += 1
    total = sum(intent_counter.values())
    rows_out = [[i, n, fmt_pct(n, total)] for i, n in intent_counter.most_common()]
    print_table(["intent", "count", "pct"], rows_out)

    # ── 工具调用排行 ─────────────────────────────────
    section("🔧 工具调用排行（按调用次数）")
    tool_stats: dict[str, dict] = defaultdict(lambda: {"count": 0, "fails": 0, "durations": []})
    for t in tool_calls:
        tool = t["name"] or "(unknown)"
        tool_stats[tool]["count"] += 1
        if not t["success"]:
            tool_stats[tool]["fails"] += 1
        if t["duration_ms"] is not None:
            tool_stats[tool]["durations"].append(t["duration_ms"])
    if tool_stats:
        rows_out = []
        for tool, st in sorted(tool_stats.items(), key=lambda kv: -kv[1]["count"]):
            rows_out.append([
                tool,
                st["count"],
                st["fails"],
                fmt_pct(st["fails"], st["count"]),
                fmt_ms(st["durations"]),
            ])
        print_table(["tool", "calls", "fails", "fail%", "timing"], rows_out)
    else:
        print("(窗口内无工具调用)")

    # ── 每用户活跃度 ─────────────────────────────────
    section("👤 用户活跃度（top 10）")
    user_chats: Counter = Counter()
    user_tools: Counter = Counter()
    for c in chats:
        if c["username"]:
            user_chats[c["username"]] += 1
    for t in tool_calls:
        if t["username"]:
            user_tools[t["username"]] += 1
    rows_out = []
    for u, n in user_chats.most_common(10):
        rows_out.append([u, n, user_tools.get(u, 0)])
    if rows_out:
        print_table(["user", "chats", "tool_calls"], rows_out)

    # ── 失败的 chat 抽样（如果有）─────────────────────
    if chat_errors:
        section("❌ 失败 chat 抽样（最多 5 条）")
        fails = [c for c in chats if not c["success"]][:5]
        for c in fails:
            err = c["payload"].get("error", "(no error msg)")
            print(f"  [{c['ts']}] user={c['username']} mode={c['payload'].get('mode')} "
                  f"intent={c['payload'].get('intent')} err={err[:120]}")

    # ── 工具失败抽样 ─────────────────────────────────
    failed_tools = [t for t in tool_calls if not t["success"]]
    if failed_tools:
        section("⚠️  工具失败抽样（最多 5 条）")
        for t in failed_tools[:5]:
            print(f"  [{t['ts']}] user={t['username']} tool={t['name']} "
                  f"via={t['payload'].get('via')} duration={t['duration_ms']}ms")

    # ── 原始事件抽样（--raw）─────────────────────────
    if args.raw:
        section("🧾 原始事件抽样（最近 10 条）")
        sample = rows[-10:]
        for ts, username, event_type, name, payload_json, duration_ms, success in sample:
            print(f"  [{ts}] {event_type:10s} {(name or ''):20s} user={username or '-':10s} "
                  f"dur={duration_ms or '-'} ok={bool(success)}  payload={payload_json or ''}")

    print()
    print("=" * 60)
    print("提示：跑 `python analyze.py --raw` 可以看到原始事件，方便发现盲区。")
    print("     按需在 events 表 SELECT 自己关心的维度，原始数据都在。")


if __name__ == "__main__":
    main()
