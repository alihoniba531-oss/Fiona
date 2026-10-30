"""Offline source contracts for the match empty state and the profile rename.

These checks read files inside the repository only. No network, database, Node.js,
or git history is involved (spec 2026-10-28, T4 and T5).
"""

import re
import socket
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
MATCH = ROOT / "frontend/app/match/page.tsx"
PROFILE = ROOT / "frontend/app/profile/page.tsx"
DOCS = (
    ROOT / "README.md",
    ROOT / "PLAN.md",
    ROOT / "docs/ARCHITECTURE.md",
)

OLD_NAME = "旧社交画像"
NEW_NAME = "社交画像（旧版）"
PROFILE_SENTENCE = (
    "这里保留社交画像（旧版），不展示新会话的私有记忆。"
    "你可以在“我的分身”中查看新记忆；那里的「清空记忆与个人画像」会一并清空这份社交画像（旧版），聊天记录会保留。"
)

BOLD_TOKENS = ("font-semibold", "font-bold", "fontWeight", "<strong")
BOLD_WEIGHT = re.compile(r"font-weight\s*:\s*(?:[6-9]\d\d|bold(?:er)?)")


@pytest.fixture(scope="module", autouse=True)
def block_real_network():
    patch = pytest.MonkeyPatch()

    def forbidden(*args, **kwargs):
        raise AssertionError("empty-state source tests forbid sockets and DNS")

    for name in ("connect", "connect_ex"):
        patch.setattr(socket.socket, name, forbidden)
    for name in ("create_connection", "getaddrinfo", "gethostbyname", "gethostbyname_ex"):
        patch.setattr(socket, name, forbidden)
    yield
    patch.undo()


def read(path):
    return path.read_text(encoding="utf-8")


def bold_offenders(source):
    offenders = [token for token in BOLD_TOKENS if token in source]
    offenders.extend(match.group(0) for match in BOLD_WEIGHT.finditer(source))
    return offenders


def test_match_empty_section_explains_both_ways_to_meet_people():
    source = read(MATCH)
    start = source.find("<section data-match-empty")
    assert start != -1, "match page must render a data-match-empty section"
    end = source.find("</section>", start)
    assert end != -1, "data-match-empty section must be closed"

    section = source[start:end]
    for phrase in (
        "匹配是什么",
        "发送打招呼",
        "查看公开名片设置",
        "不会建立真人聊天",
        'href="/agents/me"',
        'target={embedded ? "_top" : undefined}',
    ):
        assert phrase in section, f"match empty section is missing {phrase!r}"
    for banned in ("匿名", "不知道你是谁", "Skill", "自动交流", "左侧"):
        assert banned not in section, f"match empty section must not say {banned!r}"


def test_match_page_keeps_mobile_variant_and_replaces_the_tiny_anonymous_hint():
    source = read(MATCH)
    assert "max-md:" not in source, "embedded match page must use mobile: variants only"
    assert bold_offenders(source) == [], "match page must not add bold styling"
    assert (
        source.count(
            '<p className="text-fs-12 text-[color:var(--ink2)]">双方都接受匹配后，对方会出现在这里</p>'
        )
        == 1
    ), "the recent-chat empty hint must appear exactly once with the v1.2 markup"
    assert '{rooms.length > 0 && <p className="mt-3">从「最近聊天」选一位' in source
    assert 'text-[11px] text-muted-foreground">接受匹配后会出现在这里' not in source
    assert source.count("{/* 匿名头像 */}") == 1


def test_match_empty_section_immediately_follows_the_zero_pending_branch():
    source = read(MATCH)
    assert re.search(
        r"\{pendingMatches\.length === 0 \? \(\s*<section data-match-empty",
        source,
    ), "the empty section must be the first child of the zero-pending branch"


def test_match_empty_section_moves_top_spacing_from_margin_to_padding():
    source = read(MATCH)
    open_tag = re.search(r"<section data-match-empty\b[^>]*>", source)
    assert open_tag is not None, "match page must render a data-match-empty section"
    class_attr = re.search(r'className="([^"]*)"', open_tag.group(0))
    assert class_attr is not None, "empty section must carry a className"
    classes = class_attr.group(1).split()

    assert "pt-10" in classes, "empty section needs pt-10 so short screens keep the buttons"
    assert "mobile:pt-2" in classes
    assert "mt-10" not in classes, "empty section must not push its buttons off-screen with mt-10"
    assert "mobile:mt-2" not in classes


def test_profile_page_uses_the_new_social_profile_name_everywhere():
    source = read(PROFILE)
    assert OLD_NAME not in source
    assert source.count(NEW_NAME) >= 3
    assert PROFILE_SENTENCE in source
    assert "暂无社交画像（旧版）" in source
    assert '.join("、")' in source
    assert '.join(" · ")' not in source


def test_profile_name_is_updated_in_each_document():
    for path in DOCS:
        source = read(path)
        assert OLD_NAME not in source, f"{path.name} still uses {OLD_NAME!r}"
        assert source.count(NEW_NAME) >= 1, f"{path.name} must use {NEW_NAME!r} at least once"
