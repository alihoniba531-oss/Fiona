"""Offline experiment CLI. No SDK or credential access occurs at import time."""

from __future__ import annotations

import argparse
import asyncio
import copy
import hashlib
import json
import re
from pathlib import Path

from .agent_pool import AGENTS, get_agent, validate_agents
from .bible import build_setup
from .context import build_review_bible
from .deliberation import deliberate
from .llm_router import BudgetExhausted, ConfigurationError, LLMRouter, StepFailed, parse_model, validate_environment, validate_model_settings
from .report import estimate_report, generate_blind, generate_report, load_prices
from .run_store import RunStore
from .schemas import compact, validate_insertions, validate_review, validate_setup
from .writing import write_chapter


def validate_config(config: dict) -> None:
    if not isinstance(config, dict):
        raise ValueError("配置必须为 JSON 对象")
    if config.get("experiment") not in ("A", "B", "C"):
        raise ValueError("experiment 必须为 A、B 或 C")
    if config.get("panel_mode", "merge") not in ("merge", "critique"):
        raise ValueError("panel_mode 必须为 merge 或 critique")
    if not isinstance(config.get("seed_idea"), str) or not config["seed_idea"].strip():
        raise ValueError("seed_idea 必须为非空文本")
    target = config.get("target")
    adaptation = config.get("adaptation")
    if not isinstance(target, dict) or any(type(target.get(key)) is not int or target[key] < 1 for key in ("min_chapters", "max_chapters", "chapter_words")):
        raise ValueError("target 章数与字数必须为正整数")
    if target["min_chapters"] > target["max_chapters"]:
        raise ValueError("min_chapters 不得大于 max_chapters")
    if not isinstance(adaptation, dict) or any(type(adaptation.get(key)) is not int or adaptation[key] < 1 for key in ("max_main_characters", "max_scenes_per_chapter")):
        raise ValueError("adaptation 上限必须为正整数")
    if type(config.get("critique_rounds")) is not int or config["critique_rounds"] != 1:
        raise ValueError("P0 的 critique_rounds 必须为 1")
    validate_agents(config)
    notes = config.get("user_notes", {})
    if not isinstance(notes, dict) or any(not isinstance(key, str) or not re.fullmatch(r"[1-9][0-9]*", key) or not isinstance(value, str) or not value.strip() for key, value in notes.items()):
        raise ValueError("user_notes 必须为正整数字符串章号到非空留言的对象")
    experiment = config["experiment"]
    if experiment == "A":
        if type(config.get("chapters_per_arm")) is not int or not 1 <= config["chapters_per_arm"] <= target["max_chapters"]:
            raise ValueError("chapters_per_arm 必须为不超过 max_chapters 的正整数")
        arms = config.get("arms")
        if not isinstance(arms, dict) or set(arms) != {"solo", "panel"}:
            raise ValueError("实验 A 必须有 solo 和 panel 两组")
        for name, participants in arms.items():
            if not isinstance(participants, list) or not participants or "editor" not in participants or len(participants) != len(set(participants)):
                raise ValueError("每组必须包含主编且不得重复智能体")
            if any(role not in config["agents"] or AGENTS[role]["category"] != "deliberation" for role in participants):
                raise ValueError("组别只能使用已配置的推演智能体")
        if arms["solo"] != ["editor"] or not any(role != "editor" for role in arms["panel"]):
            raise ValueError("solo 必须只有主编，panel 必须包含其他推演智能体")
    if experiment == "C":
        if "corrupter" not in config["agents"]:
            raise ValueError("实验 C 缺少 corrupter")
        reviewers = config.get("reviewers_to_compare")
        if not isinstance(reviewers, list) or not reviewers:
            raise ValueError("实验 C 必须配置 reviewers_to_compare")
        for model in reviewers:
            _model_spec(model)


def _model_spec(model):
    if not isinstance(model, str) or not re.fullmatch(r"(dashscope|deepseek|anthropic|ark|fake):[^\s:]+", model):
        raise ValueError("模型规格必须为合法的 提供方:型号，提供方只能为 dashscope、deepseek、anthropic、ark、fake")
    parse_model(model)


