"""讨论群第二期界面的静态守卫：只读前端源码与四份文档，离线运行。"""

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
LIBRARY_FILES = (
    FRONTEND / "lib" / "discuss.ts",
    FRONTEND / "lib" / "discussLogic.ts",
)
APP_DIR = FRONTEND / "app" / "discuss"
COMPONENTS_DIR = FRONTEND / "components" / "discuss"
PAGE_FILES = (
    APP_DIR / "page.tsx",
    APP_DIR / "new" / "page.tsx",
    APP_DIR / "[id]" / "page.tsx",
)
DOC_FILES = (
    ROOT / "README.md",
    ROOT / "PLAN.md",
    ROOT / "docs" / "ARCHITECTURE.md",
    ROOT / "CLAUDE.md",
)
FORBIDDEN_TYPE_STYLES = (
    "font-medium",
    "font-semibold",
    "font-bold",
    "font-extrabold",
    "font-black",
    "fontWeight",
    "font-weight",
)
FORBIDDEN_TYPE_STYLE = re.compile(
    "|".join(re.escape(token) for token in FORBIDDEN_TYPE_STYLES)
    + r"|font-\[\d|<(?:b|strong)\b",
    re.IGNORECASE,
)


def discuss_files():
    """返回要扫描的全部讨论群前端文件；缺文件或目录时用断言失败。"""
    for path in LIBRARY_FILES:
        assert path.is_file(), f"缺少讨论群文件：{path.relative_to(ROOT)}"
    assert APP_DIR.is_dir(), f"缺少讨论群目录：{APP_DIR.relative_to(ROOT)}"
    assert COMPONENTS_DIR.is_dir(), f"缺少讨论群目录：{COMPONENTS_DIR.relative_to(ROOT)}"
    files = list(LIBRARY_FILES)
    files += sorted(path for path in APP_DIR.rglob("*") if path.is_file())
    files += sorted(path for path in COMPONENTS_DIR.rglob("*") if path.is_file())
    assert files, "没有扫描到任何讨论群前端文件"
    return files


def read_discuss_sources():
    files = discuss_files()
    assert len(files) > 0
    assert all(path.is_file() for path in files)
    return {path: path.read_text(encoding="utf-8") for path in files}


def mask_comments_and_strings(source):
    """把注释与字符串换成空格，保留换行与字符位置，便于找真正的代码。"""
    chars = list(source)
    index = 0
    length = len(source)
    state = "code"
    quote = ""
    while index < length:
        char = source[index]
        following = source[index + 1] if index + 1 < length else ""
        if state == "code":
            if char == "/" and following == "/":
                state = "line"
                chars[index] = chars[index + 1] = " "
                index += 2
            elif char == "/" and following == "*":
                state = "block"
                chars[index] = chars[index + 1] = " "
                index += 2
            elif char in "\"'`":
                state = "string"
                quote = char
                chars[index] = " "
                index += 1
            else:
                index += 1
        elif state == "line":
            if char == "\n":
                state = "code"
            else:
                chars[index] = " "
            index += 1
        elif state == "block":
            if char == "*" and following == "/":
                state = "code"
                chars[index] = chars[index + 1] = " "
                index += 2
            else:
                if char != "\n":
                    chars[index] = " "
                index += 1
        else:
            if char == "\\":
                chars[index] = " "
                if index + 1 < length:
                    chars[index + 1] = " "
                index += 2
            elif char == quote:
                state = "code"
                chars[index] = " "
                index += 1
            else:
                if char != "\n":
                    chars[index] = " "
                index += 1
    return "".join(chars)


def skip_string(source, start):
    quote = source[start]
    index = start + 1
    while index < len(source):
        if source[index] == "\\":
            index += 2
        elif source[index] == quote:
            return index + 1
        else:
            index += 1
    return len(source)


def scan_tag(source, start):
    """从 '<' 起读一个 JSX 标签，跳过引号与 {} 里的内容。"""
    index = start + 1
    depth = 0
    quote = ""
    while index < len(source):
        char = source[index]
        if quote:
            if char == "\\":
                index += 2
                continue
            if char == quote:
                quote = ""
            index += 1
            continue
        if char in "\"'`":
            quote = char
            index += 1
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            if depth > 0:
                depth -= 1
        elif char == "<" and depth == 0:
            return None
        elif char == ">" and depth == 0:
            return index + 1, source[start:index + 1]
        index += 1
    return None


