"""Drafting, evidence based editorial review and incremental archiving."""

from __future__ import annotations

from copy import deepcopy
from difflib import SequenceMatcher
import re

from .bible import apply_archive
from .context import build_review_bible, build_writer_context, trim_bible
from .deliberation import messages_for
from .schemas import ValidationError, compact, validate_archive, validate_review


def compact_length(text):
    return len(re.sub(r"\s+", "", text))


def _paragraphs(text):
    paragraphs = [paragraph for paragraph in re.split(r"\n\s*\n", text)
                  if paragraph.strip()]
    if len(paragraphs) <= 2 and len(text.splitlines()) >= 6:
        return [line for line in text.splitlines() if line.strip()]
    return paragraphs


def changed_passages(previous_text, current_text, *, limit=3000):
    """Compute changed paragraphs; ``limit=None`` preserves the full evidence.

    The default remains the bounded payload view. Review validation requests
    the full collection separately, so clipping never removes an error's scope.
    Deletions have no surviving passage to quote and yield no new passages.
    """
    previous, current = _paragraphs(previous_text), _paragraphs(current_text)
    changed = []
    for operation, _a, _b, start, end in SequenceMatcher(
            None, previous, current, autojunk=False).get_opcodes():
        if operation in {"insert", "replace"}:
            changed.extend(current[start:end])
    changed = list(dict.fromkeys(changed))
    return _passages_payload(changed, limit=limit)


def _passages_payload(passages, *, limit=3000):
    """Bound only model context, never the collection used to validate reviews."""
    if limit is None or sum(map(len, passages)) <= limit:
        return list(passages)
    marker = "（改动段落超过上限，已截断）"
    remaining = max(0, limit - len(marker))
    bounded = []
    for paragraph in passages:
        if not remaining:
            break
        bounded.append(paragraph[:remaining])
        remaining -= len(bounded[-1])
    bounded.append(marker[:limit])
    return bounded


def _validate_focused_review(data, body, *, adaptation_blocking, previous_issues,
                             passages):
    """Keep old blockers in scope and downgrade fresh unchanged-text findings."""
    review = validate_review(data, body, adaptation_blocking=adaptation_blocking)
    old_evidence = [compact(issue["evidence"]) for issue in previous_issues]
    changed_evidence = [compact(passage) for passage in passages]
    body_compact = compact(body)
    paragraphs = [compact(paragraph) for paragraph in _paragraphs(body)]

    def was_reported(issue, evidence):
        index = issue.get("previous_issue_index")
        if type(index) is int and 1 <= index <= len(previous_issues):
            return True
        start = body_compact.find(evidence)
        for old in old_evidence:
            if evidence in old or old in evidence:
                return True
            old_start = body_compact.find(old)
            if (start >= 0 and old_start >= 0
                    and start < old_start + len(old) and old_start < start + len(evidence)):
                return True
            if any(evidence in paragraph and old in paragraph for paragraph in paragraphs):
                return True
        return False

    for issue in review["issues"]:
        evidence = compact(issue["evidence"])
        if not was_reported(issue, evidence) and not any(evidence in passage for passage in changed_evidence):
            issue["blocking"] = False
            issue["outside_changes"] = True
    review["passed"] = not any(issue["blocking"] for issue in review["issues"])
    return review


def validate_manuscript(body, chapter, title):
    """Validate a canonical manuscript after normalization by the pipeline."""
    if not isinstance(body, str) or not body:
        raise ValidationError(["写手必须输出非空 Markdown 正文"])
    expected = f"# 第{chapter}章 {title}"
    if body.splitlines()[0] != expected:
        raise ValidationError([f"正文首行必须是 {expected}"])
    return body


def normalize_manuscript(body, chapter, title):
    """Accept harmless Markdown variations and return a canonical fresh string."""
    if not isinstance(body, str):
        raise ValidationError(["写手必须输出非空 Markdown 正文"])
    lines = body.strip().splitlines()
    if (len(lines) >= 2 and lines[0].strip().lower() in ("```markdown", "```")
            and lines[-1].strip() == "```"):
        lines = "\n".join(lines[1:-1]).strip().splitlines()
    if not lines or not "\n".join(lines).strip():
        raise ValidationError(["写手必须输出非空 Markdown 正文"])
    expected = f"# 第{chapter}章 {title}"
    heading = re.compile(r"^#{1,3}\s*第\s*([0-9零〇一二两三四五六七八九十百千]+)\s*章[\s:：]*(.*)$")

    def matching_heading(line):
        match = heading.match(line)
        if match and _chapter_number(match.group(1)) == chapter:
            return match
        return None

    if matching_heading(lines[0]):
        lines[0] = expected
    else:
        lines.insert(0, expected)
    next_line = 1
    while next_line < len(lines) and not lines[next_line].strip():
        next_line += 1
    if next_line < len(lines):
        duplicate = matching_heading(lines[next_line])
        if duplicate and duplicate.group(2).strip() == title.strip():
            del lines[next_line]
    return validate_manuscript("\n".join(lines), chapter, title)


