"""第四批源码规则（T3-1 的参考实现，Claude 的门禁用的就是它）：python3 -I gate_rules.py <仓库根>

退出码 = 失败项数。每条规则打印命中数与前两处。
新测试要把这些规则写进测试文件本身，不得 import、执行或读取本文件。
"""
import os, re, sys

ROOT = os.path.abspath(sys.argv[1])
SCAN = ("frontend/app", "frontend/components", "frontend/lib")
EXEMPT = "frontend/components/ui/"
EXTS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".css")
JS = (".ts", ".tsx", ".js", ".jsx", ".mjs")
SCALE = {"11", "12", "13", "15", "16.5", "18", "22", "30", "46", "76"}
FS = {"--fs-11": "11px", "--fs-12": "12px", "--fs-13": "13px", "--fs-15": "15px", "--fs-16-5": "16.5px",
      "--fs-18": "18px", "--fs-22": "22px", "--fs-30": "30px", "--fs-46": "46px", "--fs-76": "76px"}
FSVAR = r"var\(--fs-(?:11|12|13|15|16-5|18|22|30|46|76)\)"
D = r"""(?<![^\s"'`{}(!])"""            # 类名左边界
V = r"""(?:[^\s"'`{}(]*?:)?"""          # variants 链，如 max-md: / @[640px]: / [&_p]:
R = r"""(?=$|[\s"'`{}),;!/$])"""        # 类名右边界
SHADCN = (r"(?:background|foreground|card(?:-foreground)?|popover(?:-foreground)?|primary(?:-foreground)?|secondary(?:-foreground)?"
          r"|muted(?:-foreground)?|accent(?:-foreground)?|destructive|border|input|ring|sidebar(?:-[a-z-]+)?)")
COLOR_UTILS = r"(?:text|bg|border(?:-[trblxyse])?|ring(?:-offset)?|outline|fill|stroke|divide|placeholder|caret|accent|decoration|from|via|to)"
LEGACY = r"(?:amber-ink|rec-soft|rec|dim|glass-border|glass-strong|glass-hi|shadow|sidebar[\w-]*)"
TYPE_WORDS = ("number", "string", "undefined", "null", "boolean", "any", "unknown", "React.", "CSSProperties", "Property.")

