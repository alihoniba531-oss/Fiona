"""讨论群聊天卡片前端契约：字段拷贝、抽屉跳转、刷新重建与分发。

静态用例直接读源码，不依赖 node 或前端依赖；两条在 Node 里转译执行真实
源码的用例照 test_novel_chat_create_frontend.py 的守卫，缺 node 或
frontend/node_modules 时在起 Node 之前整组 skip。两个卡片组件由别的任务
落盘，这里只锁 ChatBubble 的分发源码，不读组件实现。
"""
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from test_claude_agent_frontend import block_after


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
PAGE = FRONTEND / "app/page.tsx"
BUBBLE = FRONTEND / "components/ChatBubble.tsx"
CONVERSATIONS = FRONTEND / "lib/useConversations.ts"
DEPENDENCIES = {
    "typescript": "typescript/lib/typescript.js",
    "react": "react/index.js",
    "react-dom/server": "react-dom/server.js",
}
BOM = b"\xef\xbb\xbf"
TAIL_SHA256 = "e0718e4916e73ad0b697656069e77abaff73b6473c6a5dbe0af97c892c42b0ce"
TASK_UUID = "12345678-1234-1234-1234-123456789abc"
GROUP_HEX = "12345678123412341234123456789abc"
VALID_TASK_PATH = f"/discuss/new?embed=1&task={TASK_UUID}"
VALID_GROUP_PATH = f"/discuss/{GROUP_HEX}?embed=1"
INVALID_PATHS = [
    f"/discuss/new?task={TASK_UUID}",
    f"/discuss/new?embed=1&task={TASK_UUID[:-2]}",
    f"/discuss/new?embed=1&task={TASK_UUID}0",
    f"/discuss/{TASK_UUID}?embed=1",
    f"{VALID_TASK_PATH}&x=1",
    f"{VALID_GROUP_PATH}&x=1",
    "javascript:alert(1)",
    f"https://example.com{VALID_GROUP_PATH}",
    f"//example.com{VALID_GROUP_PATH}",
    f"/discuss/{GROUP_HEX.upper()}?embed=1",
]


def require_node_dependencies():
    missing = [name for name, entry in DEPENDENCIES.items()
               if not (FRONTEND / "node_modules" / entry).is_file()]
    if missing:
        pytest.skip("frontend dependencies unavailable: " + ", ".join(missing))
    if not shutil.which("node"):
        pytest.skip("node is unavailable")


def read(path):
    return path.read_text(encoding="utf-8")


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
        assert block.count("task_id: data.card.task_id,") == 1, block
        assert block.count("note_id: data.card.note_id,") == 1, block
    assert source.count("task_id: data.card.task_id,") == 2
    assert source.count("note_id: data.card.note_id,") == 2
    assert PAGE.read_bytes()[:3] == BOM, "page.tsx 的 UTF-8 BOM 丢失"


def test_page_stream_cards_copy_discuss_ids_in_both_blocks():
    check_page_cards(read(PAGE))
    for field in ("task_id: data.card.task_id,", "note_id: data.card.note_id,"):
        bad = read(PAGE).replace(field, "", 1)
        with pytest.raises(AssertionError):
            check_page_cards(bad)


def test_page_keeps_bom_and_locked_tail_hash():
    raw = PAGE.read_bytes()
    assert raw[:3] == BOM
    source = read(PAGE)
    start = source.index("            // 旅行规划卡：")
    end = source.index("          if (data.done)", start)
    digest = hashlib.sha256(source[start:end].encode()).hexdigest()
    assert digest == TAIL_SHA256
    bad = source.replace("            // 旅行规划卡：", "            // 旅行规划卡: ", 1)
    assert bad != source
    assert hashlib.sha256(bad[start:end].encode()).hexdigest() != TAIL_SHA256
    with pytest.raises(AssertionError):
        assert hashlib.sha256(bad[start:end].encode()).hexdigest() == TAIL_SHA256


