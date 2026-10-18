# -*- coding: utf-8 -*-
"""写歌歌词结构校验与纯代码自检的离线单测。

只测 song.lyrics_check 的纯函数；所有用例把 FIONA_SONG_DIR 指到临时目录，
不读写仓库文件、不访问数据库和网络。
"""

import pytest
from pypinyin import Style, lazy_pinyin

from song import lyrics_check as lc


@pytest.fixture(autouse=True)
def _isolated_song_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("FIONA_SONG_DIR", str(tmp_path / "song_data"))


def _vocal(
    section_id="s1",
    section_type="chorus",
    lines=4,
    chars=(7, 9),
    rhyme="AABB",
):
    return {
        "id": section_id,
        "type": section_type,
        "lines": lines,
        "chars": list(chars) if chars is not None else None,
        "rhyme": rhyme,
    }


def _instrumental(section_id="s1", section_type="intro", **extra):
    section = {"id": section_id, "type": section_type, "lines": 0}
    section.update(extra)
    return section


def _check_single(
    lines,
    *,
    rhyme="free",
    chars=(1, 30),
    lang="Chinese",
    section_type="chorus",
):
    structure = [_vocal("s1", section_type, len(lines), chars, rhyme)]
    sections = [{"id": "s1", "lines": list(lines)}]
    return lc.check_lyrics(structure, sections, lang)


def _codes(issues):
    return [issue["code"] for issue in issues]


def _finals(line):
    return lazy_pinyin(
        line,
        style=Style.FINALS,
        strict=True,
        errors=lambda chunk: list(chunk),
    )


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------


def test_public_constants():
    assert lc.SECTION_TYPES == (
        "intro",
        "verse",
        "pre-chorus",
        "chorus",
        "bridge",
        "inst",
        "outro",
        "hook",
        "build-up",
        "drop",
        "solo",
    )
    assert set(lc.INSTRUMENTAL_TYPES) == {"intro", "inst", "outro", "solo"}
    assert lc.RHYME_FORMATS == ("AABB", "ABAB", "XAXA", "AAAA", "free")
    assert lc.SECTION_TYPE_LABELS == {
        "intro": "前奏",
        "verse": "主歌",
        "pre-chorus": "导歌",
        "chorus": "副歌",
        "bridge": "桥段",
        "inst": "间奏",
        "outro": "尾奏",
        "hook": "记忆点",
        "build-up": "铺垫",
        "drop": "高潮段",
        "solo": "独奏",
    }
    assert lc.PROVIDER_CHAR_LIMITS == {
        "Chinese": 700,
        "Cantonese": 700,
        "English": 2000,
    }


# ---------------------------------------------------------------------------
# count_chars
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("春风又绿江南岸", 7),
        ("我有 123 个梦", 7),
        ("hello 世界", 3),
        ("Hello, 世界!", 3),
        ("2026年", 5),
        ("床前明月光，疑是地上霜。", 10),
        ("", 0),
        ("  ！！！", 0),
    ],
)
def test_count_chars_chinese(line, expected):
    assert lc.count_chars(line, "Chinese") == expected


def test_count_chars_cantonese_uses_same_rules():
    assert lc.count_chars("春天花開", "Cantonese") == 4
    assert lc.count_chars("我有 123 個夢", "Cantonese") == 7


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("hello brave new world", 4),
        ("hello, world!", 2),
        ("  ", 0),
        ("one\ntwo", 2),
        ("...", 1),
    ],
)
def test_count_chars_english_words(line, expected):
    assert lc.count_chars(line, "English") == expected


def test_count_chars_latin_words_and_digits():
    assert lc.count_chars("abc def", "Chinese") == 2
    assert lc.count_chars("abcdef", "Chinese") == 1
    assert lc.count_chars("a-b", "Chinese") == 2
    assert lc.count_chars("abc123", "Chinese") == 4
    assert lc.count_chars("１２３", "Chinese") == 3


def test_count_chars_tolerates_non_string():
    assert lc.count_chars(None, "Chinese") == 0
    assert lc.count_chars(None, "English") == 0


# ---------------------------------------------------------------------------
# structure_errors
# ---------------------------------------------------------------------------


def test_structure_errors_accepts_valid_blueprint():
    structure = [
        _instrumental("s1", "intro"),
        _vocal("s2", "verse", 4, (7, 9), "AABB"),
        _vocal("s3", "chorus", 4, (7, 9), "AABB"),
    ]
    assert lc.structure_errors(structure) == []