# (编号, 说明, 正则, 适用扩展名, 逐行=True / 整文件=False)
RULES = [
    ("F1", "text-[…] 方括号只许 color: 开头（任意值字号、length:、var(--fs-*) 当颜色都算）", re.compile(D + V + r"!?text-\[(?!color:)"), EXTS, True),
    ("F2", "禁止 text-(…) 圆括号写法", re.compile(D + V + r"!?text-\("), EXTS, True),
    ("F3", "具名字号 text-xs/sm/base/lg/xl/2xl…9xl", re.compile(D + V + r"!?text-(?:xs|sm|base|lg|xl|[2-9]xl)" + R), EXTS, True),
    ("F4", "任意属性 [font-size:…] / [font:…] 一律禁止", re.compile(r"\[(?:font-size|font)\s*:"), EXTS, True),
    ("F5", "拼接字号类 text-${ / text-[${ / \"text-\" +", re.compile(D + V + r"""text-\[?\$\{|["']text-\[?["']\s*\+|`text-\[?`"""), EXTS, True),
    ("F6", "字号类紧贴 ${", re.compile(D + V + r"!?text-(?:\[[^\]\s]*\]|\([^)\s]*\)|[a-z0-9][a-z0-9.\-]*)(?:/[^\s$]+)?\$\{"), EXTS, True),
    ("F7", "行内 fontSize / font 的值必须恰为 \"var(--fs-*)\" 之一", re.compile(
        r"""(?<![\w$.-])(?:["']?(?:fontSize|font)["']?\s*:\s*(?P<val>[^,}\n]+)|fontSize\s*=\s*(?P<attr>"[^"]*"|'[^']*'|\{[^}]*\}))"""), JS, True),
    ("F8", "<small>/<sub>/<sup> 开标签（可跨行）里没有 text-fs-*", re.compile(r"<(?:small|sub|sup)\b[^>]*>"), (".tsx", ".jsx"), False),
    ("F9", "CSS 的 font-size / font（整文件、忽略大小写、可跨行）不是 var(--fs-*) 之一", re.compile(r"(?<![\w-])(?:font-size|font)\s*:\s*(?P<val>[^;}]+)", re.I), (".css",), False),
    ("F10", "text-fs-<值> 不在字阶里（如 text-fs-14、text-fs-16-5）", re.compile(D + V + r"!?text-fs-(?P<val>[0-9A-Za-z.\-]+)" + R), EXTS, True),
    ("K1", "text-muted-foreground", re.compile(D + V + r"!?text-muted-foreground" + R), EXTS, True),
    ("K2", "全部 shadcn 语义颜色类（含 K1）", re.compile(D + V + r"!?" + COLOR_UTILS + r"-" + SHADCN + r"(?:/[\w.\[\]%()-]+)?" + R), EXTS, True),
    ("K3", "遗留变量名（使用或定义）", re.compile(r"var\(\s*--" + LEGACY + r"\s*[,)]|(?:^|[;{\s])--" + LEGACY + r"\s*:"), EXTS, True),
    ("K4", "TS/TSX 里直接引用 shadcn 别名变量", re.compile(r"var\(\s*--" + SHADCN + r"\s*[,)]"), JS, True),
    ("K5", "B 式颜色写法 util-[var(--x)]，必须写成 [color:var(--x)]", re.compile(D + V + r"!?" + COLOR_UTILS + r"-\[var\(\s*--(?!fs-)[\w-]+\s*[,)]"), EXTS, True),
    ("K6", "颜色工具的圆括号写法 util-(…) 一律禁止", re.compile(D + V + r"!?" + COLOR_UTILS + r"-\("), EXTS, True),
    ("R2", "--ink3 / --dim 当文字色", re.compile(
        r"""text-\[(?:color:)?var\(--(?:ink3|dim)\)\]|text-\((?:color:)?--(?:ink3|dim)\)|(?<![\w\-\[])color\s*:\s*["'`]?var\(--(?:ink3|dim)\)"""), EXTS, True),
    ("R3", "var(--stamp) 只许出现在两处：globals.css 的 --seal-soft 定义、Seal.tsx 的 fill", re.compile(r"var\(\s*--stamp\s*[,)]"), EXTS, True),
    ("R4", "文字色带透明度后缀（/N、/[…]、/(…)）", re.compile(
        D + V + r"!?text-(?:\[color:var\(--[\w-]+\)\]|\((?:color:)?--[\w-]+\)|(?:muted-)?foreground)/(?:\d+|\[[^\]]+\]|\([^)]+\))"), EXTS, True),
]


def strip_css_comments(s):
    return re.sub(r"/\*.*?\*/", lambda m: re.sub(r"[^\n]", " ", m.group(0)), s, flags=re.S)


def files():
    out = []
    for d in SCAN:
        for base, dirs, names in os.walk(os.path.join(ROOT, d)):
            dirs[:] = [x for x in dirs if x not in ("node_modules", ".next")]
            out += [os.path.relpath(os.path.join(base, n), ROOT) for n in names if n.endswith(EXTS)]
    return sorted(f for f in out if not f.startswith(EXEMPT))


def scan():
    hits = {r[0]: [] for r in RULES}
    fl = files()
    for f in fl:
        text = open(os.path.join(ROOT, f), encoding="utf-8").read()
        if f.endswith(".css"):
            text = strip_css_comments(text)
        lines = text.splitlines()
        for rid, _desc, rx, exts, per_line in RULES:
            if not f.endswith(exts):
                continue
            units = [(i, l) for i, l in enumerate(lines, 1)] if per_line else [(1, text)]
            for ln, unit in units:
                for m in rx.finditer(unit):
                    at = ln if per_line else text.count("\n", 0, m.start()) + 1
                    line = lines[at - 1] if at - 1 < len(lines) else ""
                    if rid == "F7":
                        val = (m.group("val") or m.group("attr") or "").strip().rstrip(";").strip()
                        if re.fullmatch(r"""\{?\s*["'`]""" + FSVAR + r"""["'`]\s*\}?""", val): continue
                        if val.startswith(TYPE_WORDS): continue
                        if f == "frontend/components/Seal.tsx" and val == '"30"': continue
                    if rid == "F8" and "text-fs-" in m.group(0): continue
                    if rid == "F9":
                        val = re.sub(r"\s+", " ", m.group("val")).strip()
                        if re.fullmatch(FSVAR + r"(?: !important)?", val) or val in ("inherit", "max(var(--fs-16-5), 1em)"): continue
                    if rid == "F10" and m.group("val").rstrip(".") in SCALE: continue
                    if rid == "R3":
                        if f == "frontend/app/globals.css" and line.strip() == "--seal-soft: color-mix(in srgb, var(--stamp) 12%, transparent);": continue
                        if f == "frontend/components/Seal.tsx" and 'fill="var(--stamp)"' in line: continue
                    hits[rid].append(f"{f}:{at}  {m.group(0)[:60]!r}")
    return fl, hits


