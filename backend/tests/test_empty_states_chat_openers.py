"""Offline contracts for the P2-10 new-chat openers and empty-state wording.

The openers only prefill the composer, open generate mode, or open the file
picker.  They must never send a chat request (sending spends strawberries), and
the Enter handler must ignore auto-repeat only after preventDefault(), so
holding Enter on an opener cannot insert newlines or send repeatedly.

The exact-source checks below follow T3-1/T3-2/T3-3 (v1.2) and §10 item 8.5.
"""

import re
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "frontend/app/page.tsx"
PICKER = ROOT / "frontend/components/ConversationPicker.tsx"

OPENER_NAMES = ("startChatOpener", "startDrawOpener", "startPhotoOpener")
OPENER_LABELS = ("聊聊今天", "帮我画一张…", "看看我拍的这张图")

# T3-3 (v1.2): exactly these eight lines, once leading/trailing whitespace is
# stripped from each line.  In particular the auto-repeat guard must sit after
# e.preventDefault() and before handleSend().
HANDLE_KEY_DOWN_LINES = [
    "const handleKeyDown = (e: React.KeyboardEvent) => {",
    'if (e.key !== "Enter" || e.shiftKey) return;',
    "// Use ref for IME composing state — more reliable than e.nativeEvent.isComposing",
    "if (isComposingRef.current) return;",
    "e.preventDefault();",
    "if (e.repeat) return;",
    "handleSend();",
    "};",
]

# T3-1 (v1.2), whitespace-normalized to one line.
OPENER_BODIES = {
    "startChatOpener": (
        "const startChatOpener = () => { "
        "if (conversationLocked || conversationLoading || !currentConversation || imageMode || hasReferenceImages || !!input.trim()) return; "
        'composeSongSection("聊聊今天"); };'
    ),
    "startDrawOpener": (
        "const startDrawOpener = () => { "
        "if (pendingImage || isReadingImage || isReadingReferences || conversationLocked || conversationLoading || !currentConversation || imageMode || hasReferenceImages) return; "
        "setImageMode(true); "
        "requestAnimationFrame(() => textareaRef.current?.focus()); };"
    ),
    "startPhotoOpener": (
        "const startPhotoOpener = () => { "
        "if (imageMode || hasReferenceImages || isReadingImage || isReadingReferences || isLoading || conversationLoading || !currentConversation) return; "
        "fileInputRef.current?.click(); };"
    ),
}

# T3-2 (v1.2), whitespace-normalized.  Comparing the whole button, not just
# onClick, also rules out extra handlers such as onKeyDown.
OPENER_BUTTONS = {
    "startChatOpener": (
        '<button type="button" className="chip min-h-10" '
        "disabled={conversationLocked || conversationLoading || !currentConversation || imageMode || hasReferenceImages || !!input.trim()} "
        "onClick={startChatOpener}>聊聊今天</button>"
    ),
    "startDrawOpener": (
        '<button type="button" className="chip min-h-10" '
        "disabled={!!pendingImage || isReadingImage || isReadingReferences || conversationLocked || conversationLoading || !currentConversation || imageMode || hasReferenceImages} "
        "onClick={startDrawOpener}>帮我画一张…</button>"
    ),
    "startPhotoOpener": (
        '<button type="button" className="chip min-h-10" '
        "disabled={imageMode || hasReferenceImages || isReadingImage || isReadingReferences || isLoading || conversationLoading || !currentConversation} "
        "onClick={startPhotoOpener}>看看我拍的这张图</button>"
    ),
}

# HEAD contract, copied literally (do not read git history): the composer
# prefill helper only sets the input and focuses the textarea on the next frame.
COMPOSE_SONG_SECTION = """\
const composeSongSection = useCallback((text: string) => {
  setInput(text);
  requestAnimationFrame(() => textareaRef.current?.focus());
}, []);"""


def _source() -> str:
    return PAGE.read_text(encoding="utf-8")