def _chapter_number(value):
    """Read Arabic and ordinary Chinese chapter numbers without changing text."""
    if value.isascii() and value.isdecimal():
        return int(value)
    digits = {character: number for number, character in enumerate("零一二三四五六七八九")}
    digits.update({"〇": 0, "两": 2})
    if all(character in digits for character in value):
        return int("".join(str(digits[character]) for character in value))
    units = {"十": 10, "百": 100, "千": 1000}
    number = total = 0
    for character in value:
        if character in digits:
            number = digits[character]
        elif character in units:
            total += (number or 1) * units[character]
            number = 0
        else:
            return None
    return total + number


async def apply_archived_chapter(router, config, compass, bible, archive, *,
                                 chapter, title, beat_sheet, arm, arc_step_key=None,
                                 decision=None):
    """Apply one canonical delta and shared P1 metadata/paid volume-summary task.

    Both a newly written chapter and a user-edited latest chapter use this path.
    Callers provide the complete previous bible, not its context-only view.
    """
    next_bible = apply_archive(bible, archive, chapter, title,
                               config=config, decision=decision)
    if config.get("enable_context_compression"):
        old_ids = {item["id"] for item in bible["locked"]["characters"]}
        new_ids = [item["id"] for item in next_bible["locked"]["characters"]
                   if item["id"] not in old_ids]
        seen = list(dict.fromkeys([*beat_sheet["characters"], *new_ids]))
        next_bible["dynamic"]["chapter_summaries"][-1]["characters"] = seen
        for identifier in seen:
            next_bible["dynamic"]["character_states"][identifier]["last_seen_chapter"] = chapter
    if config.get("enable_arc_summaries") and chapter % 10 == 0:
        arc_start = chapter - 9
        summaries = [item for item in next_bible["dynamic"]["chapter_summaries"]
                     if arc_start <= item["chapter"] <= chapter]

        def validate_arc(data):
            if (not isinstance(data, dict) or not isinstance(data.get("summary"), str)
                    or not 1 <= len(data["summary"].strip()) <= 600):
                raise ValidationError(["卷摘要必须为 1–600 字的非空文本"])
            return {"summary": data["summary"].strip()}

        arc_bible = (trim_bible(next_bible, chapter + 1, beat_sheet["characters"])
                     if config.get("enable_context_compression") else next_bible)
        payload = {"task": "arc_summary", "chapter": chapter,
                   "start_chapter": arc_start, "end_chapter": chapter,
                   "chapter_summaries": summaries,
                   "bible": {"locked": deepcopy(arc_bible["locked"]),
                             "compass": deepcopy(compass)}}
        card, messages = messages_for("archivist", payload, task="arc_summary",
            chapter_words=config["target"]["chapter_words"],
            split_context=config.get("enable_context_compression", False),
            structure=config.get("structure"), experiment=config.get("experiment"))
        arc = await router.call(
            step_key=arc_step_key or f"arm-{arm}/ch{chapter:03d}/07-arc-summary-archivist.json",
            role="archivist", model=config["agents"]["archivist"], messages=messages,
            max_tokens=card["max_tokens"], output=card["output"],
            experiment=config["experiment"], arm=arm, chapter=chapter, validator=validate_arc)
        arcs = next_bible["dynamic"].setdefault("arc_summaries", [])
        arcs[:] = [item for item in arcs if item.get("end_chapter") != chapter]
        arcs.append({"start_chapter": arc_start, "end_chapter": chapter, "summary": arc["summary"]})
    return next_bible


