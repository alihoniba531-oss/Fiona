"""设计系统第四批：源码门禁（T3-1）。

这些断言只读仓库内的前端源码，完全离线，不依赖 git 历史，也不读取
规格附件。规则、正则与块解析逻辑按规格 T3-1 写在文件自身。
"""

import os
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCAN_DIRS = ("frontend/app", "frontend/components", "frontend/lib")
EXEMPT_PREFIX = "frontend/components/ui/"
EXTS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".css")
JS_EXTS = (".ts", ".tsx", ".js", ".jsx", ".mjs")

SCALE = {"11", "12", "13", "15", "16.5", "18", "22", "30", "46", "76"}
FS = {
    "--fs-11": "11px",
    "--fs-12": "12px",
    "--fs-13": "13px",
    "--fs-15": "15px",
    "--fs-16-5": "16.5px",
    "--fs-18": "18px",
    "--fs-22": "22px",
    "--fs-30": "30px",
    "--fs-46": "46px",
    "--fs-76": "76px",
}
FSVAR = r"var\(--fs-(?:11|12|13|15|16-5|18|22|30|46|76)\)"

# D = 类名左边界；V = variants 链；R = 类名右边界。
D = r"""(?<![^\s"'`{}(!])"""
V = r"""(?:[^\s"'`{}(]*?:)?"""
R = r"""(?=$|[\s"'`{}),;!/$])"""

SHADCN = (
    r"(?:background|foreground|card(?:-foreground)?|popover(?:-foreground)?|primary(?:-foreground)?|secondary(?:-foreground)?"
    r"|muted(?:-foreground)?|accent(?:-foreground)?|destructive|border|input|ring|sidebar(?:-[a-z-]+)?)"
)
COLOR_UTILS = (
    r"(?:text|bg|border(?:-[trblxyse])?|ring(?:-offset)?|outline|fill|stroke|divide|placeholder|caret|accent|decoration|from|via|to)"
)
LEGACY = r"(?:amber-ink|rec-soft|rec|dim|glass-border|glass-strong|glass-hi|shadow|sidebar[\w-]*)"
TYPE_WORDS = (
    "number",
    "string",
    "undefined",
    "null",
    "boolean",
    "any",
    "unknown",
    "React.",
    "CSSProperties",
    "Property.",
)

