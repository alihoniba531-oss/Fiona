#!/usr/bin/env python3
"""WO0 短片工作室离线可测试探针；付费操作必须显式传入 --yes-spend。"""
from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
import logging
import shutil
import sys
from types import SimpleNamespace

from _studio_probe_common import (
    ENV_NAMES, EXIT_CODES, UNCERTAIN_MESSAGE, ProbeFailure, Runtime,
    apply_failure, fingerprint, rounded_money,
)
import _studio_probe_media as media
import _studio_probe_speech as speech
import _studio_probe_brain as brain


# 单价表均待核实，单位为每百万 token；Claude 为美元，其余为人民币。
# 与导演辅助模块共享唯一价格表；支持 STUDIO_PROBE_PRICE_<PROVIDER>_IN / _OUT。
BRAIN_PRICES = brain.DEFAULT_PRICES


def _positive(value):
    try:
        result = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("必须是正整数") from None
    if result < 1:
        raise argparse.ArgumentTypeError("必须是正整数")
    return result


def _money(value):
    try:
        result = Decimal(value)
    except InvalidOperation:
        raise argparse.ArgumentTypeError("金额必须是非负有限数字") from None
    if not result.is_finite() or result < 0:
        raise argparse.ArgumentTypeError("金额必须是非负有限数字")
    return result


def build_parser():
    parser = argparse.ArgumentParser(description="短片工作室服务探针：默认仅报价，确认金额后才发起付费调用")
    commands = parser.add_subparsers(dest="command", required=True, title="探针")

    def command(name, help_text, *, paid=True):
        child = commands.add_parser(name, help=help_text, description=help_text)
        child.add_argument("--label", default="", help="用途标签，写入报告")
        if paid:
            child.add_argument("--yes-spend", type=_money, metavar="金额", help="本次确认的人民币金额，须达到报价上限")
        return child

    command("plan", "列出默认报价与本地环境状态，不联网", paid=False)
    wan = command("wan", "万相图生视频")
    wan.add_argument("--image", required=True, help="本地首帧图片路径")
    wan.add_argument("--prompt", required=True, help="视频提示词")
    wan.add_argument("--model", choices=["wan3.0-video", "wan3.0-video-prime"], default="wan3.0-video")
    wan.add_argument("--resolution", choices=["480P", "720P", "1080P"], default="480P")
    wan.add_argument("--duration", type=int, default=5)
    wan.add_argument("--ratio", default="adaptive", choices=["adaptive", "21:9", "16:9", "4:3", "1:1", "3:4", "9:16"])
    wan.add_argument("--audio", action=argparse.BooleanOptionalAction, default=True)
    seedance = command("seedance", "Seedance 2.5 首帧生视频")
    seedance.add_argument("--image", required=True)
    seedance.add_argument("--prompt", required=True)
    seedance.add_argument("--model", default=media.DEFAULT_SEEDANCE_MODEL)
    seedance.add_argument("--resolution", choices=["480p", "720p", "1080p"], default="480p")
    seedance.add_argument("--duration", type=int, default=5)
    seedance.add_argument("--generate-audio", action=argparse.BooleanOptionalAction, default=True)
    seedream = command("seedream", "Seedream 出图")
    seedream.add_argument("--prompt", required=True)
    seedream.add_argument("--size", required=True, metavar="WxH")
    seedream.add_argument("--ref", action="append", default=[], help="本地参考图，可重复")
    seedream.add_argument("--model", default=media.DEFAULT_SEEDREAM_MODEL)
    audio = command("seed-audio", "Seed-Audio 配乐、环境声和音效")
    audio.add_argument("--prompt", required=True)
    audio.add_argument("--kind", choices=["bgm", "ambience", "sfx"], default="bgm")
    audio.add_argument("--duration", type=_positive, default=30, help="目标时长标签；参考接口未提供硬性时长字段")
    audio.add_argument("--format", choices=["wav", "mp3", "pcm", "ogg_opus"], default="wav")
    cosy = command("cosyvoice", "CosyVoice 中文配音")
    cosy.add_argument("--text", required=True)
    cosy.add_argument("--voice", default=speech.DEFAULT_VOICE)
    cosy.add_argument("--model", default="cosyvoice-v2")
    edge = command("edge-tts", "免费的英文配音；需要 edge_tts ≥7.3.1", paid=False)
    edge.add_argument("--text", required=True)
    edge.add_argument("--voice", default="en-US-AndrewNeural")
    director = command("brain", "导演分镜或关键帧质检")
    director.add_argument("--provider", required=True, choices=["claude", "qwen", "deepseek", "qwen-vl"])
    director.add_argument("--task", choices=["shots", "vision"], default="shots")
    director.add_argument("--input", help="shots 场景文本文件")
    director.add_argument("--image", help="vision 本地关键帧图片")
    director.add_argument("--model", default=None)
    breakdown = command("breakdown", "长文分块与分集拆解，最多三个 map 同时运行")
    breakdown.add_argument("--provider", choices=["claude", "qwen", "deepseek"], default="qwen")
    breakdown.add_argument("--text-file", required=True)
    breakdown.add_argument("--chunk-chars", type=_positive, default=10000)
    breakdown.add_argument("--max-chunks", type=_positive)
    breakdown.add_argument("--episode-seconds", type=_positive, default=210)
    poll = command("poll", "凭 task_id 免费继续查询和下载，只发 GET", paid=False)
    poll.add_argument("--provider", choices=["wan", "seedance"], required=True)
    poll.add_argument("--task-id", required=True)
    return parser


