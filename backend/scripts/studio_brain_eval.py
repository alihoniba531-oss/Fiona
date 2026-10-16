#!/usr/bin/env python3
"""Manual director evaluation: quote first, explicit CNY spend authorization, no DB."""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_CEILING
import html
import json
import os
from pathlib import Path
import sys
import time

from fastapi import HTTPException

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

TEXT_TASKS = ("read_through", "style_proposals", "bible_extract")
MODELS = {"qwen": "qwen3.8-max", "deepseek": "deepseek-v4-pro"}
LABELS = {"claude": "Claude", "qwen": "千问", "deepseek": "DeepSeek"}


def _money(value):
    try:
        amount = Decimal(str(value))
    except InvalidOperation:
        raise argparse.ArgumentTypeError("金额必须为非负有限数字") from None
    if not amount.is_finite() or amount < 0:
        raise argparse.ArgumentTypeError("金额必须为非负有限数字")
    return amount


def build_parser():
    parser = argparse.ArgumentParser(description="导演模型评测：先报价，--yes-spend 以人民币确认总预算；不经过数据库")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--text-file", "--input", type=Path, help="UTF-8 本地素材文件，最多20000字")
    source.add_argument("--text", help="直接提供素材，最多20000字")
    parser.add_argument("--providers", nargs="+", choices=list(LABELS), default=list(LABELS))
    parser.add_argument("--claude-model", default="claude-opus-5-5")
    parser.add_argument("--image", type=Path, help="可选本地图片；额外运行看图质检")
    parser.add_argument("--yes-spend", type=_money, metavar="金额", help="授权的人民币总预算，须达到报价上限")
    parser.add_argument("--usd-to-cny", type=_money, default=Decimal("7.2"), help="仅供授权折算的固定汇率，默认7.2；报告分别列USD/CNY")
    parser.add_argument("--output-dir", type=Path, default=BACKEND_ROOT / "studio_data" / "_eval")
    return parser


def _runtime():
    # Import provider code only; unlike run_brain there is no BYOK lookup or job
    # persistence. Quoting never instantiates an SDK client or opens a database.
    from studio import brain, brain_tasks, pricing
    return brain, brain_tasks, pricing


def _vision_model():
    from studio.config import get_settings
    model = get_settings().vision_model
    if not model:
        raise HTTPException(409, "工作室视觉模型未配置，请设置 FIONA_STUDIO_VISION_MODEL")
    return model


def build_plan(args, text):
    brain, tasks, pricing = _runtime()
    if not text.strip() or len(text) > 20000:
        raise ValueError("素材须为1–20000字")
    if args.usd_to_cny <= 0:
        raise ValueError("授权折算汇率必须大于0")
    if args.image is not None and not args.image.is_file():
        raise ValueError("图片文件不存在")
    plan = []
    totals = {"USD": Decimal(0), "CNY": Decimal(0)}
    for provider in dict.fromkeys(args.providers):
        for task in (*TEXT_TASKS, *(("frame_qc",) if args.image else ())):
            definition = tasks.get_task(task)
            model = (args.claude_model if provider == "claude" else
                     _vision_model() if task == "frame_qc" else MODELS[provider])
            inputs = {"text": text}
            initial_chars = brain.estimate_input_chars(task, inputs)
            image_tokens = 16384 if task == "frame_qc" else 0
            estimates = [pricing.estimate_brain(model, initial_chars, definition.max_tokens,
                                                image_tokens=image_tokens),
                         pricing.estimate_brain_repair(model, initial_chars, definition.max_tokens,
                                                       image_tokens=image_tokens)]
            currency = estimates[0]["currency"]
            maximum = sum((Decimal(str(item["amount"])) for item in estimates), Decimal(0))
            totals[currency] += maximum
            plan.append({"provider": provider, "task": task, "model": model,
                         "currency": currency, "maximum": maximum,
                         "first_max": estimates[0]["amount"], "repair_max": estimates[1]["amount"]})
    authorized_cny = (totals["CNY"] + totals["USD"] * args.usd_to_cny).quantize(
        Decimal("0.00000001"), rounding=ROUND_CEILING)
    return plan, totals, authorized_cny


