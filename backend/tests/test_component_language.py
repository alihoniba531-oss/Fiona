"""Offline checks for the shared component language (spec 2026-10-28, T7).

Everything here reads files inside this repository and runs local Node.js only.
No network, database, or git history is used.
"""

import json
import re
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
APP = FRONTEND / "app"
COMPONENTS = FRONTEND / "components"
LIB = FRONTEND / "lib"

GLOBALS_CSS = APP / "globals.css"
LAYOUT = APP / "layout.tsx"
PAGE = APP / "page.tsx"
CHAT_BUBBLE = COMPONENTS / "ChatBubble.tsx"
CONFIRM_DIALOG = COMPONENTS / "ConfirmDialog.tsx"
SETTINGS = APP / "settings/page.tsx"
PLAZA = APP / "plaza/page.tsx"
PROFILE = APP / "profile/page.tsx"
LOCAL_WATCH = COMPONENTS / "LocalWatchSection.tsx"
AGENT_MEMORY = COMPONENTS / "AgentMemoryPanel.tsx"
CHAT_MODEL = COMPONENTS / "ChatModelSection.tsx"
AGENT_EXCHANGE = COMPONENTS / "AgentExchangeWorkspace.tsx"
NOVEL_WORKBENCH = COMPONENTS / "novel/NovelWorkbench.tsx"
TTS_CHUNKS = LIB / "ttsChunks.ts"

NATIVE_DIALOG = re.compile(
    r"(^|[^.A-Za-z_])(window\.)?(confirm|alert)\(\s*[`\"']", re.MULTILINE
)

# The 12 native dialog payloads from spec section 2.3, each reduced to a
# template-variable-free fragment that is unique to its call site.
DIALOG_COPY = [
    (SETTINGS, "的所有聊天记录？此操作不可恢复。"),
    (SETTINGS, "的账号、聊天、画像、匹配、帖子、上传文件、自带模型配置与 Key。确定继续？"),
    (SETTINGS, "账号数据已删除，但有媒体文件需要管理员继续清理。"),
    (PAGE, "清空当前聊天界面？（历史记录仍保留）"),
    (PAGE, "删除这段对话及其中的消息？其他对话和分身设定会保留。此操作不可恢复。"),
    (PAGE, "只能上传图片"),
    (PAGE, "图片不能超过 5MB"),
    (LOCAL_WATCH, "的令牌？监控程序将停止。"),
    (LOCAL_WATCH, "删除规则「"),
    (AGENT_MEMORY, "清空分身记忆和已有个人画像？聊天记录与分身设定会保留，后续交流可形成新的记忆。"),
    (CHAT_MODEL, "确定删除自带模型配置与 Key？之后聊天将使用平台模型。"),
    (NOVEL_WORKBENCH, "」？章节、推演和留言都会删除，无法恢复。"),
]

DIALOG_OWNERS = [
    SETTINGS,
    PAGE,
    LOCAL_WATCH,
    AGENT_MEMORY,
    CHAT_MODEL,
    NOVEL_WORKBENCH,
]


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def slice_between(source: str, start_marker: str, end_marker: str) -> str:
    start = source.index(start_marker)
    end = source.index(end_marker, start)
    return source[start:end]


def test_source_tree_has_no_native_confirm_or_alert_dialogs():
    sources = [
        path
        for root in (APP, COMPONENTS, LIB)
        for path in root.rglob("*")
        if path.suffix in {".ts", ".tsx"}
    ]
    assert len(sources) >= 100, f"Only found {len(sources)} frontend source files"

    offenders = []
    for path in sources:
        source = read(path)
        for match in NATIVE_DIALOG.finditer(source):
            line = source.count("\n", 0, match.start()) + 1
            offenders.append(f"{path.relative_to(ROOT)}:{line}")
    assert offenders == [], "Native confirm/alert remains: " + ", ".join(offenders)


@pytest.mark.parametrize("path,fragment", DIALOG_COPY)
def test_replaced_dialog_copy_is_present_exactly_once(path, fragment):
    assert read(path).count(fragment) == 1, f"{fragment!r} is not unique in {path}"


def test_dialog_owners_use_shared_hooks_and_novel_keeps_local_confirm():
    for path in DIALOG_OWNERS:
        assert "useConfirm()" in read(path), f"{path} does not use useConfirm()"
    for path in (SETTINGS, PAGE):
        assert "useNotice()" in read(path), f"{path} does not use useNotice()"
    assert "confirm(" in read(NOVEL_WORKBENCH)


def test_confirm_dialog_exports_contract():
    source = read(CONFIRM_DIALOG)
    assert "export function ConfirmProvider" in source
    assert "export function useConfirm" in source
    assert "export function useNotice" in source
    for token in ("showModal(", '"alertdialog"', "confirm-dialog", "ConfirmProvider missing"):
        assert token in source, f"ConfirmDialog.tsx is missing {token!r}"


