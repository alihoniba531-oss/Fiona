"""聊天修改意见卡前端契约：分发、刷新重建、SSR 状态、交互与源码锁。

源码断言不启动 node，缺 frontend 依赖时也照常运行。渲染与交互用例在
node 里用仓库内 typescript 转译真实组件：渲染用例照 test_desk_views_frontend
的 NODE_RENDERER 写法；交互用例照 test_desk_dock_races_frontend 的迷你 hooks
运行时（另加 unmount），用真实的点击处理函数驱动。新功能类用例先过
_require_feedback()，HEAD 上以 AssertionError 失败；起 node 前统一过依赖守卫。
"""
import ast
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

import test_claude_agent_frontend as shared
from test_claude_agent_frontend import block_after
from test_component_language import NATIVE_DIALOG


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
DEPENDENCIES = {
    "typescript": "typescript/lib/typescript.js",
    "react": "react/index.js",
    "react-dom/server": "react-dom/server.js",
}

BUBBLE = FRONTEND / "components/ChatBubble.tsx"
COMPONENT = FRONTEND / "components/NovelFeedbackCard.tsx"
FEEDBACK_LIB = FRONTEND / "lib/novelFeedback.ts"
CONVERSATIONS = FRONTEND / "lib/useConversations.ts"
PAGE = FRONTEND / "app/page.tsx"
ROUTER = ROOT / "backend/routers/novel.py"

UUID = "12345678-1234-1234-1234-123456789abc"
PLAN_CHAPTER = 2
MAX_CHAPTERS = 50

FEE = {
    "strawberries": "重新定稿会再调用一次编辑部，按实际用量扣草莓。",
    "own_model": "这本书的主编用的是你自己的模型，重新定稿不扣草莓，但会用掉你自己的模型额度。",
    "free": "这次重新定稿不扣草莓。",
}


def _require_feedback():
    """HEAD 上没有新功能，以 AssertionError 失败而不是收集错误。"""
    for path in (ROOT / "backend/novel/feedback.py", COMPONENT, FEEDBACK_LIB):
        assert path.is_file(), f"{path.name} 尚未实现"


def read(path):
    return path.read_text(encoding="utf-8")


def require_node_dependencies():
    missing = [name for name, entry in DEPENDENCIES.items()
               if not (ROOT / "frontend/node_modules" / entry).is_file()]
    if missing:
        pytest.skip("frontend dependencies unavailable: " + ", ".join(missing))
    if not shutil.which("node"):
        pytest.skip("node is unavailable")


@pytest.mark.parametrize("missing", [*DEPENDENCIES, "node"])
def test_node_tests_skip_before_node_when_any_dependency_is_missing(monkeypatch, tmp_path, missing):
    for name, entry in DEPENDENCIES.items():
        path = tmp_path / "frontend/node_modules" / entry
        path.parent.mkdir(parents=True, exist_ok=True)
        if name != missing:
            path.write_text("", encoding="utf-8")
    monkeypatch.setitem(globals(), "ROOT", tmp_path)
    if missing == "node":
        monkeypatch.setattr(shutil, "which", lambda command: None)
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: pytest.fail(
        "Node must not start without dependencies"))
    expected = ("node is unavailable" if missing == "node"
                else "frontend dependencies unavailable: " + missing)
    with pytest.raises(pytest.skip.Exception, match=re.escape(expected)):
        require_node_dependencies()


# ────────────────────────── 视图夹具与断言辅助 ──────────────────────────


def make_book(**overrides):
    book = {
        "status": "awaiting_plan",
        "chapters_done": 1,
        "max_chapters": MAX_CHAPTERS,
        "awaiting_chapter": PLAN_CHAPTER,
        "awaiting_is_final": False,
        "pending_notes": 0,
        "automation": "per_chapter",
        "redo_cost": "strawberries",
        "plan_row_status": "awaiting_plan_approval",
        "redo_pending": False,
    }
    book.update(overrides)
    return book


def make_note(**overrides):
    note = {
        "sent_at": "2026-11-12 10:00:01",
        "status": "pending",
        "delivered_chapter": None,
        "adopted": None,
        "response": None,
        "planned_chapter": None,
        "planned_adopted": None,
        "planned_response": None,
    }
    note.update(overrides)
    return note


def make_view(**overrides):
    view = {
        "id": "feedback-1",
        "novel_id": UUID,
        "book_title": "长夜",
        "next_chapters": "",
        "current_plan": "",
        "plan_chapter": None,
        "written": [],
        "note": None,
        "redo_started_at": None,
        "book": None,
        "created_at": "2026-11-12 10:00:00",
    }
    view.update(overrides)
    return view


def plan_action_description(cost):
    return (
        "重新定稿会让编辑部拿原来的讨论材料加上这些要求，重新写一版第 "
        f"{PLAN_CHAPTER} 章细纲；它看不到你现在看到的这一版，是否照改由编辑部判断。"
        f"{FEE[cost]}只想改几处的话，也可以在书斋里直接改细纲，再点「改完批准」"
        "（批准后照常开始写这一章）。"
    )


PLAN_RUNNING = (
    f"编辑部正在带着这些要求重新定稿第 {PLAN_CHAPTER} 章细纲，"
    "完成后会停下来等你确认。卡片不会自动更新，刷新页面可以看到最新进展。"
)
PLAN_PAUSED = "重新定稿还没有完成：这本书暂停了，请到书斋查看原因；恢复写作后会接着重新定稿。"
PLAN_FAILED = "重新定稿没有完成：这本书处于失败状态，不能再继续写。"
PLAN_DONE = f"已经带着这些要求重新定稿过第 {PLAN_CHAPTER} 章细纲。"
PLAN_DONE_AWAITING = PLAN_DONE + "新细纲在书斋里等你确认。"
PLAN_NOT_PER_CHAPTER = (
    "这本书现在不是逐章确认，重新定稿后会直接开始写正文、不会停下来等你确认；"
    "这一项请到书斋里处理。"
)
PLAN_FAILED_ROW = "这本书处于失败状态，不能再继续写，这一项不能再用。"
PLAN_ROW_PAUSED = (
    f"第 {PLAN_CHAPTER} 章细纲还在等你确认，但这本书暂停了；"
    "恢复写作、回到等你确认后可以再用这一项。"
)
PLAN_ROW_RUNNING = (
    f"第 {PLAN_CHAPTER} 章细纲还在等你确认，但书斋正在处理这本书；"
    "处理完、回到等你确认后可以再用这一项。"
)
PLAN_PLANNING_RUNNING = (
    f"书斋正在重新定稿第 {PLAN_CHAPTER} 章细纲；"
    "完成后如果仍在等你确认这一章，可以再用这一项。"
)
PLAN_PLANNING_PAUSED = (
    f"书斋重新定稿第 {PLAN_CHAPTER} 章细纲时暂停了；"
    "恢复写作、回到等你确认后可以再用这一项。"
)
PLAN_NOT_AWAITING = f"第 {PLAN_CHAPTER} 章细纲已经不在等你确认了，这一项不能再用。"
DELETED = "这本书已经删除。"

PLAN_DESCRIPTIONS = [
    DELETED,
    PLAN_RUNNING,
    PLAN_PAUSED,
    PLAN_FAILED,
    PLAN_DONE,
    PLAN_DONE_AWAITING,
    plan_action_description("strawberries"),
    plan_action_description("own_model"),
    plan_action_description("free"),
    PLAN_NOT_PER_CHAPTER,
    PLAN_FAILED_ROW,
    PLAN_ROW_PAUSED,
    PLAN_ROW_RUNNING,
    PLAN_PLANNING_RUNNING,
    PLAN_PLANNING_PAUSED,
    PLAN_NOT_AWAITING,
]


def planned_normal(chapter):
    return f"编辑部已经在第 {chapter} 章细纲里读到这条要求；这一章写完后，这里会记为已下发。"


PLANNED_FAILED = (
    "编辑部已经在第 2 章细纲里读到这条要求，但这本书处于失败状态，不能再继续写，"
    "这条留言不会被下发。"
)
CHAPTER_COMPLETED_NOTE = "这本书已经完结，这条留言不会再被读到。"
CHAPTER_FAILED_NOTE = "这本书处于失败状态，这条留言不会再被读到。"
CHAPTER_AWAITING_END = "这本书在等你确认完结；只有选择再写几章，编辑部才会读到这条要求。"
CHAPTER_FINAL = (
    f"第 {PLAN_CHAPTER} 章会是这本书的最后一章；只有选择再写几章，编辑部才会读到这条要求。"
)
CHAPTER_NEXT_PLAN = "第 3 章规划细纲时，编辑部会读到这条要求。"
CHAPTER_LATER = "编辑部会在下一次为新的一章规划细纲时读到这条要求；那一章写完后，这里会显示编辑部的回应。"
CHAPTER_COMPLETED = "这本书已经完结，编辑部不会再读留言。"
CHAPTER_FAILED = "这本书处于失败状态，编辑部不会再读留言。"
CHAPTER_FULL = "这本书的待下发留言已满 5 条，等编辑部用掉一些再交。"
CHAPTER_PREFIX = "这本书现在有 2 条待下发留言（最多 5 条，包括书斋里留的和别的卡片交出的）。"
CHAPTER_LATER_TAIL = (
    "编辑部只在下一次为新的一章规划细纲时参考一次"
    "（正在规划、正在重新定稿或已经出了细纲的那一章读不到），不会长期生效。"
)
RETRACT = "交出后不能撤回。"

CHAPTER_DESCRIPTIONS = [
    planned_normal(2),
    planned_normal(3),
    PLANNED_FAILED,
    DELETED,
    CHAPTER_COMPLETED_NOTE,
    CHAPTER_FAILED_NOTE,
    CHAPTER_AWAITING_END,
    CHAPTER_FINAL,
    CHAPTER_NEXT_PLAN,
    CHAPTER_LATER,
    CHAPTER_COMPLETED,
    CHAPTER_FAILED,
    CHAPTER_FULL,
    CHAPTER_PREFIX + CHAPTER_LATER_TAIL + RETRACT,
    CHAPTER_AWAITING_END + RETRACT,
    CHAPTER_FINAL + RETRACT,
    (
        f"第 {PLAN_CHAPTER} 章细纲已经出来了，这条要求要到第 3 章规划细纲时编辑部才会读到；"
        f"想让第 {PLAN_CHAPTER} 章就照做，可以在书斋里直接改第 {PLAN_CHAPTER} 章细纲。"
        + RETRACT
    ),
    CHAPTER_LATER_TAIL + RETRACT,
]

WRITTEN_DESCRIPTION = (
    "这些章节不会自动修改，要改就在书斋里打开这一章，点「改稿」自己改。"
    "改最新写好的一章会重新归档（再调用一次档案员，可能扣草莓），完成前不会开始下一章，"
    "已经出来、等你确认的下一章细纲也不会跟着重做。"
    "改较早的章节会把它后面已写好的章永久标成「待复核」（短片工作室照收，会标出待复核）；"
    "故事圣经和章节摘要也不会重算，编辑部之后仍按旧记录规划。"
    "可以再交一条留言说明改了什么，但留言只在下一次规划细纲时参考一次。"
)


def assert_only_description(html, expected, all_descriptions):
    if expected is None:
        for other in all_descriptions:
            assert other not in html, f"不应出现其他状态的说明：{other}"
        return
    assert expected in html, expected
    for other in all_descriptions:
        if other != expected and other not in expected:
            assert other not in html, f"不应出现其他状态的说明：{other}"


def has_disabled(tag):
    """只匹配属性名 disabled，跳过 class 里的 disabled: 工具类。"""
    return re.search(r'\sdisabled(?:=""|(?=[\s/>]))', tag) is not None


def button_with_text(html, text):
    matches = re.findall(
        r"<button\b[^>]*>" + re.escape(text) + r"</button>", html)
    assert len(matches) == 1, f"期望恰好一个「{text}」按钮，实际 {matches}"
    return matches[0]


def assert_button_absent(html, text):
    assert f">{text}</button>" not in html, f"不应出现「{text}」按钮"


def assert_tag(html, tag):
    if tag is None:
        assert '<span class="tag">' not in html
    else:
        assert f'<span class="tag">{tag}</span>' in html, tag


def assert_no_response(html):
    for phrase in ("编辑部采纳：", "编辑部没有采纳：", "编辑部的回应："):
        assert phrase not in html, phrase


def assert_description_paragraph(html, description):
    pattern = (
        r'<p(?: id="[^"]+")? class="mt-2 break-words text-fs-12 '
        r'text-\[color:var\(--ink2\)\]">' + re.escape(description) + r"</p>"
    )
    matches = re.findall(pattern, html)
    assert len(matches) == 1, f"说明段不逐字匹配：{description}"


def assert_response_paragraph(html, response):
    pattern = (
        r'<p class="mt-1 break-words text-fs-12 text-\[color:var\(--ink2\)\]">'
        + re.escape(response) + r"</p>"
    )
    matches = re.findall(pattern, html)
    assert len(matches) == 1, f"回应段不逐字匹配：{response}"


# ────────────────────────── 源码约束（不起 node） ──────────────────────────


def check_component_source(source):
    for banned in (
        "font-medium", "font-semibold", "font-bold", "fontWeight", "font-weight",
        "<dialog", "alert(", "window.confirm", "window.alert",
    ):
        assert banned not in source, f"NovelFeedbackCard 不得包含 {banned}"
    assert re.search(r"<(b|strong)[\s>]", source) is None, "不得出现 b/strong 标签"
    assert NATIVE_DIALOG.search(source) is None, "不得调用原生 confirm/alert"
    assert "const confirm = useConfirm();" in source
    assert source.count("confirm(") == source.count("confirm({") >= 1
    sizes = set(re.findall(r"text-fs-[0-9.]+", source))
    assert sizes <= {"text-fs-12", "text-fs-13", "text-fs-15"}, sizes
    colors = set(re.findall(r"text-\[color:var\(--([a-z0-9-]+)\)\]", source))
    assert colors <= {"ink2", "seal"}, colors
    assert re.search(r"#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(", source) is None


