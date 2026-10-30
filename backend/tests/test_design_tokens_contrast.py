"""T3-2 设计令牌对比度门禁（WCAG 2.x）。

只读 frontend/app/globals.css，离线运行，不依赖 node_modules 或 git 历史。
四套主题按浏览器层叠：
  昼       = :root；
  夜       = :root + .dark；
  昼素瓷   = :root + :root[data-solid]；
  夜素瓷   = :root + .dark + :root[data-solid] + .dark[data-solid]。
半透明底色先按 alpha 叠到 --paper / --hi 上，逐通道四舍五入，再计算对比度。
--seal-soft 从别名 :root 的 color-mix(in srgb, var(--X) N%, transparent) 解析，
HEAD 上兼容旧名 --rec-soft；解析不到直接 AssertionError。
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GLOBALS = ROOT / "frontend" / "app" / "globals.css"

# 被检查的 16 个颜色。--stamp 在 HEAD 上不存在，按 --seal 代算。
CHECKED_COLORS = (
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
REQUIRED_COLORS = tuple(key for key in CHECKED_COLORS if key != "--stamp")

# 底色集合 S。半透明时分别叠到 --paper 与 --hi 上各算一次。
SURFACE_NAMES = ("paper", "hi", "slip", "glass", "glass2", "chip", "tile", "mount")
# 悬停 / 录音底实际出现的基色：--seal-soft 叠在这些底的 --paper / --hi 版本上。
SOFT_BASES = ("paper", "hi", "glass", "glass2", "tile")

HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
RGBA_RE = re.compile(r"^rgba\((\d+),\s*(\d+),\s*(\d+),\s*([\d.]+)\)$")
SEAL_SOFT_RE = re.compile(
    r"color-mix\(in srgb, var\((--[\w-]+)\) (\d+(?:\.\d+)?)%, transparent\)"
)


def _blocks(css: str, selector: str) -> list[dict[str, str]]:
    """顶层同名块，按源码顺序；每块转成 令牌 -> 值 的字典。"""
    pattern = re.compile(
        r"(?m)^" + re.escape(selector) + r"\s*\{(.*?)\n?\}",
        re.S,
    )
    return [
        dict(re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", match.group(1)))
        for match in pattern.finditer(css)
    ]


def _read_globals() -> str:
    if not GLOBALS.is_file():
        raise AssertionError(f"找不到 {GLOBALS}")
    return GLOBALS.read_text(encoding="utf-8")


def _parse_themes(css_text: str) -> tuple[dict[str, dict[str, str]], dict[str, str]]:
    """解析四套主题并检查主题块结构，返回层叠后的主题与别名 :root。"""
    css = re.sub(r"/\*.*?\*/", " ", css_text, flags=re.S)
    roots = _blocks(css, ":root")
    nights = _blocks(css, ".dark")
    day_solids = _blocks(css, ":root[data-solid]")
    night_solids = _blocks(css, ".dark[data-solid]")

    if len(roots) < 2:
        raise AssertionError(
            f"需要两个 :root 块（主题块 + 别名块），实际 {len(roots)} 个"
        )
    if not nights:
        raise AssertionError("缺少顶层 .dark 夜主题块")
    if not day_solids:
        raise AssertionError("缺少 :root[data-solid] 昼素瓷主题块")
    if not night_solids:
        raise AssertionError("缺少 .dark[data-solid] 夜素瓷主题块")

    day, alias = roots[0], roots[1]
    night = nights[0]
    day_solid = day_solids[0]
    night_solid = night_solids[0]
    theme_blocks = {
        "day": day,
        "night": night,
        "day-solid": day_solid,
        "night-solid": night_solid,
    }

    key_sets = {name: frozenset(block) for name, block in theme_blocks.items()}
    if len(set(key_sets.values())) != 1:
        first_name = next(iter(key_sets))
        first_keys = key_sets[first_name]
        diffs = []
        for name, keys in key_sets.items():
            if keys != first_keys:
                diffs.append(
                    f"{name} 比 {first_name} 多 {sorted(keys - first_keys)}、"
                    f"少 {sorted(first_keys - keys)}"
                )
        raise AssertionError("四个主题块的键集合不同：" + "；".join(diffs))

    for name, block in theme_blocks.items():
        missing = [key for key in REQUIRED_COLORS if key not in block]
        if missing:
            raise AssertionError(f"{name} 主题缺少被检查的颜色：{missing}")

    # 别名 :root 与其后的顶层 .dark 不得重定义被检查的颜色。
    alias_blocks = [("别名 :root", alias)]
    alias_blocks.extend(
        (f"其后的顶层 .dark 第 {index} 块", block)
        for index, block in enumerate(nights[1:], start=1)
    )
    for label, block in alias_blocks:
        clash = sorted(key for key in block if key in CHECKED_COLORS)
        if clash:
            raise AssertionError(
                f"{label} 不得定义被检查的颜色，实际定义了 {clash}"
            )

    themes = {
        "day": dict(day),
        "night": {**day, **night},
        "day-solid": {**day, **day_solid},
        "night-solid": {**day, **night, **day_solid, **night_solid},
    }
    return themes, alias


def _parse_seal_soft(alias: dict[str, str]) -> tuple[str, float]:
    """解析别名 :root 里 --seal-soft 的定义；HEAD 上按旧名 --rec-soft 回退。"""
    raw = alias.get("--seal-soft", "")
    match = SEAL_SOFT_RE.fullmatch(raw.strip())
    if match is None and "--rec-soft" in alias:
        raw = alias["--rec-soft"]
        match = SEAL_SOFT_RE.fullmatch(raw.strip())
    if match is None:
        raise AssertionError(
            "--seal-soft 定义无法解析，需要 "
            "color-mix(in srgb, var(--X) N%, transparent)："
            f"{raw!r}"
        )
    return match.group(1), float(match.group(2)) / 100.0


def _parse_color(value: str, name: str) -> tuple[float, float, float, float]:
    """参与计算的令牌只允许 #RRGGBB 或 rgba(r,g,b,a)。"""
    value = value.strip()
    if HEX_RE.match(value):
        return (
            int(value[1:3], 16),
            int(value[3:5], 16),
            int(value[5:7], 16),
            1.0,
        )
    match = RGBA_RE.match(value)
    if match is not None:
        return tuple(float(part) for part in match.groups())  # type: ignore[return-value]
    raise AssertionError(
        f"{name} 的取值 {value!r} 不是 #RRGGBB 或 rgba(r,g,b,a)"
    )