def _used_models(config):
    if config["experiment"] == "C":
        return [config["agents"]["corrupter"], *config["reviewers_to_compare"]]
    roles = {"editor", "writer", "archivist"}
    if "reviewer" in config["agents"]:
        roles.add("reviewer")
    if config["experiment"] == "A":
        roles.update(role for arm in config["arms"].values() for role in arm)
    else:
        roles.update(role for role in config["agents"] if AGENTS[role]["category"] == "deliberation")
    return [config["agents"][role] for role in sorted(roles)]


def _messages(role, payload, config, task=None):
    card = get_agent(role, chapter_words=config["target"]["chapter_words"], task=task)
    return [{"role": "system", "content": card["system_prompt"]}, {"role": "user", "content": json.dumps(payload, ensure_ascii=False, sort_keys=True)}], card["max_tokens"]


def _notes(config, chapter):
    return [{"id": f"N{index}", "text": config["user_notes"][key]} for index, key in enumerate(sorted(config.get("user_notes", {}), key=int), 1) if int(key) == chapter]


async def _setup(router, store, config):
    payload = {"task": "setup", "seed_idea": config["seed_idea"], "target": config["target"], "adaptation": config["adaptation"]}
    messages, max_tokens = _messages("editor", payload, config, "setup")
    data = await router.call(step_key="setup/steps/00-setup-editor.json", role="editor", model=config["agents"]["editor"], messages=messages, max_tokens=max_tokens, validator=lambda value: validate_setup(value, config), experiment=config["experiment"])
    compass, bible = build_setup(data, config)
    store.write_json("setup/compass.json", compass)
    store.write_json("setup/bible_v1.json", bible)
    return compass, bible


async def _chapter(router, store, config, compass, bible, chapter, arm, participants, history, written_words, previous_text):
    prefix = f"arm-{arm}/ch{chapter:03d}"
    store.write_json(f"{prefix}/bible_before.json", bible)
    meeting = await deliberate(router, config, compass, bible, chapter=chapter, arm=arm, participants=participants, history=history, written_words=written_words, user_notes=_notes(config, chapter))
    result = await write_chapter(router, config, compass, bible, meeting, chapter=chapter, arm=arm, previous_text=previous_text)
    decision = meeting["decision"]
    title = decision["beat_sheet"]["title"]
    store.write_text(f"{prefix}/chapter.md", result["body"])
    store.write_json(f"{prefix}/bible_v{result['bible']['version']}.json", result["bible"])
    store.write_json(f"{prefix}/flags.json", result["flags"])
    record = {"chapter": chapter, "title": title, "meeting": meeting, "ending_status": decision["ending_status"], "flags": result["flags"], "review_rounds": result["review_rounds"], "revision_rounds": result.get("revision_rounds", 0), "summary": result["archive"]["summary"], "archive": result["archive"]}
    reviews = result.get("reviews", [])
    record["review_dropped_issues"] = sum(len(review.get("dropped_issues", [])) for review in reviews)
    record["review_blocking_defaulted"] = sum(
        issue.get("blocking_defaulted") is True
        for review in reviews for issue in review.get("issues", []))
    store.write_json(f"{prefix}/chapter_record.json", record)
    return result, decision


async def _experiment_a(router, store, config):
    compass, initial = await _setup(router, store, config)
    for arm in ("solo", "panel"):
        bible, history, written_words, previous = copy.deepcopy(initial), [], 0, ""
        for chapter in range(1, config["chapters_per_arm"] + 1):
            result, decision = await _chapter(router, store, config, compass, bible, chapter, arm, config["arms"][arm], history, written_words, previous)
            bible, previous = result["bible"], result["body"]
            written_words += len(re.sub(r"\s", "", previous))
            history.append(decision)
    generate_blind(store.out)