def test_layout_wraps_children_in_confirm_provider_in_order():
    source = read(LAYOUT)
    body_start = source.index("<body")
    lens = source.index("<LensDefs />", body_start)
    provider = source.index("<ConfirmProvider>", body_start)
    pwa = source.index("<PwaRegister />", body_start)
    assert lens < provider < pwa


def test_chat_bubble_message_row_contract():
    source = read(CHAT_BUBBLE)
    for token in (
        "setMuted",
        "setHovered",
        "onMouseEnter",
        "VolumeX",
        "Trash2",
        '"播放语音"',
        '"静音"',
    ):
        assert token not in source, f"ChatBubble.tsx still contains {token!r}"

    for token in (
        "onSpeak?: (id: string, text: string) => void;",
        "speaking?: boolean;",
        "speakDisabled?: boolean;",
        '"朗读"',
        '"停止"',
        '"复制"',
        '"已复制"',
        '"复制失败"',
        '"删除"',
        "stripMessageMarkdown(",
        "navigator.clipboard",
    ):
        assert token in source, f"ChatBubble.tsx is missing {token!r}"

    animation_lines = [line for line in source.splitlines() if "msg-in-" in line]
    assert len(animation_lines) == 1, "msg-in- must appear in exactly one expression"
    animation = animation_lines[0]
    assert 'startsWith("db-")' in animation
    assert '"msg-in-right"' in animation and '"msg-in-left"' in animation


def test_single_message_speak_chain():
    page = read(PAGE)
    body = slice_between(page, "const handleSpeakMessage", "}, [")
    prime = body.index("primeTtsAudio()")
    for token in ("setTimeout", ".then("):
        if token in body:
            assert prime < body.index(token), f"primeTtsAudio() must precede {token}"
    assert "await" not in body, "handleSpeakMessage must not await"
    assert "setVoiceOn" not in body, "single-message speech must not enable auto speech"
    assert "splitTtsChunks(" in body
    assert "setSpeakingMessageId(id)" in body

    clear_body = slice_between(page, "const clearTtsQueue = useCallback", "}, [")
    assert "setSpeakingMessageId(null)" in clear_body

    bubble_jsx = slice_between(page, "<ChatBubble", "/>")
    assert "speaking={speakingMessageId === msg.id}" in bubble_jsx
    assert "speakDisabled={isLoading}" in bubble_jsx


