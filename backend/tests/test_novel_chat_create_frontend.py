"""聊天建书前端契约：卡片、刷新重建、抽屉导航与向导预填。

渲染用例复用 test_claude_agent_frontend.render_card（真实执行 ChatBubble
里的 ChatCard），只在 Node runner 中注入一个 NovelDraftCard 桩，以便在
没有浏览器 effect 的 SSR 环境里验证分支分发和 draft_id 透传。经 shared.render_card
的用例由共享 helper 探测依赖并 skip；直接起 node 的三条用例由本文件的
require_node_dependencies 守卫，缺 node_modules 时同样 skip。
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

import test_claude_agent_frontend as shared
from test_claude_agent_frontend import block_after


ROOT = Path(__file__).resolve().parents[2]
DEPENDENCIES = {
    "typescript": "typescript/lib/typescript.js",
    "react": "react/index.js",
    "react-dom/server": "react-dom/server.js",
}


def require_node_dependencies():
    missing = [name for name, entry in DEPENDENCIES.items()
               if not (ROOT / "frontend/node_modules" / entry).is_file()]
    if missing:
        pytest.skip("frontend dependencies unavailable: " + ", ".join(missing))
    if not shutil.which("node"):
        pytest.skip("node is unavailable")


BUBBLE = ROOT / "frontend/components/ChatBubble.tsx"
CARD = ROOT / "frontend/components/NovelDraftCard.tsx"
CONVERSATIONS = ROOT / "frontend/lib/useConversations.ts"
PAGE = ROOT / "frontend/app/page.tsx"
WIZARD = ROOT / "frontend/components/novel/NovelWizard.tsx"
NOVELS = ROOT / "frontend/lib/novels.ts"
UUID = "12345678-1234-1234-1234-123456789abc"


@pytest.mark.parametrize("missing", DEPENDENCIES)
def test_node_tests_skip_before_node_when_any_dependency_is_missing(monkeypatch, tmp_path, missing):
    for name, entry in DEPENDENCIES.items():
        path = tmp_path / "frontend/node_modules" / entry
        path.parent.mkdir(parents=True, exist_ok=True)
        if name != missing:
            path.write_text("", encoding="utf-8")
    monkeypatch.setitem(globals(), "ROOT", tmp_path)
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: pytest.fail(
        "Node must not start without dependencies"))
    with pytest.raises(pytest.skip.Exception,
                       match=re.escape("frontend dependencies unavailable: " + missing)):
        require_node_dependencies()


def read(path):
    return path.read_text(encoding="utf-8")


def function_block(source, marker):
    """从 marker 起取完整函数体，跳过参数里的解构花括号。"""
    start = source.index(marker)
    opening = source.index("{", source.index(")", start))
    depth = 0
    for index in range(opening, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start:index + 1]
    raise AssertionError(f"Unclosed function: {marker}")


def render_novel_draft_card(monkeypatch, tmp_path, card, bad_source=None):
    """调用共享 render_card，注入 NovelDraftCard 桩并捕获 draft_id。"""
    real_run = shared.subprocess.run

    def run(args, **kwargs):
        if (isinstance(args, list) and len(args) >= 3 and args[0] == "node"
                and args[1] == "-e" and "const ChatCard = Function(" in args[2]):
            args = list(args)
            runner = args[2]
            runner = runner.replace(
                "const ChatCard = Function(",
                "const NovelDraftCard = props => React.createElement('div', "
                "{'data-novel-draft': props.draftId, 'data-has-open': "
                "typeof props.onOpenNovel === 'function' ? 'yes' : 'no'}, '草稿卡');\n"
                "const ChatCard = Function(",
                1,
            )
            runner = runner.replace(
                "'openExternal', 'toSafeExternalUrl', compiled",
                "'openExternal', 'toSafeExternalUrl', 'NovelDraftCard', compiled",
            )
            runner = runner.replace(
                "openExternal, toSafeExternalUrl);",
                "openExternal, toSafeExternalUrl, NovelDraftCard);",
            )
            runner = runner.replace(
                "React.createElement(ChatCard, {card: JSON.parse(process.argv[2])})",
                "React.createElement(ChatCard, {card: JSON.parse(process.argv[2]), onOpenNovel: () => {}})",
            )
            args[2] = runner
        return real_run(args, **kwargs)

    if bad_source is not None:
        bad = tmp_path / "ChatBubble.bad-copy.tsx"
        bad.write_text(bad_source, encoding="utf-8")
        monkeypatch.setattr(shared, "BUBBLE", bad)
        try:
            return shared.render_card(card)
        finally:
            bad.unlink(missing_ok=True)
    monkeypatch.setattr(shared.subprocess, "run", run)
    return shared.render_card(card)


# ────────────────────────── ChatCard 分发 ──────────────────────────


def test_chat_card_renders_novel_draft_with_draft_id(monkeypatch, tmp_path):
    source = read(BUBBLE)
    assert (ROOT / "frontend/components/NovelDraftCard.tsx").is_file()
    assert 'if (card.subtype === "novel_draft")' in source
    assert "<NovelDraftCard draftId=" in source and "onOpenNovel={onOpenNovel} />" in source
    html = render_novel_draft_card(monkeypatch, tmp_path, {
        "source": "书斋", "points": [], "subtype": "novel_draft", "draft_id": UUID,
    })
    assert f'data-novel-draft="{UUID}"' in html
    assert 'data-has-open="yes"' in html
    assert "草稿卡" in html

    # 坏副本：把 novel_draft 分支禁用后，同一渲染断言必须变红。
    bad_source = source.replace('if (card.subtype === "novel_draft")', "if (false)", 1)
    html_bad = render_novel_draft_card(monkeypatch, tmp_path, {
        "source": "书斋", "points": [], "subtype": "novel_draft", "draft_id": UUID,
    }, bad_source=bad_source)
    with pytest.raises(AssertionError):
        assert f'data-novel-draft="{UUID}"' in html_bad


CHAT_CARD_TAG = re.compile(r"<ChatCard\b[^>]*/>")


def check_bubble_passes_open_novel(source):
    body = function_block(source, "function ChatBubble(")
    assert "onOpenNovel" in body.split(")", 1)[0], "ChatBubble 未解构 onOpenNovel"
    tags = CHAT_CARD_TAG.findall(body)
    assert len(tags) == 2, tags
    for tag in tags:
        assert "onOpenNovel={onOpenNovel}" in tag, tag


def test_chat_bubble_passes_open_novel_to_every_chat_card():
    source = read(BUBBLE)
    check_bubble_passes_open_novel(source)
    for bad in (
        source.replace(" onOpenNovel={onOpenNovel} songCardCompact", " songCardCompact", 1),
        source.replace("onCompose, onOpenNovel, songCardCompact }: ChatBubbleProps",
                       "onCompose, songCardCompact }: ChatBubbleProps", 1),
    ):
        assert bad != source
        with pytest.raises(AssertionError):
            check_bubble_passes_open_novel(bad)


# ────────────────────────── NovelDraftCard 三态与样式 ──────────────────────────


def test_novel_draft_component_states_paths_and_weights():
    assert CARD.is_file(), "NovelDraftCard.tsx 尚未实现"
    source = read(CARD)
    for text in (
        "正在读取草稿…", "书斋草稿 · 《", "去书斋建书", "已建书《", "草稿已不存在",
        "/novels/new?embed=1&draft=", "?embed=1", ".slice(0, 80)",
        "ceramic-card w-[340px] max-w-full", "btn btn-primary min-h-10",
    ):
        assert text in source, f"NovelDraftCard 缺少 {text}"
    assert not re.search(r"font-semibold|font-bold", source)

    bad = source.replace("className=\"btn btn-primary min-h-10\"", "className=\"btn btn-primary min-h-10 font-bold\"", 1)
    assert re.search(r"font-semibold|font-bold", bad)


def test_novel_draft_component_renders_loading_state(monkeypatch):
    require_node_dependencies()
    assert CARD.is_file(), "NovelDraftCard.tsx 尚未实现"
    source = read(CARD)
    component = function_block(source, "export default function NovelDraftCard(")
    component = component.replace("export default function NovelDraftCard", "function NovelDraftCard", 1)
    script = """