def test_structure_errors_requires_a_list():
    assert _codes(lc.structure_errors(None)) == ["structure_shape"]
    assert _codes(lc.structure_errors("s1")) == ["structure_shape"]


def test_structure_errors_requires_one_to_sixteen_sections():
    assert _codes(lc.structure_errors([])) == ["structure_shape"]

    structure = [_instrumental(f"s{i}", "inst") for i in range(1, 18)]
    structure[-1] = _vocal("s17", "chorus", 4, (7, 9), "AABB")
    assert _codes(lc.structure_errors(structure)) == ["structure_shape"]


def test_structure_errors_accepts_sixteen_sections():
    structure = [_instrumental(f"s{i}", "inst") for i in range(1, 16)]
    structure.append(_vocal("s16", "chorus", 4, (7, 9), "AABB"))
    assert lc.structure_errors(structure) == []


@pytest.mark.parametrize("bad_id", ["S1", "s100", "s1.", "", "1"])
def test_structure_errors_rejects_bad_section_id(bad_id):
    structure = [
        _instrumental("s1", "inst"),
        _vocal(bad_id, "chorus", 4, (7, 9), "AABB"),
    ]
    errors = lc.structure_errors(structure)
    assert _codes(errors) == ["section_id"]
    assert errors[0]["section_id"] == bad_id


def test_structure_errors_rejects_duplicate_section_id():
    structure = [
        _vocal("s1", "verse", 4, (7, 9), "AABB"),
        _vocal("s1", "chorus", 4, (7, 9), "AABB"),
    ]
    errors = lc.structure_errors(structure)
    assert _codes(errors) == ["section_id"]
    assert "重复" in errors[0]["message"]


def test_structure_errors_rejects_unknown_type():
    structure = [
        {
            "id": "s1",
            "type": "rap",
            "lines": 4,
            "chars": [7, 9],
            "rhyme": "AABB",
        },
        _vocal("s2", "chorus", 4, (7, 9), "AABB"),
    ]
    errors = lc.structure_errors(structure)
    assert "section_type" in _codes(errors)


def test_structure_errors_requires_chorus_or_hook():
    structure = [
        _instrumental("s1", "intro"),
        _vocal("s2", "verse", 4, (7, 9), "AABB"),
        _vocal("s3", "bridge", 4, (7, 9), "AABB"),
    ]
    errors = lc.structure_errors(structure)
    assert _codes(errors) == ["chorus_required"]


def test_structure_errors_accepts_hook_instead_of_chorus():
    structure = [_vocal("s1", "hook", 2, (1, 10), "free")]
    assert lc.structure_errors(structure) == []


@pytest.mark.parametrize("lines", [0, 13])
def test_structure_errors_vocal_line_bounds(lines):
    structure = [_vocal("s1", "chorus", lines, (7, 9), "AABB")]
    errors = lc.structure_errors(structure)
    assert _codes(errors) == ["section_lines"]


@pytest.mark.parametrize("lines", [1, 2])
def test_structure_errors_instrumental_must_have_zero_lines(lines):
    structure = [_instrumental("s1", "intro", lines=lines), _vocal("s2", "chorus")]
    errors = lc.structure_errors(structure)
    assert _codes(errors) == ["section_lines"]


def test_structure_errors_instrumental_lines_must_be_present():
    structure = [{"id": "s1", "type": "intro"}, _vocal("s2", "chorus")]
    errors = lc.structure_errors(structure)
    assert _codes(errors) == ["section_lines"]


@pytest.mark.parametrize(
    "chars",
    [
        [0, 5],
        [5, 31],
        [9, 7],
        [7],
        [1, 2, 3],
        ["1", 2],
        None,
    ],
)
def test_structure_errors_chars_range(chars):
    structure = [_vocal("s1", "chorus", 4, chars, "AABB")]
    errors = lc.structure_errors(structure)
    assert _codes(errors) == ["section_chars"]


@pytest.mark.parametrize("rhyme", ["AABA", "", None, "aabb"])
def test_structure_errors_rhyme_format(rhyme):
    structure = [_vocal("s1", "chorus", 4, (7, 9), rhyme)]
    errors = lc.structure_errors(structure)
    assert _codes(errors) == ["section_rhyme"]


