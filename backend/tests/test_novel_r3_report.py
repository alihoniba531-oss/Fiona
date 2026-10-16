"""Decision normalization warnings remain visible in author-facing reports."""

import json

import pytest

from novel.report import generate_report


def write_record(out, chapter, *, warnings=None):
    decision = {
        "chosen_proposal_ids": [],
        "rationale": "按当前伏笔推进。",
        "merge_note": "保留已经校验的节拍。",
        "objection_responses": [],
        "user_note_responses": [],
        "ending_status": "continue",
    }
    if warnings is not None:
        decision["warnings"] = warnings
    record = {
        "chapter": chapter,
        "title": f"第{chapter}章标题",
        "meeting": {"decision": decision},
        "summary": "本章摘要。",
    }
    path = out / f"arm-panel/ch{chapter:03d}/chapter_record.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")


def test_report_lists_each_normalization_warning_in_its_chapter(tmp_path):
    warnings = [
        {"field": "beat_sheet.foreshadowing_resolve", "id": "F011", "reason": "已回收"},
        {"field": "beat_sheet.foreshadowing_resolve", "id": "F999", "reason": "不存在"},
    ]
    write_record(tmp_path, 11)
    write_record(tmp_path, 12, warnings=warnings)

    text = generate_report(tmp_path)

    previous, final = text.split("## arm-panel 第 12 章", 1)
    assert "裁决警告" not in previous
    assert "裁决警告：" in final
    assert "| 字段 | ID | 原因 |" in final
    assert "| beat_sheet.foreshadowing_resolve | F011 | 已回收 |" in final
    assert "| beat_sheet.foreshadowing_resolve | F999 | 不存在 |" in final
    assert final.index("裁决警告") < final.index("摘要：本章摘要。")
    assert (tmp_path / "report.md").read_text(encoding="utf-8") == text


@pytest.mark.parametrize("warnings", [None, []], ids=["legacy-record", "empty-warnings"])
def test_report_without_warnings_preserves_legacy_summary(tmp_path, warnings):
    write_record(tmp_path, 1, warnings=warnings)

    text = generate_report(tmp_path)

    assert "推演会摘要：\n- 主编独自构思。" in text
    assert "理由：按当前伏笔推进。" in text
    assert "摘要：本章摘要。" in text
    assert "裁决警告" not in text