const ts = require('typescript');
const React = require('react');
const {renderToStaticMarkup} = require('react-dom/server');
const compiled = ts.transpileModule(process.argv[1], {compilerOptions: {jsx: ts.JsxEmit.React}}).outputText;
const useState = initial => [typeof initial === 'function' ? initial() : initial, () => {}];
const useEffect = () => {};
class ApiError extends Error { constructor(message, status) { super(message); this.status = status; } }
const getNovelDraft = async () => { throw new Error('must not run in SSR'); };
const NovelDraftCard = Function('React', 'useState', 'useEffect', 'getNovelDraft', 'ApiError',
  compiled + '\\nreturn NovelDraftCard;')(React, useState, useEffect, getNovelDraft, ApiError);
process.stdout.write(renderToStaticMarkup(React.createElement(NovelDraftCard, {draftId: 'x'})));
"""
    result = subprocess.run(
        ["node", "-e", script, component], cwd=ROOT / "frontend",
        capture_output=True, text=True, check=True,
    )
    html = result.stdout
    assert "正在读取草稿…" in html and "ceramic-card" in html
    # 坏副本：换掉加载文案后同一断言必须变红。
    bad = component.replace("正在读取草稿…", "加载中", 1)
    bad_result = subprocess.run(
        ["node", "-e", script, bad], cwd=ROOT / "frontend",
        capture_output=True, text=True, check=True,
    )
    with pytest.raises(AssertionError):
        assert "正在读取草稿…" in bad_result.stdout


# ────────────────────────── 刷新重建 ──────────────────────────


def test_use_conversations_rebuilds_song_and_draft_cards():
    require_node_dependencies()
    source = read(CONVERSATIONS)
    assert "novel_draft_id?: string | null" in source
    assert 'subtype: "novel_draft", draft_id: message.novel_draft_id' in source
    function = block_after(source, "function toMessages(")
    script = """