def test_structure_errors_instrumental_may_omit_chars_and_rhyme():
    structure = [_instrumental("s1", "intro"), _vocal("s2", "chorus")]
    assert lc.structure_errors(structure) == []


def test_structure_errors_rejects_non_object_section():
    structure = [None, _vocal("s2", "chorus")]
    errors = lc.structure_errors(structure)
    assert _codes(errors) == ["section_shape"]


def test_structure_error_shape():
    structure = [
        {"id": "x", "type": "nope"},
        _vocal("s1", "chorus", 0, [0, 99], "bad"),
    ]
    errors = lc.structure_errors(structure)
    assert errors
    for error in errors:
        assert set(error) == {"code", "section_id", "line_index", "message"}
        assert error["line_index"] is None
        assert isinstance(error["message"], str) and error["message"]
        assert error["code"]


# ---------------------------------------------------------------------------
# summarize_structure
# ---------------------------------------------------------------------------


def test_summarize_structure_matches_spec_example():
    structure = [
        _vocal("s1", "verse", 4, (7, 9), "AABB"),
        _vocal("s2", "chorus", 4, (7, 9), "AABB"),
    ]
    assert (
        lc.summarize_structure(structure)
        == "s1 主歌 4 行 7–9 字 AABB；s2 副歌 4 行 7–9 字 AABB"
    )


def test_summarize_structure_instrumental():
    structure = [
        _instrumental("s1", "intro"),
        _vocal("s2", "chorus", 4, (7, 9), "AABB"),
    ]
    assert (
        lc.summarize_structure(structure)
        == "s1 前奏 器乐；s2 副歌 4 行 7–9 字 AABB"
    )


def test_summarize_structure_empty_or_invalid():
    assert lc.summarize_structure([]) == ""
    assert lc.summarize_structure(None) == ""


# ---------------------------------------------------------------------------
# build_provider_text
# ---------------------------------------------------------------------------


def _provider_fixture():
    structure = [
        _instrumental("s1", "intro"),
        _vocal("s2", "verse", 2, (3, 5), "free"),
        _vocal("s3", "chorus", 2, (3, 5), "free"),
    ]
    sections = [
        {"id": "s1", "lines": []},
        {"id": "s2", "lines": ["春风来", "花正开"]},
        {"id": "s3", "lines": ["天边月", "照心间"]},
    ]
    return structure, sections


def test_build_provider_text_exact_shape():
    structure, sections = _provider_fixture()
    expected = (
        "[intro]\n"
        "[verse]\n"
        "春风来\n"
        "花正开\n"
        "[chorus]\n"
        "天边月\n"
        "照心间"
    )
    text = lc.build_provider_text(structure, sections)
    assert text == expected
    assert "\n\n" not in text
    assert not text.startswith("\n")
    assert not text.endswith("\n")


def test_build_provider_text_instrumental_has_only_label():
    text = lc.build_provider_text(
        [_instrumental("s1", "inst")],
        [{"id": "s1", "lines": ["器乐段不应该有歌词"]}],
    )
    assert text == "[inst]"


def test_build_provider_text_ignores_unknown_sections():
    structure = [_vocal("s1", "chorus", 1, (1, 30), "free")]
    sections = [
        {"id": "s1", "lines": ["花"]},
        {"id": "s9", "lines": ["不属于蓝图"]},
    ]
    assert lc.build_provider_text(structure, sections) == "[chorus]\n花"


# ---------------------------------------------------------------------------
# check_lyrics：正常路径与错误
# ---------------------------------------------------------------------------


def _valid_project():
    structure = [
        _instrumental("s1", "intro"),
        _vocal("s2", "verse", 4, (7, 9), "AABB"),
        _vocal("s3", "chorus", 4, (7, 9), "AABB"),
    ]
    sections = [
        {"id": "s1", "lines": []},
        {
            "id": "s2",
            "lines": [
                "春风吹过山岗上",
                "一路花香到故乡",
                "梦里那条小河流",
                "带着思念慢慢走",
            ],
        },
        {
            "id": "s3",
            "lines": [
                "天边月亮照心间",
                "你的笑脸在眼前",
                "岁月如歌唱不完",
                "这份温柔永不变",
            ],
        },
    ]
    return structure, sections