def _format_quote(estimate):
    result = f"预估金额：人民币 {rounded_money(estimate['min_cny']):.2f}–{rounded_money(estimate['max_cny']):.2f} 元"
    if "max_usd" in estimate:
        result += f"；美元 {estimate['min_usd']:.6f}–{estimate['max_usd']:.6f}"
    return result + "。" + estimate.get("note", "")


def _plan(rt, record):
    estimates = {}
    for name in ("wan", "seedance", "seedream", "seed-audio", "poll"):
        args = SimpleNamespace(command=name, duration=5, resolution="480P" if name == "wan" else "480p")
        estimates[name] = media.quote(args, rt)
    estimates["cosyvoice"] = speech.quote(SimpleNamespace(text="默认配音文本。" * 12), rt)
    estimates["edge-tts"] = {"min_cny": 0, "max_cny": 0, "note": "免费"}
    estimates.update(brain.plan_quotes(rt))
    record["estimates"] = estimates
    rt.emit("默认参数报价（文本类需输入，示例字数和输出预算见说明）：")
    for name, estimate in estimates.items():
        rt.emit(f"{name}：{_format_quote(estimate)}")
    record["environment"] = {name: {"set": bool(rt.env.get(name)), "length": len(rt.env.get(name, ""))}
                             for name in ENV_NAMES}
    for name, state in record["environment"].items():
        rt.emit(f"{name}：{'已设置' if state['set'] else '未设置'}，长度 {state['length']}")
    record["tools"] = {name: bool(shutil.which(name)) for name in ("ffprobe", "ffmpeg")}
    for name, available in record["tools"].items():
        rt.emit(f"{name}：{'可用' if available else '不可用'}")
    module, version = speech.edge_module()
    record["edge_tts"] = {"importable": module is not None, "version": version}
    rt.emit(f"edge_tts：{'可导入' if module is not None else '未安装'}，版本 {version or '未知'}")
    record["status"] = "succeeded"


def _uncertain_fingerprints(record):
    found = []
    if isinstance(record, dict):
        if record.get("fingerprint") and record.get("status") == "uncertain":
            found.append(record["fingerprint"])
        for value in record.values():
            found.extend(_uncertain_fingerprints(value))
    elif isinstance(record, list):
        for value in record:
            found.extend(_uncertain_fingerprints(value))
    return list(dict.fromkeys(found))


def main(argv=None, *, runtime=None):
    args = build_parser().parse_args(argv)
    rt = runtime or Runtime()
    parameters = {key: str(value) if isinstance(value, Decimal) else value for key, value in vars(args).items()}
    record = {"probe": args.command, "label": args.label, "timestamp": rt.timestamp(), "parameters": parameters}
    started = rt.monotonic()
    previous_logging = logging.root.manager.disable
    # SDK 的 DEBUG 环境设置也不能把鉴权头带进日志；一次 CLI 运行结束后恢复。
    logging.disable(sys.maxsize)
    try:
        if args.command == "plan":
            _plan(rt, record)
        elif args.command == "edge-tts":
            speech.run_edge(args, rt, record)
        elif args.command == "poll":
            media.run(args, rt, record)
        else:
            handler = brain if args.command in {"brain", "breakdown"} else speech if args.command == "cosyvoice" else media
            estimate = handler.quote(args, rt)
            record["quote"] = estimate
            rt.emit(_format_quote(estimate))
            threshold = rounded_money(estimate["max_cny"])
            if args.yes_spend is None or args.yes_spend < threshold:
                record["status"] = "quoted"
                rt.emit(f"未发起请求；如确认报价，请传入 --yes-spend {threshold:.2f} 或更高金额。")
            elif args.command == "cosyvoice":
                speech.run_cosyvoice(args, rt, record)
            else:
                handler.run(args, rt, record)
    except ProbeFailure as exc:
        apply_failure(record, exc)
        rt.emit(str(exc))
    except (OSError, ValueError, ImportError) as exc:
        apply_failure(record, ProbeFailure("error", str(exc), code=type(exc).__name__))
        rt.emit(f"本地处理失败：{exc}")
    except Exception as exc:
        # 付费阶段的传输异常已由 paid_call 分类；此处不触发任何补发。
        apply_failure(record, ProbeFailure("error", str(exc), code=type(exc).__name__))
        rt.emit(f"探针处理失败：{exc}")
    finally:
        logging.disable(previous_logging)
    record.setdefault("status", "succeeded")
    record.setdefault("exit_code", EXIT_CODES.get(record["status"], 1))
    record["elapsed_s"] = round(rt.monotonic() - started, 6)
    if record["status"] == "uncertain":
        record.setdefault("fingerprint", fingerprint(parameters))
    uncertain_fingerprints = _uncertain_fingerprints(record)
    if uncertain_fingerprints:
        record["uncertainty_note"] = UNCERTAIN_MESSAGE
        rt.emit(UNCERTAIN_MESSAGE + "。本次请求指纹：" + "、".join(uncertain_fingerprints))
    for key in ("truncation_note", "budget_note"):
        if record.get(key):
            rt.emit(record[key])
    if record.get("task_id"):
        rt.emit(f"task_id：{record['task_id']}")
    try:
        rt.persist(record)
    except (OSError, ValueError) as exc:
        rt.last_record = record
        rt.emit(f"报告写入失败：{type(exc).__name__}；请保存上面的任务 ID 和指纹，勿重新提交付费请求。")
        return record["exit_code"] or 1
    rt.emit(f"探针状态：{record['status']}；报告已保存。")
    return record["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