def require_rendering_dependencies():
    probe = """
const packages = ['typescript'];
const missing = packages.filter(name => {
  try { require.resolve(name, {paths: [process.argv[1]]}); return false; }
  catch { return true; }
});
process.stdout.write(JSON.stringify(missing));
"""
    try:
        result = subprocess.run(
            ["node", "-e", probe, str(FRONTEND)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        pytest.skip("Frontend TypeScript runtime unavailable; splitTtsChunks check skipped")
    missing = json.loads(result.stdout)
    if missing:
        pytest.skip("Frontend dependencies unavailable: " + ", ".join(missing))


TTS_RUNNER = r"""
const fs = require('fs');
const ts = require('typescript');
const source = fs.readFileSync(process.argv[1], 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText;
const moduleShim = { exports: {} };
new Function('module', 'exports', compiled)(moduleShim, moduleShim.exports);
const splitTtsChunks = moduleShim.exports.splitTtsChunks;
const cases = JSON.parse(process.argv[2]);
process.stdout.write(JSON.stringify(cases.map(text => splitTtsChunks(text))));
"""


def run_split_tts(cases):
    require_rendering_dependencies()
    completed = subprocess.run(
        ["node", "-e", TTS_RUNNER, str(TTS_CHUNKS), json.dumps(cases, ensure_ascii=False)],
        cwd=str(FRONTEND),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def without_whitespace(text: str) -> str:
    return re.sub(r"\s+", "", text)


def test_split_tts_chunks_behavior():
    corpus = "".join(f"{'字' * 18}{index % 10}。" for index in range(30))
    assert len(corpus) == 600

    outputs = run_split_tts(
        ["", " \n\t ", "第一句。第二句！", "字" * 600, "版本 4.5 发布。下一句", corpus]
    )
    empty, whitespace, two_sentences, long_text, version, sentences = outputs

    assert empty == [] and whitespace == []
    assert len(two_sentences) == 1
    assert len(long_text) == 3
    assert all(len(segment) <= 250 for segment in long_text)
    assert len(version) == 1 and "4.5" in version[0]
    assert all(len(segment) <= 250 for segment in sentences)
    assert without_whitespace("".join(sentences)) == without_whitespace(corpus)


def css_block(source: str, marker: str) -> str:
    start = source.index(marker)
    opening = source.index("{", start)
    depth = 0
    for index in range(opening, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise AssertionError(f"Unclosed CSS block: {marker}")


def test_base_layer_has_ink_focus_visible_rule():
    block = css_block(read(GLOBALS_CSS), "@layer base")
    assert ":focus-visible" in block
    assert "outline:1px solid var(--ink)" in block


def test_bold_and_middle_dot_cleanup():
    page = read(PAGE)
    assert "font-semibold" not in page
    exchange = read(AGENT_EXCHANGE)
    assert '<b className="readout">' not in exchange

    new_copy = [
        (CHAT_BUBBLE, "（AI 分身）"),
        (CHAT_BUBBLE, "由你的模型回复"),
        (SETTINGS, "Chloe AI 助理（内测版）"),
        (PLAZA, "更新中，"),
        (PLAZA, "标签（最多 5 个）"),
        (PROFILE, '.join("、")'),
        (LOCAL_WATCH, '（{typeLabels[rule.kind]}，{rule.enabled ? "已启用" : "已停用"}）'),
        (AGENT_EXCHANGE, "我的 AI 分身（发起方）"),
        (AGENT_EXCHANGE, "对方 AI 分身（受邀方）"),
    ]
    for path, fragment in new_copy:
        assert fragment in read(path), f"{fragment!r} is missing from {path}"

    old_copy = [
        (PLAZA, "更新中 · "),
        (PLAZA, "标签 · 最多 5"),
        (PROFILE, '.join(" · ")'),
        (SETTINGS, "Chloe AI 助理 · 内测版"),
        (AGENT_EXCHANGE, "我的 AI 分身 · 发起方"),
        (AGENT_EXCHANGE, "对方 AI 分身 · 受邀方"),
        (CHAT_BUBBLE, "· AI 分身"),
        (CHAT_BUBBLE, " · 由你的模型回复"),
    ]
    for path, fragment in old_copy:
        assert fragment not in read(path), f"{fragment!r} still appears in {path}"

    assert exchange.count("平台官方 AI · 无真人用户") == 1


def test_confirm_dialog_uses_module_level_queue_without_context():
    source = read(CONFIRM_DIALOG)
    for token in ("createContext", "useContext", "readContext", "ConfirmContext"):
        assert token not in source, f"ConfirmDialog.tsx still contains {token!r}"
    assert 'Promise.reject(new Error("ConfirmProvider missing"))' in source
    assert "let host: ((item: QueueItem) => void) | null = null;" in source
    assert "host = enqueue;" in source
    assert "if (host === enqueue) host = null;" in source

    # Check only the function body: the declaration itself necessarily contains
    # the name followed by "(", which must not be mistaken for a Hook call.
    for name in ("useConfirm", "useNotice"):
        start = source.index(f"export function {name}")
        body_start = source.index("{", start) + 1
        body_end = source.index("\n}", body_start)
        body = source[body_start:body_end]
        assert not re.search(r"\buse[A-Z]\w*\(", body), f"{name} calls a Hook"


def require_confirm_dialog_dependencies():
    probe = """
const packages = ['typescript', 'react', 'react/jsx-runtime'];
const missing = packages.filter(name => {
  try { require.resolve(name, {paths: [process.argv[1]]}); return false; }
  catch { return true; }
});
process.stdout.write(JSON.stringify(missing));
"""
    try:
        result = subprocess.run(
            ["node", "-e", probe, str(FRONTEND)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        pytest.skip("Frontend dialog runtime unavailable; module queue check skipped")
    missing = json.loads(result.stdout)
    if missing:
        pytest.skip("Frontend dependencies unavailable: " + ", ".join(missing))


CONFIRM_DIALOG_RUNNER = r"""
const fs = require('fs');
const ts = require('typescript');
const source = fs.readFileSync(process.argv[1], 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2020,
    jsx: ts.JsxEmit.ReactJSX,
  },
}).outputText;
const moduleShim = { exports: {} };
new Function('require', 'module', 'exports', compiled)(require, moduleShim, moduleShim.exports);
moduleShim.exports.useConfirm()({ body: 'x' }).then(
  () => { process.stdout.write('resolved'); process.exitCode = 1; },
  error => { process.stdout.write(error && error.message ? error.message : String(error)); },
);
"""


def test_use_confirm_rejects_without_mounted_provider():
    require_confirm_dialog_dependencies()
    completed = subprocess.run(
        ["node", "-e", CONFIRM_DIALOG_RUNNER, str(CONFIRM_DIALOG)],
        cwd=str(FRONTEND),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == "ConfirmProvider missing"