# ────────────────────────── openDiscussAt ──────────────────────────

OPEN_DISCUSS_SCRIPT = r"""
const ts = require('typescript');
const compiled = ts.transpileModule(process.argv[1], {
  compilerOptions: {target: ts.ScriptTarget.ES2020},
}).outputText;
const factory = Function(
  'discussAllowed', 'setDrawer', 'discussFrameRef',
  compiled + '\nreturn openDiscussAt;'
);
const cases = JSON.parse(process.argv[2]);
const rows = cases.map(item => {
  let drawer = '', replaced = '';
  const setDrawer = value => { drawer = value; };
  const discussFrameRef = {current: {contentWindow: {location: {
    replace: value => { replaced = value; },
  }}}};
  factory(item.allowed, setDrawer, discussFrameRef)(item.path);
  return {path: item.path, allowed: item.allowed, drawer, replaced};
});
process.stdout.write(JSON.stringify(rows));
"""


def run_open_discuss(source, cases):
    function = block_after(source, "const openDiscussAt = (path: string) =>")
    result = subprocess.run(
        ["node", "-e", OPEN_DISCUSS_SCRIPT, function, json.dumps(cases)],
        cwd=FRONTEND, capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)


def check_open_discuss(rows):
    for row in rows:
        if row["allowed"] and row["path"] in (VALID_TASK_PATH, VALID_GROUP_PATH):
            assert row["drawer"] == "discuss", row
            assert row["replaced"] == row["path"], row
        else:
            assert row["drawer"] == "", row
            assert row["replaced"] == "", row


def test_page_open_discuss_at_accepts_only_two_shapes():
    require_node_dependencies()
    source = read(PAGE)
    assert "const openDiscussAt = (path: string) => {" in source
    assert r"/^\/discuss\/new\?embed=1&task=[0-9a-f-]{36}$/" in source
    assert r"/^\/discuss\/[0-9a-f]{32}\?embed=1$/" in source
    cases = [
        {"allowed": True, "path": VALID_TASK_PATH},
        {"allowed": True, "path": VALID_GROUP_PATH},
        *[{"allowed": True, "path": path} for path in INVALID_PATHS],
        {"allowed": False, "path": VALID_TASK_PATH},
        {"allowed": False, "path": VALID_GROUP_PATH},
    ]
    rows = run_open_discuss(source, cases)
    assert len(rows) == len(cases)
    check_open_discuss(rows)

    # 坏副本：去掉白名单判断后，javascript: 等非法路径会被放行。
    marker = r"if (!/^\/discuss\/new"
    assert source.count(marker) == 1
    start = source.index(marker)
    end = source.index("return;", start) + len("return;")
    bad = source[:start] + "if (false) return;" + source[end:]
    assert bad != source
    bad_rows = run_open_discuss(
        bad, [{"allowed": True, "path": path} for path in INVALID_PATHS]
    )
    with pytest.raises(AssertionError):
        check_open_discuss(bad_rows)


# ────────────────────────── toMessages ──────────────────────────

ALL_DISCUSS_IDS = {
    "song_project_id": "song-1",
    "novel_draft_id": "draft-1",
    "novel_feedback_id": "feedback-1",
    "discuss_task_id": "task-1",
    "discuss_note_id": "note-1",
}
ALL_CARDS = [
    {"source": "写歌", "points": [], "subtype": "song_project", "project_id": "song-1"},
    {"source": "书斋", "points": [], "subtype": "novel_draft", "draft_id": "draft-1"},
    {"source": "书斋", "points": [], "subtype": "novel_feedback", "feedback_id": "feedback-1"},
    {"source": "讨论群", "points": [], "subtype": "discuss_task", "task_id": "task-1"},
    {"source": "讨论群", "points": [], "subtype": "discuss_note", "note_id": "note-1"},
]