# ---- globals.css 块解析（令牌层用） ----
def parse_blocks(css):
    """按花括号深度切块，返回顶层节点列表；节点 = {"prelude", "decls", "children", "line"}。"""
    css = strip_css_comments(css)
    root = {"prelude": "", "decls": "", "children": [], "line": 0}
    stack, buf, i, quote = [root], [], 0, None
    while i < len(css):
        ch = css[i]
        if quote:
            buf.append(ch)
            if ch == quote: quote = None
        elif ch in "\"'":
            quote = ch; buf.append(ch)
        elif ch == "{":
            node = {"prelude": re.sub(r"\s+", " ", "".join(buf)).strip(), "decls": "", "children": [], "line": css.count("\n", 0, i) + 1}
            stack[-1]["children"].append(node); stack.append(node); buf = []
        elif ch == "}":
            stack[-1]["decls"] += "".join(buf); buf = []; stack.pop()
        elif ch == ";":
            stack[-1]["decls"] += "".join(buf) + ";"; buf = []
        else:
            buf.append(ch)
        i += 1
    return root["children"]


def decls_of(node):
    out = {}
    for d in node["decls"].split(";"):
        if ":" in d:
            k, v = d.split(":", 1); out.setdefault(k.strip(), []).append(re.sub(r"\s+", " ", v).strip())
    return out


def walk(nodes, anc=()):
    for n in nodes:
        yield n, anc
        yield from walk(n["children"], anc + (n,))