def test_check_lyrics_valid_project():
    structure, sections = _valid_project()
    result = lc.check_lyrics(structure, sections, "Chinese")

    assert result["ok"] is True
    assert result["errors"] == []
    assert result["warnings"] == []
    assert len(result["lines"]) == 8
    for record in result["lines"]:
        assert set(record) == {
            "section_id",
            "line_index",
            "chars",
            "rhyme_group",
            "rhyme_ok",
        }
        assert record["chars"] == 7
        assert record["rhyme_ok"] is True
        assert record["rhyme_group"] is not None

    expected_text = (
        "[intro]\n"
        "[verse]\n"
        "春风吹过山岗上\n"
        "一路花香到故乡\n"
        "梦里那条小河流\n"
        "带着思念慢慢走\n"
        "[chorus]\n"
        "天边月亮照心间\n"
        "你的笑脸在眼前\n"
        "岁月如歌唱不完\n"
        "这份温柔永不变"
    )
    assert result["provider_text"] == expected_text
    assert result["provider_chars"] == len(expected_text)


def test_check_lyrics_english_counts_words():
    structure = [_vocal("s1", "chorus", 2, (2, 2), "free")]
    sections = [{"id": "s1", "lines": ["hello world", "goodbye moon"]}]
    result = lc.check_lyrics(structure, sections, "English")
    assert result["ok"] is True
    assert [record["chars"] for record in result["lines"]] == [2, 2]
    assert [record["rhyme_group"] for record in result["lines"]] == [None, None]
    assert result["provider_text"] == "[chorus]\nhello world\ngoodbye moon"


def test_check_lyrics_result_keys():
    result = _check_single(["花"])
    assert set(result) == {
        "ok",
        "errors",
        "warnings",
        "lines",
        "provider_text",
        "provider_chars",
    }


def test_error_structure_mismatch_order():
    structure = [
        _vocal("s1", "verse", 1, (1, 30), "free"),
        _vocal("s2", "chorus", 1, (1, 30), "free"),
    ]
    sections = [
        {"id": "s2", "lines": ["好"]},
        {"id": "s1", "lines": ["好"]},
    ]
    result = lc.check_lyrics(structure, sections, "Chinese")
    assert result["ok"] is False
    assert "structure_mismatch" in _codes(result["errors"])


def test_error_structure_mismatch_ids():
    structure = [
        _vocal("s1", "verse", 1, (1, 30), "free"),
        _vocal("s2", "chorus", 1, (1, 30), "free"),
    ]
    sections = [
        {"id": "s1", "lines": ["好"]},
        {"id": "s3", "lines": ["好"]},
    ]
    result = lc.check_lyrics(structure, sections, "Chinese")
    assert result["ok"] is False
    assert "structure_mismatch" in _codes(result["errors"])
    assert "empty_section" in _codes(result["errors"])


def test_error_empty_section_without_lines():
    structure = [_vocal("s1", "chorus", 1, (1, 30), "free")]
    result = lc.check_lyrics(structure, [{"id": "s1", "lines": []}], "Chinese")
    assert result["ok"] is False
    assert "empty_section" in _codes(result["errors"])


def test_error_empty_section_blank_line_is_one_based():
    structure = [_vocal("s1", "chorus", 2, (1, 30), "free")]
    result = lc.check_lyrics(
        structure,
        [{"id": "s1", "lines": ["好", "   "]}],
        "Chinese",
    )
    empties = [e for e in result["errors"] if e["code"] == "empty_section"]
    assert len(empties) == 1
    assert empties[0]["line_index"] == 2
    assert empties[0]["section_id"] == "s1"


def test_error_instrumental_has_lines():
    structure = [
        _instrumental("s1", "intro"),
        _vocal("s2", "chorus", 1, (1, 30), "free"),
    ]
    sections = [
        {"id": "s1", "lines": ["啦"]},
        {"id": "s2", "lines": ["花"]},
    ]
    result = lc.check_lyrics(structure, sections, "Chinese")
    assert result["ok"] is False
    assert "instrumental_has_lines" in _codes(result["errors"])
    assert {record["section_id"] for record in result["lines"]} == {"s2"}


@pytest.mark.parametrize("bracket", ["[", "]", "【", "】"])
def test_error_bracket_in_line(bracket):
    result = _check_single([f"春{bracket}风"])
    assert result["ok"] is False
    bracket_errors = [e for e in result["errors"] if e["code"] == "bracket_in_line"]
    assert len(bracket_errors) == 1
    assert bracket_errors[0]["line_index"] == 1