# 每条规则：(编号, 说明, 正则, 适用扩展名, 是否逐行扫描)
RULES = (
    (
        "F1",
        "text-[…] 方括号只许 color: 开头（任意值字号、length:、var(--fs-*) 当颜色都算）",
        re.compile(D + V + r"!?text-\[(?!color:)"),
        EXTS,
        True,
    ),
    (
        "F2",
        "禁止 text-(…) 圆括号写法",
        re.compile(D + V + r"!?text-\("),
        EXTS,
        True,
    ),
    (
        "F3",
        "具名字号 text-xs/sm/base/lg/xl/2xl…9xl",
        re.compile(D + V + r"!?text-(?:xs|sm|base|lg|xl|[2-9]xl)" + R),
        EXTS,
        True,
    ),
    (
        "F4",
        "任意属性 [font-size:…] / [font:…] 一律禁止",
        re.compile(r"\[(?:font-size|font)\s*:"),
        EXTS,
        True,
    ),
    (
        "F5",
        '拼接字号类 text-${ / text-[${ / "text-" +',
        re.compile(D + V + r"""text-\[?\$\{|["']text-\[?["']\s*\+|`text-\[?`"""),
        EXTS,
        True,
    ),
    (
        "F6",
        "字号类紧贴 ${",
        re.compile(D + V + r"!?text-(?:\[[^\]\s]*\]|\([^)\s]*\)|[a-z0-9][a-z0-9.\-]*)(?:/[^\s$]+)?\$\{"),
        EXTS,
        True,
    ),
    (
        "F7",
        '行内 fontSize / font 的值必须恰为 "var(--fs-*)" 之一',
        re.compile(
            r"""(?<![\w$.-])(?:["']?(?:fontSize|font)["']?\s*:\s*(?P<val>[^,}\n]+)|fontSize\s*=\s*(?P<attr>"[^"]*"|'[^']*'|\{[^}]*\}))"""
        ),
        JS_EXTS,
        True,
    ),
    (
        "F8",
        "<small>/<sub>/<sup> 开标签（可跨行）里没有 text-fs-*",
        re.compile(r"<(?:small|sub|sup)\b[^>]*>"),
        (".tsx", ".jsx"),
        False,
    ),
    (
        "F9",
        "CSS 的 font-size / font（整文件、忽略大小写、可跨行）不是 var(--fs-*) 之一",
        re.compile(r"(?<![\w-])(?:font-size|font)\s*:\s*(?P<val>[^;}]+)", re.I),
        (".css",),
        False,
    ),
    (
        "F10",
        "text-fs-<值> 不在字阶里（如 text-fs-14、text-fs-16-5）",
        re.compile(D + V + r"!?text-fs-(?P<val>[0-9A-Za-z.\-]+)" + R),
        EXTS,
        True,
    ),
    (
        "K1",
        "text-muted-foreground",
        re.compile(D + V + r"!?text-muted-foreground" + R),
        EXTS,
        True,
    ),
    (
        "K2",
        "全部 shadcn 语义颜色类（含 K1）",
        re.compile(
            D + V + r"!?" + COLOR_UTILS + r"-" + SHADCN + r"(?:/[\w.\[\]%()-]+)?" + R
        ),
        EXTS,
        True,
    ),
    (
        "K3",
        "遗留变量名（使用或定义）",
        re.compile(r"var\(\s*--" + LEGACY + r"\s*[,)]|(?:^|[;{\s])--" + LEGACY + r"\s*:"),
        EXTS,
        True,
    ),
    (
        "K4",
        "TS/TSX 里直接引用 shadcn 别名变量",
        re.compile(r"var\(\s*--" + SHADCN + r"\s*[,)]"),
        JS_EXTS,
        True,
    ),
    (
        "K5",
        "B 式颜色写法 util-[var(--x)]，必须写成 [color:var(--x)]",
        re.compile(D + V + r"!?" + COLOR_UTILS + r"-\[var\(\s*--(?!fs-)[\w-]+\s*[,)]"),
        EXTS,
        True,
    ),
    (
        "K6",
        "颜色工具的圆括号写法 util-(…) 一律禁止",
        re.compile(D + V + r"!?" + COLOR_UTILS + r"-\("),
        EXTS,
        True,
    ),
    (
        "R2",
        "--ink3 / --dim 当文字色",
        re.compile(
            r"""text-\[(?:color:)?var\(--(?:ink3|dim)\)\]|text-\((?:color:)?--(?:ink3|dim)\)|(?<![\w\-\[])color\s*:\s*["'`]?var\(--(?:ink3|dim)\)"""
        ),
        EXTS,
        True,
    ),
    (
        "R3",
        "var(--stamp) 只许出现在两处：globals.css 的 --seal-soft 定义、Seal.tsx 的 fill",
        re.compile(r"var\(\s*--stamp\s*[,)]"),
        EXTS,
        True,
    ),
    (
        "R4",
        "文字色带透明度后缀（/N、/[…]、/(…)）",
        re.compile(
            D
            + V
            + r"!?text-(?:\[color:var\(--[\w-]+\)\]|\((?:color:)?--[\w-]+\)|(?:muted-)?foreground)/(?:\d+|\[[^\]]+\]|\([^)]+\))"
        ),
        EXTS,
        True,
    ),
)