TO_MESSAGES_SCRIPT = r"""
const ts = require('typescript');
const compiled = ts.transpileModule(process.argv[1], {
  compilerOptions: {target: ts.ScriptTarget.ES2020},
}).outputText;
const API = '/api';
const storedReferenceImagePaths = () => [];
const toMessages = Function(
  'API', 'storedReferenceImagePaths', compiled + '\nreturn toMessages;'
)(API, storedReferenceImagePaths);
const base = {id: 1, role: 'assistant', content: 'x', image_path: null,
  created_at: '2026-11-02 10:00:00'};
const cases = JSON.parse(process.argv[2]);
const payload = Object.fromEntries(cases.map(item => [
  item.name, toMessages([{...base, ...item.value}])[0].cards ?? null,
]));
process.stdout.write(JSON.stringify(payload));
"""


def run_to_messages(source, cases):
    function = block_after(source, "function toMessages(")
    result = subprocess.run(
        ["node", "-e", TO_MESSAGES_SCRIPT, function, json.dumps(cases)],
        cwd=FRONTEND, capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)


def test_use_conversations_rebuilds_discuss_cards_after_existing_three():
    require_node_dependencies()
    source = read(CONVERSATIONS)
    assert "discuss_task_id?: string | null" in source
    assert "discuss_note_id?: string | null" in source
    assert 'subtype: "discuss_task", task_id: message.discuss_task_id' in source
    assert 'subtype: "discuss_note", note_id: message.discuss_note_id' in source
    cases = [
        {"name": "all", "value": ALL_DISCUSS_IDS},
        {"name": "task_only", "value": {"discuss_task_id": "task-1"}},
        {"name": "note_only", "value": {"discuss_note_id": "note-1"}},
        {"name": "missing", "value": {"song_project_id": "song-1"}},
        {"name": "none", "value": {}},
        {"name": "user_with_ids", "value": {**ALL_DISCUSS_IDS, "role": "user"}},
    ]
    payload = run_to_messages(source, cases)
    assert payload["all"] == ALL_CARDS
    assert payload["task_only"] == [
        {"source": "讨论群", "points": [], "subtype": "discuss_task", "task_id": "task-1"},
    ]
    assert payload["note_only"] == [
        {"source": "讨论群", "points": [], "subtype": "discuss_note", "note_id": "note-1"},
    ]
    assert payload["missing"] == [
        {"source": "写歌", "points": [], "subtype": "song_project", "project_id": "song-1"},
    ]
    assert payload["none"] is None
    assert payload["user_with_ids"] is None

    # 坏副本：禁用任务卡分支后，all 的精确列表必须变红。
    bad = source.replace(
        'if (message.role === "assistant" && message.discuss_task_id)', "if (false)", 1)
    assert bad != source
    bad_payload = run_to_messages(bad, [{"name": "all", "value": ALL_DISCUSS_IDS}])
    with pytest.raises(AssertionError):
        assert bad_payload["all"] == ALL_CARDS


# ────────────────────────── ChatBubble ──────────────────────────

CHAT_CARD_TAG = re.compile(r"<ChatCard\b[^>]*/>")


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


def check_bubble_discuss_wiring(source):
    body = function_block(source, "function ChatBubble(")
    header = body.split(")", 1)[0]
    assert "onOpenDiscuss" in header, "ChatBubble 未解构 onOpenDiscuss"
    tags = CHAT_CARD_TAG.findall(body)
    assert len(tags) == 2, tags
    for tag in tags:
        assert tag.count("onOpenDiscuss={onOpenDiscuss}") == 1, tag
    card = block_after(source, "function ChatCard(")
    for fragment in (
        'if (card.subtype === "discuss_task")',
        "if (!card.task_id) return null;",
        "<DiscussTaskCard taskId={card.task_id} onOpenDiscuss={onOpenDiscuss} />",
        'if (card.subtype === "discuss_note")',
        "if (!card.note_id) return null;",
        "<DiscussNoteCard noteId={card.note_id} onOpenDiscuss={onOpenDiscuss} />",
    ):
        assert fragment in card, f"ChatCard 缺少 {fragment}"
    for fragment in (
        'import DiscussTaskCard from "@/components/DiscussTaskCard";',
        'import DiscussNoteCard from "@/components/DiscussNoteCard";',
        "task_id?: string;",
        "note_id?: string;",
    ):
        assert fragment in source, f"ChatBubble 缺少 {fragment}"
    assert source.count("onOpenDiscuss?: (path: string) => void;") == 2