def iter_jsx_tags(source):
    """逐个产出 JSX 标签文本，忽略注释与普通字符串里的尖括号。"""
    index = 0
    length = len(source)
    while index < length:
        char = source[index]
        following = source[index + 1] if index + 1 < length else ""
        if char == "/" and following == "/":
            newline = source.find("\n", index + 2)
            index = length if newline < 0 else newline + 1
            continue
        if char == "/" and following == "*":
            closing = source.find("*/", index + 2)
            index = length if closing < 0 else closing + 2
            continue
        if char in "\"'`":
            index = skip_string(source, index)
            continue
        if char == "<" and index + 1 < length and (
            source[index + 1].isalpha() or source[index + 1] in ">/"
        ):
            tag = scan_tag(source, index)
            if tag is not None:
                end, text = tag
                yield text
                index = end
                continue
        index += 1


def strip_leading_comments_and_space(source):
    text = source.lstrip("\ufeff")
    while True:
        text = text.lstrip()
        if text.startswith("//"):
            newline = text.find("\n")
            if newline < 0:
                return ""
            text = text[newline + 1:]
            continue
        if text.startswith("/*"):
            closing = text.find("*/")
            if closing < 0:
                return ""
            text = text[closing + 2:]
            continue
        return text


def test_discuss_frontend_has_no_bold_font_weight():
    # 先证明正则抓得到带属性的标签、任意属性类和内联样式，再扫描真实文件。
    samples = (
        '<strong className="x">新的一版</strong>',
        '<b className="x">加粗</b>',
        '[font-weight:600]',
        "style={{ fontWeight: 600 }}",
    )
    for sample in samples:
        assert FORBIDDEN_TYPE_STYLE.search(sample), f"字重守卫漏掉样例：{sample!r}"
    assert not FORBIDDEN_TYPE_STYLE.search("font-normal"), "font-normal 必须允许"
    sources = read_discuss_sources()
    assert len(sources) > 0
    hits = []
    for path, text in sources.items():
        for match in FORBIDDEN_TYPE_STYLE.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            hits.append(f"{path.relative_to(ROOT)}:{line}: {match.group(0)}")
    assert not hits, "讨论群界面不允许字重写法：\n" + "\n".join(hits)


def test_discuss_frontend_has_no_dangerously_set_inner_html():
    sources = read_discuss_sources()
    assert len(sources) > 0
    hits = [
        str(path.relative_to(ROOT))
        for path, text in sources.items()
        if "dangerouslySetInnerHTML" in text
    ]
    assert not hits, "讨论群界面不允许 dangerouslySetInnerHTML：" + ", ".join(hits)


def test_discuss_logic_only_imports_types():
    path = FRONTEND / "lib" / "discussLogic.ts"
    assert path.is_file(), "缺少 frontend/lib/discussLogic.ts"
    source = path.read_text(encoding="utf-8")
    assert source, "frontend/lib/discussLogic.ts 是空的"
    masked = mask_comments_and_strings(source)
    imports = list(re.finditer(r"\bimport\b", masked))
    for match in imports:
        assert re.match(r"\s+type\b", masked[match.end():]), (
            "frontend/lib/discussLogic.ts 里有不是 import type 的 import："
            f"{source[match.start():match.start() + 60]!r}"
        )


def test_target_blank_tags_carry_noopener_noreferrer():
    sources = read_discuss_sources()
    assert len(sources) > 0
    blank_tags = []
    for path, text in sources.items():
        for tag in iter_jsx_tags(text):
            if re.search(r'target\s*=\s*"_blank"', tag):
                blank_tags.append((path, tag))
                assert re.search(r'rel\s*=\s*"noopener noreferrer"', tag), (
                    f"{path.relative_to(ROOT)} 的 target=\"_blank\" 标签缺少 "
                    f"rel=\"noopener noreferrer\"：{tag!r}"
                )
    assert blank_tags, "没有找到 target=\"_blank\" 的链接标签"