def token_layer(path):
    top = parse_blocks(open(path, encoding="utf-8").read())
    res = {}
    roots = [n for n in top if n["prelude"] == ":root"]
    by = lambda p: [n for n in top if n["prelude"] == p]
    day, alias = (roots + [None, None])[:2]
    night, dsol, nsol = (by(".dark") + [None])[0], (by(":root[data-solid]") + [None])[0], (by(".dark[data-solid]") + [None])[0]
    later_dark = by(".dark")[1:]
    # T1 --fs-*：只在别名 :root 里，各一次，值正确
    fsdefs = [(n, k, v) for n, _a in walk(top) for k, vs in decls_of(n).items() if k.startswith("--fs-") for v in vs]
    res["T1 10 个 --fs-* 只定义在别名 :root、各一次、值正确"] = (
        alias is not None and sorted(k for _n, k, _v in fsdefs) == sorted(FS)
        and all(n is alias and FS.get(k) == v for n, k, v in fsdefs))
    # T2 @theme inline 块内登记，块外没有；四档行高精确
    theme = by("@theme inline")
    tdec = decls_of(theme[0]) if len(theme) == 1 else {}
    want = {"--text-fs-" + k[5:].replace("16-5", "16" + chr(92) + ".5"): "var(" + k + ")" for k in FS}
    lh = {"--text-fs-12--line-height": "calc(16 / 12)", "--text-fs-13--line-height": "calc(20 / 13)",
          "--text-fs-15--line-height": "1.5", "--text-fs-22--line-height": "calc(28 / 22)"}
    inside = {k: v for k, v in tdec.items() if k.startswith("--text-fs-")}
    outside = [k for n, _a in walk(top) if not (theme and n is theme[0]) for k in decls_of(n) if k.startswith("--text-fs-")]
    res["T2 @theme inline 内登记 10 个 --text-fs-*、四档行高精确、块外没有"] = (
        len(theme) == 1 and not outside and set(inside) == set(want) | set(lh)
        and all(inside[k] == [v] for k, v in {**want, **lh}.items()))
    # T3 逐块取值；四个主题块键集合相同；别名块与后面的 .dark 块不定义被检查的颜色
    def val(n, k): return (decls_of(n).get(k) or [None])[-1] if n else None
    checked = ("--ink", "--ink2", "--ink3", "--seal", "--stamp", "--paper", "--hi", "--slip", "--glass", "--glass2",
               "--chip", "--tile", "--mount", "--btn", "--btnink", "--glyph")
    themes = [day, night, dsol, nsol]
    res["T3 四套主题逐块取值正确、键集合相同"] = (
        all(themes) and len({frozenset(decls_of(n)) for n in themes}) == 1
        and all(val(n, "--ink3") == "#6F7C76" and val(n, "--seal") == "#A8322A" and val(n, "--stamp") == "#A8322A" for n in (day, dsol))
        and all(val(n, "--seal") == "#E56F5D" and val(n, "--stamp") == "#BF4537" for n in (night, nsol))
        and not [k for n in [alias] + later_dark if n for k in decls_of(n) if k in checked])
    # T4 --seal-soft 定义
    soft = [(n, v) for n, _a in walk(top) for k, vs in decls_of(n).items() if k == "--seal-soft" for v in vs]
    res["T4 --seal-soft 只在别名 :root 定义一次，为 --stamp 的 12%"] = (
        len(soft) == 1 and soft[0][0] is alias and soft[0][1] == "color-mix(in srgb, var(--stamp) 12%, transparent)")
    # T5 手机输入框护栏
    guard = [(n, a) for n, a in walk(top) if "max(var(--fs-16-5), 1em)" in decls_of(n).get("font-size", [])]
    sel = 'input, textarea, select'.split(", ")
    want_sel = [f':root:not([data-shell="desktop"]) {s}' for s in sel]
    res["T5 手机输入框护栏：选择器三项、在顶层 @media (width < 48rem) 里、不进 @layer"] = (
        len(guard) == 1 and [s.strip() for s in guard[0][0]["prelude"].split(",")] == want_sel
        and len(guard[0][1]) == 1 and guard[0][1][0]["prelude"] == "@media (width < 48rem)"
        and not any(x["prelude"].startswith("@layer") for x in guard[0][1]))
    # T6 默认占位符颜色在第一个 @layer base 里
    base = by("@layer base")
    ph = [c for c in base[0]["children"] if c["prelude"] == "::placeholder"] if base else []
    res["T6 ::placeholder { color: var(--ink2) } 在第一个 @layer base 里"] = len(ph) == 1 and decls_of(ph[0]) == {"color": ["var(--ink2)"]}
    # T7 body 规则块的字号
    body = [c for c in base[0]["children"] if c["prelude"] == "body"] if base else []
    res["T7 body 规则块里 font-size: var(--fs-16-5)"] = len(body) == 1 and decls_of(body[0]).get("font-size") == ["var(--fs-16-5)"]
    # T8 两个对话框的遮罩：用 var(--scrim)，带原来的颜色作兜底（旧版 Safari 的 ::backdrop 取不到 :root 变量）
    want_bd = {".image-preview-dialog::backdrop": "var(--scrim, rgba(31,41,38,.18))", ".dark .image-preview-dialog::backdrop": "var(--scrim, rgba(0,0,0,.45))",
               ".confirm-dialog::backdrop": "var(--scrim, rgba(31,41,38,.18))", ".dark .confirm-dialog::backdrop": "var(--scrim, rgba(0,0,0,.45))"}
    got_bd = {}
    for n, _a in walk(top):
        if n["prelude"].endswith("::backdrop"):
            got_bd.setdefault(n["prelude"], []).extend(decls_of(n).get("background", []))
    res["T8 两个对话框的 ::backdrop 用 var(--scrim) 并带兜底色，昼夜各一条"] = got_bd == {k: [v] for k, v in want_bd.items()}
    return res


def main():
    fl, hits = scan()
    fails = 0
    ok = len(fl) >= 130
    fails += not ok
    print(f"{'PASS' if ok else 'FAIL'} 扫描到 {len(fl)} 个文件（至少 130）")
    for rid, desc, *_ in RULES:
        n = len(hits[rid]); fails += n > 0
        print(f"{'PASS' if n == 0 else 'FAIL'} {rid:4s} {n:4d}  {desc}" + ("" if n == 0 else "  例 " + " | ".join(hits[rid][:2])))
    for name, ok in token_layer(os.path.join(ROOT, "frontend/app/globals.css")).items():
        fails += not ok
        print(f"{'PASS' if ok else 'FAIL'} {name}")
    print("== FAIL", fails)
    return fails


if __name__ == "__main__":
    sys.exit(main())