async def _experiment_b(router, store, config):
    compass, bible = await _setup(router, store, config)
    participants = [role for role in config["agents"] if AGENTS[role]["category"] == "deliberation"]
    history, written_words, previous, replies = [], 0, "", []
    target = config["target"]
    for chapter in range(1, target["max_chapters"] + 1):
        result, decision = await _chapter(router, store, config, compass, bible, chapter, "panel", participants, history, written_words, previous)
        bible, previous = result["bible"], result["body"]
        written_words += len(re.sub(r"\s", "", previous))
        history.append(decision)
        replies += [{"chapter": chapter, **reply} for reply in decision["user_note_responses"]]
        if decision["ending_status"] == "end":
            store.set_status("running", completion={"chapter": chapter, "within_target": target["min_chapters"] <= chapter <= target["max_chapters"], "open_major_foreshadowing": [item for item in bible["dynamic"]["foreshadowing"] if item["status"] == "open" and item["importance"] == "major"], "ending_statuses": [item["ending_status"] for item in history], "user_note_responses": replies})
            return


def evidence_matches(evidence: str, sentence: str, minimum: int = 8) -> bool:
    """Use the same evidence normalization as the review schema."""
    left, right = compact(evidence), compact(sentence)
    return any(left[index:index + minimum] in right for index in range(len(left) - minimum + 1))


def insert_contradictions(body: str, insertions: list[dict]) -> str:
    """Offsets are computed in the original draft, so inserted anchors cannot cascade."""
    positions = [(body.index(item["after_anchor"]) + len(item["after_anchor"]), index, item["new_sentence"]) for index, item in enumerate(insertions)]
    for position, _, sentence in sorted(positions, reverse=True):
        body = body[:position] + "\n" + sentence + body[position:]
    return body