def _slice_block(source: str, first_line: str, last_line: str) -> list[str]:
    """Slice from the unique ``first_line`` through the next ``last_line``.

    Both ends are included and compared by stripped content, so the source may
    be re-indented without weakening the contract.
    """
    lines = source.splitlines()
    starts = [index for index, line in enumerate(lines) if line.strip() == first_line]
    assert len(starts) == 1, f"expected exactly one line: {first_line!r}"
    start = starts[0]
    for end in range(start + 1, len(lines)):
        if lines[end].strip() == last_line:
            return lines[start:end + 1]
    raise AssertionError(f"missing closing line {last_line!r} after {first_line!r}")


def _normalize(lines: list[str]) -> str:
    return " ".join(" ".join(lines).split())


def opener_block(source: str, name: str) -> list[str]:
    """Return the whole opener declaration, closing ``};`` included."""
    return _slice_block(source, f"const {name} = () => {{", "};")


def opener_body(source: str, name: str) -> str:
    return "\n".join(opener_block(source, name))


def test_chat_openers_offer_three_draft_only_actions():
    source = _source()
    assert "data-chat-openers" in source
    for name, label in zip(OPENER_NAMES, OPENER_LABELS):
        buttons = re.findall(rf"<button\b[^>]*>{re.escape(label)}</button>", source)
        assert len(buttons) == 1, label
        assert f"onClick={{{name}}}" in buttons[0], name
        assert source.count(f"onClick={{{name}}}") == 1, name
    for name in OPENER_NAMES:
        body = opener_body(source, name)
        for forbidden in ("handleSend", "handleSendRef", "apiFetch", "fetch("):
            assert forbidden not in body, f"{name} must not call {forbidden}"
    # The removed standalone generate-mode button and both hidden file inputs
    # stay exactly as locked by the existing page contracts.
    assert "onClick={() => setImageMode(true)}" not in source
    assert source.count('type="file"') == 2


def test_chat_opener_guards_match_their_actions():
    source = _source()
    chat = opener_body(source, "startChatOpener")
    assert "!!input.trim()" in chat
    assert 'composeSongSection("聊聊今天")' in chat
    draw = opener_body(source, "startDrawOpener")
    assert "setImageMode(true)" in draw
    assert "textareaRef.current?.focus()" in draw
    photo = opener_body(source, "startPhotoOpener")
    assert "fileInputRef.current?.click()" in photo
    # 「聊聊今天」 stays disabled while the composer already holds a draft.
    buttons = re.findall(r"<button\b[^>]*>聊聊今天</button>", source)
    assert len(buttons) == 1
    assert "!!input.trim()" in buttons[0]


def test_enter_key_ignores_auto_repeat():
    source = _source()
    body = _slice_block(
        source,
        "const handleKeyDown = (e: React.KeyboardEvent) => {",
        "};",
    )
    assert [line.strip() for line in body] == HANDLE_KEY_DOWN_LINES
    # The rest of the handler stays untouched.
    text = "\n".join(body)
    assert 'if (e.key !== "Enter" || e.shiftKey) return;' in text
    assert "handleSend();" in text


def test_chat_opener_bodies_match_the_spec_exactly():
    source = _source()
    for name in OPENER_NAMES:
        assert _normalize(opener_block(source, name)) == OPENER_BODIES[name], name
    # Regression guard: composeSongSection must stay byte-for-byte identical to
    # HEAD, so the openers cannot gain side effects through it.
    compose = _slice_block(
        source,
        "const composeSongSection = useCallback((text: string) => {",
        "}, []);",
    )
    assert textwrap.dedent("\n".join(compose)) == COMPOSE_SONG_SECTION


def test_chat_opener_buttons_match_the_spec_exactly():
    source = _source()
    for name, label in zip(OPENER_NAMES, OPENER_LABELS):
        buttons = re.findall(rf"<button\b[^>]*>{re.escape(label)}</button>", source)
        assert len(buttons) == 1, label
        assert _normalize([buttons[0]]) == OPENER_BUTTONS[name], name


def test_empty_chat_wording_points_at_the_conversation_list():
    page = _source()
    assert "在对话列表里点「新建」，开始和自己的分身交流。" in page
    assert "对话加载失败，请在对话列表里重试。" in page
    assert "点击上方“新对话”" not in page
    assert "请在上方重试" not in page
    picker = PICKER.read_text(encoding="utf-8")
    assert "点「新建」，开始和自己的分身交流。" in picker
    assert "点「新对话」" not in picker