async def write_chapter(router, config, compass, bible, meeting, *, chapter, arm,
                        previous_text=""):
    """Write and archive one accepted decision, with at most two review revisions.

    Files containing the final manuscript, bible and flags are deliberately left
    to the experiment orchestrator; each paid call is persisted by the router.
    """
    decision = meeting["decision"]
    beat_sheet = decision["beat_sheet"]
    title = beat_sheet["title"]
    words = config["target"]["chapter_words"]
    length_range = {"min": (3 * words + 4) // 5, "max": 8 * words // 5,
                    "target": words}
    context = build_writer_context(compass, bible, beat_sheet, chapter,
                                   previous_text=previous_text,
                                   compressed=config.get("enable_context_compression", False))
    if config.get("structure") == "v2":
        context["genre_payoff"] = deepcopy(decision.get("genre_payoff"))
        context["milestones_advanced"] = deepcopy(decision.get("milestones_advanced", []))
    prefix = f"arm-{arm}/ch{chapter:03d}"
    flags, reviews = [], []
    body = ""
    blocking_issues = []
    revision_rounds = 0
    previous_review_body = ""
    focused_reviews = config.get("experiment") == "P1"

    async def call(role, task, filename, payload, validator):
        card, messages = messages_for(role, {"task": task, "chapter": chapter, **payload},
                                      chapter_words=words, task=task,
                                      split_context=config.get("enable_context_compression", False),
                                      structure=config.get("structure"), experiment=config.get("experiment"))
        return await router.call(
            step_key=f"{prefix}/{filename}", role=role, model=config["agents"][role],
            messages=messages, max_tokens=card["max_tokens"], validator=validator,
            output=card["output"], experiment=config["experiment"], arm=arm,
            chapter=chapter)

    for revision in range(3):
        for length_attempt in range(2):
            length_instruction = ""
            if length_attempt:
                previous_length = compact_length(body)
                direction = "超出" if previous_length > length_range["max"] else "不足"
                length_instruction = (
                    f"上一稿 {previous_length} 字，{direction}范围 "
                    f"{length_range['min']}–{length_range['max']} 字；"
                    f"请重写完整正文，目标 {words} 字，宁可略短，不要超过上限。")
            body = await call(
                "writer", "write", f"04-write-writer-r{revision}-a{length_attempt}.json",
                {"context": context,
                 "title": title, "target_words": words, "length_range": length_range,
                 "previous_draft": body,
                 "blocking_issues": blocking_issues, "revision": revision,
                 "write_attempt": length_attempt,
                 "length_instruction": length_instruction},
                lambda text: normalize_manuscript(text, chapter, title))
            if length_range["min"] <= compact_length(body) <= length_range["max"]:
                break
        if "reviewer" not in config["agents"]:
            break
        review_payload = {
            "body": body, "beat_sheet": beat_sheet,
            "bible": build_review_bible(compass, bible, chapter, beat_sheet["characters"]),
            "review_round": revision}
        if config.get("structure") == "v2":
            review_payload["genre_payoff"] = deepcopy(decision.get("genre_payoff"))
        adaptation_blocking = bool(config.get("drama_adaptation"))
        if adaptation_blocking:
            review_payload["adaptation_blocking"] = True
            review_payload["adaptation_limits"] = config["adaptation"]
        if revision >= 1:
            review_payload["previous_blocking_issues"] = deepcopy(blocking_issues)
        passages = []
        if focused_reviews and revision >= 1:
            passages = changed_passages(previous_review_body, body, limit=None)
            if passages:
                review_payload["changed_passages"] = _passages_payload(passages)
        review = await call(
            "reviewer", "review", f"05-review-reviewer-r{revision}.json",
            review_payload, lambda data: (
                _validate_focused_review(data, body, adaptation_blocking=adaptation_blocking,
                                         previous_issues=blocking_issues, passages=passages)
                if focused_reviews and revision >= 1 else
                validate_review(data, body, adaptation_blocking=adaptation_blocking)))
        previous_review_body = body
        reviews.append(review)
        if not review["issues"] and review["dropped_issues"] and "review_degraded" not in flags:
            flags.append("review_degraded")
        blocking_issues = [deepcopy(issue) for issue in review["issues"] if issue["blocking"]]
        if not blocking_issues:
            break
        if revision == 2:
            flags.append("review_unresolved")
            break
        revision_rounds += 1

    # A review revision can also fix a previously short or long draft.  The
    # chapter's length flag describes the accepted final manuscript.
    if not length_range["min"] <= compact_length(body) <= length_range["max"]:
        flags.insert(0, "length_out_of_range")
    archive_payload = {"body": body, "beat_sheet": beat_sheet,
                       "bible": (build_review_bible(compass, bible, chapter, beat_sheet["characters"])
                                 if config.get("enable_context_compression") else bible)}
    if config.get("structure") == "v2":
        archive_payload["genre_payoff"] = deepcopy(decision.get("genre_payoff"))
        archive_payload["milestones_advanced"] = deepcopy(decision.get("milestones_advanced", []))
    archive = await call(
        "archivist", "archive", "06-archive-archivist.json",
        archive_payload,
        lambda data: validate_archive(
            data, bible, require_new_appearance=config.get("experiment") == "P1",
            config=config, decision=decision))
    next_bible = await apply_archived_chapter(
        router, config, compass, bible, archive, chapter=chapter, title=title,
        beat_sheet=beat_sheet, arm=arm, decision=decision)
    if archive["locked_conflicts"]:
        flags.append("locked_conflict")
    if archive["deviation_from_beat_sheet"]["deviated"]:
        flags.append("deviation")
    return {"body": body, "bible": next_bible, "flags": flags,
            "review_rounds": len(reviews), "revision_rounds": revision_rounds,
            "reviews": reviews, "archive": archive,
            "open_major_foreshadowing": [deepcopy(item)
                                          for item in next_bible["dynamic"]["foreshadowing"]
                                          if item["importance"] == "major" and item["status"] == "open"]}