def test_feedback_card_source_avoids_bold_native_dialogs_and_dialog_tags():
    _require_feedback()
    check_component_source(read(COMPONENT))


COMPONENT_MUTATIONS = [
    ("window-confirm", lambda source: source.replace(
        "await confirm({", 'window.confirm("确定？")', 1)),
    ("confirm-call", lambda source: source.replace(
        "const confirm = useConfirm();",
        "const confirm = useConfirm();\n  if (!confirm(body)) return;", 1)),
    ("alert-call", lambda source: source.replace(
        "const confirm = useConfirm();",
        "const confirm = useConfirm();\n  alert(novelErrorMessage(error));", 1)),
    ("window-alert", lambda source: source.replace(
        "const confirm = useConfirm();",
        'const confirm = useConfirm();\n  window.alert("x");', 1)),
    ("strong-tag", lambda source: source.replace(
        'chaptersDescription += "交出后不能撤回。";',
        'chaptersDescription += "交出后不能撤回。";\n      const badStrong = <strong>交出后不能撤回</strong>;', 1)),
    ("b-tag", lambda source: source.replace(
        "  const finalChapter =",
        "  const badBold = <b>交出后不能撤回</b>;\n  const finalChapter =", 1)),
    ("font-medium", lambda source: source.replace(
        'className="px-4 py-3 text-fs-15"',
        'className="px-4 py-3 text-fs-15 font-medium"', 1)),
    ("dialog-tag", lambda source: source.replace(
        '<div className="ceramic-card w-[420px] max-w-full overflow-hidden">',
        '<dialog className="ceramic-card w-[420px] max-w-full overflow-hidden">', 1)),
    ("confirm-hook", lambda source: source.replace(
        "const confirm = useConfirm();", "", 1)),
    ("font-size-token", lambda source: source.replace(
        "text-fs-13", "text-fs-11", 1)),
    ("hex-color", lambda source: source.replace(
        "text-[color:var(--ink2)]", "text-[#123456]", 1)),
]


@pytest.mark.parametrize("name,mutate", COMPONENT_MUTATIONS, ids=[item[0] for item in COMPONENT_MUTATIONS])
def test_feedback_card_source_constraints_catch_bad_copies(name, mutate):
    _require_feedback()
    source = read(COMPONENT)
    bad = mutate(source)
    assert bad != source, name
    with pytest.raises(AssertionError):
        check_component_source(bad)


def page_card_blocks(source):
    blocks = []
    marker = "const card: CardData = {"
    start = 0
    while True:
        index = source.find(marker, start)
        if index < 0:
            break
        opening = source.index("{", index)
        depth = 0
        end = None
        for position in range(opening, len(source)):
            if source[position] == "{":
                depth += 1
            elif source[position] == "}":
                depth -= 1
                if depth == 0:
                    end = position + 1
                    break
        assert end is not None, "未闭合的 const card: CardData 块"
        blocks.append(source[index:end])
        start = end
    return blocks


def check_page_cards(source):
    blocks = page_card_blocks(source)
    assert len(blocks) == 2, f"期望两个 const card: CardData 块，实际 {len(blocks)}"
    for block in blocks:
        assert block.count("feedback_id: data.card.feedback_id,") == 1, block
    assert PAGE.read_bytes()[:3] == b"\xef\xbb\xbf", "page.tsx 的 UTF-8 BOM 丢失"


def test_page_stream_cards_bind_feedback_id_in_both_blocks():
    _require_feedback()
    check_page_cards(read(PAGE))


def test_page_stream_cards_self_check_requires_both_blocks():
    _require_feedback()
    source = read(PAGE)
    bad = source.replace("feedback_id: data.card.feedback_id,", "", 1)
    assert bad != source
    with pytest.raises(AssertionError):
        check_page_cards(bad)


def feedback_routes(source):
    tree = ast.parse(source)
    routes = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if not isinstance(node.func.value, ast.Name) or node.func.value.id != "router":
            continue
        if node.func.attr not in {"get", "post", "put", "patch", "delete"}:
            continue
        if not node.args or not isinstance(node.args[0], ast.Constant) or not isinstance(node.args[0].value, str):
            continue
        path = re.sub(r"\{[^}]+\}", "{}", node.args[0].value)
        if path.startswith("/feedback"):
            routes.append((node.func.attr, path))
    return routes


def check_feedback_routes(source):
    routes = feedback_routes(source)
    expected = [
        ("get", "/feedback/{}"),
        ("post", "/feedback/{}/note"),
        ("post", "/feedback/{}/redo"),
    ]
    assert sorted(routes) == sorted(expected), routes
    for item in expected:
        assert routes.count(item) == 1, item


def test_novel_feedback_routes_keep_their_http_methods():
    _require_feedback()
    check_feedback_routes(read(ROUTER))


def test_novel_feedback_route_method_check_catches_note_get():
    _require_feedback()
    source = read(ROUTER)
    bad = source.replace(
        "@router.post('/feedback/{feedback_id}/note')",
        "@router.get('/feedback/{feedback_id}/note')", 1)
    assert bad != source
    with pytest.raises(AssertionError):
        check_feedback_routes(bad)


# ────────────────────────── ChatCard 分发 ──────────────────────────