RULE_BY_ID = {rule[0]: rule for rule in RULES}
FONT_RULES = ("F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "F10")
COLOR_RULES = ("K1", "K2", "K3", "K4", "K5", "K6")
ROLE_RULES = ("R2", "R3", "R4")


def _strip_css_comments(text):
    """把 CSS 注释替换成等长空白，保留换行，避免行号漂移。"""
    return re.sub(
        r"/\*.*?\*/",
        lambda match: re.sub(r"[^\n]", " ", match.group(0)),
        text,
        flags=re.S,
    )


def _scan_files(root=ROOT):
    """返回扫描面内的相对路径，排序后去掉 components/ui 原件。"""
    found = []
    for directory in SCAN_DIRS:
        for base, dirs, names in os.walk(root / directory):
            dirs[:] = [name for name in dirs if name not in ("node_modules", ".next")]
            for name in names:
                if name.endswith(EXTS):
                    rel = (Path(base) / name).relative_to(root).as_posix()
                    found.append(rel)
    return sorted(rel for rel in found if not rel.startswith(EXEMPT_PREFIX))


def _load_sources(root=ROOT):
    return [
        (rel, (root / rel).read_text(encoding="utf-8"))
        for rel in _scan_files(root)
    ]


def _count_hits(sources):
    """按参考实现的扫描方式返回 {规则: [(路径, 行号, 命中文本, 该行)]}。"""
    hits = {rule[0]: [] for rule in RULES}
    for rel, raw in sources:
        text = _strip_css_comments(raw) if rel.endswith(".css") else raw
        lines = text.splitlines()
        for rid, _desc, rx, exts, per_line in RULES:
            if not rel.endswith(exts):
                continue
            if per_line:
                units = list(enumerate(lines, 1))
            else:
                units = [(1, text)]
            for line_no, unit in units:
                for match in rx.finditer(unit):
                    at = line_no if per_line else text.count("\n", 0, match.start()) + 1
                    line = lines[at - 1] if at - 1 < len(lines) else ""
                    if rid == "F7":
                        val = (match.group("val") or match.group("attr") or "").strip()
                        val = val.rstrip(";").strip()
                        if re.fullmatch(
                            r"""\{?\s*["'`]""" + FSVAR + r"""["'`]\s*\}?""", val
                        ):
                            continue
                        if val.startswith(TYPE_WORDS):
                            continue
                        if rel == "frontend/components/Seal.tsx" and val == '"30"':
                            continue
                    elif rid == "F8" and "text-fs-" in match.group(0):
                        continue
                    elif rid == "F9":
                        val = re.sub(r"\s+", " ", match.group("val")).strip()
                        if re.fullmatch(FSVAR + r"(?: !important)?", val):
                            continue
                        if val in ("inherit", "max(var(--fs-16-5), 1em)"):
                            continue
                    elif rid == "F10" and match.group("val").rstrip(".") in SCALE:
                        continue
                    elif rid == "R3":
                        if (
                            rel == "frontend/app/globals.css"
                            and line.strip()
                            == "--seal-soft: color-mix(in srgb, var(--stamp) 12%, transparent);"
                        ):
                            continue
                        if rel == "frontend/components/Seal.tsx" and 'fill="var(--stamp)"' in line:
                            continue
                    hits[rid].append((rel, at, match.group(0), line))
    return hits


def _rule_report(hits, rule_ids):
    lines = []
    failed = 0
    for rid in rule_ids:
        found = hits[rid]
        if found:
            failed += 1
        lines.append(f"{'FAIL' if found else 'PASS'} {rid} 命中 {len(found)} 处")
        for rel, line_no, match, _line in found[:3]:
            lines.append(f"    {rel}:{line_no}  {match[:60]!r}")
    return failed, "\n".join(lines)


def _assert_no_hits(hits, rule_ids, title):
    failed, report = _rule_report(hits, rule_ids)
    assert failed == 0, f"{title}未通过（{failed} 条规则有命中）：\n{report}"


# ---- 令牌层：按花括号深度切块 ----
def _parse_blocks(css):
    """按花括号深度切块，返回顶层节点列表；节点含 prelude/decls/children/line。"""
    css = _strip_css_comments(css)
    root = {"prelude": "", "decls": "", "children": [], "line": 0}
    stack, buf, index, quote = [root], [], 0, None
    while index < len(css):
        char = css[index]
        if quote:
            buf.append(char)
            if char == quote:
                quote = None
        elif char in "\"'":
            quote = char
            buf.append(char)
        elif char == "{":
            node = {
                "prelude": re.sub(r"\s+", " ", "".join(buf)).strip(),
                "decls": "",
                "children": [],
                "line": css.count("\n", 0, index) + 1,
            }
            stack[-1]["children"].append(node)
            stack.append(node)
            buf = []
        elif char == "}":
            stack[-1]["decls"] += "".join(buf)
            buf = []
            stack.pop()
        elif char == ";":
            stack[-1]["decls"] += "".join(buf) + ";"
            buf = []
        else:
            buf.append(char)
        index += 1
    return root["children"]


def _decls_of(node):
    out = {}
    for declaration in node["decls"].split(";"):
        if ":" in declaration:
            key, value = declaration.split(":", 1)
            out.setdefault(key.strip(), []).append(re.sub(r"\s+", " ", value).strip())
    return out


def _walk(nodes, ancestors=()):
    for node in nodes:
        yield node, ancestors
        yield from _walk(node["children"], ancestors + (node,))


def _token_layer(css_text):
    """返回令牌层 T1–T8 的 {断言名: 是否通过}，按花括号块逐块判断。"""
    top = _parse_blocks(css_text)
    res = {}
    roots = [node for node in top if node["prelude"] == ":root"]

    def by(prelude):
        return [node for node in top if node["prelude"] == prelude]

    day, alias = (roots + [None, None])[:2]
    night = (by(".dark") + [None])[0]
    day_solid = (by(":root[data-solid]") + [None])[0]
    night_solid = (by(".dark[data-solid]") + [None])[0]
    later_dark = by(".dark")[1:]

    # T1：10 个 --fs-* 只在别名 :root 里，各一次，值正确，没有别的 --fs-*。
    fsdefs = [
        (node, key, value)
        for node, _ancestors in _walk(top)
        for key, values in _decls_of(node).items()
        if key.startswith("--fs-")
        for value in values
    ]
    res["T1 10 个 --fs-* 只定义在别名 :root、各一次、值正确"] = (
        alias is not None
        and sorted(key for _node, key, _value in fsdefs) == sorted(FS)
        and all(node is alias and FS.get(key) == value for node, key, value in fsdefs)
    )

    # T2：@theme inline 内登记 10 个 --text-fs-*，四档行高精确，块外没有。
    theme = by("@theme inline")
    theme_decls = _decls_of(theme[0]) if len(theme) == 1 else {}
    want = {
        "--text-fs-" + key[5:].replace("16-5", "16" + chr(92) + ".5"): "var(" + key + ")"
        for key in FS
    }
    line_heights = {
        "--text-fs-12--line-height": "calc(16 / 12)",
        "--text-fs-13--line-height": "calc(20 / 13)",
        "--text-fs-15--line-height": "1.5",
        "--text-fs-22--line-height": "calc(28 / 22)",
    }
    inside = {
        key: value
        for key, value in theme_decls.items()
        if key.startswith("--text-fs-")
    }
    outside = [
        key
        for node, _ancestors in _walk(top)
        if not (theme and node is theme[0])
        for key in _decls_of(node)
        if key.startswith("--text-fs-")
    ]
    res["T2 @theme inline 内登记 10 个 --text-fs-*、四档行高精确、块外没有"] = (
        len(theme) == 1
        and not outside
        and set(inside) == set(want) | set(line_heights)
        and all(
            inside[key] == [value]
            for key, value in {**want, **line_heights}.items()
        )
    )

    # T3：四套主题逐块取值正确，四个主题块键集合相同，别名与后面的 .dark 不定义颜色。
    def val(node, key):
        return (_decls_of(node).get(key) or [None])[-1] if node else None

    checked = (
        "--ink",
        "--ink2",
        "--ink3",
        "--seal",
        "--stamp",
        "--paper",
        "--hi",
        "--slip",
        "--glass",
        "--glass2",
        "--chip",
        "--tile",
        "--mount",
        "--btn",
        "--btnink",
        "--glyph",
    )
    themes = [day, night, day_solid, night_solid]
    res["T3 四套主题逐块取值正确、键集合相同"] = (
        all(themes)
        and len({frozenset(_decls_of(node)) for node in themes}) == 1
        and all(
            val(node, "--ink3") == "#6F7C76"
            and val(node, "--seal") == "#A8322A"
            and val(node, "--stamp") == "#A8322A"
            for node in (day, day_solid)
        )
        and all(
            val(node, "--seal") == "#E56F5D" and val(node, "--stamp") == "#BF4537"
            for node in (night, night_solid)
        )
        and not [
            key
            for node in [alias] + later_dark
            if node
            for key in _decls_of(node)
            if key in checked
        ]
    )

    # T4：--seal-soft 只在别名 :root 定义一次，为 --stamp 的 12%。
    soft = [
        (node, value)
        for node, _ancestors in _walk(top)
        for key, values in _decls_of(node).items()
        if key == "--seal-soft"
        for value in values
    ]
    res["T4 --seal-soft 只在别名 :root 定义一次，为 --stamp 的 12%"] = (
        len(soft) == 1
        and soft[0][0] is alias
        and soft[0][1] == "color-mix(in srgb, var(--stamp) 12%, transparent)"
    )

    # T5：手机输入框护栏的选择器、外层 @media 与 @layer 位置。
    guard = [
        (node, ancestors)
        for node, ancestors in _walk(top)
        if "max(var(--fs-16-5), 1em)" in _decls_of(node).get("font-size", [])
    ]
    selectors = [f':root:not([data-shell="desktop"]) {name}' for name in ("input", "textarea", "select")]
    res["T5 手机输入框护栏：选择器三项、在顶层 @media (width < 48rem) 里、不进 @layer"] = (
        len(guard) == 1
        and [item.strip() for item in guard[0][0]["prelude"].split(",")] == selectors
        and len(guard[0][1]) == 1
        and guard[0][1][0]["prelude"] == "@media (width < 48rem)"
        and not any(item["prelude"].startswith("@layer") for item in guard[0][1])
    )

    # T6/T7：第一个 @layer base 的直接子规则。
    base = by("@layer base")
    placeholder = (
        [child for child in base[0]["children"] if child["prelude"] == "::placeholder"]
        if base
        else []
    )
    res["T6 ::placeholder { color: var(--ink2) } 在第一个 @layer base 里"] = (
        len(placeholder) == 1
        and _decls_of(placeholder[0]) == {"color": ["var(--ink2)"]}
    )
    body = [child for child in base[0]["children"] if child["prelude"] == "body"] if base else []
    res["T7 body 规则块里 font-size: var(--fs-16-5)"] = (
        len(body) == 1
        and _decls_of(body[0]).get("font-size") == ["var(--fs-16-5)"]
    )

    # T8：两个对话框的遮罩用 var(--scrim)，带原来的颜色作兜底；旧版 Safari 的 ::backdrop 取不到 :root 变量。
    want_backdrop = {
        ".image-preview-dialog::backdrop": "var(--scrim, rgba(31,41,38,.18))",
        ".dark .image-preview-dialog::backdrop": "var(--scrim, rgba(0,0,0,.45))",
        ".confirm-dialog::backdrop": "var(--scrim, rgba(31,41,38,.18))",
        ".dark .confirm-dialog::backdrop": "var(--scrim, rgba(0,0,0,.45))",
    }
    got_backdrop = {}
    for node, _ancestors in _walk(top):
        if node["prelude"].endswith("::backdrop"):
            got_backdrop.setdefault(node["prelude"], []).extend(
                _decls_of(node).get("background", [])
            )
    res["T8 两个对话框的 ::backdrop 用 var(--scrim) 并带兜底色，昼夜各一条"] = (
        got_backdrop
        == {selector: [value] for selector, value in want_backdrop.items()}
    )
    return res


# ---- 分组门禁 ----
def test_font_size_rules():
    sources = _load_sources()
    assert len(sources) >= 130, f"扫描文件数不足 130：只找到 {len(sources)} 个"
    _assert_no_hits(_count_hits(sources), FONT_RULES, "字号规则")


def test_color_rules():
    sources = _load_sources()
    assert len(sources) >= 130, f"扫描文件数不足 130：只找到 {len(sources)} 个"
    _assert_no_hits(_count_hits(sources), COLOR_RULES, "颜色规则")


def test_role_rules():
    sources = _load_sources()
    assert len(sources) >= 130, f"扫描文件数不足 130：只找到 {len(sources)} 个"
    _assert_no_hits(_count_hits(sources), ROLE_RULES, "角色规则")


def test_token_layer():
    files = _scan_files()
    assert len(files) >= 130, f"扫描文件数不足 130：只找到 {len(files)} 个"
    css = (ROOT / "frontend/app/globals.css").read_text(encoding="utf-8")
    result = _token_layer(css)
    report = "\n".join(
        f"{'PASS' if passed else 'FAIL'} {name}" for name, passed in result.items()
    )
    assert all(result.values()), f"令牌层未通过：\n{report}"


# ---- 自检：每条规则一个会命中的坏样本、一个不误伤的好样本 ----
def _selfcheck_sources(cases):
    for rid, rel, bad, good in cases:
        hits = _count_hits([(rel, bad)])
        assert hits[rid], f"自检失败：{rid} 坏样本没有命中：{bad!r}"
        hits = _count_hits([(rel, good)])
        assert not hits[rid], f"自检失败：{rid} 好样本被误伤：{hits[rid][:3]!r}"


def test_selfcheck_source_rules():
    required_good = (
        '<div className="text-fs-30! mobile:text-fs-22 @[640px]:text-fs-15 text-fs-16.5" />\n'
        '<div className="text-fs-22 leading-[inherit]" />\n'
        '<div className="text-fs-15 text-pretty" />\n'
        '// 句末的英文句点不算进值：text-fs-12.'
    )
    cases = [
        ("F1", "frontend/components/SelfCheck.tsx", '<div className="text-[14px]" />', '<div className="text-[color:var(--ink2)]" />'),
        ("F2", "frontend/components/SelfCheck.tsx", '<div className="text-(--ink2)" />', '<div className="text-[color:var(--ink2)]" />'),
        ("F3", "frontend/components/SelfCheck.tsx", '<div className="max-md:text-sm" />', '<div className="max-md:text-fs-15" />'),
        ("F4", "frontend/components/SelfCheck.tsx", '<div className="[font-size:14px]" />', '<div className="font-medium" />'),
        ("F5", "frontend/components/SelfCheck.tsx", '<div className={`text-[${x}]`} />', '<div className={`text-fs-15 ${x}`} />'),
        ("F6", "frontend/components/SelfCheck.tsx", '<div className={`text-fs-13${x}`} />', '<div className={`text-fs-13 ${x}`} />'),
        ("F7", "frontend/components/SelfCheck.tsx", "const style = { fontSize: 14 };", 'const style = { fontSize: "var(--fs-13)" };'),
        ("F8", "frontend/components/SelfCheck.tsx", '<small className="x">说明</small>', '<small className="text-fs-11">说明</small>'),
        ("F9", "frontend/app/selfcheck.css", ".zz { font-size: 14px; }\n.ff { font: 14px/1.5 serif; }", ".ok { font-size: var(--fs-13); }\n.inherit { font-size: inherit; }\n.guard { font-size: max(var(--fs-16-5), 1em); }\n/* .old { font-size: 14px; } */"),
        ("F10", "frontend/components/SelfCheck.tsx", '<div className="text-fs-14" />', required_good),
        ("K1", "frontend/components/SelfCheck.tsx", '<div className="text-muted-foreground" />', '<div className="text-[color:var(--ink2)]" />'),
        ("K2", "frontend/components/SelfCheck.tsx", '<div className="hover:bg-secondary/50" />', '<div className="hover:bg-[color:var(--slip)]/50" />'),
        ("K3", "frontend/components/SelfCheck.tsx", 'const old = "var(--rec)";\nconst shell = { "--amber-ink": "var(--ink)" };', 'const ok = "var(--seal)";'),
        ("K4", "frontend/components/SelfCheck.ts", 'const old = "var(--ring)";', 'const ok = "var(--ink)";'),
        ("K5", "frontend/components/SelfCheck.tsx", '<div className="text-[var(--ink2)]" />', '<div className="text-[color:var(--ink2)]" />'),
        ("K6", "frontend/components/SelfCheck.tsx", '<div className="bg-(--slip)" />', '<div className="bg-[color:var(--slip)]" />'),
        ("R2", "frontend/components/SelfCheck.tsx", '<div className="text-[color:var(--ink3)]" />', '<div className="text-[color:var(--ink2)]" />'),
        ("R4", "frontend/components/SelfCheck.tsx", '<div className="text-[color:var(--ink)]/60" />', '<div className="text-[color:var(--ink)]" />'),
    ]
    _selfcheck_sources(cases)

    # 规格 T3 总则列出的合法写法不能被任何一条源码规则误伤。
    assert not any(
        _count_hits([("frontend/components/SelfCheck.tsx", required_good)]).values()
    ), "自检失败：规格 T3 总则的合法写法被某条规则误伤"

    # R3：非 Seal 组件里写 var(--stamp) 要命中，两处原文放行。
    assert _count_hits(
        [("frontend/components/NotSeal.tsx", '<rect fill="var(--stamp)" />')]
    )["R3"], "自检失败：R3 坏样本没有命中"

    # F7 的类型声明、JSX 属性与 Seal.tsx 白名单属于合法写法。
    good_f7 = [
        ("frontend/components/SelfCheck.tsx", "const style: { fontSize: number } = {};"),
        ("frontend/components/SelfCheck.tsx", '<div style={{ fontSize: "var(--fs-13)" }} />'),
        ("frontend/components/Seal.tsx", '<text fontSize="30">印</text>'),
    ]
    for rel, text in good_f7:
        assert not _count_hits([(rel, text)])["F7"], f"自检失败：F7 好样本被误伤：{text!r}"

    # R3 只放行两处原文。
    good_r3 = [
        (
            "frontend/app/globals.css",
            "  --seal-soft: color-mix(in srgb, var(--stamp) 12%, transparent);",
        ),
        ("frontend/components/Seal.tsx", '<rect x="2" y="2" fill="var(--stamp)"/>'),
    ]
    assert not _count_hits(good_r3)["R3"], "自检失败：R3 白名单里的两处被误伤"


def _selfcheck_theme(prelude, overrides):
    values = {
        "--ink": "#1F2926",
        "--ink2": "#56635E",
        "--paper": "#F5F1E8",
        "--hi": "#EFE9DD",
        "--slip": "#E9E2D4",
        "--glass": "#F8F4EC",
        "--glass2": "#F2EDE3",
        "--chip": "#E4DCCD",
        "--tile": "#FBF8F1",
        "--mount": "#EDE7DA",
        "--btn": "#1F2926",
        "--btnink": "#F4F7F4",
        "--glyph": "#F6F1E8",
    }
    values.update(overrides)
    body = " ".join(f"{key}: {value};" for key, value in values.items())
    return f"{prelude} {{ {body} }}"


def _selfcheck_token_css():
    day = _selfcheck_theme(
        ":root",
        {"--ink3": "#6F7C76", "--seal": "#A8322A", "--stamp": "#A8322A"},
    )
    night = _selfcheck_theme(
        ".dark",
        {"--ink3": "#78726A", "--seal": "#E56F5D", "--stamp": "#BF4537"},
    )
    day_solid = _selfcheck_theme(
        ":root[data-solid]",
        {"--ink3": "#6F7C76", "--seal": "#A8322A", "--stamp": "#A8322A"},
    )
    night_solid = _selfcheck_theme(
        ".dark[data-solid]",
        {"--ink3": "#78726A", "--seal": "#E56F5D", "--stamp": "#BF4537"},
    )
    alias = r"""
:root {
  --fs-11: 11px; --fs-12: 12px; --fs-13: 13px; --fs-15: 15px; --fs-16-5: 16.5px;
  --fs-18: 18px; --fs-22: 22px; --fs-30: 30px; --fs-46: 46px; --fs-76: 76px;
  --seal-soft: color-mix(in srgb, var(--stamp) 12%, transparent);
}
"""
    theme = r"""
@theme inline {
  --text-fs-11: var(--fs-11);
  --text-fs-12: var(--fs-12);
  --text-fs-12--line-height: calc(16 / 12);
  --text-fs-13: var(--fs-13);
  --text-fs-13--line-height: calc(20 / 13);
  --text-fs-15: var(--fs-15);
  --text-fs-15--line-height: 1.5;
  --text-fs-16\.5: var(--fs-16-5);
  --text-fs-18: var(--fs-18);
  --text-fs-22: var(--fs-22);
  --text-fs-22--line-height: calc(28 / 22);
  --text-fs-30: var(--fs-30);
  --text-fs-46: var(--fs-46);
  --text-fs-76: var(--fs-76);
}
"""
    base = r"""
@layer base {
  ::placeholder { color: var(--ink2); }
  body { font-family: var(--font-sans-stack); font-size: var(--fs-16-5); }
}
"""
    dialogs = r"""
@layer components {
  .image-preview-dialog::backdrop { background:var(--scrim, rgba(31,41,38,.18)); }
  .dark .image-preview-dialog::backdrop { background:var(--scrim, rgba(0,0,0,.45)); }
  .confirm-dialog::backdrop { background:var(--scrim, rgba(31,41,38,.18)); }
  .dark .confirm-dialog::backdrop { background:var(--scrim, rgba(0,0,0,.45)); }
}
"""
    guard = r"""
@media (width < 48rem) {
  :root:not([data-shell="desktop"]) input, :root:not([data-shell="desktop"]) textarea, :root:not([data-shell="desktop"]) select { font-size: max(var(--fs-16-5), 1em); }
}
"""
    return "\n".join((day, night, day_solid, night_solid, alias, theme, base, dialogs, guard))


def test_selfcheck_token_layer():
    css = _selfcheck_token_css()
    result = _token_layer(css)
    assert all(result.values()), "自检失败：合法的令牌层样本未通过：\n" + "\n".join(
        f"{'PASS' if passed else 'FAIL'} {name}" for name, passed in result.items()
    )

    # T1：字号令牌值写错。
    bad = css.replace("--fs-13: 13px;", "--fs-13: 14px;")
    assert not _token_layer(bad)["T1 10 个 --fs-* 只定义在别名 :root、各一次、值正确"]

    # T2：13 档行高被改成 1.4。
    bad = css.replace(
        "--text-fs-13--line-height: calc(20 / 13);",
        "--text-fs-13--line-height: 1.4;",
    )
    assert not _token_layer(bad)["T2 @theme inline 内登记 10 个 --text-fs-*、四档行高精确、块外没有"]

    # T3：昼主题 --seal 值写错。
    bad = css.replace("--seal: #A8322A;", "--seal: #A8322B;", 1)
    assert not _token_layer(bad)["T3 四套主题逐块取值正确、键集合相同"]

    # T4：--seal-soft 的 mix 比例写错。
    bad = css.replace(
        "--seal-soft: color-mix(in srgb, var(--stamp) 12%, transparent);",
        "--seal-soft: color-mix(in srgb, var(--stamp) 20%, transparent);",
    )
    assert not _token_layer(bad)["T4 --seal-soft 只在别名 :root 定义一次，为 --stamp 的 12%"]

    # T5：护栏选择器少一项。
    bad = css.replace(" input, :root:not([data-shell=\"desktop\"]) textarea", "")
    assert not _token_layer(bad)["T5 手机输入框护栏：选择器三项、在顶层 @media (width < 48rem) 里、不进 @layer"]

    # T6：默认占位符颜色不是 --ink2。
    bad = css.replace("::placeholder { color: var(--ink2); }", "::placeholder { color: var(--ink3); }")
    assert not _token_layer(bad)["T6 ::placeholder { color: var(--ink2) } 在第一个 @layer base 里"]

    # T7：body 没有字号。
    bad = css.replace(
        "body { font-family: var(--font-sans-stack); font-size: var(--fs-16-5); }",
        "body { font-family: var(--font-sans-stack); }",
    )
    assert not _token_layer(bad)["T7 body 规则块里 font-size: var(--fs-16-5)"]

    # T8：遮罩的兜底色被去掉，旧版 Safari 的 ::backdrop 会变透明。
    bad = css.replace("var(--scrim, rgba(31,41,38,.18))", "var(--scrim)").replace(
        "var(--scrim, rgba(0,0,0,.45))", "var(--scrim)"
    )
    assert not _token_layer(bad)["T8 两个对话框的 ::backdrop 用 var(--scrim) 并带兜底色，昼夜各一条"]
