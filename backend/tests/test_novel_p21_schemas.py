"""Offline P2.1 schema coverage, including the R1 compatibility switches."""

from copy import deepcopy
import inspect

import pytest

from novel.agent_pool import get_agent
from novel.bible import apply_archive, build_setup
from novel.fake_llm import FakeLLM
from novel.schemas import ValidationError, compact, validate_archive, validate_review


BODY = "林澈站在机房门前核对原始记录。"
LONG_APPEARANCE = "身形清瘦，黑色齐耳短发，左眉有浅疤，常穿深灰工装外套。"


def review_issue(category, blocking=True, evidence=BODY):
    return {"category": category, "problem": "本章场景超过约定数量。",
            "evidence": evidence, "fix": "合并重复场景。", "blocking": blocking}


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("category", ["style", "adaptation"])
@pytest.mark.parametrize("model_blocking", [False, True])
def test_review_blocking_respects_opt_in_and_keeps_style_nonblocking(
        enabled, category, model_blocking):
    data = {"issues": [review_issue(category, model_blocking)]}
    before = deepcopy(data)
    result = validate_review(data, BODY, adaptation_blocking=enabled)
    expected = enabled and category == "adaptation" and model_blocking
    assert result["issues"][0]["blocking"] is expected
    assert result["passed"] is (not expected)
    assert data == before


@pytest.mark.parametrize("category", ["style", "adaptation"])
def test_review_default_still_downgrades_advice(category):
    data = {"issues": [review_issue(category)]}
    assert validate_review(data, BODY) == validate_review(data, BODY, adaptation_blocking=False)
    assert validate_review(data, BODY)["passed"] is True


@pytest.mark.parametrize("evidence", ["短引文", "正文没有出现过的完整引文"])
def test_adaptation_opt_in_keeps_evidence_requirements(evidence):
    result = validate_review({"issues": [review_issue("adaptation", evidence=evidence)]},
                             BODY, adaptation_blocking=True)
    assert result["issues"] == [] and len(result["dropped_issues"]) == 1
    assert result["passed"] is True


def archive_with_character(appearance):
    fake = FakeLLM()
    config = {"target": {"min_chapters": 1, "max_chapters": 2, "chapter_words": 300},
              "adaptation": {"max_main_characters": 6, "max_scenes_per_chapter": 3}}
    _, bible = build_setup(fake.default_response({"task": "setup"}), config)
    archive = fake.default_response({"task": "archive", "chapter": 1})
    archive["new_characters"] = [{"name": "记录保管人", "role": "supporting", "age": "40",
        "appearance": appearance, "personality": "谨慎", "motivation": "保全原件"}]
    return archive, bible


@pytest.mark.parametrize("appearance", [None, "", "短发", " \n\t", "人" * 19,
                                           "「" + "人 " * 19 + "」"])
def test_strict_archive_rejects_missing_or_short_new_appearance(appearance):
    archive, bible = archive_with_character(appearance)
    before = deepcopy(archive)
    with pytest.raises(ValidationError, match=r"new_characters\[0\]\.appearance"):
        validate_archive(archive, bible, require_new_appearance=True)
    assert archive == before


@pytest.mark.parametrize("appearance", ["人" * 20, "「" + "人 \n" * 20 + "」", LONG_APPEARANCE])
def test_strict_archive_accepts_twenty_compact_characters(appearance):
    archive, bible = archive_with_character(appearance)
    before = deepcopy(archive)
    result = validate_archive(archive, bible, require_new_appearance=True)
    assert result == before and result is not archive
    assert len(compact(result["new_characters"][0]["appearance"])) >= 20


@pytest.mark.parametrize("appearance", [None, "", "短发"])
def test_archive_default_and_apply_archive_keep_legacy_appearance(appearance):
    archive, bible = archive_with_character(appearance)
    before = deepcopy(archive)
    result = validate_archive(archive, bible)
    assert result == validate_archive(archive, bible, require_new_appearance=False)
    assert result["new_characters"][0]["appearance"] == (appearance or "")
    updated = apply_archive(bible, archive, 1, "核验")
    assert updated["locked"]["characters"][-1]["appearance"] == (appearance or "")
    assert archive == before and bible["version"] == 1


def test_new_schema_switches_are_keyword_only_and_default_off():
    for validator, name in ((validate_review, "adaptation_blocking"),
                            (validate_archive, "require_new_appearance")):
        parameter = inspect.signature(validator).parameters[name]
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
        assert parameter.default is False


def test_prompts_explain_adaptation_exception_and_new_character_cards():
    prompt = get_agent("reviewer")["system_prompt"]
    assert "style 和 adaptation 一律 blocking=false" in prompt
    assert "唯一例外：payload 含 adaptation_blocking=true 时" in prompt
    assert "本章场景数超过 adaptation_limits.max_scenes_per_chapter" in prompt
    assert "本章出场的主要人物超过 adaptation_limits.max_main_characters" in prompt
    assert "其余 adaptation 问题仍为 false" in prompt
    assert ("new_characters 每人必须写外形，不少于 20 字，写清发型、体型、衣着或显著特征，"
            "便于改编时出角色卡") in get_agent("archivist")["system_prompt"]