def test_discuss_pages_start_with_use_client():
    for path in PAGE_FILES:
        assert path.is_file(), f"缺少讨论群页面：{path.relative_to(ROOT)}"
    for path in PAGE_FILES:
        source = path.read_text(encoding="utf-8")
        assert source, f"{path.relative_to(ROOT)} 是空的"
        body = strip_leading_comments_and_space(source)
        assert re.match(r"([\"'])use client\1\s*;?", body), (
            f"{path.relative_to(ROOT)} 没有以 \"use client\" 开头"
        )


def test_discuss_table_headers_carry_font_normal():
    sources = read_discuss_sources()
    headers = []
    for path, text in sources.items():
        if path.suffix != ".tsx":
            continue
        for tag in iter_jsx_tags(text):
            if re.match(r"^<th(?:\s|>)", tag):
                headers.append((path, tag))
    assert headers, "没有找到讨论群表格的 <th>"
    for path, tag in headers:
        assert "font-normal" in tag, (
            f"{path.relative_to(ROOT)} 的 <th> 缺少 font-normal：{tag!r}"
        )


def test_discuss_dialogs_are_native_and_use_scrim():
    sources = read_discuss_sources()
    dialogs = []
    for path, text in sources.items():
        assert 'role="dialog"' not in text, (
            f"{path.relative_to(ROOT)} 仍有手写的 role=\"dialog\" 弹层"
        )
        if path.suffix != ".tsx":
            continue
        for tag in iter_jsx_tags(text):
            if re.match(r"^<dialog(?:\s|>)", tag):
                dialogs.append((path, tag))
    assert dialogs, "没有找到讨论群的原生 <dialog>"
    for path, tag in dialogs:
        assert "scrim-dialog" in tag, (
            f"{path.relative_to(ROOT)} 的 <dialog> 缺少 scrim-dialog：{tag!r}"
        )


def test_discuss_shell_main_and_content_flex_chain():
    source = (FRONTEND / "components" / "discuss" / "DiscussShell.tsx").read_text(
        encoding="utf-8"
    )
    tags = list(iter_jsx_tags(source))
    mains = [tag for tag in tags if re.match(r"^<main(?:\s|>)", tag)]
    contents = [tag for tag in tags if "@container" in tag]
    assert len(mains) == 1, "外壳里应恰好有一个 <main>"
    assert len(contents) == 1, "外壳里应恰好有一个带 @container 的内容容器"
    assert "flex min-h-0 min-w-0 flex-1 flex-col" in mains[0], (
        f"<main> 必须是纵向 flex 滚动容器：{mains[0]!r}"
    )
    assert "flex-[1_0_auto]" in contents[0], (
        f"内容容器必须用 flex:1 0 auto，不能写死 h-full：{contents[0]!r}"
    )
    assert "h-full" not in contents[0]
    assert "py-5" in contents[0]


def test_discuss_chat_flex_chain_and_min_height():
    timeline = (FRONTEND / "components" / "discuss" / "DiscussTimeline.tsx").read_text(
        encoding="utf-8"
    )
    tags = list(iter_jsx_tags(timeline))
    sections = [tag for tag in tags if 'aria-label="群聊"' in tag]
    viewports = [tag for tag in tags if "ref={viewportRef}" in tag]
    assert len(sections) == 1, "消息组件里应恰好有一个 aria-label=群聊 的 section"
    assert len(viewports) == 1, "消息组件里应恰好有一个 ref=viewportRef 的消息区"
    assert "flex-[1_0_auto]" in sections[0], (
        f"群聊 section 必须能撑满父级：{sections[0]!r}"
    )
    assert "min-h-[120px]" in viewports[0], (
        f"消息区最小高度必须是 120px：{viewports[0]!r}"
    )
    assert "flex-[1_1_0px]" in viewports[0], (
        f"消息区基准必须是 0px：{viewports[0]!r}"
    )
    viewport_index = tags.index(viewports[0])
    middle = tags[viewport_index - 1]
    assert middle.startswith("<div"), f"消息区外层应是 div：{middle!r}"
    assert "flex-[1_0_auto]" in middle, (
        f"消息区外层必须能撑满：{middle!r}"
    )