const ts = require('typescript');
const compiled = ts.transpileModule(process.argv[1], {compilerOptions: {target: ts.ScriptTarget.ES2020}}).outputText;
const API = '/api';
const storedReferenceImagePaths = () => [];
const toMessages = Function('API', 'storedReferenceImagePaths', compiled + '\\nreturn toMessages;')(API, storedReferenceImagePaths);
const base = {id: 1, role: 'assistant', content: 'x', image_path: null, created_at: '2026-11-02 10:00:00'};
const cases = [
  {name: 'both', value: {...base, song_project_id: 'song-1', novel_draft_id: 'draft-1'}},
  {name: 'draft', value: {...base, novel_draft_id: 'draft-1'}},
  {name: 'none', value: {...base}},
];
process.stdout.write(JSON.stringify(Object.fromEntries(cases.map(item => [item.name, toMessages([item.value])[0].cards ?? null]))));
"""
    result = subprocess.run(
        ["node", "-e", script, function], cwd=ROOT / "frontend",
        capture_output=True, text=True, check=True,
    )
    payload = json.loads(result.stdout)
    assert payload["both"] == [
        {"source": "写歌", "points": [], "subtype": "song_project", "project_id": "song-1"},
        {"source": "书斋", "points": [], "subtype": "novel_draft", "draft_id": "draft-1"},
    ]
    assert payload["draft"] == [{"source": "书斋", "points": [], "subtype": "novel_draft", "draft_id": "draft-1"}]
    assert payload["none"] is None

    # 坏副本：禁用 novel_draft 分支后，both 不再含草稿卡。
    bad = source.replace('if (message.role === "assistant" && message.novel_draft_id)', "if (false)", 1)
    bad_function = block_after(bad, "function toMessages(")
    bad_result = subprocess.run(
        ["node", "-e", script, bad_function], cwd=ROOT / "frontend",
        capture_output=True, text=True, check=True,
    )
    bad_payload = json.loads(bad_result.stdout)
    with pytest.raises(AssertionError):
        assert any(card.get("subtype") == "novel_draft" for card in (bad_payload["both"] or []))


# ────────────────────────── page.tsx ──────────────────────────


def test_page_open_novel_at_accepts_only_two_shapes():
    require_node_dependencies()
    source = read(PAGE)
    assert "const openNovelAt = (path: string) => {" in source
    assert r"/^\/novels\/new\?embed=1&draft=[0-9a-f-]{36}$/" in source
    assert r"/^\/novels\/[0-9a-f-]{36}\?embed=1$/" in source
    function = block_after(source, "const openNovelAt = (path: string) =>")
    script = """