def _provider(brain, args, provider, task, vision_model=None):
    if provider == "claude":
        return brain.ClaudeProvider({"api_key": os.environ["ANTHROPIC_API_KEY"],
                    "model": args.claude_model, "provider": "anthropic", "enabled": True, "status": "ok"})
    if task == "frame_qc":
        model = vision_model or _vision_model()
        _runtime()[2].brain_price(model)
        instance = brain.QwenProvider(api_key=os.environ["DASHSCOPE_API_KEY"])
        instance.pin_vision_model(model)
        return instance
    if provider == "qwen":
        return brain.QwenProvider(api_key=os.environ["DASHSCOPE_API_KEY"])
    return brain.DeepSeekProvider(api_key=os.environ["DEEPSEEK_API_KEY"])


def _check_keys(args):
    needed = {"claude": "ANTHROPIC_API_KEY", "qwen": "DASHSCOPE_API_KEY", "deepseek": "DEEPSEEK_API_KEY"}
    names = {needed[item] for item in args.providers}
    if args.image and any(item != "claude" for item in args.providers):
        names.add("DASHSCOPE_API_KEY")
    if any(not os.getenv(name, "").strip() for name in names):
        raise ValueError("所选提供方缺少环境变量Key；没有发起请求")


async def evaluate(args, text, plan):
    brain, _tasks, pricing = _runtime()
    rows = []
    for item in plan:
        record = {**item, "attempts": [], "status": "failed", "output": None,
                  "warnings": [], "repaired": False}
        client = _provider(brain, args, item["provider"], item["task"],
                           item["model"] if item["task"] == "frame_qc" and item["provider"] != "claude" else None)
        repair = None
        for attempt in range(2):
            record["repaired"] = attempt == 1
            reserved = item["first_max" if attempt == 0 else "repair_max"]
            started = time.monotonic()
            try:
                reply = await client.call(item["task"], {"text": text},
                    images=[args.image] if item["task"] == "frame_qc" else None, repair=repair)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                # Never write exception bodies, which can contain prompts/keys.
                record["status"] = getattr(error, "status", "uncertain")
                record["error_code"] = getattr(error, "code", type(error).__name__)
                usage = getattr(error, "usage", None)
                model = getattr(error, "model", None) or item["model"]
                if record["status"] == "failed" and usage is not None:
                    cost, warnings = pricing.settle_brain_response(model, usage,
                        currency=item["currency"], reserved_amount=reserved)
                    record["warnings"].extend(warnings)
                    record["error_message"] = getattr(error, "message", "导演模型没有返回内容")
                    state = "已收到完整失败响应，费用按用量结算"
                else:
                    cost = {"currency": item["currency"], "amount": 0 if record["status"] == "rejected" else None}
                    state = "已发起请求，可能已扣费，费用未知" if record["status"] == "uncertain" else "请求被拒绝（未扣费）"
                record["attempts"].append({"usage": usage or {}, "cost": cost, "model": model,
                    "stop_reason": getattr(error, "stop_reason", None),
                    "latency_s": getattr(error, "latency_s", None) or time.monotonic() - started,
                    "request_state": state})
                break
            model = reply.model or item["model"]
            cost, warnings = pricing.settle_brain_response(model, reply.usage,
                currency=item["currency"], reserved_amount=reserved)
            record["warnings"].extend([*warnings, *getattr(reply, "warnings", [])])
            record["attempts"].append({"usage": reply.usage, "cost": cost,
                "model": model, "stop_reason": reply.stop_reason, "latency_s": reply.latency_s})
            if reply.stop_reason in {"max_tokens", "length"}:
                record.update(status="invalid_output", error_code="max_tokens",
                              error_message="输出超长被截断，请缩短素材或减少勾选的任务")
                break
            try:
                output, warnings = brain.validate_reply(item["task"], reply, {"text": text})
            except brain.InvalidBrainOutput as error:
                if attempt == 1:
                    record["status"] = "invalid_output"
                    record["error_code"] = "invalid_output"
                    break
                repair = {"output": reply.text, "errors": error.errors}
                continue
            record.update(status="succeeded", output=output,
                          warnings=[*record["warnings"], *warnings], repaired=attempt == 1)
            break
        if item["task"] == "frame_qc" and item["provider"] != "claude":
            actual_model = record["attempts"][-1]["model"] if record["attempts"] else item["model"]
            record["warnings"].append(brain.VISION_WARNING.format(model=actual_model))
        record["warnings"] = list(dict.fromkeys(record["warnings"]))
        rows.append(record)
    return rows