def test_error_line_too_long():
    result = _check_single(["花" * 31], chars=(1, 30))
    assert result["ok"] is False
    too_long = [e for e in result["errors"] if e["code"] == "line_too_long"]
    assert len(too_long) == 1
    record = result["lines"][0]
    assert record["chars"] == 31


def test_line_of_exactly_thirty_chars_is_allowed():
    result = _check_single(["花" * 30], chars=(30, 30))
    assert result["ok"] is True
    assert "line_too_long" not in _codes(result["errors"])


def test_error_too_long_chinese():
    lines = ["春" * 30 for _ in range(12)]
    structure = [
        _vocal("s1", "chorus", 12, (30, 30), "free"),
        _vocal("s2", "chorus", 12, (30, 30), "free"),
        _vocal("s3", "chorus", 12, (30, 30), "free"),
    ]
    sections = [
        {"id": "s1", "lines": list(lines)},
        {"id": "s2", "lines": list(lines)},
        {"id": "s3", "lines": list(lines)},
    ]
    result = lc.check_lyrics(structure, sections, "Chinese")
    assert result["ok"] is False
    assert result["provider_chars"] > 700
    assert "too_long" in _codes(result["errors"])
    assert "line_too_long" not in _codes(result["errors"])


def test_error_too_long_english():
    lines = ["a" * 200 for _ in range(12)]
    structure = [_vocal("s1", "chorus", 12, (1, 30), "free")]
    sections = [{"id": "s1", "lines": list(lines)}]
    result = lc.check_lyrics(structure, sections, "English")
    assert result["ok"] is False
    assert result["provider_chars"] > 2000
    assert "too_long" in _codes(result["errors"])


def test_error_too_long_cantonese():
    lines = ["春" * 20 for _ in range(12)]
    structure = [
        _vocal("s1", "chorus", 12, (20, 20), "free"),
        _vocal("s2", "chorus", 12, (20, 20), "free"),
        _vocal("s3", "chorus", 12, (20, 20), "free"),
    ]
    sections = [
        {"id": "s1", "lines": list(lines)},
        {"id": "s2", "lines": list(lines)},
        {"id": "s3", "lines": list(lines)},
    ]
    result = lc.check_lyrics(structure, sections, "Cantonese")
    assert result["ok"] is False
    assert result["provider_chars"] > 700
    assert "too_long" in _codes(result["errors"])


def test_error_too_long_when_text_shorter_than_five_chars():
    result = lc.check_lyrics([], [], "Chinese")
    assert result["ok"] is False
    assert result["provider_chars"] == 0
    assert "too_long" in _codes(result["errors"])


# ---------------------------------------------------------------------------
# check_lyrics：警告
# ---------------------------------------------------------------------------


def test_warning_line_count():
    structure = [_vocal("s1", "chorus", 4, (1, 30), "free")]
    sections = [{"id": "s1", "lines": ["花", "家"]}]
    result = lc.check_lyrics(structure, sections, "Chinese")
    assert result["ok"] is True
    assert _codes(result["warnings"]) == ["line_count"]


def test_warning_char_count():
    structure = [_vocal("s1", "chorus", 2, (7, 9), "free")]
    sections = [{"id": "s1", "lines": ["花" * 5, "花" * 11]}]
    result = lc.check_lyrics(structure, sections, "Chinese")
    assert result["ok"] is True
    char_warnings = [w for w in result["warnings"] if w["code"] == "char_count"]
    assert len(char_warnings) == 2
    assert {w["line_index"] for w in char_warnings} == {1, 2}
    assert "7–9 字" in char_warnings[0]["message"]


def test_char_count_allows_one_char_tolerance():
    structure = [_vocal("s1", "chorus", 2, (7, 9), "free")]
    sections = [{"id": "s1", "lines": ["花" * 6, "花" * 10]}]
    result = lc.check_lyrics(structure, sections, "Chinese")
    assert result["ok"] is True
    assert "char_count" not in _codes(result["warnings"])


def test_warning_chorus_variant_identical_choruses_do_not_warn():
    structure = [
        _vocal("s1", "chorus", 2, (1, 30), "free"),
        _vocal("s2", "chorus", 2, (1, 30), "free"),
    ]
    sections = [
        {"id": "s1", "lines": ["花", "家"]},
        {"id": "s2", "lines": ["花", "家"]},
    ]
    result = lc.check_lyrics(structure, sections, "Chinese")
    assert result["ok"] is True
    assert "chorus_variant" not in _codes(result["warnings"])