def _source_data(source_run):
    if source_run is None:
        raise ValueError("实验 C 必须提供 --source-run")
    source = Path(source_run)
    try:
        manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
        if manifest.get("experiment", manifest.get("config", {}).get("experiment")) != "A":
            raise ValueError("--source-run 必须为实验 A")
        chapter_path = source / "arm-panel/ch004"
        body = (chapter_path / "chapter.md").read_text(encoding="utf-8")
        record = json.loads((chapter_path / "chapter_record.json").read_text(encoding="utf-8"))
        bible = json.loads((chapter_path / "bible_before.json").read_text(encoding="utf-8"))
        compass = json.loads((source / "setup/compass.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, KeyError):
        raise ValueError("--source-run 缺少 panel 第4章最终稿、细纲或章前圣经") from None
    beat_sheet = record["meeting"]["decision"]["beat_sheet"]
    fingerprint = hashlib.sha256(json.dumps([body, bible, beat_sheet, compass], ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    return body, bible, beat_sheet, compass, fingerprint


async def _experiment_c(router, store, config, source):
    body, bible, beat_sheet, compass, fingerprint = source
    if store.manifest.get("source_fingerprint", fingerprint) != fingerprint:
        raise ValueError("来源内容已变化，请换一个 --out")
    store.set_status("running", source_fingerprint=fingerprint)
    store.write_text("source/original.md", body)
    store.write_json("source/bible_before.json", bible)
    store.write_json("source/beat_sheet.json", beat_sheet)
    store.write_json("source/compass.json", compass)
    payload = {"task": "corrupt", "body": body, "bible": bible, "beat_sheet": beat_sheet}
    messages, max_tokens = _messages("corrupter", payload, config)
    corrupted = await router.call(step_key="control/01-corrupt-corrupter.json", role="corrupter", model=config["agents"]["corrupter"], messages=messages, max_tokens=max_tokens, validator=lambda value: validate_insertions(value, body, bible), experiment="C", chapter=4, arm="control")
    insertions = corrupted["insertions"]
    contaminated = insert_contradictions(body, insertions)
    store.write_text("control/contaminated.md", contaminated)
    store.write_json("control/insertions.json", insertions)
    comparison = []
    for index, model in enumerate(config["reviewers_to_compare"], 1):
        reviews = {}
        for label, draft in (("original", body), ("contaminated", contaminated)):
            messages, max_tokens = _messages("reviewer", {"task": "review", "chapter": 4, "body": draft, "bible": build_review_bible(compass, bible), "beat_sheet": beat_sheet, "review_round": 0}, config)
            reviews[label] = await router.call(step_key=f"control/reviewer-{index:02d}/{label}.json", role="reviewer", model=model, messages=messages, max_tokens=max_tokens, validator=lambda value, draft=draft: validate_review(value, draft), experiment="C", chapter=4, arm=label)
        caught = [any(evidence_matches(issue["evidence"], insertion["new_sentence"]) for issue in reviews["contaminated"]["issues"]) for insertion in insertions]
        comparison.append({"model": model, "caught_count": sum(caught), "caught": caught, "false_positives": sum(issue["blocking"] for issue in reviews["original"]["issues"]), "original": reviews["original"], "contaminated": reviews["contaminated"]})
    store.write_json("comparison.json", comparison)


async def run_experiment(config, out, *, dry_run=False, source_run=None, max_total_tokens=3_000_000, prices=None, fake=None) -> int:
    """Run or resume an experiment, returning the documented process exit code."""
    store = None
    try:
        validate_config(config)
        prices = load_prices(prices)
        if type(max_total_tokens) is not int or max_total_tokens < 0:
            raise ValueError("max-total-tokens 必须为非负整数")
        validate_model_settings(_used_models(config), dry_run=dry_run)
        validate_environment(_used_models(config), dry_run=dry_run)
        source = _source_data(source_run) if config["experiment"] == "C" else None
        store = RunStore(out, config, dry_run=dry_run, max_total_tokens=max_total_tokens)
        store.set_status("running", experiment=config["experiment"])
        router = LLMRouter(store, fake=fake, dry_run=dry_run)
        if config["experiment"] == "A":
            await _experiment_a(router, store, config)
        elif config["experiment"] == "B":
            await _experiment_b(router, store, config)
        else:
            await _experiment_c(router, store, config, source)
        store.set_status("completed")
        generate_report(store.out, prices)
        if dry_run:
            print(estimate_report(store.out), end="")
        return 0
    except BudgetExhausted:
        if store is not None:
            store.set_status("budget_exhausted")
            generate_report(store.out, prices)
        print("预算耗尽：budget_exhausted；请放宽 --max-total-tokens 后续跑")
        return 3
    except StepFailed as error:
        if store is not None:
            store.set_status(error.status, failed_step=getattr(error, "step_key", None) or store.manifest.get("failed_step"))
            generate_report(store.out, prices)
        failed_step = getattr(error, "step_key", None) or (store.manifest.get("failed_step") if store is not None else None)
        print(f"步骤失败：{error.status} failed_step={failed_step or 'unknown'}")
        return 4
    except (ConfigurationError, ValueError, OSError) as error:
        if store is not None:
            store.set_status("config_error")
        print(f"配置或环境错误：{error}")
        return 2


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="小说工坊 P0 离线实验")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run")
    run.add_argument("--config", required=True)
    run.add_argument("--out", required=True)
    run.add_argument("--dry-run", action="store_true")
    run.add_argument("--source-run")
    run.add_argument("--max-total-tokens", type=int, default=3_000_000)
    run.add_argument("--prices")
    report = commands.add_parser("report")
    report.add_argument("--out", required=True)
    report.add_argument("--prices")
    args = parser.parse_args(argv)
    if args.command == "report":
        try:
            if not (Path(args.out) / "manifest.json").is_file():
                raise ValueError("运行目录缺少 manifest.json")
            generate_report(args.out, args.prices)
            return 0
        except (ValueError, OSError) as error:
            print(f"配置或环境错误：{error}")
            return 2
    try:
        config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    except (ValueError, OSError):
        print("配置文件不存在或 JSON 无效")
        return 2
    return asyncio.run(run_experiment(config, args.out, dry_run=args.dry_run, source_run=args.source_run, max_total_tokens=args.max_total_tokens, prices=args.prices))


if __name__ == "__main__":
    raise SystemExit(main())