const ts = require('typescript');
const compiled = ts.transpileModule(process.argv[1], {compilerOptions: {target: ts.ScriptTarget.ES2020}}).outputText;
let src = '', drawer = '';
const setNovelFrameSrc = value => { src = value; };
const setDrawer = value => { drawer = value; };
const openNovelAt = Function('setNovelFrameSrc', 'setDrawer', compiled + '\\nreturn openNovelAt;')(setNovelFrameSrc, setDrawer);
const paths = JSON.parse(process.argv[2]);
process.stdout.write(JSON.stringify(paths.map(path => {
  src = ''; drawer = '';
  openNovelAt(path);
  return {path, src, drawer};
})));
"""
    valid_new = f"/novels/new?embed=1&draft={UUID}"
    valid_book = f"/novels/{UUID}?embed=1"
    invalid = [
        f"/novels/new?draft={UUID}",
        f"/novels/{UUID}",
        f"/novels/{UUID}?embed=1&x=1",
        "/novels/new?embed=1&draft=short",
        "javascript:alert(1)",
        "https://example.com/novels/new?embed=1",
        "//example.com/novels/new?embed=1",
        "/novels/../login",
        f"/novels/{UUID.upper()}?embed=1",
        "/novels/new?embed=1&draft=12345678-1234-1234-1234-123456789abz",
    ]
    result = subprocess.run(
        ["node", "-e", script, function, json.dumps([valid_new, valid_book] + invalid)],
        cwd=ROOT / "frontend", capture_output=True, text=True, check=True,
    )
    rows = json.loads(result.stdout)
    for row in rows[:2]:
        assert row["src"] == row["path"] and row["drawer"] == "novel"
    for row in rows[2:]:
        assert row["src"] == "" and row["drawer"] == "", row

    # 坏副本：把白名单条件去掉后，危险路径会被接受。
    bad = source.replace(
        "if (!/^\\/novels\\/new\\?embed=1&draft=[0-9a-f-]{36}$/.test(path)\n"
        "      && !/^\\/novels\\/[0-9a-f-]{36}\\?embed=1$/.test(path)) return;",
        "if (false) return;",
        1,
    )
    assert bad != source
    bad_function = block_after(bad, "const openNovelAt = (path: string) =>")
    bad_result = subprocess.run(
        ["node", "-e", script, bad_function, json.dumps(["javascript:alert(1)"])],
        cwd=ROOT / "frontend", capture_output=True, text=True, check=True,
    )
    with pytest.raises(AssertionError):
        assert json.loads(bad_result.stdout)[0]["src"] == ""


def test_page_stream_cards_copy_draft_id_and_iframe_uses_state():
    source = read(PAGE)
    assert source.count("draft_id: data.card.draft_id") == 2
    assert "onOpenNovel={openNovelAt}" in source
    assert 'const [novelFrameSrc, setNovelFrameSrc] = useState("/novels?embed=1")' in source
    assert "src={novelFrameSrc}" in source
    assert 'src="/novels?embed=1"' not in source.split('title="书斋工作区"', 1)[1].split(">", 1)[0]

    bad = source.replace("draft_id: data.card.draft_id", "", 1)
    with pytest.raises(AssertionError):
        assert bad.count("draft_id: data.card.draft_id") == 2


# ────────────────────────── 向导与 API ──────────────────────────


def test_wizard_reads_draft_prefills_and_submits_draft_id():
    source = read(WIZARD)
    for text in (
        'useSearchParams().get("draft")',
        "getNovelDraft",
        "setSeed(nextDraft.seed_idea)",
        "setMinChapters(String(target.min_chapters))",
        "setMaxChapters(String(target.max_chapters))",
        "setChapterWords(String(target.chapter_words))",
        "setDraftId(nextDraft.id)",
        "createNovel({ ...input, draft_id: draftId ?? undefined }",
        "草稿不存在",
        "这份草稿已建成《",
    ):
        assert text in source, f"NovelWizard 缺少 {text}"

    bad = source.replace("draft_id: draftId ?? undefined", "", 1)
    with pytest.raises(AssertionError):
        assert "draft_id: draftId ?? undefined" in bad


def test_novels_lib_exposes_draft_lookup_and_input_field():
    source = read(NOVELS)
    assert "export interface NovelDraft" in source
    assert "draft_id?: string" in source
    assert "export const getNovelDraft" in source
    assert '"/novels/drafts/"' in source or "'/novels/drafts/'" in source

    bad = source.replace("draft_id?: string", "", 1)
    with pytest.raises(AssertionError):
        assert "draft_id?: string" in bad