def test_warning_chorus_variant_different_choruses():
    structure = [
        _vocal("s1", "chorus", 2, (1, 30), "free"),
        _vocal("s2", "chorus", 2, (1, 30), "free"),
    ]
    sections = [
        {"id": "s1", "lines": ["花", "家"]},
        {"id": "s2", "lines": ["花", "天"]},
    ]
    result = lc.check_lyrics(structure, sections, "Chinese")
    assert result["ok"] is True
    variants = [w for w in result["warnings"] if w["code"] == "chorus_variant"]
    assert len(variants) == 1
    assert variants[0]["section_id"] == "s2"
    assert variants[0]["line_index"] is None


def test_issue_shape_for_check_lyrics():
    structure = [
        _vocal("s1", "chorus", 2, (7, 9), "AABB"),
        _vocal("s2", "chorus", 2, (7, 9), "AABB"),
    ]
    sections = [
        {"id": "s1", "lines": ["[花]", "天"]},
        {"id": "s2", "lines": ["花", "心"]},
    ]
    result = lc.check_lyrics(structure, sections, "Chinese")
    assert result["errors"]
    assert result["warnings"]
    for issue in result["errors"] + result["warnings"]:
        assert set(issue) == {"code", "section_id", "line_index", "message"}
        assert isinstance(issue["message"], str) and issue["message"]
        assert issue["line_index"] is None or isinstance(issue["line_index"], int)


# ---------------------------------------------------------------------------
# 押韵：十三辙与格式
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("pair", "rhyme_name"),
    [
        (("花", "家"), "发花"),
        (("歌", "多"), "梭波"),
        (("雪", "姐"), "乜斜"),
        (("时", "去"), "一七"),
        (("苦", "书"), "姑苏"),
        (("来", "快"), "怀来"),
        (("飞", "回"), "灰堆"),
        (("好", "桥"), "遥条"),
        (("秋", "走"), "油求"),
        (("天", "元"), "言前"),
        (("春", "军"), "人辰"),
        (("光", "香"), "江阳"),
        (("风", "穷"), "中东"),
    ],
)
def test_each_thirteen_rhyme_has_a_matching_pair(pair, rhyme_name):
    result = _check_single(list(pair), rhyme="AABB")
    assert result["ok"] is True
    assert [record["rhyme_group"] for record in result["lines"]] == [rhyme_name] * 2
    assert [record["rhyme_ok"] for record in result["lines"]] == [True, True]
    assert "rhyme" not in _codes(result["warnings"])


@pytest.mark.parametrize(
    ("pair", "rhyme_name"),
    [
        (("花", "家"), "发花"),
        (("春", "军"), "人辰"),
        (("回", "飞"), "灰堆"),
        (("秋", "走"), "油求"),
        (("雪", "姐"), "乜斜"),
    ],
)
def test_known_same_rhyme_pairs(pair, rhyme_name):
    result = _check_single(list(pair), rhyme="AABB")
    assert {record["rhyme_group"] for record in result["lines"]} == {rhyme_name}
    assert all(record["rhyme_ok"] is True for record in result["lines"])


def test_known_different_rhyme_pair():
    result = _check_single(["天", "心"], rhyme="AABB")
    assert [record["rhyme_group"] for record in result["lines"]] == ["言前", "人辰"]
    assert [record["rhyme_ok"] for record in result["lines"]] == [False, False]
    assert len([w for w in result["warnings"] if w["code"] == "rhyme"]) == 2


def test_rhyme_format_aabb_success():
    result = _check_single(["花", "家", "天", "前"], rhyme="AABB")
    assert [record["rhyme_ok"] for record in result["lines"]] == [True] * 4
    assert "rhyme" not in _codes(result["warnings"])


def test_rhyme_format_aabb_failure_marks_both_lines():
    result = _check_single(["花", "家", "天", "心"], rhyme="AABB")
    assert [record["rhyme_ok"] for record in result["lines"]] == [
        True,
        True,
        False,
        False,
    ]
    rhyme_warnings = [w for w in result["warnings"] if w["code"] == "rhyme"]
    assert {w["line_index"] for w in rhyme_warnings} == {3, 4}


def test_rhyme_format_abab_success():
    result = _check_single(["花", "天", "家", "前"], rhyme="ABAB")
    assert [record["rhyme_group"] for record in result["lines"]] == [
        "发花",
        "言前",
        "发花",
        "言前",
    ]
    assert [record["rhyme_ok"] for record in result["lines"]] == [True] * 4