def test_discuss_room_layout_flex_chain():
    room = (FRONTEND / "components" / "discuss" / "DiscussRoom.tsx").read_text(
        encoding="utf-8"
    )
    tags = list(iter_jsx_tags(room))
    roots = [tag for tag in tags if "data-discuss-room" in tag]
    contents = [tag for tag in tags if "ref={contentRef}" in tag]
    layouts = [tag for tag in tags if "grid-rows-[auto_minmax(0,1fr)]" in tag]
    chats = [tag for tag in tags if 'id="discuss-panel-chat"' in tag]
    assert len(roots) == 1, "房间根节点应恰好有一个 data-discuss-room"
    assert len(contents) == 1, "标签区内容层应恰好有一个 ref=contentRef"
    assert len(layouts) == 1, "宽布局两栏 grid 应恰好有一个"
    assert len(chats) == 1, "群聊分区应恰好有一个 id=discuss-panel-chat"
    assert "flex-[1_0_auto]" in roots[0], (
        f"房间根节点必须能撑满：{roots[0]!r}"
    )
    assert "flex-[1_0_auto]" in contents[0], (
        f"标签区内容层必须能撑满：{contents[0]!r}"
    )
    assert "flex-[1_1_0px]" in layouts[0], (
        f"宽布局两栏的 flex 基准必须是 0px：{layouts[0]!r}"
    )
    assert "min-h-[320px]" in layouts[0], (
        f"宽布局两栏最小高度必须是 320px：{layouts[0]!r}"
    )
    assert "flex flex-[1_0_auto] flex-col" in layouts[0], (
        f"窄布局布局层必须能撑满：{layouts[0]!r}"
    )
    assert "flex-[1_0_auto]" in chats[0], (
        f"窄布局群聊分区必须能撑满：{chats[0]!r}"
    )
    chat_index = tags.index(chats[0])
    inner = tags[chat_index + 1]
    assert inner.startswith("<div"), f"群聊分区内层应是 div：{inner!r}"
    assert "flex-[1_0_auto]" in inner, (
        f"群聊分区内层必须能撑满：{inner!r}"
    )


def test_discuss_dialog_padding_is_inside_not_on_dialog_element():
    path = FRONTEND / "components" / "discuss" / "DiscussDialogs.tsx"
    source = path.read_text(encoding="utf-8")
    dialogs = [
        tag for tag in iter_jsx_tags(source)
        if re.match(r"^<dialog(?:\s|>)", tag)
    ]
    assert dialogs, "没有找到讨论群的原生 <dialog>"
    for tag in dialogs:
        assert "scrim-dialog" in tag
        assert not re.search(r"\bp[trblxy]?-\d", tag), (
            f"<dialog> 自身不能带内边距，否则点内边距会被当成点遮罩：{tag!r}"
        )
    assert "p-6" in source, "对话框内容层应保留内边距"


def brace_block(source: str, marker: str) -> str:
    """Return the balanced ``{...}`` block starting at marker."""
    start = source.index(marker)
    opening = source.index("{", start)
    depth = 0
    for index in range(opening, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start:index + 1]
    raise AssertionError(f"unclosed block after {marker}")


def function_block(source: str, marker: str) -> str:
    """Return the balanced ``{...}`` function body starting at marker."""
    start = source.index(marker)
    body = source.index("): JSX.Element {", start)
    opening = body + len("): JSX.Element ")
    depth = 0
    for index in range(opening, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start:index + 1]
    raise AssertionError(f"unclosed block after {marker}")