def _cell(value):
    return html.escape(str(value)).replace("|", "&#124;").replace("\n", "<br>")


def write_report(args, text, totals, cap, records):
    args.output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    path = args.output_dir / f"{timestamp}.md"
    providers = list(dict.fromkeys(args.providers))
    lines = ["# 导演模型手动评测", "", f"素材长度：{len(text)} 字。原文不写入报告。",
             f"报价上限：USD {totals['USD']:.8f}；CNY {totals['CNY']:.8f}（含每项最多一次修正）。",
             f"授权折算：1 USD = {args.usd_to_cny} CNY，仅供本次授权；合计人民币 {cap:.8f}。",
             "", "| 任务 | " + " | ".join(LABELS[item] for item in providers) + " |",
             "| --- | " + " | ".join("---" for _ in providers) + " |"]
    for task in (*TEXT_TASKS, *(("frame_qc",) if args.image else ())):
        cells = []
        for provider in providers:
            record = next(row for row in records if row["task"] == task and row["provider"] == provider)
            parts = [f"状态：{record['status']}；已修正：{'是' if record['repaired'] else '否'}",
                     f"警告：{'；'.join(record['warnings']) or '无'}"]
            if record.get("error_code"):
                parts.append(f"错误码：{record['error_code']}")
            if record.get("error_message"):
                parts.append(record["error_message"])
            for index, attempt in enumerate(record["attempts"], 1):
                cost = attempt["cost"]
                amount = "未知（可能已扣费）" if cost["amount"] is None else cost["amount"]
                parts.append(f"调用{index}：{attempt['model']}；费用 {cost['currency']} {amount}；"
                             f"{attempt.get('request_state', '已收到响应')}；"
                             f"耗时 {attempt['latency_s']:.3f}s；stop_reason={attempt['stop_reason']}；"
                             f"usage={json.dumps(attempt['usage'], ensure_ascii=False, sort_keys=True)}")
            if record["output"] is not None:
                parts.append(json.dumps(record["output"], ensure_ascii=False, indent=2))
            cells.append(_cell("\n".join(parts)))
        lines.append("| " + _cell(task) + " | " + " | ".join(cells) + " |")
    lines.extend(["", "各家实际价格仍须以作者账单核实。", ""])
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        text = args.text if args.text is not None else args.text_file.read_text(encoding="utf-8-sig")
        plan, totals, cap = build_plan(args, text)
        print(f"预估最高花费（含一次修正）：USD {totals['USD']:.8f}；CNY {totals['CNY']:.8f}。")
        print(f"按授权折算汇率 {args.usd_to_cny}，需 --yes-spend 至少 {cap:.8f} 人民币。")
        if args.yes_spend is None or args.yes_spend < cap:
            print("未提供足额授权；没有发起任何模型请求。")
            return 2
        _check_keys(args)
        records = asyncio.run(evaluate(args, text, plan))
        path = write_report(args, text, totals, cap, records)
        print(f"报告：{path}")
        return 0 if all(row["status"] == "succeeded" for row in records) else 1
    except HTTPException as error:
        print(f"评测未运行：{error.detail}", file=sys.stderr)
        return 1
    except (OSError, ValueError) as error:
        # Local validation messages above contain no source text or credentials.
        print(f"评测未运行：{type(error).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