def test_chat_bubble_has_two_discuss_branches_and_two_wired_tags():
    source = read(BUBBLE)
    check_bubble_discuss_wiring(source)
    for bad in (
        source.replace(" onOpenDiscuss={onOpenDiscuss} />}", " />}", 1),
        source.replace(
            "songCardCompact={songCardCompact} onOpenDiscuss={onOpenDiscuss} />",
            "songCardCompact={songCardCompact} onOpenDiscuss={path => openDiscussAt(path)} />",
            1,
        ),
        source.replace('if (card.subtype === "discuss_task")', "if (false)", 1),
        source.replace(
            'import DiscussNoteCard from "@/components/DiscussNoteCard";', "", 1),
    ):
        assert bad != source
        with pytest.raises(AssertionError):
            check_bubble_discuss_wiring(bad)


# ────────────────────────── page.tsx → ChatBubble ──────────────────────────

CHAT_BUBBLE_TAG = re.compile(r"<ChatBubble\b[\s\S]*?/>")


def chat_bubble_element(source):
    tags = CHAT_BUBBLE_TAG.findall(source)
    assert len(tags) == 1, f"期望 page.tsx 恰好 1 个 <ChatBubble 元素，实际 {len(tags)}"
    return tags[0]


def check_page_chat_bubble_open_discuss(source):
    element = chat_bubble_element(source)
    assert element.count("onOpenDiscuss={openDiscussAt}") == 1, element
    assert source.count("onOpenDiscuss={openDiscussAt}") == 1, (
        "onOpenDiscuss={openDiscussAt} 应在 page.tsx 全文件恰好出现一次"
    )


def test_page_chat_bubble_passes_open_discuss_once():
    source = read(PAGE)
    check_page_chat_bubble_open_discuss(source)

    element = chat_bubble_element(source)

    # 坏副本 F11：去掉聊天消息列表 <ChatBubble 上的 onOpenDiscuss 传递。
    removed = source.replace(
        element, element.replace("onOpenDiscuss={openDiscussAt}", "", 1), 1)
    assert removed != source
    with pytest.raises(AssertionError):
        check_page_chat_bubble_open_discuss(removed)

    # 坏副本：整个元素被删掉，不能再靠「找到了就成立」的恒真断言混过去。
    deleted = source.replace(element, "", 1)
    assert deleted != source
    with pytest.raises(AssertionError):
        check_page_chat_bubble_open_discuss(deleted)

    # 坏副本：属性重复一次，全文件唯一性必须变红。
    duplicated = source.replace(
        "onOpenDiscuss={openDiscussAt}",
        "onOpenDiscuss={openDiscussAt}\n                      onOpenDiscuss={openDiscussAt}",
        1,
    )
    assert duplicated != source
    with pytest.raises(AssertionError):
        check_page_chat_bubble_open_discuss(duplicated)

    # 坏副本：换成内联包装函数，精确传递必须变红。
    wrapped = source.replace(
        "onOpenDiscuss={openDiscussAt}",
        "onOpenDiscuss={path => openDiscussAt(path)}",
        1,
    )
    assert wrapped != source
    with pytest.raises(AssertionError):
        check_page_chat_bubble_open_discuss(wrapped)


# ────────────────────────── discuss.ts 三请求 ──────────────────────────

DISCUSS_TS = FRONTEND / "lib/discuss.ts"