def test_rhyme_format_abab_failure():
    result = _check_single(["花", "天", "家", "心"], rhyme="ABAB")
    assert [record["rhyme_ok"] for record in result["lines"]] == [
        True,
        False,
        True,
        False,
    ]
    rhyme_warnings = [w for w in result["warnings"] if w["code"] == "rhyme"]
    assert {w["line_index"] for w in rhyme_warnings} == {2, 4}


def test_rhyme_format_xaxa_only_even_lines_judged():
    result = _check_single(["风", "花", "雨", "家"], rhyme="XAXA")
    assert [record["rhyme_group"] for record in result["lines"]] == [
        "中东",
        "发花",
        "一七",
        "发花",
    ]
    assert [record["rhyme_ok"] for record in result["lines"]] == [
        None,
        True,
        None,
        True,
    ]
    assert "rhyme" not in _codes(result["warnings"])


def test_rhyme_format_xaxa_failure():
    result = _check_single(["风", "花", "雨", "心"], rhyme="XAXA")
    assert [record["rhyme_ok"] for record in result["lines"]] == [
        None,
        False,
        None,
        False,
    ]
    rhyme_warnings = [w for w in result["warnings"] if w["code"] == "rhyme"]
    assert {w["line_index"] for w in rhyme_warnings} == {2, 4}


def test_rhyme_format_aaaa_success():
    result = _check_single(["花", "家", "花", "家"], rhyme="AAAA")
    assert [record["rhyme_ok"] for record in result["lines"]] == [True] * 4


def test_rhyme_format_aaaa_failure():
    result = _check_single(["花", "家", "花", "心"], rhyme="AAAA")
    assert [record["rhyme_ok"] for record in result["lines"]] == [False] * 4
    rhyme_warnings = [w for w in result["warnings"] if w["code"] == "rhyme"]
    assert {w["line_index"] for w in rhyme_warnings} == {1, 2, 3, 4}


def test_rhyme_format_free_does_not_judge():
    result = _check_single(["花", "天"], rhyme="free")
    assert [record["rhyme_ok"] for record in result["lines"]] == [None, None]
    assert "rhyme" not in _codes(result["warnings"])


def test_rhyme_ignores_lines_without_han_characters():
    # 纯英文行不参与判定：参与行按顺序压缩为 花、家、天。
    result = _check_single(["花", "Hello", "家", "天"], rhyme="AABB")
    assert [record["rhyme_group"] for record in result["lines"]] == [
        "发花",
        None,
        "发花",
        "言前",
    ]
    assert [record["rhyme_ok"] for record in result["lines"]] == [
        True,
        None,
        True,
        None,
    ]


def test_rhyme_aabb_odd_line_is_not_judged():
    result = _check_single(["花", "家", "天", "前", "风"], rhyme="AABB")
    assert [record["rhyme_ok"] for record in result["lines"]] == [
        True,
        True,
        True,
        True,
        None,
    ]


# ---------------------------------------------------------------------------
# 多音字：必须用整行上下文
# ---------------------------------------------------------------------------


def test_chang_finals_differ_by_context_but_last_char_groups_follow_line():
    # 实测 pypinyin：长江 ['ang','iang']、长大 ['ang','a']。
    # 「长」本身的韵母都是 ang，不写“同字不同韵母”的断言。
    assert _finals("长江") == ["ang", "iang"]
    assert _finals("长大") == ["ang", "a"]
    assert _finals("长江") != _finals("长大")

    result = _check_single(["长江", "长大"], rhyme="AABB")
    assert [record["rhyme_group"] for record in result["lines"]] == [
        "江阳",
        "发花",
    ]
    assert [record["rhyme_ok"] for record in result["lines"]] == [False, False]


def test_le_finals_depend_on_full_line_context():
    # 同一个「乐」字：快乐读 le（e，梭波），音乐读 yue（ve，乜斜）。
    assert "乐" in "快乐" and "乐" in "音乐"
    assert _finals("快乐")[-1] == "e"
    assert _finals("音乐")[-1] == "ve"

    result = _check_single(["快乐", "音乐"], rhyme="AABB")
    assert [record["rhyme_group"] for record in result["lines"]] == [
        "梭波",
        "乜斜",
    ]
    assert [record["rhyme_ok"] for record in result["lines"]] == [False, False]