def test_discuss_room_reads_use_server_cursor():
    room = (FRONTEND / "components" / "discuss" / "DiscussRoom.tsx").read_text(
        encoding="utf-8"
    )
    assert "cursorRef" in room
    assert "advanceDiscussCursor" in room
    assert "getDiscussGroup(id, maxMessageId" not in room
    assert room.count("getDiscussGroup(id, cursorRef.current") == 3, (
        "poll、refreshDetail、reloadPlan 的 after 都必须用服务器读取游标"
    )
    assert "const publishDetail = useCallback(" in room
    assert "const sendNote = useCallback(" in room
    publish = brace_block(room, "const publishDetail = useCallback(")
    send = brace_block(room, "const sendNote = useCallback(")
    assert publish.count("cursorRef.current = advanceDiscussCursor") == 1, (
        "publishDetail 必须用服务器消息推进游标"
    )
    assert "next.messages" in publish
    assert "cursorRef" not in send, "插话成功后不能推进读取游标"
    assert room.count("cursorRef.current = advanceDiscussCursor") == 1, (
        "整个 Room 只能有一处推进游标"
    )


def test_discuss_custom_helpers_are_used_in_components():
    form = (FRONTEND / "components" / "discuss" / "DiscussCreateForm.tsx").read_text(
        encoding="utf-8"
    )
    marker = "const handleTeamChange = (members: DiscussTeamMember[]) => {"
    assert marker in form
    handle_team = brace_block(form, marker)
    assert "defaultDiscussCustomMemberModel(catalog)" in handle_team, (
        "自定义成员的初始模型必须来自 discussLogic 的纯函数"
    )

    panel = (FRONTEND / "components" / "discuss" / "DiscussPlanPanel.tsx").read_text(
        encoding="utf-8"
    )
    assert "const renderMember = (member: DiscussMember) =>" in panel
    start = panel.index("const renderMember = (member: DiscussMember) =>")
    end = panel.index("\n  return (", start)
    render_member = panel[start:end]
    assert "discussMemberShowsFocus(member)" in render_member, (
        "只读视图的分工判断必须用 discussLogic 的纯函数"
    )
    assert 'member.kind === "lens" &&' not in render_member, (
        "不能改回只判断 lens 的手写条件"
    )


def test_discuss_tables_have_column_min_width():
    document = (FRONTEND / "components" / "discuss" / "DiscussDocument.tsx").read_text(
        encoding="utf-8"
    )
    tables = [
        tag for tag in iter_jsx_tags(document)
        if re.match(r"^<table(?:\s|>)", tag)
    ]
    assert len(tables) == 1, "讨论群文档模板里应恰好有一个 <table>"
    assert "minWidth" in tables[0], f"表格缺少最小宽度：{tables[0]!r}"
    assert "style={{ minWidth: `${discussTableMinWidth(block.header.length)}em` }}" in tables[0], (
        f"表格最小宽度必须按列数计算，单位必须是 em：{tables[0]!r}"
    )


def test_discuss_composer_keeps_focus_while_sending():
    composer = (FRONTEND / "components" / "discuss" / "DiscussComposer.tsx").read_text(
        encoding="utf-8"
    )
    textareas = [
        tag for tag in iter_jsx_tags(composer)
        if "data-discuss-composer" in tag
    ]
    assert len(textareas) == 1, "插话框应恰好有一个 textarea"
    tag = textareas[0]
    assert "readOnly={sending || busy}" in tag, (
        f"发送中不能用 disabled 移走焦点：{tag!r}"
    )
    assert not re.search(r"\bdisabled\s*=", tag), (
        f"插话框不能使用 disabled 属性：{tag!r}"
    )
    assert "ref={textareaRef}" in tag
    submit_marker = "const submit = async () => {"
    assert submit_marker in composer
    submit = brace_block(composer, submit_marker)
    assert "textareaRef.current?.focus()" in submit, (
        "发送成功或失败后必须把焦点放回插话框"
    )
    assert "try {" in submit and "finally {" in submit
    try_block = brace_block(submit, "try {")
    finally_block = brace_block(submit, "finally {")
    assert "textareaRef.current?.focus()" in finally_block, (
        "焦点恢复必须在 finally 里，成功和失败都执行"
    )
    assert "textareaRef.current?.focus()" not in try_block, (
        "焦点恢复不能只放在 try 里，否则失败时丢失"
    )


