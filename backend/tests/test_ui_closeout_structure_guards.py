"""Structure guards for the two empty-state review blind spots (T5).

The existing empty-state tests match individual lines or individual button
tags, so two regressions can slip through:

* Blind spot 2: wrapping the first BYOK privacy paragraph (and the Claude note
  after it) in ``{needsKey && <> ... </>}`` keeps both locked lines intact.
  Counting lines cannot see the conditional wrapper, so this guard inspects the
  whole slice between the second ``<fieldset`` and the paragraph: braces must
  balance and no line may be left dangling on a boolean conjunction.
* Blind spot 3: adding ``onKeyDown`` to the ``role="group"`` wrapper, to the
  ``data-chat-openers`` container, or to a new ``<div>`` around a button keeps
  every ``<button>`` tag byte-for-byte identical.  This guard therefore checks
  the exact six-line opener structure and the direct parent of the buttons.

Both checks are pure functions over source text: offline, repository-only, no
git history, no node.  The real tests feed them the checked-in files; the
self-check tests feed them deliberately broken copies and require
``AssertionError``.
"""

from collections.abc import Callable
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SETTINGS = ROOT / "frontend/components/ChatModelSection.tsx"
PAGE = ROOT / "frontend/app/page.tsx"

# Blind spot 2 (ChatModelSection.tsx) -----------------------------------------
PRIVACY_PARAGRAPH_PREFIX = "<p className={noteClass}>启用后，"
BROKEN_CONDITIONAL_SUFFIXES = ("&&", "&& (", "&& <>")

# Blind spot 3 (page.tsx) -----------------------------------------------------
OPENERS_CONTAINER = (
    '<div data-chat-openers className="flex flex-col items-center gap-4 '
    'pt-8 text-center max-md:pt-4">'
)
OPENERS_STATUS_PREFIX = (
    '<p className="text-fs-15 leading-[1.85] text-[color:var(--ink2)]" role="status">'
)
OPENERS_GROUP = (
    '<div role="group" aria-label="开场" '
    'className="flex flex-wrap justify-center gap-2">'
)
OPENER_BUTTON_PREFIX = '<button type="button" className="chip min-h-10"'
OPENER_ACTIONS = (
    "onClick={startChatOpener}",
    "onClick={startDrawOpener}",
    "onClick={startPhotoOpener}",
)
GROUP_CLOSE = "</div>"


def _lines(source: str) -> list[str]:
    return source.splitlines()


def _replace_line(lines: list[str], index: int, replacement: str) -> list[str]:
    """Return a copy of ``lines`` with one entry replaced."""
    copied = list(lines)
    copied[index] = replacement
    return copied


def _line_with_stripped(lines: list[str], expected: str, label: str) -> int:
    """Index of the unique line whose stripped content equals ``expected``."""
    hits = [index for index, line in enumerate(lines) if line.strip() == expected]
    assert len(hits) == 1, (
        f"{label}：期望恰 1 行 {expected!r}，实际 {len(hits)} 行"
    )
    return hits[0]


def _assert_rejected(
    check: Callable[[str], None], source: str, message: str
) -> None:
    """Require the guard ``check`` to reject ``source`` with AssertionError."""
    try:
        check(source)
    except AssertionError:
        return
    raise AssertionError(message)


# ---------------------------------------------------------------------------
# Blind spot 2: the first privacy paragraph must not be conditionally hidden.
# ---------------------------------------------------------------------------