def _token(theme: dict[str, str], name: str, theme_name: str) -> tuple[float, float, float, float]:
    if name not in theme:
        raise AssertionError(f"{theme_name} 主题缺少令牌 {name}")
    return _parse_color(theme[name], name)


def _over(fg: tuple[float, float, float, float], bg: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    """sRGB 里按 alpha 叠到不透明底上，逐通道四舍五入。"""
    alpha = fg[3]
    return (
        round(fg[0] * alpha + bg[0] * (1 - alpha)),
        round(fg[1] * alpha + bg[1] * (1 - alpha)),
        round(fg[2] * alpha + bg[2] * (1 - alpha)),
        1.0,
    )


def _luminance(color: tuple[float, float, float, float]) -> float:
    def channel(value: float) -> float:
        value = value / 255
        return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4

    return (
        0.2126 * channel(color[0])
        + 0.7152 * channel(color[1])
        + 0.0722 * channel(color[2])
    )


def _contrast(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
) -> float:
    la, lb = _luminance(a), _luminance(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def _evaluate(
    themes: dict[str, dict[str, str]],
    soft_base: str,
    soft_alpha: float,
) -> list[tuple[str, str, str, float, float]]:
    """返回 (主题, 前景, 背景, 实际对比度, 门槛)。"""
    failures: list[tuple[str, str, str, float, float]] = []
    for theme_name, theme in themes.items():
        paper = _token(theme, "--paper", theme_name)
        hi = _token(theme, "--hi", theme_name)

        surfaces: dict[str, tuple[float, float, float, float]] = {}
        for name in SURFACE_NAMES:
            color = _token(theme, f"--{name}", theme_name)
            if color[3] < 1:
                surfaces[f"{name}@paper"] = _over(color, paper)
                surfaces[f"{name}@hi"] = _over(color, hi)
            else:
                surfaces[name] = color

        stamp = (
            _token(theme, "--stamp", theme_name)
            if "--stamp" in theme
            else _token(theme, "--seal", theme_name)
        )
        if soft_base == "--stamp":
            soft_color = stamp
        else:
            soft_color = _token(theme, soft_base, theme_name)
        soft = (soft_color[0], soft_color[1], soft_color[2], soft_alpha)
        soft_surfaces = {
            f"seal-soft@{name}": _over(soft, color)
            for name, color in surfaces.items()
            if name.split("@")[0] in SOFT_BASES
        }

        # --ink3 只当装饰，不落在 chip 上，所以排除 chip 系。
        ink3_surfaces = {
            name: color
            for name, color in surfaces.items()
            if not name.startswith("chip")
        }

        checks: list[tuple[str, str, float, float]] = []
        for fg_key, threshold, backgrounds in (
            ("--ink", 4.5, surfaces),
            ("--ink2", 4.5, surfaces),
            ("--seal", 4.5, {**surfaces, **soft_surfaces}),
            ("--ink3", 3.0, ink3_surfaces),
        ):
            fg = _token(theme, fg_key, theme_name)
            for bg_name, bg_color in backgrounds.items():
                checks.append((fg_key, bg_name, _contrast(fg, bg_color), threshold))

        checks.append(
            (
                "--btnink",
                "--btn",
                _contrast(
                    _token(theme, "--btnink", theme_name),
                    _token(theme, "--btn", theme_name),
                ),
                4.5,
            )
        )
        checks.append(
            (
                "--glyph",
                "--stamp",
                _contrast(_token(theme, "--glyph", theme_name), stamp),
                4.5,
            )
        )

        for fg_key, bg_name, ratio, threshold in checks:
            if ratio < threshold:
                failures.append((theme_name, fg_key, bg_name, ratio, threshold))

    return failures


def _format_failures(failures: list[tuple[str, str, str, float, float]]) -> str:
    lines = [f"不达标 {len(failures)} 条（WCAG 2.x）："]
    for theme_name, fg, bg, ratio, threshold in failures:
        lines.append(
            f"  {theme_name:12s} {fg:8s} 对 {bg:28s} 实际 {ratio:5.2f} < {threshold}"
        )
    counts: dict[tuple[str, str], int] = {}
    for theme_name, fg, *_ in failures:
        counts[(theme_name, fg)] = counts.get((theme_name, fg), 0) + 1
    if counts:
        lines.append(
            "分组："
            + "，".join(
                f"{theme_name}/{fg} {count}"
                for (theme_name, fg), count in sorted(counts.items())
            )
        )
    return "\n".join(lines)


def test_token_contrast() -> None:
    """四套主题下，T3-2 断言表里的每一对前景/背景都要达到门槛。"""
    themes, alias = _parse_themes(_read_globals())
    soft_base, soft_alpha = _parse_seal_soft(alias)
    failures = _evaluate(themes, soft_base, soft_alpha)
    assert not failures, _format_failures(failures)


def test_selfcheck_head_tokens_fail() -> None:
    """正控：把当前 CSS 的三个值换回 HEAD 后，不达标集合必须恰为四组 43 条。"""
    themes, alias = _parse_themes(_read_globals())
    soft_base, soft_alpha = _parse_seal_soft(alias)

    head_like = {name: dict(tokens) for name, tokens in themes.items()}
    for name in ("day", "day-solid"):
        head_like[name]["--ink3"] = "#84918B"
    for name in ("night", "night-solid"):
        head_like[name]["--seal"] = "#BF4537"
    for tokens in head_like.values():
        tokens.pop("--stamp", None)

    failures = _evaluate(head_like, soft_base, soft_alpha)
    failing_groups = {(theme_name, fg) for theme_name, fg, *_ in failures}
    expected_groups = {
        ("day", "--ink3"),
        ("day-solid", "--ink3"),
        ("night", "--seal"),
        ("night-solid", "--seal"),
    }
    assert failing_groups == expected_groups, (
        "HEAD 正控的（主题，前景）集合不符："
        f"实际 {sorted(failing_groups)}，期望 {sorted(expected_groups)}"
    )

    counts: dict[tuple[str, str], int] = {}
    for theme_name, fg, *_ in failures:
        counts[(theme_name, fg)] = counts.get((theme_name, fg), 0) + 1
    expected_counts = {
        ("day", "--ink3"): 6,
        ("day-solid", "--ink3"): 3,
        ("night", "--seal"): 21,
        ("night-solid", "--seal"): 13,
    }
    assert counts == expected_counts, (
        f"HEAD 正控的失败条数分布不符：实际 {counts}，期望 {expected_counts}"
    )
    assert len(failures) == 43, (
        f"HEAD 正控应恰好 43 条不达标，实际 {len(failures)} 条："
        + _format_failures(failures)
    )

    night_soft = [
        (bg, ratio)
        for theme_name, fg, bg, ratio, _ in failures
        if theme_name == "night" and fg == "--seal" and bg.startswith("seal-soft@")
    ]
    assert night_soft, (
        "夜主题 --seal 的失败项里缺少 seal-soft@ 悬停/录音底："
        + _format_failures(
            [
                failure
                for failure in failures
                if failure[0] == "night" and failure[1] == "--seal"
            ]
        )
    )
