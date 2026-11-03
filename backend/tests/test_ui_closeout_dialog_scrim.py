"""T3 dialog scrim closeout: one shared scrim-dialog class, offline.

The checks read only repository source.  Every dialog tag is parsed with a
small brace/string-aware scanner so ``=>`` and nested JSX expressions do not
end the tag early.  The self-checks mutate local copies and must raise
AssertionError; they never read git history or the network.
"""

import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCAN_BASES = (
    ROOT / "frontend/app",
    ROOT / "frontend/components",
    ROOT / "frontend/lib",
)
ALL_SOURCE_EXTS = (".ts", ".tsx", ".css")
DIALOG_START = re.compile(r"<dialog\b")
CLASS_ATTR = re.compile(
    r"""\bclassName\s*=\s*(?:"([^"]*)"|'([^']*)'|\{\s*([A-Za-z_$][\w$]*)\s*\})"""
)
BACKDROP_UTILITY = re.compile(r"(?<![\w-])backdrop:")


def _source_map(exts, *, skip_ui=False):
    sources = {}
    for base in SCAN_BASES:
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.suffix not in exts:
                continue
            rel = path.relative_to(ROOT).as_posix()
            if "node_modules" in path.parts or ".next" in path.parts:
                continue
            if skip_ui and rel.startswith("frontend/components/ui/"):
                continue
            sources[rel] = path.read_text(encoding="utf-8")
    return sources


def assert_scan_is_not_empty(sources, *, require_css=True):
    """A silently empty scan must never make the source assertions vacuous."""
    for base in SCAN_BASES:
        assert base.is_dir(), f"scan base is missing: {base}"
    assert sources, "source scan returned no files"
    assert "frontend/components/SongProjectCard.tsx" in sources, (
        "source scan must include the dialog component file"
    )
    if require_css:
        assert "frontend/app/globals.css" in sources, (
            "source scan must include globals.css"
        )


def _dialog_tag(source, start):
    """Return the complete opening tag beginning at ``start``."""
    assert source.startswith("<dialog", start)
    depth = 0
    quote = None
    escaped = False
    for index in range(start + len("<dialog"), len(source)):
        char = source[index]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in "\"'`":
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            assert depth >= 0, f"unbalanced braces in dialog tag: {source[start:index + 1]!r}"
        elif char == ">" and depth == 0:
            return source[start:index + 1]
    raise AssertionError(f"unterminated dialog tag: {source[start:start + 120]!r}")


def _class_name(tag, sources):
    matches = list(CLASS_ATTR.finditer(tag))
    assert len(matches) == 1, f"dialog must have exactly one className: {tag!r}"
    match = matches[0]
    direct = match.group(1) if match.group(1) is not None else match.group(2)
    if direct is not None:
        return direct
    identifier = match.group(3)
    definitions = []
    const_rx = re.compile(r'\bconst\s+' + re.escape(identifier) + r'\s*=\s*"([^"]*)"')
    for source in sources.values():
        definitions.extend(m.group(1) for m in const_rx.finditer(source))
    assert len(definitions) == 1, (
        f"dialog class identifier {identifier!r} must have exactly one const string definition"
    )
    return definitions[0]


def _dialog_classes(sources):
    dialogs = []
    for rel, source in sources.items():
        if not rel.endswith(".tsx") or rel.startswith("frontend/components/ui/"):
            continue
        for match in DIALOG_START.finditer(source):
            tag = _dialog_tag(source, match.start())
            dialogs.append((rel, tag, _class_name(tag, sources)))
    return dialogs


def assert_dialogs_have_scrim(sources, *, expected_count=13):
    dialogs = _dialog_classes(sources)
    assert len(dialogs) == expected_count, (
        f"expected {expected_count} dialog tags, found {len(dialogs)}"
    )
    for rel, tag, class_name in dialogs:
        assert "scrim-dialog" in class_name.split(), (
            f"dialog in {rel} must include scrim-dialog: {tag!r}"
        )