def check_privacy_paragraph_is_unconditional(source: str) -> None:
    """The first privacy paragraph sits bare inside the second ``<fieldset>``.

    Slicing from the second ``<fieldset`` up to (but excluding) the paragraph
    line must be brace-balanced, and no line in that slice may end with ``&&``,
    ``&& (`` or ``&& <>``.  The latter catches an opening conditional even
    when a matching ``</>}`` later restores the total brace count.
    """
    lines = _lines(source)

    paragraph_hits = [
        index for index, line in enumerate(lines)
        if line.lstrip().startswith(PRIVACY_PARAGRAPH_PREFIX)
    ]
    assert len(paragraph_hits) == 1, (
        "盲区 2：以 <p className={noteClass}>启用后， 开头的行应恰 1 行，"
        f"实际 {len(paragraph_hits)} 行；首段可能被条件包裹或删除"
    )
    paragraph_index = paragraph_hits[0]

    fieldset_lines = [
        index for index, line in enumerate(lines) if "<fieldset" in line
    ]
    assert len(fieldset_lines) >= 2, (
        "盲区 2：未找到第二个 <fieldset，无法确认首段位于聊天模型设置内"
    )
    second_fieldset = fieldset_lines[1]
    assert second_fieldset < paragraph_index, (
        "盲区 2：第二个 <fieldset 必须在首段之前"
    )

    between = lines[second_fieldset + 1:paragraph_index]
    open_braces = sum(line.count("{") for line in between)
    close_braces = sum(line.count("}") for line in between)
    assert open_braces == close_braces, (
        "盲区 2：第二个 <fieldset 与首段之间花括号不平衡"
        f"（{open_braces} 个 {{，{close_braces} 个 }}），首段可能被条件包裹"
    )

    for index, line in enumerate(between, start=second_fieldset + 2):
        stripped = line.strip()
        for suffix in BROKEN_CONDITIONAL_SUFFIXES:
            assert not stripped.endswith(suffix), (
                f"盲区 2：第 {index} 行以 {suffix!r} 结尾，"
                "首段上方出现了条件包裹："
                f"{stripped!r}"
            )


# ---------------------------------------------------------------------------
# Blind spot 3: the opener buttons must be direct children of the group.
# ---------------------------------------------------------------------------


def check_chat_opener_group_structure(source: str) -> None:
    """The empty-chat openers keep the exact expected structure.

    ``data-chat-openers`` container -> status paragraph -> ``role="group"``
    div -> the three opener buttons -> closing ``</div>``.  Any extra handler
    on the container or the group, or a new wrapper around a button, changes
    one of these lines and is rejected.
    """
    lines = _lines(source)

    start = _line_with_stripped(lines, OPENERS_CONTAINER, "盲区 3：开场容器")
    assert start + 6 < len(lines), "盲区 3：开场容器之后不足六行"

    status = lines[start + 1].strip()
    assert status.startswith(OPENERS_STATUS_PREFIX), (
        "盲区 3：开场容器下一行必须是状态段落，实际为 "
        f"{status!r}"
    )

    group = lines[start + 2].strip()
    assert group == OPENERS_GROUP, (
        "盲区 3：role=group 开场按钮组必须恰为规定行，实际为 "
        f"{group!r}；按钮组外层不得插入 onKeyDown 等处理器"
    )

    for offset, action in enumerate(OPENER_ACTIONS, start=3):
        button = lines[start + offset].strip()
        assert button.startswith(OPENER_BUTTON_PREFIX), (
            f"盲区 3：第 {start + offset + 1} 行应以 {OPENER_BUTTON_PREFIX!r} "
            f"开头，实际为 {button!r}；按钮不得被额外元素包裹"
        )
        assert action in button, (
            f"盲区 3：第 {start + offset + 1} 行缺少 {action}"
        )

    closing = lines[start + 6].strip()
    assert closing == GROUP_CLOSE, (
        "盲区 3：三个开场按钮之后必须紧接按钮组的 </div>，实际为 "
        f"{closing!r}"
    )


# ---------------------------------------------------------------------------
# Real tests.
# ---------------------------------------------------------------------------


def test_first_privacy_paragraph_is_not_wrapped_in_needs_key_conditional():
    check_privacy_paragraph_is_unconditional(SETTINGS.read_text(encoding="utf-8"))


