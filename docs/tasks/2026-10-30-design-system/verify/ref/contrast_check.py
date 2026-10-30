"""第四批对比度核算（T3-2 的参考实现）：python3 -I contrast_check.py <globals.css>

解析四套主题，层叠方式同浏览器：
  昼 = :root；夜 = :root + .dark；昼素瓷 = :root + :root[data-solid]；
  夜素瓷 = :root + .dark + :root[data-solid] + .dark[data-solid]（:root[data-solid] 特异度高于 .dark）。
半透明底按 alpha 叠到 --paper / --hi 上（逐通道四舍五入），按 WCAG 2.x 计算。
--seal-soft 按别名 :root 里的定义 color-mix(in srgb, var(--X) N%, transparent) 解析。
没有 --stamp 时（HEAD）按 --seal 代算。退出码 = 不达标条数（解析失败为 99）。
"""
import re, sys

css = re.sub(r"/\*.*?\*/", " ", open(sys.argv[1], encoding="utf-8").read(), flags=re.S)
HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
RGBA = re.compile(r"^rgba\((\d+),\s*(\d+),\s*(\d+),\s*([\d.]+)\)$")


def blocks(sel):
    """顶层同名块，按源码顺序。"""
    return [dict(re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", m.group(1)))
            for m in re.finditer(r"(?m)^" + re.escape(sel) + r"\s*\{(.*?)\n?\}", css, re.S)]


def die(msg):
    print("PARSE-FAIL", msg); sys.exit(99)


roots = blocks(":root")
day, alias = (roots + [{}, {}])[:2]
night_all = blocks(".dark")
night, later_dark = (night_all + [{}])[0], night_all[1:]
dsol, nsol = (blocks(":root[data-solid]") + [{}])[0], (blocks(".dark[data-solid]") + [{}])[0]
if not (day and night and dsol and nsol):
    die("四个主题块不全")
if len({frozenset(b) for b in (day, night, dsol, nsol)}) != 1:
    die("四个主题块的键集合不同")
CHECKED = ("--ink", "--ink2", "--ink3", "--seal", "--stamp", "--paper", "--hi", "--slip", "--glass", "--glass2", "--chip", "--tile", "--mount", "--btn", "--btnink", "--glyph")
clash = [k for b in [alias] + later_dark for k in b if k in CHECKED]
if clash:
    die(f"别名 :root 或后面的 .dark 块重定义了被检查的颜色 {clash}")
themes = {"day": {**day}, "night": {**day, **night}, "day-solid": {**day, **dsol}, "night-solid": {**day, **night, **dsol, **nsol}}

soft_def = alias.get("--seal-soft", "")
m = re.fullmatch(r"color-mix\(in srgb, var\((--[\w-]+)\) (\d+(?:\.\d+)?)%, transparent\)", soft_def.strip())
if not m and "--rec-soft" in alias:   # HEAD：旧名
    m = re.fullmatch(r"color-mix\(in srgb, var\((--[\w-]+)\) (\d+(?:\.\d+)?)%, transparent\)", alias["--rec-soft"].strip())
if not m:
    die(f"--seal-soft 定义无法解析：{soft_def!r}")
SOFT_BASE, SOFT_ALPHA = m.group(1), float(m.group(2)) / 100


def rgba(v, name):
    v = v.strip()
    if HEX.match(v):
        return (int(v[1:3], 16), int(v[3:5], 16), int(v[5:7], 16), 1.0)
    mm = RGBA.match(v)
    if mm:
        return tuple(float(x) for x in mm.groups())
    die(f"{name} 的取值 {v!r} 不是 #RRGGBB 或 rgba(r,g,b,a)")


def over(fg, bg):
    a = fg[3]
    return tuple(round(fg[i] * a + bg[i] * (1 - a)) for i in range(3)) + (1.0,)


def lum(c):
    def ch(x):
        x = x / 255
        return x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4
    return 0.2126 * ch(c[0]) + 0.7152 * ch(c[1]) + 0.0722 * ch(c[2])


def cr(a, b):
    la, lb = lum(a), lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


worst, fails = {}, []
for name, t in themes.items():
    tok = lambda k: rgba(t[k], k)
    paper, hi = tok("--paper"), tok("--hi")
    surf = {}
    for k in ("paper", "hi", "slip", "glass", "glass2", "chip", "tile", "mount"):
        c = tok("--" + k)
        if c[3] < 1:
            surf[k + "@paper"] = over(c, paper); surf[k + "@hi"] = over(c, hi)
        else:
            surf[k] = c
    stamp = tok("--stamp") if "--stamp" in t else tok("--seal")
    base = stamp if SOFT_BASE == "--stamp" and "--stamp" not in t else tok(SOFT_BASE)
    soft = (base[0], base[1], base[2], SOFT_ALPHA)
    SOFT_ON = ("paper", "hi", "glass", "glass2", "tile")   # 危险按钮悬停、录音态实际出现的底
    softs = {f"seal-soft@{k}": over(soft, v) for k, v in surf.items() if k.split("@")[0] in SOFT_ON}
    ink3_surf = {k: v for k, v in surf.items() if not k.startswith("chip")}   # --ink3 只当装饰，不落在 chip 上
    checks = []
    for fgk, need, where in (("--ink", 4.5, surf), ("--ink2", 4.5, surf), ("--seal", 4.5, {**surf, **softs}), ("--ink3", 3.0, ink3_surf)):
        for sk, sv in where.items():
            checks.append((fgk, sk, cr(tok(fgk), sv), need))
    checks.append(("--btnink", "--btn", cr(tok("--btnink"), tok("--btn")), 4.5))
    checks.append(("--glyph", "--stamp", cr(tok("--glyph"), stamp), 4.5))
    for fgk, sk, v, need in checks:
        if (name, fgk) not in worst or v < worst[(name, fgk)][1]:
            worst[(name, fgk)] = (sk, v)
        if v < need:
            fails.append((name, fgk, sk, round(v, 2), need))
for (name, fgk), (sk, v) in sorted(worst.items()):
    print(f"{name:12s} {fgk:9s} 最差 {v:5.2f}  在 {sk}")
summary = {}
for name, fgk, *_ in fails:
    summary[(name, fgk)] = summary.get((name, fgk), 0) + 1
print("不达标", len(fails), "条：", ", ".join(f"{n}/{k} {c}" for (n, k), c in sorted(summary.items())) or "无")
sys.exit(min(len(fails), 98))