def render_chat_card(monkeypatch, tmp_path, card, bad_source=None):
    """执行共享 render_card，注入 NovelFeedbackCard 桩并捕获 feedbackId。"""
    real_run = shared.subprocess.run

    def run(args, **kwargs):
        if (isinstance(args, list) and len(args) >= 3 and args[0] == "node"
                and args[1] == "-e" and "const ChatCard = Function(" in args[2]
                and "const NovelFeedbackCard = props =>" not in args[2]):
            args = list(args)
            runner = args[2]
            runner = runner.replace(
                "const ChatCard = Function(",
                "const NovelFeedbackCard = props => React.createElement('div', "
                "{'data-feedback-id': props.feedbackId, 'data-has-open': "
                "typeof props.onOpenNovel === 'function' ? 'yes' : 'no'}, '意见卡');\n"
                "const ChatCard = Function(",
                1,
            )
            runner = runner.replace(
                "'openExternal', 'toSafeExternalUrl', compiled",
                "'openExternal', 'toSafeExternalUrl', 'NovelFeedbackCard', compiled",
                1,
            )
            runner = runner.replace(
                "openExternal, toSafeExternalUrl);",
                "openExternal, toSafeExternalUrl, NovelFeedbackCard);",
                1,
            )
            runner = runner.replace(
                "React.createElement(ChatCard, {card: JSON.parse(process.argv[2])})",
                "React.createElement(ChatCard, {card: JSON.parse(process.argv[2]), onOpenNovel: () => {}})",
                1,
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


def test_chat_card_renders_novel_feedback_with_feedback_id(monkeypatch, tmp_path):
    require_node_dependencies()
    _require_feedback()
    source = read(BUBBLE)
    assert 'if (card.subtype === "novel_feedback")' in source
    assert "<NovelFeedbackCard feedbackId=" in source and "onOpenNovel={onOpenNovel} />" in source
    card = {"source": "书斋", "points": [], "subtype": "novel_feedback", "feedback_id": UUID}
    html = render_chat_card(monkeypatch, tmp_path, card)
    assert f'data-feedback-id="{UUID}"' in html
    assert 'data-has-open="yes"' in html
    assert "意见卡" in html

    empty = render_chat_card(monkeypatch, tmp_path, {
        "source": "书斋", "points": [], "subtype": "novel_feedback",
    })
    assert empty.strip() == ""

    bad_source = source.replace('if (card.subtype === "novel_feedback")', "if (false)", 1)
    assert bad_source != source
    html_bad = render_chat_card(monkeypatch, tmp_path, card, bad_source=bad_source)
    with pytest.raises(AssertionError):
        assert f'data-feedback-id="{UUID}"' in html_bad


# ────────────────────────── 刷新重建 ──────────────────────────


def run_to_messages(source):
    function = block_after(source, "function toMessages(")
    script = """
const ts = require('typescript');
const compiled = ts.transpileModule(process.argv[1], {compilerOptions: {target: ts.ScriptTarget.ES2020}}).outputText;
const API = '/api';
const storedReferenceImagePaths = () => [];
const toMessages = Function('API', 'storedReferenceImagePaths', compiled + '\\nreturn toMessages;')(API, storedReferenceImagePaths);
const base = {id: 1, role: 'assistant', content: 'x', image_path: null, created_at: '2026-11-02 10:00:00'};
const cases = [
  {name: 'feedback', value: {...base, novel_feedback_id: 'feedback-1'}},
  {name: 'all', value: {...base, song_project_id: 'song-1', novel_draft_id: 'draft-1', novel_feedback_id: 'feedback-1'}},
  {name: 'none', value: {...base}},
];
process.stdout.write(JSON.stringify(Object.fromEntries(cases.map(item => [item.name, toMessages([item.value])[0].cards ?? null]))));
"""
    result = subprocess.run(
        ["node", "-e", script, function], cwd=FRONTEND,
        capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)


def test_use_conversations_rebuilds_feedback_card_with_field_equality():
    require_node_dependencies()
    _require_feedback()
    source = read(CONVERSATIONS)
    assert "novel_feedback_id?: string | null" in source
    assert 'subtype: "novel_feedback", feedback_id: message.novel_feedback_id' in source
    payload = run_to_messages(source)
    assert payload["feedback"] == [
        {"source": "书斋", "points": [], "subtype": "novel_feedback", "feedback_id": "feedback-1"},
    ]
    assert payload["all"] == [
        {"source": "写歌", "points": [], "subtype": "song_project", "project_id": "song-1"},
        {"source": "书斋", "points": [], "subtype": "novel_draft", "draft_id": "draft-1"},
        {"source": "书斋", "points": [], "subtype": "novel_feedback", "feedback_id": "feedback-1"},
    ]
    assert payload["none"] is None

    bad = source.replace(
        'if (message.role === "assistant" && message.novel_feedback_id)', "if (false)", 1)
    assert bad != source
    bad_payload = run_to_messages(bad)
    with pytest.raises(AssertionError):
        assert any(card.get("subtype") == "novel_feedback" for card in (bad_payload["all"] or []))


# ────────────────────────── SSR 渲染 ──────────────────────────

# 与 test_desk_views_frontend.NODE_RENDERER 同一写法，只换 STUBS 并支持
# __withOpenNovel：JSON 传不了函数，渲染前注入 onOpenNovel 再删掉这个键。
NODE_RENDERER = r"""
const fs = require('fs');
const path = require('path');
const ts = require('typescript');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');

const FRONTEND = process.cwd();
const realRequire = require;

class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}
function apiJson() { throw new Error('network is disabled in feedback card tests'); }
function apiFetch() { throw new Error('network is disabled in feedback card tests'); }
function useConfirm() { return () => { throw new Error('confirm must not run in SSR'); }; }
function getNovelFeedback() { throw new Error('getNovelFeedback must not run in SSR'); }
function sendNovelFeedbackNote() { throw new Error('sendNovelFeedbackNote must not run in SSR'); }
function redoNovelFeedbackPlan() { throw new Error('redoNovelFeedbackPlan must not run in SSR'); }

const STUBS = {
  '@/lib/agents': { ApiError, apiJson },
  '@/lib/auth': { apiFetch },
  '@/lib/config': { API_BASE: '/api' },
  '@/components/ConfirmDialog': { useConfirm },
  '@/lib/novelFeedback': { getNovelFeedback, sendNovelFeedbackNote, redoNovelFeedbackPlan },
};

const cache = new Map();

function insideFrontend(file) {
  const normalized = path.resolve(file);
  return normalized === FRONTEND || normalized.startsWith(FRONTEND + path.sep);
}

function resolveFile(spec, fromDir) {
  let base;
  if (spec.startsWith('@/')) base = path.join(FRONTEND, spec.slice(2));
  else if (spec.startsWith('./') || spec.startsWith('../')) base = path.resolve(fromDir, spec);
  else throw new Error('module is not allowed: ' + spec);
  const candidates = path.extname(base)
    ? [base]
    : [base + '.tsx', base + '.ts', base + '.js',
       path.join(base, 'index.tsx'), path.join(base, 'index.ts')];
  for (const candidate of candidates) {
    const full = path.resolve(candidate);
    if (!insideFrontend(full)) throw new Error('module escapes the repository: ' + spec);
    if (fs.existsSync(full) && fs.statSync(full).isFile()) return full;
  }
  throw new Error('module not found: ' + spec + ' from ' + fromDir);
}

function requireFrom(spec, fromDir) {
  if (spec === 'react') return React;
  if (spec === 'react/jsx-runtime') return realRequire('react/jsx-runtime');
  if (spec === 'react-dom/server') return realRequire('react-dom/server');
  if (Object.prototype.hasOwnProperty.call(STUBS, spec)) return STUBS[spec];
  return loadModule(resolveFile(spec, fromDir));
}

function loadModule(file) {
  const full = path.resolve(file);
  if (!insideFrontend(full)) throw new Error('module escapes the repository: ' + file);
  if (cache.has(full)) return cache.get(full).exports;
  const moduleObject = { exports: {} };
  cache.set(full, moduleObject);
  const source = fs.readFileSync(full, 'utf8');
  const compiled = ts.transpileModule(source, {
    fileName: full,
    compilerOptions: {
      target: ts.ScriptTarget.ES2020,
      module: ts.ModuleKind.CommonJS,
      jsx: ts.JsxEmit.ReactJSX,
      esModuleInterop: true,
    },
  }).outputText;
  const fn = new Function('exports', 'require', 'module', '__filename', '__dirname', compiled);
  fn(moduleObject.exports, spec => requireFrom(spec, path.dirname(full)),
     moduleObject, full, path.dirname(full));
  return moduleObject.exports;
}

function loadSource(source, file) {
  const full = path.resolve(file);
  const compiled = ts.transpileModule(source, {
    fileName: full,
    compilerOptions: {
      target: ts.ScriptTarget.ES2020,
      module: ts.ModuleKind.CommonJS,
      jsx: ts.JsxEmit.ReactJSX,
      esModuleInterop: true,
    },
  }).outputText;
  const moduleObject = { exports: {} };
  const fn = new Function('exports', 'require', 'module', '__filename', '__dirname', compiled);
  fn(moduleObject.exports, spec => requireFrom(spec, path.dirname(full)),
     moduleObject, full, path.dirname(full));
  return moduleObject.exports;
}

try {
  const component = process.argv[3]
    ? loadSource(process.argv[3], path.join(FRONTEND, process.argv[1]))
    : loadModule(path.join(FRONTEND, process.argv[1]));
  if (typeof component.default !== 'function') {
    throw new Error('component has no default export: ' + process.argv[1]);
  }
  const props = JSON.parse(process.argv[2]);
  if (props.__withOpenNovel === true) props.onOpenNovel = () => {};
  delete props.__withOpenNovel;
  process.stdout.write(renderToStaticMarkup(React.createElement(component.default, props)));
} catch (error) {
  process.stderr.write(String((error && error.stack) || error));
  process.exit(1);
}
"""


def render_feedback(props, source=None):
    _require_feedback()
    args = ["node", "-e", NODE_RENDERER, "components/NovelFeedbackCard.tsx",
            json.dumps(props, ensure_ascii=False)]
    if source is not None:
        args.append(source)
    result = subprocess.run(
        args, cwd=FRONTEND, capture_output=True, text=True,
    )
    if result.returncode != 0:
        pytest.fail(f"node SSR failed for NovelFeedbackCard:\n{result.stderr}")
    return result.stdout


def render_view(view, *, open_novel=False, title=None, source=None):
    props = {"feedbackId": "feedback-1", "initialView": view}
    if open_novel:
        props["__withOpenNovel"] = True
    html = render_feedback(props, source=source)
    assert f"修改意见 · 《{title or view['book_title'].strip() or '未命名小说'}》" in html
    return html


# F1：书在等确认，但等的不是卡上这一章。两条都要求把 onOpenNovel 传进去，
# 这样「按钮缺失」不可能是没传回调造成的。
OTHER_CHAPTER_VIEW = dict(
    current_plan="把这一章收紧", plan_chapter=PLAN_CHAPTER,
    book=make_book(awaiting_chapter=3, plan_row_status="done"),
)
REDO_OTHER_CHAPTER_VIEW = dict(
    current_plan="把这一章收紧", plan_chapter=PLAN_CHAPTER,
    redo_started_at="2026-11-12 10:01:00",
    book=make_book(redo_pending=False, awaiting_chapter=3),
)
PLAN_CASES_WITH_OPEN_NOVEL = {
    "not-awaiting-other-chapter",
    "redo-done-awaiting-other-chapter",
}

PLAN_CASES = [
    ("redo-book-deleted", dict(
        current_plan="把这一章收紧", plan_chapter=PLAN_CHAPTER,
        redo_started_at="2026-11-12 10:01:00", book=None,
    ), "已发起重新定稿", DELETED, False),
    ("redo-running", dict(
        current_plan="把这一章收紧", plan_chapter=PLAN_CHAPTER,
        redo_started_at="2026-11-12 10:01:00",
        book=make_book(redo_pending=True, status="running"),
    ), "已发起重新定稿", PLAN_RUNNING, False),
    ("redo-setup-running", dict(
        current_plan="把这一章收紧", plan_chapter=PLAN_CHAPTER,
        redo_started_at="2026-11-12 10:01:00",
        book=make_book(redo_pending=True, status="setup_running"),
    ), "已发起重新定稿", PLAN_RUNNING, False),
    ("redo-paused", dict(
        current_plan="把这一章收紧", plan_chapter=PLAN_CHAPTER,
        redo_started_at="2026-11-12 10:01:00",
        book=make_book(redo_pending=True, status="paused"),
    ), "已发起重新定稿", PLAN_PAUSED, False),
    ("redo-failed", dict(
        current_plan="把这一章收紧", plan_chapter=PLAN_CHAPTER,
        redo_started_at="2026-11-12 10:01:00",
        book=make_book(redo_pending=True, status="failed"),
    ), "已发起重新定稿", PLAN_FAILED, False),
    ("redo-done-awaiting", dict(
        current_plan="把这一章收紧", plan_chapter=PLAN_CHAPTER,
        redo_started_at="2026-11-12 10:01:00", book=make_book(redo_pending=False),
    ), "已发起重新定稿", PLAN_DONE_AWAITING, False),
    ("redo-done-elsewhere", dict(
        current_plan="把这一章收紧", plan_chapter=PLAN_CHAPTER,
        redo_started_at="2026-11-12 10:01:00",
        book=make_book(redo_pending=False, status="completed"),
    ), "已发起重新定稿", PLAN_DONE, False),
    ("redo-done-failed", dict(
        current_plan="把这一章收紧", plan_chapter=PLAN_CHAPTER,
        redo_started_at="2026-11-12 10:01:00",
        book=make_book(redo_pending=False, status="failed"),
    ), "已发起重新定稿", PLAN_DONE, False),
    ("book-deleted", dict(
        current_plan="把这一章收紧", plan_chapter=PLAN_CHAPTER, book=None,
    ), None, DELETED, False),
    ("actionable-strawberries", dict(
        current_plan="把这一章收紧", plan_chapter=PLAN_CHAPTER,
        book=make_book(redo_cost="strawberries"),
    ), None, plan_action_description("strawberries"), True),
    ("actionable-own-model", dict(
        current_plan="把这一章收紧", plan_chapter=PLAN_CHAPTER,
        book=make_book(redo_cost="own_model"),
    ), None, plan_action_description("own_model"), True),
    ("actionable-free", dict(
        current_plan="把这一章收紧", plan_chapter=PLAN_CHAPTER,
        book=make_book(redo_cost="free"),
    ), None, plan_action_description("free"), True),
    ("not-per-chapter", dict(
        current_plan="把这一章收紧", plan_chapter=PLAN_CHAPTER,
        book=make_book(automation="per_batch"),
    ), None, PLAN_NOT_PER_CHAPTER, False),
    ("book-failed", dict(
        current_plan="把这一章收紧", plan_chapter=PLAN_CHAPTER,
        book=make_book(status="failed", plan_row_status="awaiting_plan_approval"),
    ), None, PLAN_FAILED_ROW, False),
    ("row-awaiting-paused", dict(
        current_plan="把这一章收紧", plan_chapter=PLAN_CHAPTER,
        book=make_book(status="paused", plan_row_status="awaiting_plan_approval"),
    ), None, PLAN_ROW_PAUSED, False),
    ("row-awaiting-running", dict(
        current_plan="把这一章收紧", plan_chapter=PLAN_CHAPTER,
        book=make_book(status="running", plan_row_status="awaiting_plan_approval"),
    ), None, PLAN_ROW_RUNNING, False),
    ("row-planning-running", dict(
        current_plan="把这一章收紧", plan_chapter=PLAN_CHAPTER,
        book=make_book(status="running", plan_row_status="planning"),
    ), None, PLAN_PLANNING_RUNNING, False),
    ("row-planning-paused", dict(
        current_plan="把这一章收紧", plan_chapter=PLAN_CHAPTER,
        book=make_book(status="paused", plan_row_status="planning"),
    ), None, PLAN_PLANNING_PAUSED, False),
    ("not-awaiting", dict(
        current_plan="把这一章收紧", plan_chapter=PLAN_CHAPTER,
        book=make_book(status="completed", plan_row_status=None),
    ), None, PLAN_NOT_AWAITING, False),
    ("not-awaiting-other-chapter", OTHER_CHAPTER_VIEW,
     None, PLAN_NOT_AWAITING, False),
    ("redo-done-awaiting-other-chapter", REDO_OTHER_CHAPTER_VIEW,
     "已发起重新定稿", PLAN_DONE, False),
]


def assert_plan_case(html, tag, description, actionable):
    assert_tag(html, tag)
    assert_only_description(html, description, PLAN_DESCRIPTIONS)
    assert_description_paragraph(html, description)
    if actionable:
        button = button_with_text(html, "带着这些要求重新定稿")
        assert not has_disabled(button)
        assert_button_absent(html, "交给编辑部")
        button_with_text(html, "去书斋改细纲")
    else:
        assert_button_absent(html, "带着这些要求重新定稿")
        assert_button_absent(html, "去书斋改细纲")
        assert_button_absent(html, "交给编辑部")
    assert_no_response(html)


@pytest.mark.parametrize(
    "name,overrides,tag,description,actionable",
    PLAN_CASES, ids=[item[0] for item in PLAN_CASES])
def test_feedback_card_plan_section_states(name, overrides, tag, description, actionable):
    require_node_dependencies()
    _require_feedback()
    view = make_view(**overrides)
    html = render_view(
        view, open_novel=actionable or name in PLAN_CASES_WITH_OPEN_NOVEL)
    if name in PLAN_CASES_WITH_OPEN_NOVEL:
        assert "在书斋打开" in html
    assert_plan_case(html, tag, description, actionable)


def test_feedback_card_other_awaiting_chapter_self_check():
    require_node_dependencies()
    _require_feedback()
    source = read(COMPONENT)
    html = render_view(make_view(**OTHER_CHAPTER_VIEW), open_novel=True)
    assert "在书斋打开" in html
    assert_plan_case(html, None, PLAN_NOT_AWAITING, False)

    marker = "    && book.awaiting_chapter === view.plan_chapter\n"
    assert source.count(marker) == 1
    bad = source.replace(marker, "", 1)
    assert bad != source
    bad_html = render_view(
        make_view(**OTHER_CHAPTER_VIEW), open_novel=True, source=bad)
    with pytest.raises(AssertionError) as error:
        assert_plan_case(bad_html, None, PLAN_NOT_AWAITING, False)
    print(f"F1(a) bad copy: {error.value}")

    html = render_view(make_view(**REDO_OTHER_CHAPTER_VIEW), open_novel=True)
    assert "在书斋打开" in html
    assert_plan_case(html, "已发起重新定稿", PLAN_DONE, False)

    done_marker = (
        "        planDescription = `已经带着这些要求重新定稿过第 ${chapter} 章细纲。`;\n"
        "        if (book.status === \"awaiting_plan\" && book.awaiting_chapter === chapter) {"
    )
    assert done_marker in source
    bad_done = source.replace(
        done_marker,
        "        planDescription = `已经带着这些要求重新定稿过第 ${chapter} 章细纲。`;\n"
        "        if (book.status === \"awaiting_plan\") {",
        1,
    )
    assert bad_done != source
    bad_done_html = render_view(
        make_view(**REDO_OTHER_CHAPTER_VIEW), open_novel=True, source=bad_done)
    with pytest.raises(AssertionError) as error:
        assert_plan_case(
            bad_done_html, "已发起重新定稿", PLAN_DONE, False)
    print(f"F1(b) bad copy: {error.value}")


CHAPTER_CASES = [
    ("delivered-chapter", dict(
        next_chapters="以后写慢一点",
        note=make_note(status="delivered", delivered_chapter=3, adopted=True, response="照做"),
        book=make_book(),
    ), "已下发到第 3 章", None, "编辑部采纳：照做", "none"),
    ("delivered-rejected", dict(
        next_chapters="以后写慢一点",
        note=make_note(status="delivered", delivered_chapter=None, adopted=False, response=""),
        book=make_book(),
    ), "编辑部已回应", None, "编辑部没有采纳：（没有写回应）", "none"),
    ("delivered-unknown", dict(
        next_chapters="以后写慢一点",
        note=make_note(status="delivered", delivered_chapter=3, adopted=None, response=None),
        book=make_book(),
    ), "已下发到第 3 章", None, "编辑部的回应：（没有写回应）", "none"),
    ("planned-normal", dict(
        next_chapters="以后写慢一点",
        note=make_note(status="pending", planned_chapter=3,
                       planned_adopted=False, planned_response="太长"),
        book=make_book(),
    ), "待下发", planned_normal(3), "编辑部没有采纳：太长", "none"),
    ("planned-response-unknown", dict(
        next_chapters="以后写慢一点",
        note=make_note(status="pending", planned_chapter=2,
                       planned_adopted=None, planned_response="再看看"),
        book=make_book(),
    ), "待下发", planned_normal(2), "编辑部的回应：再看看", "none"),
    ("planned-failed", dict(
        next_chapters="以后写慢一点",
        note=make_note(status="pending", planned_chapter=2,
                       planned_adopted=True, planned_response=""),
        book=make_book(status="failed"),
    ), "待下发", PLANNED_FAILED, "编辑部采纳：（没有写回应）", "none"),
    ("note-book-deleted", dict(
        next_chapters="以后写慢一点", note=make_note(), book=None,
    ), "待下发", DELETED, None, "none"),
    ("note-completed", dict(
        next_chapters="以后写慢一点", note=make_note(), book=make_book(status="completed"),
    ), "待下发", CHAPTER_COMPLETED_NOTE, None, "none"),
    ("note-failed", dict(
        next_chapters="以后写慢一点", note=make_note(), book=make_book(status="failed"),
    ), "待下发", CHAPTER_FAILED_NOTE, None, "none"),
    ("note-awaiting-end", dict(
        next_chapters="以后写慢一点", note=make_note(), book=make_book(status="awaiting_end"),
    ), "待下发", CHAPTER_AWAITING_END, None, "none"),
    ("note-awaiting-final", dict(
        next_chapters="以后写慢一点", note=make_note(),
        book=make_book(awaiting_is_final=True),
    ), "待下发", CHAPTER_FINAL, None, "none"),
    ("note-awaiting-plan", dict(
        next_chapters="以后写慢一点", note=make_note(), book=make_book(),
    ), "待下发", CHAPTER_NEXT_PLAN, None, "none"),
    ("note-other-status", dict(
        next_chapters="以后写慢一点", note=make_note(), book=make_book(status="running"),
    ), "待下发", CHAPTER_LATER, None, "none"),
    ("no-note-book-deleted", dict(
        next_chapters="以后写慢一点", book=None,
    ), None, DELETED, None, "none"),
    ("no-note-completed", dict(
        next_chapters="以后写慢一点", book=make_book(status="completed"),
    ), None, CHAPTER_COMPLETED, None, "none"),
    ("no-note-failed", dict(
        next_chapters="以后写慢一点", book=make_book(status="failed"),
    ), None, CHAPTER_FAILED, None, "none"),
    ("pending-full", dict(
        next_chapters="以后写慢一点", book=make_book(pending_notes=5),
    ), None, CHAPTER_FULL, None, "disabled"),
    ("note-enabled", dict(
        next_chapters="以后写慢一点", book=make_book(status="running"),
    ), None, CHAPTER_LATER_TAIL + RETRACT, None, "enabled"),
    ("note-prefix", dict(
        next_chapters="以后写慢一点", book=make_book(status="running", pending_notes=2),
    ), None, CHAPTER_PREFIX + CHAPTER_LATER_TAIL + RETRACT, None, "enabled"),
    ("note-awaiting-end", dict(
        next_chapters="以后写慢一点", book=make_book(status="awaiting_end"),
    ), None, CHAPTER_AWAITING_END + RETRACT, None, "enabled"),
    ("note-awaiting-final", dict(
        next_chapters="以后写慢一点", book=make_book(awaiting_is_final=True),
    ), None, CHAPTER_FINAL + RETRACT, None, "enabled"),
    ("note-awaiting-plan", dict(
        next_chapters="以后写慢一点", book=make_book(),
    ), None,
        f"第 {PLAN_CHAPTER} 章细纲已经出来了，这条要求要到第 3 章规划细纲时编辑部才会读到；"
        f"想让第 {PLAN_CHAPTER} 章就照做，可以在书斋里直接改第 {PLAN_CHAPTER} 章细纲。"
        + RETRACT, None, "enabled"),
]


@pytest.mark.parametrize(
    "name,overrides,tag,description,response,button_state",
    CHAPTER_CASES, ids=[item[0] for item in CHAPTER_CASES])
def test_feedback_card_chapter_section_states(name, overrides, tag, description, response, button_state):
    require_node_dependencies()
    view = make_view(**overrides)
    html = render_view(view)
    assert_tag(html, tag)
    assert_only_description(html, description, CHAPTER_DESCRIPTIONS)
    if description is not None:
        assert_description_paragraph(html, description)
    assert_button_absent(html, "带着这些要求重新定稿")
    assert_button_absent(html, "去书斋改细纲")
    if response is None:
        assert_no_response(html)
    else:
        assert_response_paragraph(html, response)
    if button_state == "none":
        assert_button_absent(html, "交给编辑部")
    elif button_state == "disabled":
        button = button_with_text(html, "交给编辑部")
        assert has_disabled(button)
        id_match = re.search(
            r'<p id="([^"]+)" class="mt-2[^"]*">' + re.escape(description) + "</p>", html)
        assert id_match, "待下发留言已满的说明缺少 useId"
        assert f'aria-describedby="{id_match.group(1)}"' in button
    else:
        button = button_with_text(html, "交给编辑部")
        assert not has_disabled(button)
        assert "aria-describedby" not in button


def test_feedback_card_chapter_section_does_not_guess_later_chapters():
    require_node_dependencies()
    view = make_view(
        next_chapters="以后写慢一点",
        note=make_note(status="pending", planned_chapter=3),
        book=make_book(),
    )
    html = render_view(view)
    assert "第 4 章" not in html

    final_view = make_view(
        next_chapters="以后写慢一点", book=make_book(awaiting_is_final=True))
    final_html = render_view(final_view)
    assert CHAPTER_FINAL in final_html
    assert "第 3 章" not in final_html


FINAL_CHAPTER = 50
FINAL_CHAPTER_SENTENCE = (
    "第 50 章会是这本书的最后一章；只有选择再写几章，编辑部才会读到这条要求。"
)


def last_chapter_view(note=None):
    return make_view(
        next_chapters="以后写慢一点",
        note=note,
        book=make_book(
            awaiting_chapter=FINAL_CHAPTER,
            max_chapters=FINAL_CHAPTER,
            awaiting_is_final=False,
        ),
    )


def assert_last_chapter(html, *, exact):
    assert FINAL_CHAPTER_SENTENCE in html
    assert "第 51 章" not in html
    if exact:
        assert_description_paragraph(html, FINAL_CHAPTER_SENTENCE)


def test_feedback_card_last_chapter_uses_max_chapters_branch():
    require_node_dependencies()
    _require_feedback()
    without_note = render_view(last_chapter_view())
    assert_last_chapter(without_note, exact=False)
    assert "交出后不能撤回。" in without_note

    with_pending = render_view(last_chapter_view(make_note(status="pending")))
    assert_last_chapter(with_pending, exact=True)
    assert "待下发" in with_pending


def test_feedback_card_last_chapter_self_check():
    require_node_dependencies()
    _require_feedback()
    source = read(COMPONENT)
    marker = "|| (maxChapters !== null && awaitingChapter >= maxChapters)"
    assert source.count(marker) == 1
    bad = source.replace(marker, "", 1)
    assert bad != source
    bad_without_note = render_view(last_chapter_view(), source=bad)
    with pytest.raises(AssertionError) as error:
        assert_last_chapter(bad_without_note, exact=False)
    print(f"F3 note=None bad copy: {error.value}")
    bad_with_pending = render_view(
        last_chapter_view(make_note(status="pending")), source=bad)
    with pytest.raises(AssertionError) as error:
        assert_last_chapter(bad_with_pending, exact=True)
    print(f"F3 note=pending bad copy: {error.value}")


def test_feedback_card_plan_state_order_prefers_redo_and_book_state():
    require_node_dependencies()
    deleted = render_view(make_view(
        current_plan="把这一章收紧", plan_chapter=PLAN_CHAPTER,
        redo_started_at="2026-11-12 10:01:00", book=None,
    ))
    assert DELETED in deleted
    assert PLAN_DONE not in deleted

    paused = render_view(make_view(
        current_plan="把这一章收紧", plan_chapter=PLAN_CHAPTER,
        redo_started_at="2026-11-12 10:01:00",
        book=make_book(redo_pending=False, status="paused"),
    ))
    assert PLAN_DONE in paused
    assert "还没有完成" not in paused and "没有完成" not in paused

    failed = render_view(make_view(
        current_plan="把这一章收紧", plan_chapter=PLAN_CHAPTER,
        book=make_book(status="failed", plan_row_status="awaiting_plan_approval"),
    ))
    assert PLAN_FAILED_ROW in failed
    assert PLAN_PAUSED not in failed and PLAN_RUNNING not in failed


def test_feedback_card_written_section_lists_every_issue():
    require_node_dependencies()
    view = make_view(
        written=[
            {"chapter": 1, "title": "第1章 起点", "issue": "太拖"},
            {"chapter": 2, "title": "", "issue": "人物扁平"},
            {"chapter": 3, "title": "转折", "issue": "节奏太快"},
        ],
        book=make_book(),
    )
    html = render_view(view)
    assert '<ol class="mt-1 space-y-1 text-fs-13">' in html
    assert '<li class="break-words">第 1 章 起点：太拖</li>' in html
    assert '<li class="break-words">第 2 章 待定章名：人物扁平</li>' in html
    assert '<li class="break-words">第 3 章 转折：节奏太快</li>' in html
    assert WRITTEN_DESCRIPTION in html
    assert "已写好的章节" in html

    empty = render_view(make_view(written=[], book=make_book()))
    assert "已写好的章节" not in empty

    default_title = render_view(make_view(book_title="  ", book=make_book()), title="未命名小说")
    assert "修改意见 · 《未命名小说》" in default_title


def test_feedback_card_hides_empty_sections():
    require_node_dependencies()
    html = render_view(make_view(
        current_plan="   ", plan_chapter=PLAN_CHAPTER,
        next_chapters="\n", written=[], book=make_book(),
    ))
    assert "第 2 章细纲" not in html
    assert "以后的章节" not in html
    assert "已写好的章节" not in html
    assert "<section" not in html

    no_chapter = render_view(make_view(
        current_plan="把这一章收紧", plan_chapter=None, book=make_book(),
    ))
    assert "第 2 章细纲" not in no_chapter


def test_feedback_card_renders_loading_state_without_initial_view():
    require_node_dependencies()
    html = render_feedback({"feedbackId": "feedback-1"})
    assert 'role="status"' in html
    assert "正在读取修改意见…" in html
    assert "ceramic-card" in html


def test_feedback_card_shows_full_plan_and_chapter_texts():
    require_node_dependencies()
    next_chapters = "甲" * 499 + "乙"
    current_plan = "丙" * 499 + "丁"
    assert len(next_chapters) == len(current_plan) == 500
    html = render_view(make_view(
        next_chapters=next_chapters,
        current_plan=current_plan,
        plan_chapter=PLAN_CHAPTER,
        book=make_book(),
    ))
    assert next_chapters in html
    assert current_plan in html
    assert "…" not in html
    assert ".slice(0, 80)" not in read(COMPONENT)


def test_feedback_card_bottom_hint_and_novel_entry():
    require_node_dependencies()
    actionable = make_view(
        next_chapters="以后写慢一点",
        current_plan="把这一章收紧",
        plan_chapter=PLAN_CHAPTER,
        book=make_book(),
    )
    first_hint = "书斋如果之前已经开着这本书，要回到书架重新打开它，才会看到最新的细纲和留言。"
    second_hint = (
        "在旧页面上点「批准（原样）」会直接批准你还没看过的新细纲，"
        "点「改完批准」会用旧页面里的内容覆盖新细纲。"
    )

    with_open = render_view(actionable, open_novel=True)
    assert "在书斋打开" in with_open
    assert "去书斋改细纲" in with_open
    assert first_hint in with_open
    assert second_hint not in with_open

    without_open = render_view(actionable)
    assert "在书斋打开" not in without_open
    assert "去书斋改细纲" not in without_open
    assert first_hint not in without_open

    deleted = render_view(dict(actionable, book=None), open_novel=True)
    assert "在书斋打开" not in deleted
    assert "去书斋改细纲" not in deleted
    assert first_hint not in deleted

    noted = render_view(make_view(
        next_chapters="以后写慢一点",
        note=make_note(status="pending", planned_chapter=3),
        book=make_book(),
    ), open_novel=True)
    assert "在书斋打开" in noted
    assert first_hint in noted
    assert second_hint not in noted

    redone = render_view(make_view(
        current_plan="把这一章收紧",
        plan_chapter=PLAN_CHAPTER,
        redo_started_at="2026-11-12 10:01:00",
        book=make_book(redo_pending=False, status="completed"),
    ), open_novel=True)
    assert first_hint + second_hint in redone

    quiet = render_view(make_view(
        next_chapters="以后写慢一点", book=make_book(status="running")),
        open_novel=True)
    assert "在书斋打开" in quiet
    assert "去书斋改细纲" not in quiet
    assert first_hint not in quiet


# ────────────────────────── 交互 ──────────────────────────

# 迷你 hooks 运行时来自 test_desk_dock_races_frontend；这里补 unmount()，
# 依次调用所有 effect 的清理函数。组件源码从 argv 传入，坏副本自检可复用。
NODE_INTERACTION = r"""
const fs = require('fs');
const path = require('path');
const ts = require(path.join(process.cwd(), 'node_modules/typescript'));
const FRONTEND = process.cwd();
const cfg = JSON.parse(process.argv[2]);

let slots = [], cursor = 0, pendingEffects = [], scheduled = false, unmounted = false;
let settersAfterUnmount = 0;
let Component = null, props = null, lastTree = null;
function schedule() { if (!scheduled && !unmounted) { scheduled = true; setTimeout(flush, 0); } }
function flush() {
  if (unmounted) return;
  scheduled = false; cursor = 0; pendingEffects = [];
  lastTree = Component(props);
  for (const run of pendingEffects) run();
}
const React = {
  useState(init) {
    const i = cursor++;
    if (!(i in slots)) slots[i] = { v: typeof init === 'function' ? init() : init };
    const slot = slots[i];
    return [slot.v, next => { if (unmounted) settersAfterUnmount += 1; const v = typeof next === 'function' ? next(slot.v) : next; if (!Object.is(v, slot.v)) { slot.v = v; schedule(); } }];
  },
  useRef(init) { const i = cursor++; if (!(i in slots)) slots[i] = { current: init }; return slots[i]; },
  useEffect(fn, deps) {
    const i = cursor++; const prev = slots[i];
    if (prev && deps && prev.deps && deps.every((d, k) => Object.is(d, prev.deps[k]))) return;
    if (!prev) slots[i] = { deps: null, cleanup: null };
    pendingEffects.push(() => {
      const p = slots[i];
      if (p.cleanup) p.cleanup();
      const c = fn();
      slots[i] = { deps, cleanup: typeof c === 'function' ? c : null };
    });
  },
  useId() { cursor++; return 'feedback-full-id'; },
};
const jsx = (type, p, key) => ({ type, props: p || {}, key });
const sleep = ms => new Promise(r => setTimeout(r, ms));

class ApiError extends Error {
  constructor(message, status) { super(message); this.name = 'ApiError'; this.status = status; }
}
const calls = { get: 0, note: 0, redo: 0 };
const order = [];
const signals = [];
const confirmCalls = [];
let noteDeferred = null;
let clickGetDeferred = null;
let resolveConfirm = null;

function deferred(signal) {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => {
    resolve = res;
    reject = rej;
    if (signal) signal.addEventListener('abort', () => {
      reject(Object.assign(new Error('aborted'), { name: 'AbortError' }));
    });
  });
  return { promise, resolve, reject };
}

function deferredNoAbort() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

const getNovelFeedback = (id, signal) => {
  calls.get += 1;
  order.push('get');
  signals.push({ kind: 'get', signal });
  if (cfg.getRejects && calls.get === 1) {
    if (cfg.getRejects === 'api404') return Promise.reject(new ApiError('修改意见不存在', 404));
    if (cfg.getRejects === 'api403') return Promise.reject(new ApiError('x', 403));
    return Promise.reject(new Error('x'));
  }
  if (cfg.clickGet === 'deferred' || cfg.clickGet === 'deferred-abort') {
    clickGetDeferred = cfg.clickGet === 'deferred-abort'
      ? deferred(signal)
      : deferredNoAbort();
    return clickGetDeferred.promise;
  }
  if (cfg.clickGet === 'api500') {
    return Promise.reject(new ApiError(cfg.clickErrorMessage || '服务器错误', 500));
  }
  if (cfg.clickGet === 'type') {
    return Promise.reject(new TypeError(cfg.clickErrorMessage || '网络错误'));
  }
  return Promise.resolve(cfg.clickView || cfg.retryView || cfg.initialView);
};
const sendNovelFeedbackNote = (id, signal) => {
  calls.note += 1;
  order.push('note');
  signals.push({ kind: 'note', signal });
  if (cfg.note === 'reject') return Promise.reject(new ApiError('交留言失败', 409));
  if (cfg.note === 'reject-then-success' && calls.note === 1) {
    return Promise.reject(new ApiError('交留言失败', 409));
  }
  if (cfg.note === 'reject-then-success') return Promise.resolve(cfg.noteView);
  if (cfg.note === 'immediate') return Promise.resolve(cfg.noteView);
  if (cfg.note === 'deferred-no-abort') {
    noteDeferred = deferredNoAbort();
    return noteDeferred.promise;
  }
  noteDeferred = deferred(signal);
  return noteDeferred.promise;
};
const redoNovelFeedbackPlan = (id, signal) => {
  calls.redo += 1;
  order.push('redo');
  signals.push({ kind: 'redo', signal });
  if (cfg.redo === 'reject') return Promise.reject(new ApiError('重新定稿失败', 409));
  return Promise.resolve(cfg.redoView);
};

const STUBS = {
  '@/lib/agents': { ApiError },
  '@/lib/auth': { apiFetch: async () => { throw new Error('network disabled'); } },
  '@/lib/config': { API_BASE: '/api' },
  '@/components/ConfirmDialog': {
    useConfirm: () => options => {
      confirmCalls.push(options);
      order.push('confirm');
      return new Promise(resolve => { resolveConfirm = resolve; });
    },
  },
  '@/lib/novelFeedback': { getNovelFeedback, sendNovelFeedbackNote, redoNovelFeedbackPlan },
};
const cache = new Map();

function compile(source, file) {
  return ts.transpileModule(source, {
    fileName: file,
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2020,
      jsx: ts.JsxEmit.ReactJSX,
      esModuleInterop: true,
    },
  }).outputText;
}

function resolveRequire(spec, fromDir) {
  if (spec === 'react') return React;
  if (spec === 'react/jsx-runtime') return { jsx, jsxs: jsx, Fragment: 'Fragment' };
  if (Object.prototype.hasOwnProperty.call(STUBS, spec)) return STUBS[spec];
  if (spec.startsWith('@/')) {
    const base = path.join(FRONTEND, spec.slice(2));
    const file = fs.existsSync(base + '.ts') ? base + '.ts' : base + '.tsx';
    return load(file);
  }
  throw new Error('unexpected import ' + spec + ' from ' + fromDir);
}

function load(file) {
  if (cache.has(file)) return cache.get(file).exports;
  const moduleObject = { exports: {} };
  cache.set(file, moduleObject);
  const compiled = compile(fs.readFileSync(file, 'utf8'), file);
  new Function('exports', 'require', 'module', compiled)(
    moduleObject.exports, spec => resolveRequire(spec, path.dirname(file)), moduleObject);
  return moduleObject.exports;
}

function loadSource(source, fileName) {
  const moduleObject = { exports: {} };
  const compiled = compile(source, fileName);
  new Function('exports', 'require', 'module', compiled)(
    moduleObject.exports, spec => resolveRequire(spec, FRONTEND), moduleObject);
  return moduleObject.exports;
}

Component = loadSource(process.argv[1], 'NovelFeedbackCard.tsx').default;
if (typeof Component !== 'function') throw new Error('component has no default export');
props = { feedbackId: 'feedback-1' };
if (cfg.initialView) props.initialView = cfg.initialView;
if (cfg.withOpenNovel) props.onOpenNovel = () => {};

function textOf(node) {
  if (node == null || typeof node === 'boolean') return '';
  if (typeof node === 'string' || typeof node === 'number') return String(node);
  if (Array.isArray(node)) return node.map(textOf).join('');
  if (node.props) return textOf(node.props.children);
  return '';
}
function walk(node, visit) {
  if (!node || typeof node !== 'object') return;
  if (Array.isArray(node)) { node.forEach(item => walk(item, visit)); return; }
  visit(node);
  if (node.props) walk(node.props.children, visit);
}
function elements(type) {
  const found = [];
  walk(lastTree, node => { if (node.type === type) found.push(node); });
  return found;
}
function buttons(substring) {
  return elements('button').filter(button => !substring || textOf(button).includes(substring));
}
function alerts() {
  return elements('p').filter(node => node.props && node.props.role === 'alert');
}
function snapshot(label) {
  return {
    label,
    order: order.slice(),
    calls: { ...calls },
    buttons: elements('button').map(button => ({
      text: textOf(button),
      disabled: button.props.disabled === true,
    })),
    alerts: alerts().map(textOf),
    paragraphs: elements('p').map(textOf),
    text: textOf(lastTree),
  };
}
function unmount() {
  unmounted = true;
  for (const slot of slots) {
    if (slot && typeof slot.cleanup === 'function') {
      const cleanup = slot.cleanup;
      slot.cleanup = null;
      cleanup();
    }
  }
}

const observations = [];
async function main() {
  flush();
  await sleep(10);
  if (cfg.scenario === 'note-inflight') {
    observations.push(snapshot('initial'));
    buttons('交给编辑部')[0].props.onClick();
    await sleep(10);
    observations.push(snapshot('inflight'));
    noteDeferred.resolve(cfg.noteView);
    await sleep(30);
    observations.push(snapshot('done'));
  } else if (cfg.scenario === 'note-error') {
    observations.push(snapshot('initial'));
    buttons('交给编辑部')[0].props.onClick();
    await sleep(50);
    observations.push(snapshot('error'));
  } else if (cfg.scenario === 'note-retry') {
    buttons('交给编辑部')[0].props.onClick();
    await sleep(50);
    observations.push(snapshot('error'));
    buttons('交给编辑部')[0].props.onClick();
    await sleep(30);
    observations.push(snapshot('recovered'));
  } else if (cfg.scenario === 'confirm-error') {
    buttons('重新定稿')[0].props.onClick();
    await sleep(10);
    observations.push(snapshot('confirming'));
    resolveConfirm(true);
    await sleep(50);
    observations.push(snapshot('error'));
  } else if (cfg.scenario === 'read') {
    observations.push(snapshot('first'));
    const retry = buttons('重新读取')[0];
    if (retry) {
      retry.props.onClick();
      await sleep(30);
      observations.push(snapshot('second'));
    }
  } else if (cfg.scenario === 'confirm') {
    observations.push(snapshot('initial'));
    buttons('重新定稿')[0].props.onClick();
    await sleep(10);
    observations.push(snapshot('confirming'));
    resolveConfirm(cfg.confirm === true);
    await sleep(30);
    observations.push(snapshot('settled'));
    if (cfg.afterCancelRedo) {
      buttons('重新定稿')[0].props.onClick();
      await sleep(20);
      observations.push(snapshot('second-confirming'));
    }
  } else if (cfg.scenario === 'note-then-redo') {
    buttons('交给编辑部')[0].props.onClick();
    await sleep(30);
    observations.push(snapshot('after-note'));
    buttons('重新定稿')[0].props.onClick();
    await sleep(10);
    observations.push(snapshot('confirming'));
    resolveConfirm(false);
    await sleep(20);
    observations.push(snapshot('after-confirm'));
  } else if (cfg.scenario === 'unmount') {
    buttons('交给编辑部')[0].props.onClick();
    await sleep(10);
    observations.push(snapshot('inflight'));
    unmount();
    await sleep(60);
    observations.push(snapshot('after-unmount'));
  } else if (cfg.scenario === 'unmount-note-resolve') {
    buttons('交给编辑部')[0].props.onClick();
    await sleep(10);
    observations.push(snapshot('inflight'));
    unmount();
    noteDeferred.resolve(cfg.noteView);
    await sleep(40);
    observations.push(snapshot('after-unmount'));
  } else if (cfg.scenario === 'double-note') {
    const button = buttons('交给编辑部')[0];
    button.props.onClick();
    button.props.onClick();
    await sleep(30);
    observations.push(snapshot('done'));
  } else if (cfg.scenario === 'double-redo') {
    const button = buttons('重新定稿')[0];
    button.props.onClick();
    button.props.onClick();
    await sleep(20);
    observations.push(snapshot('confirming'));
    resolveConfirm(true);
    await sleep(40);
    observations.push(snapshot('settled'));
  } else if (cfg.scenario === 'redo-reread') {
    observations.push(snapshot('initial'));
    buttons('重新定稿')[0].props.onClick();
    await sleep(10);
    observations.push(snapshot('rereading'));
    if (cfg.clickGet === 'deferred') {
      clickGetDeferred.resolve(cfg.clickView);
    }
    await sleep(20);
    observations.push(snapshot('reread'));
    if (cfg.afterRereadNote) {
      buttons('交给编辑部')[0].props.onClick();
      await sleep(30);
      observations.push(snapshot('after-note'));
    }
    if (cfg.afterRereadRedo) {
      buttons('重新定稿')[0].props.onClick();
      await sleep(20);
      observations.push(snapshot('second-reread'));
    }
    if (typeof resolveConfirm === 'function' && cfg.confirm !== undefined) {
      resolveConfirm(cfg.confirm);
      await sleep(40);
      observations.push(snapshot('settled'));
      if (cfg.afterCancelRedo) {
        buttons('重新定稿')[0].props.onClick();
        await sleep(20);
        observations.push(snapshot('second-confirming'));
      }
    }
  } else if (cfg.scenario === 'unmount-reread') {
    buttons('重新定稿')[0].props.onClick();
    await sleep(10);
    observations.push(snapshot('inflight'));
    unmount();
    clickGetDeferred.resolve(cfg.clickView);
    await sleep(40);
    observations.push(snapshot('after-unmount'));
  } else if (cfg.scenario === 'unmount-confirm') {
    buttons('重新定稿')[0].props.onClick();
    await sleep(20);
    observations.push(snapshot('inflight'));
    unmount();
    resolveConfirm(true);
    await sleep(40);
    observations.push(snapshot('after-unmount'));
  } else {
    throw new Error('unknown scenario ' + cfg.scenario);
  }
  const novels = load(path.join(FRONTEND, 'lib/novels.ts'));
  console.log(JSON.stringify({
    calls,
    order,
    settersAfterUnmount,
    signals: signals.map(item => ({
      kind: item.kind,
      has: !!item.signal,
      aborted: !!item.signal && item.signal.aborted,
    })),
    confirmCalls,
    observations,
    errorMessage403: novels.novelErrorMessage(new ApiError('x', 403)),
    errorMessage500: novels.novelErrorMessage(new ApiError(cfg.clickErrorMessage || '服务器错误', 500)),
    errorMessageType: novels.novelErrorMessage(new TypeError(cfg.clickErrorMessage || '网络错误')),
  }));
  process.exit(0);
}
main().catch(error => {
  process.stderr.write(String((error && error.stack) || error));
  process.exit(1);
});
"""


def run_interaction(source, scenario, **config):
    _require_feedback()
    payload = {"scenario": scenario}
    payload.update(config)
    result = subprocess.run(
        ["node", "-e", NODE_INTERACTION, source, json.dumps(payload, ensure_ascii=False)],
        cwd=FRONTEND, capture_output=True, text=True,
    )
    if result.returncode != 0:
        pytest.fail(f"node interaction {scenario} failed:\n{result.stderr}")
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert lines, result.stdout
    return json.loads(lines[-1])


def interaction_view(**overrides):
    base = dict(
        next_chapters="以后写慢一点",
        current_plan="把这一章收紧",
        plan_chapter=PLAN_CHAPTER,
        book=make_book(),
    )
    base.update(overrides)
    return make_view(**base)


def observation(result, label):
    matches = [item for item in result["observations"] if item["label"] == label]
    assert len(matches) == 1, result["observations"]
    return matches[0]


def button_state(observation_item, text):
    matches = [item for item in observation_item["buttons"] if item["text"] == text]
    assert len(matches) == 1, observation_item["buttons"]
    return matches[0]


def assert_no_setters_after_unmount(result):
    assert result["settersAfterUnmount"] == 0, (
        f"卸载后仍调用了 {result['settersAfterUnmount']} 次 state setter")


def test_feedback_card_note_click_disables_both_actions_while_pending():
    require_node_dependencies()
    _require_feedback()
    source = read(COMPONENT)
    view = interaction_view()
    note_view = dict(view, note=make_note(status="pending"))
    result = run_interaction(
        source, "note-inflight", initialView=view, noteView=note_view,
        note="deferred", withOpenNovel=True)

    assert result["calls"] == {"get": 0, "note": 1, "redo": 0}
    initial = observation(result, "initial")
    assert button_state(initial, "带着这些要求重新定稿")["disabled"] is False
    assert button_state(initial, "交给编辑部")["disabled"] is False
    assert button_state(initial, "去书斋改细纲")["disabled"] is False
    assert button_state(initial, "在书斋打开")["disabled"] is False

    inflight = observation(result, "inflight")
    pressed = button_state(inflight, "正在交给编辑部…")
    assert pressed["disabled"] is True
    assert button_state(inflight, "带着这些要求重新定稿")["disabled"] is True
    assert button_state(inflight, "去书斋改细纲")["disabled"] is False
    assert button_state(inflight, "在书斋打开")["disabled"] is False
    assert "交给编辑部" not in [item["text"] for item in inflight["buttons"]]

    done = observation(result, "done")
    assert "交给编辑部" not in [item["text"] for item in done["buttons"]]
    assert "待下发" in done["text"]
    assert result["signals"][0]["kind"] == "note" and result["signals"][0]["has"] is True


@pytest.mark.parametrize("cost", ["strawberries", "own_model", "free"])
def test_feedback_card_redo_confirmation_costs(cost):
    require_node_dependencies()
    _require_feedback()
    source = read(COMPONENT)
    view = make_view(
        current_plan="把这一章收紧",
        plan_chapter=PLAN_CHAPTER,
        book=make_book(redo_cost=cost),
    )
    result = run_interaction(
        source, "confirm", initialView=view, clickView=view,
        confirm=False, afterCancelRedo=True, withOpenNovel=True)
    assert result["calls"] == {"get": 2, "note": 0, "redo": 0}
    assert result["signals"][0]["kind"] == "get" and result["signals"][0]["has"] is True
    expected_body = (
        "编辑部会拿原来的讨论材料加上这张卡上的要求，重新写一版第 "
        f"{PLAN_CHAPTER} 章细纲（看不到现在这一版，是否照改由编辑部判断）。"
        f"{FEE[cost]}完成后新细纲仍会停下来等你确认。"
    )
    expected_confirm = {
        "title": f"重新定稿第 {PLAN_CHAPTER} 章细纲",
        "body": expected_body,
        "confirmLabel": "重新定稿",
    }
    # 取消确认框后再点一次：getNovelFeedback 与 confirm 都累计到 2 次。
    assert result["confirmCalls"] == [expected_confirm, expected_confirm]
    confirming = observation(result, "confirming")
    assert button_state(confirming, "带着这些要求重新定稿")["disabled"] is True
    settled = observation(result, "settled")
    assert button_state(settled, "带着这些要求重新定稿")["disabled"] is False
    assert "正在" not in settled["text"]
    second = observation(result, "second-confirming")
    assert button_state(second, "带着这些要求重新定稿")["disabled"] is True
    assert button_state(second, "带着这些要求重新定稿")["text"] == "带着这些要求重新定稿"


def test_feedback_card_redo_confirmed_calls_once_and_updates_view():
    require_node_dependencies()
    _require_feedback()
    source = read(COMPONENT)
    view = make_view(
        current_plan="把这一章收紧",
        plan_chapter=PLAN_CHAPTER,
        book=make_book(),
    )
    redo_view = dict(view, redo_started_at="2026-11-12 10:01:00")
    result = run_interaction(
        source, "confirm", initialView=view, confirm=True,
        redoView=redo_view, withOpenNovel=True)
    assert result["calls"] == {"get": 1, "note": 0, "redo": 1}
    assert len(result["confirmCalls"]) == 1
    settled = observation(result, "settled")
    assert "已发起重新定稿" in settled["text"]
    assert "带着这些要求重新定稿" not in [item["text"] for item in settled["buttons"]]


def test_feedback_card_note_success_then_redo_click_confirms_once():
    require_node_dependencies()
    _require_feedback()
    source = read(COMPONENT)
    view = interaction_view()
    note_view = dict(view, note=make_note(status="pending"))
    result = run_interaction(
        source, "note-then-redo", initialView=view, note="immediate",
        noteView=note_view, retryView=note_view, withOpenNovel=True)
    assert result["calls"] == {"get": 1, "note": 1, "redo": 0}
    assert len(result["confirmCalls"]) == 1
    after_note = observation(result, "after-note")
    assert "待下发" in after_note["text"]
    confirming = observation(result, "confirming")
    assert button_state(confirming, "带着这些要求重新定稿")["disabled"] is True
    after = observation(result, "after-confirm")
    assert button_state(after, "带着这些要求重新定稿")["disabled"] is False


def test_feedback_card_action_error_alerts_and_refetches_once():
    require_node_dependencies()
    _require_feedback()
    source = read(COMPONENT)
    view = interaction_view()
    result = run_interaction(
        source, "note-error", initialView=view, note="reject",
        retryView=view, withOpenNovel=True)
    assert result["calls"] == {"get": 1, "note": 1, "redo": 0}
    error = observation(result, "error")
    assert error["alerts"] == ["交留言失败"]
    assert button_state(error, "交给编辑部")["disabled"] is False
    assert result["signals"][1]["kind"] == "get" and result["signals"][1]["has"] is True


def test_feedback_card_read_states_and_retry():
    require_node_dependencies()
    _require_feedback()
    source = read(COMPONENT)
    view = make_view(next_chapters="以后写慢一点", book=make_book(status="running"))

    missing = run_interaction(
        source, "read", getRejects="api404", retryView=view)
    assert missing["calls"]["get"] == 1
    first = observation(missing, "first")
    assert first["text"] == "修改意见已不存在"
    assert first["buttons"] == []
    assert "你的账号暂未开通小说工坊" not in first["text"]
    assert "修改意见暂时读不到" not in first["text"]

    forbidden = run_interaction(
        source, "read", getRejects="api403", retryView=view)
    assert forbidden["calls"]["get"] == 2
    first = observation(forbidden, "first")
    assert first["text"] == forbidden["errorMessage403"] + "重新读取"
    assert forbidden["errorMessage403"] == "你的账号暂未开通小说工坊"
    assert "修改意见已不存在" not in first["text"]
    assert "修改意见暂时读不到" not in first["text"]
    assert "重新读取" in [item["text"] for item in first["buttons"]]
    second = observation(forbidden, "second")
    assert "修改意见 · 《长夜》" in second["text"]
    assert "重新读取" not in second["text"]

    broken = run_interaction(
        source, "read", getRejects="error", retryView=view)
    assert broken["calls"]["get"] == 2
    first = observation(broken, "first")
    assert first["text"] == "修改意见暂时读不到重新读取"
    assert "修改意见已不存在" not in first["text"]
    assert broken["errorMessage403"] not in first["text"]
    assert "重新读取" in [item["text"] for item in first["buttons"]]


def test_feedback_card_note_error_then_success_clears_alert():
    require_node_dependencies()
    _require_feedback()
    source = read(COMPONENT)
    view = interaction_view()
    note_view = dict(view, note=make_note(status="pending"))
    result = run_interaction(
        source, "note-retry", initialView=view, note="reject-then-success",
        noteView=note_view, withOpenNovel=True)
    assert result["calls"] == {"get": 1, "note": 2, "redo": 0}
    error = observation(result, "error")
    assert error["alerts"] == ["交留言失败"]
    recovered = observation(result, "recovered")
    assert recovered["alerts"] == []
    assert "待下发" in recovered["text"]


def test_feedback_card_redo_error_alerts_and_refetches_once():
    require_node_dependencies()
    _require_feedback()
    source = read(COMPONENT)
    view = interaction_view()
    result = run_interaction(
        source, "confirm-error", initialView=view, confirm=True,
        redo="reject", retryView=view, withOpenNovel=True)
    assert result["calls"] == {"get": 2, "note": 0, "redo": 1}
    assert len(result["confirmCalls"]) == 1
    error = observation(result, "error")
    assert error["alerts"] == ["重新定稿失败"]
    assert button_state(error, "带着这些要求重新定稿")["disabled"] is False
    assert [item["kind"] for item in result["signals"]] == ["get", "redo", "get"]
    assert result["signals"][0]["has"] is True
    assert result["signals"][2]["has"] is True


def test_feedback_card_unmount_aborts_pending_post_without_refetch_or_alert():
    require_node_dependencies()
    _require_feedback()
    source = read(COMPONENT)
    view = interaction_view()
    result = run_interaction(
        source, "unmount", initialView=view, note="deferred", withOpenNovel=True)
    assert result["calls"] == {"get": 0, "note": 1, "redo": 0}
    assert result["signals"][0]["kind"] == "note"
    assert result["signals"][0]["has"] is True
    assert result["signals"][0]["aborted"] is True
    # F6：不再读卸载前冻结的 lastTree 断言「没有 alert」（那条恒真），
    # 改由迷你运行时统计 unmount() 之后任何 state setter 的调用次数。
    assert_no_setters_after_unmount(result)


def test_feedback_card_own_model_fee_copy_self_check():
    require_node_dependencies()
    _require_feedback()
    source = read(COMPONENT)
    marker = '"这本书的主编用的是你自己的模型，重新定稿不扣草莓，但会用掉你自己的模型额度。"'
    assert source.count(marker) == 1
    bad = source.replace(marker, f'"{FEE["strawberries"]}"', 1)
    assert bad != source
    view = make_view(
        current_plan="把这一章收紧",
        plan_chapter=PLAN_CHAPTER,
        book=make_book(redo_cost="own_model"),
    )
    result = run_interaction(
        bad, "confirm", initialView=view, confirm=False, withOpenNovel=True)
    expected_body = (
        "编辑部会拿原来的讨论材料加上这张卡上的要求，重新写一版第 "
        f"{PLAN_CHAPTER} 章细纲（看不到现在这一版，是否照改由编辑部判断）。"
        f"{FEE['own_model']}完成后新细纲仍会停下来等你确认。"
    )
    assert FEE["strawberries"] in result["confirmCalls"][0]["body"]
    with pytest.raises(AssertionError):
        assert result["confirmCalls"][0]["body"] == expected_body


# ────────────────────────── R1：防重入、卸载、P1 重新读取 ──────────────────────────


def expected_confirm_body(chapter, cost):
    return (
        "编辑部会拿原来的讨论材料加上这张卡上的要求，重新写一版第 "
        f"{chapter} 章细纲（看不到现在这一版，是否照改由编辑部判断）。"
        f"{FEE[cost]}完成后新细纲仍会停下来等你确认。"
    )


def assert_confirm_options(result, chapter, cost):
    assert result["confirmCalls"] == [{
        "title": f"重新定稿第 {chapter} 章细纲",
        "body": expected_confirm_body(chapter, cost),
        "confirmLabel": "重新定稿",
    }]


def assert_double_click_note_once(result):
    assert result["calls"] == {"get": 0, "note": 1, "redo": 0}
    assert "待下发" in observation(result, "done")["text"]


def test_feedback_card_double_click_note_sends_once():
    require_node_dependencies()
    _require_feedback()
    source = read(COMPONENT)
    view = interaction_view()
    note_view = dict(view, note=make_note(status="pending"))
    result = run_interaction(
        source, "double-note", initialView=view, note="immediate",
        noteView=note_view, withOpenNovel=True)
    assert_double_click_note_once(result)


def test_feedback_card_double_click_note_self_check():
    require_node_dependencies()
    _require_feedback()
    source = read(COMPONENT)
    view = interaction_view()
    note_view = dict(view, note=make_note(status="pending"))
    config = dict(
        initialView=view, note="immediate", noteView=note_view,
        withOpenNovel=True)
    assert_double_click_note_once(
        run_interaction(source, "double-note", **config))

    marker = (
        "  const sendNote = async () => {\n"
        "    if (busyRef.current) return;"
    )
    assert source.count(marker) == 1
    bad = source.replace(marker, "  const sendNote = async () => {", 1)
    assert bad != source
    with pytest.raises(AssertionError) as error:
        assert_double_click_note_once(
            run_interaction(bad, "double-note", **config))
    print(f"F4 note bad copy: {error.value}")


def assert_double_click_redo_once(result):
    assert result["calls"] == {"get": 1, "note": 0, "redo": 1}
    assert len(result["confirmCalls"]) == 1
    assert result["order"].count("get") == 1
    assert result["order"].count("confirm") == 1
    assert result["order"].count("redo") == 1


def test_feedback_card_double_click_redo_reads_confirms_and_posts_once():
    require_node_dependencies()
    _require_feedback()
    source = read(COMPONENT)
    view = interaction_view()
    reread_view = interaction_view()
    result = run_interaction(
        source, "double-redo", initialView=view, clickView=reread_view,
        confirm=True, redoView=dict(reread_view, redo_started_at="2026-11-12 10:01:00"),
        withOpenNovel=True)
    assert_double_click_redo_once(result)
    assert_confirm_options(result, PLAN_CHAPTER, "strawberries")
    settled = observation(result, "settled")
    assert "已发起重新定稿" in settled["text"]


def test_feedback_card_double_click_redo_self_check():
    require_node_dependencies()
    _require_feedback()
    source = read(COMPONENT)
    view = interaction_view()
    reread_view = interaction_view()
    config = dict(
        initialView=view, clickView=reread_view, confirm=True,
        redoView=dict(reread_view, redo_started_at="2026-11-12 10:01:00"),
        withOpenNovel=True)
    assert_double_click_redo_once(
        run_interaction(source, "double-redo", **config))

    marker = (
        "  const sendRedo = async () => {\n"
        "    if (busyRef.current) return;"
    )
    assert source.count(marker) == 1
    bad = source.replace(marker, "  const sendRedo = async () => {", 1)
    assert bad != source
    with pytest.raises(AssertionError) as error:
        assert_double_click_redo_once(
            run_interaction(bad, "double-redo", **config))
    print(f"F4 redo bad copy: {error.value}")


def assert_unmount_reread_skips_confirm_and_redo(result):
    assert result["calls"] == {"get": 1, "note": 0, "redo": 0}
    assert result["confirmCalls"] == []
    assert_no_setters_after_unmount(result)


def test_feedback_card_unmount_before_reread_resolves_skips_confirm_and_redo():
    require_node_dependencies()
    _require_feedback()
    source = read(COMPONENT)
    view = interaction_view()
    result = run_interaction(
        source, "unmount-reread", initialView=view, clickGet="deferred",
        clickView=interaction_view(), withOpenNovel=True)
    assert_unmount_reread_skips_confirm_and_redo(result)


def test_feedback_card_unmount_reread_self_check():
    require_node_dependencies()
    _require_feedback()
    source = read(COMPONENT)
    view = interaction_view()
    config = dict(
        initialView=view, clickGet="deferred", clickView=interaction_view(),
        withOpenNovel=True)
    assert_unmount_reread_skips_confirm_and_redo(
        run_interaction(source, "unmount-reread", **config))

    marker = (
        "    if (signal?.aborted) return;\n"
        "    setResult({ kind: \"ready\", feedbackId, attempt, view: refreshed });"
    )
    assert source.count(marker) == 1
    bad = source.replace(
        marker,
        "    setResult({ kind: \"ready\", feedbackId, attempt, view: refreshed });",
        1,
    )
    assert bad != source
    with pytest.raises(AssertionError) as error:
        assert_unmount_reread_skips_confirm_and_redo(
            run_interaction(bad, "unmount-reread", **config))
    print(f"F5 reread bad copy: {error.value}")


def assert_unmount_confirm_skips_post(result):
    assert result["calls"] == {"get": 1, "note": 0, "redo": 0}
    assert len(result["confirmCalls"]) == 1
    assert_no_setters_after_unmount(result)


def test_feedback_card_unmount_during_confirm_skips_post():
    require_node_dependencies()
    _require_feedback()
    source = read(COMPONENT)
    view = interaction_view()
    result = run_interaction(
        source, "unmount-confirm", initialView=view,
        clickView=interaction_view(), withOpenNovel=True)
    assert_unmount_confirm_skips_post(result)


def test_feedback_card_unmount_confirm_self_check():
    require_node_dependencies()
    _require_feedback()
    source = read(COMPONENT)
    view = interaction_view()
    config = dict(
        initialView=view, clickView=interaction_view(), withOpenNovel=True)
    assert_unmount_confirm_skips_post(
        run_interaction(source, "unmount-confirm", **config))

    marker = (
        "    if (signal?.aborted) return;\n"
        "    if (!confirmed) {"
    )
    assert source.count(marker) == 1
    bad = source.replace(marker, "    if (!confirmed) {", 1)
    assert bad != source
    with pytest.raises(AssertionError) as error:
        assert_unmount_confirm_skips_post(
            run_interaction(bad, "unmount-confirm", **config))
    print(f"F5 confirm bad copy: {error.value}")


def assert_unmount_note_success_leaves_no_setters(result):
    assert result["calls"] == {"get": 0, "note": 1, "redo": 0}
    assert_no_setters_after_unmount(result)


def test_feedback_card_unmount_state_setter_count_self_check():
    require_node_dependencies()
    _require_feedback()
    source = read(COMPONENT)
    view = interaction_view()
    note_view = dict(view, note=make_note(status="pending"))
    config = dict(
        initialView=view, note="deferred-no-abort", noteView=note_view,
        withOpenNovel=True)
    assert_unmount_note_success_leaves_no_setters(
        run_interaction(source, "unmount-note-resolve", **config))

    marker = (
        "      const next = await sendNovelFeedbackNote(feedbackId, signal);\n"
        "      if (signal?.aborted) return;"
    )
    assert source.count(marker) == 1
    bad = source.replace(
        marker,
        "      const next = await sendNovelFeedbackNote(feedbackId, signal);",
        1,
    )
    assert bad != source
    bad_result = run_interaction(bad, "unmount-note-resolve", **config)
    assert bad_result["settersAfterUnmount"] > 0
    with pytest.raises(AssertionError) as error:
        assert_unmount_note_success_leaves_no_setters(bad_result)
    print(f"F6 note-resolve bad copy: {error.value}")


def assert_redo_reread_latest_cost(result):
    assert result["calls"] == {"get": 1, "note": 0, "redo": 1}
    assert_confirm_options(result, PLAN_CHAPTER, "strawberries")
    reread = observation(result, "reread")
    assert plan_action_description("strawberries") in reread["text"]
    assert plan_action_description("own_model") not in reread["text"]
    assert FEE["own_model"] not in result["confirmCalls"][0]["body"]
    assert "已发起重新定稿" in observation(result, "settled")["text"]


def test_feedback_card_redo_reread_uses_latest_cost_and_updates_card():
    require_node_dependencies()
    _require_feedback()
    source = read(COMPONENT)
    view = interaction_view(book=make_book(redo_cost="own_model"))
    reread_view = interaction_view()
    result = run_interaction(
        source, "redo-reread", initialView=view, clickView=reread_view,
        confirm=True,
        redoView=dict(reread_view, redo_started_at="2026-11-12 10:01:00"),
        withOpenNovel=True)
    assert_redo_reread_latest_cost(result)


def redo_started_view():
    """F7(c)/G1：重新读取视图只比卡片原视图多一个 redo_started_at。"""
    return interaction_view(
        redo_started_at="2026-11-12 10:01:00",
        book=make_book(redo_pending=False, awaiting_chapter=PLAN_CHAPTER),
    )


def assert_redo_reread_unavailable(result, *, note_clicked=False):
    reread = observation(result, "reread")
    assert button_state(reread, "交给编辑部")["disabled"] is False
    assert reread["calls"] == {"get": 1, "note": 0, "redo": 0}
    assert result["calls"] == {"get": 1, "note": 1 if note_clicked else 0, "redo": 0}
    assert result["confirmCalls"] == []
    assert PLAN_NOT_AWAITING in reread["paragraphs"]
    assert "带着这些要求重新定稿" not in [item["text"] for item in reread["buttons"]]
    assert "去书斋改细纲" not in [item["text"] for item in reread["buttons"]]
    if note_clicked:
        assert "待下发" in observation(result, "after-note")["text"]


def test_feedback_card_redo_reread_unavailable_updates_card_without_dialog():
    require_node_dependencies()
    _require_feedback()
    source = read(COMPONENT)
    view = interaction_view()
    # G2：重新读取只改书的状态，卡上文字（next_chapters）仍是点击前那一份。
    reread_view = interaction_view(
        book=make_book(awaiting_chapter=3, plan_row_status="done"),
    )
    assert reread_view["next_chapters"] == view["next_chapters"]
    assert reread_view["next_chapters"] == "以后写慢一点"
    note_view = dict(reread_view, note=make_note(status="pending"))
    result = run_interaction(
        source, "redo-reread", initialView=view, clickView=reread_view,
        afterRereadNote=True, note="immediate", noteView=note_view,
        withOpenNovel=True)
    assert_redo_reread_unavailable(result, note_clicked=True)


def assert_redo_reread_started(result, *, note_clicked=False):
    assert result["calls"] == {"get": 1, "note": 1 if note_clicked else 0, "redo": 0}
    assert result["confirmCalls"] == []
    reread = observation(result, "reread")
    assert reread["calls"] == {"get": 1, "note": 0, "redo": 0}
    assert "已发起重新定稿" in reread["text"]
    # G1：书仍 awaiting_plan、逐章确认、等确认的正是卡上这一章，
    # 重新读取视图只多一个 redo_started_at，所以说明含「新细纲在书斋里等你确认。」。
    assert PLAN_DONE_AWAITING in reread["paragraphs"]
    assert reread["text"].count(PLAN_DONE) == 1
    assert "带着这些要求重新定稿" not in [item["text"] for item in reread["buttons"]]
    assert button_state(reread, "交给编辑部")["disabled"] is False
    if note_clicked:
        assert "待下发" in observation(result, "after-note")["text"]


def test_feedback_card_redo_reread_already_started_updates_card_without_dialog():
    require_node_dependencies()
    _require_feedback()
    source = read(COMPONENT)
    view = interaction_view()
    reread_view = redo_started_view()
    # G1：重新读取视图只比卡片原视图多一个 redo_started_at。
    assert reread_view == dict(view, redo_started_at="2026-11-12 10:01:00")
    note_view = dict(reread_view, note=make_note(status="pending"))
    result = run_interaction(
        source, "redo-reread", initialView=view, clickView=reread_view,
        afterRereadNote=True, note="immediate", noteView=note_view,
        withOpenNovel=True)
    assert_redo_reread_started(result, note_clicked=True)


def assert_redo_reread_failure(result, expected, *, second_click):
    assert result["confirmCalls"] == []
    initial = observation(result, "initial")
    reread = observation(result, "reread")
    assert reread["calls"] == {"get": 1, "note": 0, "redo": 0}
    assert reread["alerts"] == [expected]
    # 卡片其余内容保持点击前的样子，错误只在第一节末尾追加。
    assert reread["text"].replace(expected, "", 1) == initial["text"]
    assert reread["text"].index("去书斋改细纲") < reread["text"].index(expected)
    assert reread["text"].index(expected) < reread["text"].index("以后的章节")
    assert button_state(reread, "带着这些要求重新定稿")["disabled"] is False
    if second_click:
        assert result["calls"] == {"get": 2, "note": 0, "redo": 0}
        assert [item["kind"] for item in result["signals"]] == ["get", "get"]


@pytest.mark.parametrize("kind,message", [
    ("api500", None),
    ("type", "网络错误"),
    ("type", "Failed to fetch"),
])
def test_feedback_card_redo_reread_failure_keeps_view_and_alerts(kind, message):
    require_node_dependencies()
    _require_feedback()
    source = read(COMPONENT)
    view = interaction_view()
    config = dict(
        initialView=view, clickGet=kind, afterRereadRedo=True,
        withOpenNovel=True)
    if message is not None:
        config["clickErrorMessage"] = message
    result = run_interaction(source, "redo-reread", **config)
    if kind == "api500":
        expected = result["errorMessage500"]
    else:
        expected = result["errorMessageType"]
    if message == "Failed to fetch":
        # G4：novelErrorMessage 对不含汉字的报错统一返回这句。
        assert expected == "请求未完成，请稍后重试。"
    assert_redo_reread_failure(result, expected, second_click=True)


def test_feedback_card_redo_reread_busy_state_and_order():
    require_node_dependencies()
    _require_feedback()
    source = read(COMPONENT)
    view = interaction_view()
    reread_view = interaction_view()
    result = run_interaction(
        source, "redo-reread", initialView=view, clickGet="deferred",
        clickView=reread_view, confirm=False, withOpenNovel=True)
    rereading = observation(result, "rereading")
    button = button_state(rereading, "带着这些要求重新定稿")
    assert button["disabled"] is True
    assert button["text"] == "带着这些要求重新定稿"
    assert button_state(rereading, "交给编辑部")["disabled"] is True
    assert rereading["order"] == ["get"]

    reread = observation(result, "reread")
    assert button_state(reread, "带着这些要求重新定稿")["disabled"] is True
    assert reread["order"] == ["get", "confirm"]

    assert result["calls"] == {"get": 1, "note": 0, "redo": 0}
    assert result["confirmCalls"][0]["body"] == expected_confirm_body(
        PLAN_CHAPTER, "strawberries")


def redo_reread_scenario(source, initial_view, reread_view, **config):
    return run_interaction(
        source, "redo-reread", initialView=initial_view,
        clickView=reread_view, withOpenNovel=True, **config)


def test_feedback_card_redo_reread_self_check_catches_stale_view():
    require_node_dependencies()
    _require_feedback()
    source = read(COMPONENT)
    view = interaction_view(book=make_book(redo_cost="own_model"))
    reread_view = interaction_view()
    good = redo_reread_scenario(
        source, view, reread_view, confirm=True,
        redoView=dict(reread_view, redo_started_at="2026-11-12 10:01:00"))
    assert_redo_reread_latest_cost(good)

    unavailable_view = interaction_view(
        book=make_book(awaiting_chapter=3, plan_row_status="done"),
    )
    assert_redo_reread_unavailable(
        redo_reread_scenario(source, interaction_view(), unavailable_view))

    started_view = redo_started_view()
    assert_redo_reread_started(
        redo_reread_scenario(source, interaction_view(), started_view))

    marker = "      refreshed = await getNovelFeedback(feedbackId, signal);"
    assert source.count(marker) == 1
    bad = source.replace(marker, "      refreshed = view;", 1)
    assert bad != source

    with pytest.raises(AssertionError) as error:
        assert_redo_reread_latest_cost(redo_reread_scenario(
            bad, view, reread_view, confirm=True,
            redoView=dict(reread_view, redo_started_at="2026-11-12 10:01:00")))
    print(f"F7 stale-view fee bad copy: {error.value}")

    with pytest.raises(AssertionError) as error:
        assert_redo_reread_unavailable(
            redo_reread_scenario(bad, interaction_view(), unavailable_view))
    print(f"F7 stale-view unavailable bad copy: {error.value}")

    with pytest.raises(AssertionError) as error:
        assert_redo_reread_started(
            redo_reread_scenario(bad, interaction_view(), started_view))
    print(f"F7 stale-view started bad copy: {error.value}")


def test_feedback_card_redo_reread_self_check_catches_old_fee_sentence():
    require_node_dependencies()
    _require_feedback()
    source = read(COMPONENT)
    view = interaction_view(book=make_book(redo_cost="own_model"))
    reread_view = interaction_view()
    config = dict(
        confirm=True,
        redoView=dict(reread_view, redo_started_at="2026-11-12 10:01:00"))
    assert_redo_reread_latest_cost(
        redo_reread_scenario(source, view, reread_view, **config))

    marker = "redoCostSentence(refreshed.book?.redo_cost)"
    assert source.count(marker) == 1
    bad = source.replace(
        marker, "redoCostSentence(view.book?.redo_cost)", 1)
    assert bad != source
    with pytest.raises(AssertionError) as error:
        assert_redo_reread_latest_cost(
            redo_reread_scenario(bad, view, reread_view, **config))
    print(f"F7 old-fee bad copy: {error.value}")


def test_feedback_card_redo_reread_self_check_catches_skipping_availability():
    require_node_dependencies()
    _require_feedback()
    source = read(COMPONENT)
    unavailable_view = interaction_view(
        book=make_book(awaiting_chapter=3, plan_row_status="done"),
    )
    started_view = redo_started_view()
    assert_redo_reread_unavailable(
        redo_reread_scenario(source, interaction_view(), unavailable_view))
    assert_redo_reread_started(
        redo_reread_scenario(source, interaction_view(), started_view))

    marker = "if (!redoAvailable(refreshed) || chapter === null) {"
    assert source.count(marker) == 1
    bad = source.replace(marker, "if (chapter === null) {", 1)
    assert bad != source
    with pytest.raises(AssertionError) as error:
        assert_redo_reread_unavailable(
            redo_reread_scenario(bad, interaction_view(), unavailable_view))
    print(f"F7 skipped-availability unavailable bad copy: {error.value}")
    with pytest.raises(AssertionError) as error:
        assert_redo_reread_started(
            redo_reread_scenario(bad, interaction_view(), started_view))
    print(f"F7 skipped-availability started bad copy: {error.value}")


# ────────────────────────── R2：G1–G5 ──────────────────────────


def test_feedback_card_redo_reread_started_self_check_catches_missing_flag():
    """G1：删掉 redoAvailable 的 !view.redo_started_at 时，F7(c) 必须变红。"""
    require_node_dependencies()
    _require_feedback()
    source = read(COMPONENT)
    started_view = redo_started_view()
    assert_redo_reread_started(
        redo_reread_scenario(source, interaction_view(), started_view))

    marker = "    && !view.redo_started_at\n"
    assert source.count(marker) == 1
    bad = source.replace(marker, "", 1)
    assert bad != source
    with pytest.raises(AssertionError) as error:
        assert_redo_reread_started(
            redo_reread_scenario(bad, interaction_view(), started_view))
    print(f"G1 missing redo_started guard bad copy: {error.value}")


def assert_redo_cancel_then_reclick(result):
    assert result["calls"] == {"get": 2, "note": 0, "redo": 0}
    assert len(result["confirmCalls"]) == 2
    settled = observation(result, "settled")
    assert button_state(settled, "带着这些要求重新定稿")["disabled"] is False
    second = observation(result, "second-confirming")
    assert button_state(second, "带着这些要求重新定稿")["disabled"] is True


def test_feedback_card_early_exit_resets_busy_self_check():
    """G2：提前结束的三条路径都要复位 busy 与 busyRef，不能只看 disabled。"""
    require_node_dependencies()
    _require_feedback()
    source = read(COMPONENT)

    unavailable_view = interaction_view(
        book=make_book(awaiting_chapter=3, plan_row_status="done"),
    )
    note_view = dict(unavailable_view, note=make_note(status="pending"))
    note_config = dict(
        initialView=interaction_view(), clickView=unavailable_view,
        afterRereadNote=True, note="immediate", noteView=note_view,
        withOpenNovel=True)
    assert_redo_reread_unavailable(
        run_interaction(source, "redo-reread", **note_config),
        note_clicked=True)

    both_marker = (
        "    if (!redoAvailable(refreshed) || chapter === null) {\n"
        "      busyRef.current = false;\n"
        "      setBusy(null);\n"
        "      return;\n"
        "    }"
    )
    assert source.count(both_marker) == 1
    bad_both = source.replace(
        both_marker,
        "    if (!redoAvailable(refreshed) || chapter === null) {\n"
        "      return;\n"
        "    }",
        1,
    )
    assert bad_both != source
    with pytest.raises(AssertionError) as error:
        assert_redo_reread_unavailable(
            run_interaction(bad_both, "redo-reread", **note_config),
            note_clicked=True)
    print(f"G2 unavailable both-reset bad copy: {error.value}")

    only_busy_marker = (
        "    if (!redoAvailable(refreshed) || chapter === null) {\n"
        "      busyRef.current = false;\n"
    )
    assert source.count(only_busy_marker) == 1
    bad_only_busy = source.replace(
        only_busy_marker,
        "    if (!redoAvailable(refreshed) || chapter === null) {\n",
        1,
    )
    assert bad_only_busy != source
    with pytest.raises(AssertionError) as error:
        assert_redo_reread_unavailable(
            run_interaction(bad_only_busy, "redo-reread", **note_config),
            note_clicked=True)
    print(f"G2 unavailable busyRef-only bad copy: {error.value}")

    failure_config = dict(
        initialView=interaction_view(), clickGet="api500",
        clickErrorMessage="服务器错误", afterRereadRedo=True,
        withOpenNovel=True)
    assert_redo_reread_failure(
        run_interaction(source, "redo-reread", **failure_config),
        "服务器错误", second_click=True)

    failure_marker = (
        "      setActionError({ section: \"plan\", message: novelErrorMessage(error) });\n"
        "      busyRef.current = false;\n"
        "      setBusy(null);\n"
        "      return;\n"
        "    }\n"
        "    if (signal?.aborted) return;"
    )
    assert source.count(failure_marker) == 1
    bad_failure = source.replace(
        failure_marker,
        "      setActionError({ section: \"plan\", message: novelErrorMessage(error) });\n"
        "      setBusy(null);\n"
        "      return;\n"
        "    }\n"
        "    if (signal?.aborted) return;",
        1,
    )
    assert bad_failure != source
    with pytest.raises(AssertionError) as error:
        assert_redo_reread_failure(
            run_interaction(bad_failure, "redo-reread", **failure_config),
            "服务器错误", second_click=True)
    print(f"G2 reread-failure busyRef-only bad copy: {error.value}")

    cancel_config = dict(
        initialView=interaction_view(), clickView=interaction_view(),
        confirm=False, afterCancelRedo=True, withOpenNovel=True)
    assert_redo_cancel_then_reclick(
        run_interaction(source, "redo-reread", **cancel_config))

    cancel_marker = (
        "    if (!confirmed) {\n"
        "      busyRef.current = false;\n"
        "      setBusy(null);\n"
        "      return;\n"
        "    }"
    )
    assert source.count(cancel_marker) == 1
    bad_cancel = source.replace(
        cancel_marker,
        "    if (!confirmed) {\n"
        "      setBusy(null);\n"
        "      return;\n"
        "    }",
        1,
    )
    assert bad_cancel != source
    with pytest.raises(AssertionError) as error:
        assert_redo_cancel_then_reclick(
            run_interaction(bad_cancel, "redo-reread", **cancel_config))
    print(f"G2 confirm-cancel busyRef-only bad copy: {error.value}")


def assert_unmount_during_reread_abort(result):
    assert result["calls"] == {"get": 1, "note": 0, "redo": 0}
    assert result["confirmCalls"] == []
    assert_no_setters_after_unmount(result)
    get_signals = [item for item in result["signals"] if item["kind"] == "get"]
    assert len(get_signals) == 1, result["signals"]
    assert get_signals[0]["has"] is True
    assert get_signals[0]["aborted"] is True


def test_feedback_card_unmount_during_reread_aborts_and_skips_setters():
    """G3：重新读取途中卸载，桩在 abort 时 reject，不能再弹框或发请求。"""
    require_node_dependencies()
    _require_feedback()
    source = read(COMPONENT)
    result = run_interaction(
        source, "unmount-reread", initialView=interaction_view(),
        clickGet="deferred-abort", clickView=interaction_view(),
        withOpenNovel=True)
    assert_unmount_during_reread_abort(result)


def test_feedback_card_unmount_reread_abort_self_check():
    require_node_dependencies()
    _require_feedback()
    source = read(COMPONENT)
    config = dict(
        initialView=interaction_view(), clickGet="deferred-abort",
        clickView=interaction_view(), withOpenNovel=True)
    assert_unmount_during_reread_abort(
        run_interaction(source, "unmount-reread", **config))

    marker = (
        "    } catch (error) {\n"
        "      if (signal?.aborted) return;\n"
        "      setActionError({ section: \"plan\", message: novelErrorMessage(error) });\n"
        "      busyRef.current = false;"
    )
    assert source.count(marker) == 1
    bad = source.replace(
        marker,
        "    } catch (error) {\n"
        "      setActionError({ section: \"plan\", message: novelErrorMessage(error) });\n"
        "      busyRef.current = false;",
        1,
    )
    assert bad != source
    bad_result = run_interaction(bad, "unmount-reread", **config)
    assert bad_result["settersAfterUnmount"] > 0
    with pytest.raises(AssertionError) as error:
        assert_unmount_during_reread_abort(bad_result)
    print(f"G3 reread abort guard bad copy: {error.value}")


def test_feedback_card_redo_reread_error_message_self_check():
    """G4：非 ApiError 且报错不含汉字时必须显示 novelErrorMessage 的固定文案。"""
    require_node_dependencies()
    _require_feedback()
    source = read(COMPONENT)
    config = dict(
        initialView=interaction_view(), clickGet="type",
        clickErrorMessage="Failed to fetch", withOpenNovel=True)
    result = run_interaction(source, "redo-reread", **config)
    assert result["errorMessageType"] == "请求未完成，请稍后重试。"
    assert observation(result, "reread")["alerts"] == ["请求未完成，请稍后重试。"]
    assert_redo_reread_failure(
        result, "请求未完成，请稍后重试。", second_click=False)

    marker = (
        "      setActionError({ section: \"plan\", message: novelErrorMessage(error) });\n"
        "      busyRef.current = false;\n"
        "      setBusy(null);\n"
        "      return;\n"
    )
    assert source.count(marker) == 1
    bad = source.replace(
        marker,
        "      setActionError({ section: \"plan\", message: error instanceof Error "
        "? error.message : \"修改意见暂时读不到\" });\n"
        "      busyRef.current = false;\n"
        "      setBusy(null);\n"
        "      return;\n",
        1,
    )
    assert bad != source
    with pytest.raises(AssertionError) as error:
        assert_redo_reread_failure(
            run_interaction(bad, "redo-reread", **config),
            "请求未完成，请稍后重试。", second_click=False)
    print(f"G4 reread error message bad copy: {error.value}")


# ────────────────────────── 请求路径 ──────────────────────────

NODE_PATHS = r"""
const ts = require('typescript');
const source = process.argv[1];
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText;
const calls = [];
const apiJson = (url, init) => { calls.push({ url, init }); return Promise.resolve({}); };
const moduleObject = { exports: {} };
new Function('exports', 'require', 'module', compiled)(moduleObject.exports, spec => {
  if (spec === '@/lib/agents') return { apiJson };
  if (spec === '@/lib/config') return { API_BASE: '/api' };
  throw new Error('unexpected import ' + spec);
}, moduleObject);
const signal = { name: 'signal' };
(async () => {
  await moduleObject.exports.getNovelFeedback('a/b', signal);
  await moduleObject.exports.sendNovelFeedbackNote('a/b', signal);
  await moduleObject.exports.redoNovelFeedbackPlan('a/b', signal);
  console.log(JSON.stringify(calls.map(call => ({
    url: call.url,
    method: call.init && call.init.method !== undefined ? call.init.method : null,
    hasSignal: !!(call.init && call.init.signal === signal),
  }))));
})();
"""

EXPECTED_PATHS = [
    {"url": "/api/novels/feedback/a%2Fb", "method": None, "hasSignal": True},
    {"url": "/api/novels/feedback/a%2Fb/note", "method": "POST", "hasSignal": True},
    {"url": "/api/novels/feedback/a%2Fb/redo", "method": "POST", "hasSignal": True},
]


def run_request_paths(source):
    _require_feedback()
    result = subprocess.run(
        ["node", "-e", NODE_PATHS, source], cwd=FRONTEND,
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        pytest.fail(f"node request path probe failed:\n{result.stderr}")
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert lines, result.stdout
    return json.loads(lines[-1])


def test_novel_feedback_request_paths_and_signal_passthrough():
    require_node_dependencies()
    _require_feedback()
    calls = run_request_paths(read(FEEDBACK_LIB))
    assert calls == EXPECTED_PATHS


def test_novel_feedback_request_path_self_check_catches_plan_redo():
    require_node_dependencies()
    _require_feedback()
    source = read(FEEDBACK_LIB)
    assert '"/redo"' in source
    bad = source.replace('"/redo"', '"/plan/redo"', 1)
    assert bad != source
    calls = run_request_paths(bad)
    with pytest.raises(AssertionError):
        assert calls == EXPECTED_PATHS
