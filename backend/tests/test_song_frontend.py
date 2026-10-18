# -*- coding: utf-8 -*-
"""写歌前端卡片与接入的源代码契约测试（全离线，不依赖 git 历史）。"""

import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SONGS = ROOT / "frontend/lib/songs.ts"
CARD = ROOT / "frontend/components/SongProjectCard.tsx"
BUBBLE = ROOT / "frontend/components/ChatBubble.tsx"
PAGE = ROOT / "frontend/app/page.tsx"
CONVERSATIONS = ROOT / "frontend/lib/useConversations.ts"


@pytest.fixture(autouse=True)
def isolated_song_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("FIONA_SONG_DIR", str(tmp_path / "song_data"))


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


@pytest.mark.parametrize("path", [SONGS, CARD])
def test_song_frontend_has_no_bold_font_weight(path):
    source = read(path)
    for token in ("font-semibold", "font-bold", "fontWeight", "font-medium"):
        assert token not in source, f"{path.name} 不应出现 {token}"
    assert not re.search(r"\bfont-(?:extrabold|black)\b", source)


def test_ai_generated_badge_lives_in_shared_shell_before_all_state_branches():
    source = read(CARD)
    shell_start = source.index("function SongCardShell(")
    component_start = source.index("export default function SongProjectCard(")
    badge = source.index('<span className="tag shrink-0 text-xs">AI 生成</span>')
    # 页眉在组件和所有 return 分支之前定义，任何状态都复用它。
    assert shell_start < badge < component_start
    assert source.count('<span className="tag shrink-0 text-xs">AI 生成</span>') == 1
    assert "写歌 ·《" in source and "写歌" in source

    # 每个状态都在自己的 SongCardShell 实例内，公共页眉一定被渲染。
    for marker in (
        "正在读取写歌项目…",
        "写歌项目读取失败",
        "这个写歌项目已删除",
        "歌词还在写，Claude 提交后会显示在这里",
    ):
        position = source.index(marker, component_start)
        before = source[:position]
        assert before.rfind("<SongCardShell") > before.rfind("</SongCardShell>"), marker
        assert source.find("</SongCardShell>", position) > position, marker
    assert source.count("<SongCardShell") >= 5


def test_page_copies_project_id_in_both_card_paths():
    source = read(PAGE)
    copies = re.findall(r"const card: CardData = \{(.*?)\n {12}\};", source, re.S)
    assert len(copies) == 2
    assert all("project_id: data.card.project_id" in copy for copy in copies)
    assert "onCompose={composeSongSection}" in source
    assert "songCardCompact={projectId => lastSongCardMessageId.get(projectId) !== msg.id}" in source


def test_conversation_history_rebuilds_song_project_card():
    source = read(CONVERSATIONS)
    assert re.search(r"song_project_id\?\s*:\s*string\s*\|\s*null", source)
    assert "message.role === \"assistant\" && message.song_project_id" in source
    assert 'source: "写歌"' in source
    assert 'subtype: "song_project"' in source
    assert "project_id: message.song_project_id" in source


def test_chat_bubble_renders_song_card_and_compact_duplicate():
    source = read(BUBBLE)
    assert "import SongProjectCard from \"@/components/SongProjectCard\";" in source
    assert 'card.subtype === "song_project"' in source
    assert "<SongProjectCard projectId={projectId} onCompose={onCompose} />" in source
    assert "写歌《${title}》已更新，见下方最新卡片" in source
    assert "写歌已更新，见下方最新卡片" in source
    assert "songCardCompact?: (projectId: string) => boolean" in source


def test_lyrics_section_contract_and_compose_text():
    card = read(CARD)
    songs = read(SONGS)
    for label in (
        "前奏", "主歌", "导歌", "副歌", "桥段", "间奏",
        "尾奏", "记忆点", "铺垫", "高潮段", "独奏",
    ):
        assert f'{label}' in songs
    assert 'const composeText = `把【${typeLabel} ${section.id}】改成：`;' in card
    assert "改这一段" in card
    assert "本稿修改" in card
    assert "（器乐）" in card
    assert "字数与押韵检查通过" in card
    assert "不押" in card
    assert "生成试听（" in card


def test_generation_confirm_dialog_lines_are_verbatim():
    card = read(CARD)
    assert (
        "将用第 {lyricsRevision} 稿歌词生成一首约 {durationSeconds} 秒的试听，"
        "预扣 {price} 颗草莓，失败自动退回。"
    ) in card
    assert "歌词与曲风参数会发送给字节跳动火山引擎生成音乐。" in card
    assert "生成的音频带有 AI 生成标识。" in card
    assert "确认生成" in card and "取消" in card
    assert "crypto.randomUUID().replace(/-/g, \"\")" in read(SONGS)


def test_polling_audio_and_error_contract():
    songs = read(SONGS)
    assert "POLL_INTERVAL_MS = 4000" in songs
    assert "MAX_INFLIGHT_MS = 15 * 60 * 1000" in songs
    assert "document.hidden" in songs
    assert "visibilitychange" in songs
    assert "new AbortController()" in songs and "current.abort()" in songs
    assert "return /^[0-9a-f]{32}$/.test(versionId)" in songs
    assert "`${API}/songs/versions/${versionId}/audio`" in songs
    assert "typeof detail === \"string\" ? detail" in songs
    assert "apiFetch(" in songs


def test_song_label_maps_match_reference_counts():
    source = read(SONGS)
    expected = {
        "GENRE_LABELS": 119,
        "MOOD_LABELS": 26,
        "TIMBRE_LABELS": 27,
        "KMODE_LABELS": 2,
        "TEMPO_LABELS": 8,
        "LANG_LABELS": 3,
    }
    for name, count in expected.items():
        start = source.index(f"export const {name}: Record<string, string> = {{")
        end = source.index("};", start)
        keys = re.findall(r'^  "([^"]+)":', source[start:end], re.M)
        assert len(keys) == count, name


@pytest.mark.parametrize("path", [SONGS, CARD, BUBBLE, PAGE, CONVERSATIONS])
def test_song_frontend_does_not_import_studio_components(path):
    source = read(path)
    assert "components/studio" not in source
    assert "@/components/studio" not in source


def test_rejected_version_copy_is_separate_from_failed():
    source = read(CARD)
    assert "提交被拒，已退回草莓" in source

    start = source.index("function versionStatusText(")
    end = source.index("\n}\n", start)
    status_body = source[start:end]
    assert re.search(r'case "rejected":\s*\n\s*return "提交被拒，已退回草莓";', status_body)
    assert re.search(r'case "failed":\s*\n\s*return "失败";', status_body)
    # rejected 不能再和 failed 挂在同一个 case 上。
    assert re.search(r'case "failed":\s*\n\s*case "rejected":', status_body) is None

    # failure_message 只随真正的 failed 展示，rejected 不再是 failed 布尔的一部分。
    assert 'const failed = version.status === "failed";' in source
    assert 'const failed = version.status === "failed" || version.status === "rejected";' not in source
    assert '{version.failure_message || "生成失败，请稍后再试"}' in source