def test_chat_openers_are_not_wrapped_by_extra_keyboard_handlers():
    check_chat_opener_group_structure(PAGE.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Self-checks: each deliberately broken copy must be rejected.
# ---------------------------------------------------------------------------


def _privacy_paragraph_index(lines: list[str]) -> int:
    hits = [
        index for index, line in enumerate(lines)
        if line.lstrip().startswith(PRIVACY_PARAGRAPH_PREFIX)
    ]
    assert len(hits) == 1, "自检前置条件不成立：首段应恰 1 行"
    return hits[0]


def test_selfcheck_privacy_guard_rejects_split_needs_key_wrapper():
    source = SETTINGS.read_text(encoding="utf-8")
    check_privacy_paragraph_is_unconditional(source)
    lines = _lines(source)
    paragraph = _privacy_paragraph_index(lines)
    assert "已选 Claude：" in lines[paragraph + 1]

    broken = list(lines)
    # Insert the closing tag after the Claude note first, then the opener
    # before the paragraph, so both indices refer to the original lines.
    broken.insert(paragraph + 2, "</>}")
    broken.insert(paragraph, "{needsKey && <>")
    broken_source = "\n".join(broken) + "\n"
    assert broken_source != source

    _assert_rejected(
        check_privacy_paragraph_is_unconditional,
        broken_source,
        "自检失败：首段前一行插入 {needsKey && <>、Claude 提示后插入 </>} "
        "的坏副本没有被拦住",
    )


def test_selfcheck_privacy_guard_rejects_single_line_needs_key_wrapper():
    source = SETTINGS.read_text(encoding="utf-8")
    check_privacy_paragraph_is_unconditional(source)
    lines = _lines(source)
    paragraph = _privacy_paragraph_index(lines)
    broken_lines = _replace_line(
        lines,
        paragraph,
        "{needsKey && " + lines[paragraph].strip() + "}",
    )
    broken_source = "\n".join(broken_lines) + "\n"
    assert broken_source != source

    _assert_rejected(
        check_privacy_paragraph_is_unconditional,
        broken_source,
        "自检失败：把首段改成 {needsKey && <p …>…</p>} 单行的坏副本没有被拦住",
    )


def _opener_container_index(lines: list[str]) -> int:
    return _line_with_stripped(lines, OPENERS_CONTAINER, "盲区 3：开场容器")


def test_selfcheck_opener_guard_rejects_on_key_down_on_group():
    source = PAGE.read_text(encoding="utf-8")
    check_chat_opener_group_structure(source)
    lines = _lines(source)
    start = _opener_container_index(lines)
    assert lines[start + 2].strip() == OPENERS_GROUP
    broken_lines = _replace_line(
        lines,
        start + 2,
        OPENERS_GROUP[:-1] + " onKeyDown={noop}>",
    )
    broken_source = "\n".join(broken_lines) + "\n"
    assert broken_source != source

    _assert_rejected(
        check_chat_opener_group_structure,
        broken_source,
        "自检失败：给 role=group 开场按钮组加 onKeyDown 的坏副本没有被拦住",
    )


def test_selfcheck_opener_guard_rejects_wrapped_first_button():
    source = PAGE.read_text(encoding="utf-8")
    check_chat_opener_group_structure(source)
    lines = _lines(source)
    start = _opener_container_index(lines)
    first_button = start + 3
    assert lines[first_button].strip().startswith(OPENER_BUTTON_PREFIX)

    # One extra line: the wrapper opens on the button line and closes after it.
    broken_lines = list(lines)
    broken_lines[first_button] = (
        "<div onKeyDown={noop}>" + lines[first_button].strip()
    )
    broken_lines.insert(first_button + 1, "</div>")
    broken_source = "\n".join(broken_lines) + "\n"
    assert broken_source != source

    _assert_rejected(
        check_chat_opener_group_structure,
        broken_source,
        "自检失败：把第一个开场按钮包进 <div onKeyDown={noop}> 的坏副本"
        "没有被拦住",
    )


def test_selfcheck_opener_guard_rejects_on_key_down_on_container():
    source = PAGE.read_text(encoding="utf-8")
    check_chat_opener_group_structure(source)
    lines = _lines(source)
    start = _opener_container_index(lines)
    broken_lines = _replace_line(
        lines,
        start,
        OPENERS_CONTAINER[:-1] + " onKeyDown={noop}>",
    )
    broken_source = "\n".join(broken_lines) + "\n"
    assert broken_source != source

    _assert_rejected(
        check_chat_opener_group_structure,
        broken_source,
        "自检失败：给 data-chat-openers 容器加 onKeyDown 的坏副本没有被拦住",
    )
