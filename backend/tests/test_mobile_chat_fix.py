"""Source-text contracts for the 2026-10-28 mobile chat fix.

Covers P1-1 (shell clipping), P1-2 (latest pill), P1-4 (conversation modal
material), P2-12 (idle composer height) and P3-16 (drawer / modal bottom edge).
Every assertion is a pure text check against checked-in frontend sources.  The
module never touches the network, git history or files outside the repository.
"""

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "frontend/app/page.tsx"
SCROLL = ROOT / "frontend/components/ChatScrollArea.tsx"
GLOBALS = ROOT / "frontend/app/globals.css"


def balanced_block(source, marker, start=0):
    """Return the marker and the balanced ``{...}`` block that follows it."""
    begin = source.index(marker, start)
    opening = source.index("{", begin)
    depth = 0
    for index in range(opening, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[begin : index + 1]
    raise AssertionError(f"Unclosed block after {marker}")


# Verbatim six-line block from ChatScrollArea.tsx (HEAD lines 30-35).
UPDATE_BUTTON_BLOCK = """\
  const updateButton = useCallback(() => {
    const viewport = viewportRef.current;
    if (!viewport) return;
    const distance = viewport.scrollHeight - viewport.clientHeight - viewport.scrollTop;
    setShowLatest(!followingRef.current && distance > BOTTOM_TOLERANCE);
  }, []);
"""

# Verbatim 18-line block from ChatScrollArea.tsx (HEAD lines 96-113).
ON_SCROLL_BLOCK = """\
  const onScroll = () => {
    const viewport = viewportRef.current;
    if (!viewport) return;
    const top = viewport.scrollTop;
    const max = Math.max(0, viewport.scrollHeight - viewport.clientHeight);
    const previous = previousRef.current;
    const atBottom = max - top <= BOTTOM_TOLERANCE;
    // A larger viewport or shorter content clamps scrollTop downward without
    // any user input. Do not treat that automatic clamp as an upward gesture.
    const clampedByResize = previous && max < previous.max && atBottom && !upwardIntentRef.current;
    if (previous && top < previous.top - BOTTOM_TOLERANCE && !clampedByResize) {
      followingRef.current = false;
    }
    if (atBottom && !upwardIntentRef.current) followingRef.current = true;
    previousRef.current = { top, max };
    upwardIntentRef.current = false;
    updateButton();
  };
"""

# Exact T5 material rule appended inside the mobile drawer media query.
T5_RULE = """\
  :root:not([data-shell=desktop]) .drawer-panel > .glaze-finish,
  :root:not([data-shell=desktop]) .chat-conversation-modal > .glaze > .glaze-finish { background-image:radial-gradient(ellipse 90% 24% at 24% 0%, var(--sheen), transparent 70%); box-shadow:inset 0 1px 0 var(--lip); }"""


def test_chat_shell_clips_instead_of_scrolling():
    source = PAGE.read_text()
    assert "chat-shell relative flex flex-col h-dvh overflow-clip" in source
    assert "chat-shell relative flex flex-col h-dvh overflow-hidden" not in source


def test_scroll_area_reports_latest_visibility_without_moving_logic():
    source = SCROLL.read_text()
    for fragment in (
        "renderLatestButton",
        "onLatestVisibilityChange?.(showLatest)",
        "[showLatest, onLatestVisibilityChange]",
        "{renderLatestButton && showLatest && <button",
        "scrollToLatest",
    ):
        assert fragment in source, fragment
    assert UPDATE_BUTTON_BLOCK in source
    assert ON_SCROLL_BLOCK in source
    # Anchor on the dedented top-level return: the effect cleanup also contains
    # a four-space-indented ``return (`` that plain ``  return (`` would hit.
    component_return = source.index("\n  return (")
    assert (
        source.index("const onScroll = ")
        < source.index("onLatestVisibilityChange?.(showLatest)")
        < component_return
    )
    assert source.count("回到最新") == 1
    # Four substring uses live on three lines: the Props field, the
    # destructured parameter, and the effect line (call + dependency array).
    assert source.count("onLatestVisibilityChange") == 4
    assert source.count("onLatestVisibilityChange?.") == 1
    assert len(
        [line for line in source.splitlines() if "onLatestVisibilityChange" in line]
    ) == 3


def test_page_latest_pill_lives_outside_the_masked_layer():
    source = PAGE.read_text()
    for fragment in (
        "<ChatScrollArea",
        "</ChatScrollArea>",
        'className="chat-message-layer',
        '<Glaze as="footer"',
        "chat-latest",
    ):
        assert source.count(fragment) == 1, fragment

    scroll_end = source.index("</ChatScrollArea>")
    layer_end = source.index("</div>", scroll_end)
    pill = source.index("chat-latest")
    footer = source.index('<Glaze as="footer"')
    assert layer_end < pill < footer
    assert "chat-latest" not in source[source.index("<ChatScrollArea") : scroll_end]

    match = re.search(r'className="([^"]*\bchat-latest\b[^"]*)"', source)
    assert match is not None
    classes = match.group(1)
    for token in (
        "border-border",
        "bg-background",
        "text-muted-foreground",
        "shadow-sm",
        "outline-primary",
    ):
        assert token not in classes, token
    assert "z-[1]" in classes
    assert "z-[2]" not in classes
    assert "z-[3]" not in classes
    assert "absolute" in classes
    assert "bottom-[calc(var(--composer-height)+34px)]" in classes
    assert "max-md:bottom-[calc(var(--composer-height)+var(--tabbar-h)+env(safe-area-inset-bottom)+12px)]" in classes
    assert "opacity-" not in classes

    assert "renderLatestButton={false}" in source
    assert "onLatestVisibilityChange={setShowLatestPill}" in source
    assert source.count("onLatestVisibilityChange=") == 1
    assert "const [showLatestPill, setShowLatestPill] = useState(false);" in source
    assert source.count("showLatestPill") >= 2
    assert source.count("回到最新") == 1

    pill_start = source.index("{showLatestPill && <button")
    pill_end = source.index("</button>}", pill_start)
    pill_block = source[pill_start:pill_end]
    assert "chat-latest" in pill_block
    assert "onClick={() => chatScrollRef.current?.scrollToLatest()}" in pill_block
    assert "scrollToLatest()" in pill_block

    panel_lines = [line for line in source.splitlines() if "data-chat-panel" in line]
    assert len(panel_lines) == 1
    assert '"--composer-height"' in panel_lines[0]
    layer_lines = [line for line in source.splitlines() if 'className="chat-message-layer' in line]
    assert len(layer_lines) == 1
    assert "--composer-height" not in layer_lines[0]


def test_globals_css_mobile_modal_and_drawer_edges():
    css = GLOBALS.read_text()
    assert ".drawer-panel" in css
    first = css.index(".drawer-panel")
    media_start = css.rindex("@media (width < 48rem)", 0, first)
    block = balanced_block(css, "@media (width < 48rem)", media_start)

    for fragment in (
        ":root:not([data-shell=desktop]) .chat-conversation-modal > .glaze > .glaze-blur",
        ":root:not([data-shell=desktop]) .chat-conversation-modal > .glaze > .glaze-tint",
        ".chat-conversation-modal > .glaze > .glaze-lens { display:none; }",
        ".chat-conversation-modal > .glaze > .glaze-tint { background:var(--glass2); }",
        ":root:not([data-shell=desktop]) .drawer-panel > .glaze-finish",
        ":root:not([data-shell=desktop]) .chat-conversation-modal > .glaze > .glaze-finish",
    ):
        assert fragment in block, fragment

    assert T5_RULE in block
    assert "box-shadow:inset 0 1px 0 var(--lip)" in T5_RULE
    assert "lipdk" not in T5_RULE
    assert ":root[data-shell=desktop] .chat-conversation-modal" not in block

    finish_rules = re.findall(r"([^{}]*\.glaze-finish[^{}]*)\{([^{}]*)\}", block)
    assert finish_rules
    for _selector, body in finish_rules:
        assert "lipdk" not in body
        assert "linear-gradient" not in body
        assert "inset 0 1px 0 var(--lip)" in body

    # Existing drawer material rules survive next to the new modal rules.
    assert ":root:not([data-shell=desktop]) .drawer-panel > .glaze-blur" in block
    assert ":root:not([data-shell=desktop]) .drawer-panel > .glaze-tint" in block
    assert "-webkit-mask-image:none" in block
    assert "mask-image:none" in block
    assert ".drawer-panel > .glaze-lens { display:none; }" in block
    assert ".drawer-panel > .glaze-tint { background:var(--glass2); }" in block


def test_mobile_composer_uses_shorter_spacing():
    source = PAGE.read_text()
    footer_lines = [line for line in source.splitlines() if '<Glaze as="footer"' in line]
    assert len(footer_lines) == 1
    footer = footer_lines[0]
    assert "px-[18px] pb-3 pt-3" in footer
    assert "rounded-[14px]" in footer
    assert "max-md:pt-2" in footer
    assert "max-md:pb-1.5" in footer
    assert re.search(r"max-md:pt-2(?![\d.])", footer) is not None
    assert re.search(r"max-md:pb-1\.5(?![\d.])", footer) is not None
    assert re.search(r"max-md:pb-2(?![\d.])", footer) is None
    assert len(re.findall(r"max-md:pb-", footer)) == 1
    assert len(re.findall(r"max-md:pt-", footer)) == 1

    row_lines = [
        line for line in source.splitlines()
        if "border-t border-[color:var(--carve)] pt-2" in line
    ]
    assert len(row_lines) == 1
    row = row_lines[0]
    for token in ("max-md:mt-1", "max-md:pt-1", "max-md:text-fs-11"):
        assert token in row, token

    inner_lines = [line for line in source.splitlines() if "composer-inner" in line]
    assert len(inner_lines) == 1
    assert "max-md:py-1.5" in inner_lines[0]
    assert "max-md:py-2" not in inner_lines[0]


def test_page_copy_contracts():
    source = PAGE.read_text()
    assert source.count('每条消息消耗 <span className="readout font-normal">10</span> 颗草莓') == 1
    assert source.count('"平台模型 · 每条 10 颗草莓"') == 2
    assert source.count("平台模型每条消息消耗 10 颗；自带模型聊天不扣") == 1
    assert source.count("Enter 发送，Shift + Enter 换行") == 1


def test_no_new_bold_font_weights():
    page = PAGE.read_text()
    scroll = SCROLL.read_text()
    assert page.count("font-semibold") <= 3
    assert "font-semibold" not in scroll
    assert "font-bold" not in scroll