TASK_CARD_GET_CALL = (
    'apiJson<DiscussTaskCardView>(taskCardPath(id), { signal, cache: "no-store" })'
)
NOTE_CARD_GET_CALL = (
    'apiJson<DiscussNoteCardView>(noteCardPath(id), { signal, cache: "no-store" })'
)
NOTE_CARD_SEND_CALL = (
    'apiJson<DiscussNoteCardView>(`${noteCardPath(id)}/send`, json("POST", {}, signal))'
)
TASK_CARD_PATH = (
    "const taskCardPath = (id: string) => `${root}/task-cards/${encodeURIComponent(id)}`;"
)
NOTE_CARD_PATH = (
    "const noteCardPath = (id: string) => `${root}/note-cards/${encodeURIComponent(id)}`;"
)


def discuss_request_block(source, name):
    marker = f"export const {name} = "
    start = source.find(marker)
    assert start >= 0, f"缺少 {name}"
    end = source.find(";", start)
    assert end >= 0, f"{name} 未闭合"
    return source[start:end + 1]


def check_discuss_card_requests(source):
    for name in ("getDiscussTaskCard", "getDiscussNoteCard", "sendDiscussNoteCard"):
        assert f"export const {name} = " in source, f"缺少 {name}"

    for name, call in (
        ("getDiscussTaskCard", TASK_CARD_GET_CALL),
        ("getDiscussNoteCard", NOTE_CARD_GET_CALL),
    ):
        block = discuss_request_block(source, name)
        assert call in block, f"{name} 的请求写法变了：{block}"
        assert "method" not in block, f"{name} 应走 apiJson 默认 GET，不带 method 字段"

    send_block = discuss_request_block(source, "sendDiscussNoteCard")
    assert NOTE_CARD_SEND_CALL in send_block, (
        f"sendDiscussNoteCard 的 POST 写法变了：{send_block}"
    )

    assert source.count(TASK_CARD_PATH) == 1, (
        "taskCardPath 必须用 `${root}/task-cards/${encodeURIComponent(id)}`"
    )
    assert source.count(NOTE_CARD_PATH) == 1, (
        "noteCardPath 必须用 `${root}/note-cards/${encodeURIComponent(id)}`"
    )


def test_discuss_card_requests_keep_get_and_post_and_exact_paths():
    source = read(DISCUSS_TS)
    check_discuss_card_requests(source)

    task_element = discuss_request_block(source, "getDiscussTaskCard")
    bad_copies = {
        # 坏副本：读任务卡从默认 GET 改成 POST。
        "getDiscussTaskCard 改成 POST": source.replace(
            task_element,
            task_element.replace(
                TASK_CARD_GET_CALL,
                'apiJson<DiscussTaskCardView>(taskCardPath(id), json("POST", {}, signal))',
                1,
            ),
            1,
        ),
        # 坏副本 F52：送意见卡的 POST 改成 PUT。
        "sendDiscussNoteCard 的 POST 改成 PUT": source.replace(
            'json("POST", {}, signal)', 'json("PUT", {}, signal)', 1),
        # 坏副本 F53：任务卡路径改成下划线。
        "taskCardPath 改成 task_cards": source.replace(
            TASK_CARD_PATH, TASK_CARD_PATH.replace("/task-cards/", "/task_cards/"), 1),
        # 坏副本 F53：意见卡路径改成下划线。
        "noteCardPath 改成 note_cards": source.replace(
            NOTE_CARD_PATH, NOTE_CARD_PATH.replace("/note-cards/", "/note_cards/"), 1),
        # 坏副本：删掉一个读取函数。
        "删掉 getDiscussNoteCard": source.replace(
            "export const getDiscussNoteCard = ", "const getDiscussNoteCardGone = ", 1),
    }
    for label, bad in bad_copies.items():
        assert bad != source, f"坏副本未生效：{label}"
        with pytest.raises(AssertionError):
            check_discuss_card_requests(bad)