def _strip_css_comments(css):
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def _backdrop_preludes(css):
    source = _strip_css_comments(css)
    assert source.count("::backdrop") == 2, (
        f"globals.css must have exactly two ::backdrop rules, found {source.count('::backdrop')}"
    )
    matches = re.findall(r"([^{}]*?::backdrop)\s*\{", source)
    assert len(matches) == 2, f"could not parse both ::backdrop rules: {matches!r}"
    return [re.sub(r"\s+", " ", prelude).strip() for prelude in matches]


def assert_scrim_backdrop_rules(css):
    assert _backdrop_preludes(css) == [
        ".scrim-dialog::backdrop",
        ".dark .scrim-dialog::backdrop",
    ], "::backdrop must be defined only by .scrim-dialog and its .dark variant"


def _backdrop_utility_hits(source):
    return list(BACKDROP_UTILITY.finditer(source))


def assert_no_backdrop_utility(sources):
    for rel, source in sources.items():
        for match in BACKDROP_UTILITY.finditer(source):
            line = source.count("\n", 0, match.start()) + 1
            raise AssertionError(
                f"{rel}:{line}: Tailwind backdrop: utility is forbidden: "
                f"{source[match.start():match.start() + 40]!r}"
            )


def test_all_dialogs_use_scrim_dialog():
    sources = _source_map((".tsx",), skip_ui=True)
    assert_scan_is_not_empty(sources, require_css=False)
    assert_dialogs_have_scrim(sources)

    # Parser self-check: => and a nested statement block before className.
    sample = (
        '<dialog ref={r} onCancel={e => { if (b) e.preventDefault(); }} '
        'className="x scrim-dialog">'
    )
    assert _dialog_tag(sample, 0) == sample
    assert _class_name(_dialog_tag(sample, 0), {}) == "x scrim-dialog"

    # A static class without the shared marker must fail.
    bad = '<dialog className="m-auto backdrop:bg-[color:var(--scrim)]">'
    with pytest.raises(AssertionError):
        assert_dialogs_have_scrim(
            {"frontend/components/SelfCheck.tsx": bad}, expected_count=1
        )

    # Identifier classes resolve through their unique const definition.
    good_identifier = (
        'const dialogClass = "m-auto scrim-dialog";\n'
        "export function X() { return <dialog className={dialogClass} />; }"
    )
    assert_dialogs_have_scrim(
        {"frontend/components/SelfCheck.tsx": good_identifier}, expected_count=1
    )
    bad_identifier = (
        'const dialogClass = "m-auto";\n'
        "export function X() { return <dialog className={dialogClass} />; }"
    )
    with pytest.raises(AssertionError):
        assert_dialogs_have_scrim(
            {"frontend/components/SelfCheck.tsx": bad_identifier}, expected_count=1
        )


def test_scrim_backdrop_rules_are_the_only_two():
    css = (ROOT / "frontend/app/globals.css").read_text(encoding="utf-8")
    assert_scrim_backdrop_rules(css)


def test_no_backdrop_tailwind_variants_remain():
    sources = _source_map(ALL_SOURCE_EXTS)
    assert_scan_is_not_empty(sources)
    assert_no_backdrop_utility(sources)

    # The regex must catch the old utility, but not backdrop-filter or the CSS
    # pseudo-element rule that this batch intentionally keeps.
    with pytest.raises(AssertionError):
        assert_no_backdrop_utility(
            {"frontend/components/SelfCheck.tsx": 'className="backdrop:bg-x"'}
        )
    assert not _backdrop_utility_hits("backdrop-filter:blur(1px)")
    assert not _backdrop_utility_hits(".a::backdrop {")
    assert not _backdrop_utility_hits("foo-backdrop:bg-x")


def test_selfcheck_empty_scan_is_rejected():
    with pytest.raises(AssertionError):
        assert_scan_is_not_empty({})
    with pytest.raises(AssertionError):
        assert_scan_is_not_empty({"frontend/app/globals.css": ""})