def test_discuss_timeline_tracks_messages_while_hidden():
    timeline = (FRONTEND / "components" / "discuss" / "DiscussTimeline.tsx").read_text(
        encoding="utf-8"
    )
    block = function_block(timeline, "export default function DiscussTimeline")
    assert "pendingWhileHiddenRef" in block, "隐藏期间的新消息必须有独立标记"
    assert "if (!active)" in block, "不可见分支必须记录新消息"
    assert "pendingWhileHiddenRef.current = true" in block, (
        "不可见期间收到新消息时必须置位"
    )
    assert "if (arrived && !firstViewRef.current) pendingWhileHiddenRef.current = true;" in block, (
        "第一次看到群聊之前不能留下过期的隐藏标记"
    )
    assert "!pendingWhileHiddenRef.current" in block, (
        "回来时必须读取隐藏期间的标记"
    )
    assert "setHasNew(true)" in block, "回来时不在底部必须提示新消息"
    effect_marker = (
        "if (!active || firstViewRef.current || !pendingWhileHiddenRef.current) return;"
    )
    assert effect_marker in timeline
    effect_start = timeline.index(effect_marker)
    effect_end = timeline.index("}, [active]);", effect_start)
    hidden_effect = timeline[effect_start:effect_end]
    assert "pendingWhileHiddenRef.current = false;" in hidden_effect, (
        "跟随或提示之后必须清掉隐藏标记，避免下次无新消息也重复"
    )
    assert "const shouldFollow = nearBottomRef.current;" in hidden_effect, (
        "回来时是否跟随必须取决于离开前是否在底部"
    )
    assert "const shouldFollow = true;" not in hidden_effect
    assert "const shouldFollow = false;" not in hidden_effect


def test_discuss_external_links_use_safe_external_url():
    for name in ("DiscussDocument.tsx", "DiscussSourcesPanel.tsx"):
        source = (FRONTEND / "components" / "discuss" / name).read_text(
            encoding="utf-8"
        )
        tags = [
            tag for tag in iter_jsx_tags(source)
            if re.search(r'target\s*=\s*"_blank"', tag)
        ]
        assert tags, f"{name} 没有找到 target=_blank 链接"
        for tag in tags:
            assert "href={href}" in tag, (
                f"{name} 的外链必须使用经过 safeExternalUrl 的 href：{tag!r}"
            )
        assert "safeExternalUrl(source.url)" in source, (
            f"{name} 的 href 必须经过 safeExternalUrl"
        )
        assert "href={source.url}" not in source, (
            f"{name} 不能直接使用 source.url 作为 href"
        )
        href_lines = [
            line.strip() for line in source.splitlines() if "const href" in line
        ]
        assert len(href_lines) == 1, f"{name} 应恰好有一条 const href 赋值"
        assert href_lines[0].count("source.url") == 1, (
            f"{name} 的 href 赋值除了 safeExternalUrl 的参数外不能再出现 source.url："
            f"{href_lines[0]!r}"
        )


def test_documents_mention_discuss_ui_second_phase():
    assert len(DOC_FILES) == 4
    texts = {}
    for path in DOC_FILES:
        assert path.is_file(), f"缺少文档：{path.relative_to(ROOT)}"
        texts[path] = path.read_text(encoding="utf-8")
    assert texts
    for path, text in texts.items():
        assert "讨论群界面（第二期）" in text, (
            f"{path.relative_to(ROOT)} 没有「讨论群界面（第二期）」"
        )


def claude_discuss_ui_section(text):
    marker = "## 讨论群界面（第二期）"
    assert marker in text, "CLAUDE.md 没有「## 讨论群界面（第二期）」"
    start = text.index(marker)
    following = re.search(r"\n#{1,2}[ \t]", text[start + len(marker):])
    end = len(text) if following is None else start + len(marker) + following.start() + 1
    return text[start:end]


def test_claude_discuss_ui_section_is_within_700_bytes():
    path = ROOT / "CLAUDE.md"
    assert path.is_file(), "缺少 CLAUDE.md"
    text = path.read_text(encoding="utf-8")
    section = claude_discuss_ui_section(text)
    assert section
    size = len(section.encode("utf-8"))
    assert size <= 700, f"CLAUDE.md 的讨论群界面一节为 {size} 字节"
