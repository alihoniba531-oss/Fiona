"""WO3d 块 C：风格提案输入与定妆出图提示词（纯函数，不发任何请求，不读原文全文）。"""

from __future__ import annotations


PROMPT_LIMIT = 1800
"""定妆提示词总长度上限（字符）；超出时按优先级裁剪，见 build_sheet_prompt。"""

KINDS = ("character", "location", "prop")
REALISMS = ("photoreal", "anime", "3d")

_KIND_LABELS = {"character": "人物", "location": "场景", "prop": "道具"}
_LAYOUTS = {
    "character": "三视图：正面、侧面、背面全身",
    "location": "同一地点的三个机位：全景、中景、细节",
    "prop": "三视图：正面、侧面、背面，另加一处细节特写",
}
_FRAME = "各视图横向等距排开、视图之间留白；画面内不加任何文字标签；纯白干净背景，边缘清晰便于抠像；16:9 横幅。"
_REALISM = {
    "photoreal": ("写实摄影质感，真实材质与自然光线衰减", "不要动漫、不要插画"),
    "anime": ("二维动画质感，清晰线条与赛璐璐上色", "不要照片质感、不要写实"),
    "3d": ("三维渲染质感，明确的体积感与材质反射", "不要照片、不要二维线稿"),
}
_SKIN = "真实皮肤质感：可见毛孔、细纹与皮肤油光变化。"
_ORIGINAL = {
    "character": "原创角色，原创设计，不模仿任何已知作品、品牌或真人。",
    "location": "原创设计，不模仿任何已知作品、品牌或真人。",
    "prop": "原创设计，不模仿任何已知作品、品牌或真人。",
}

_SYNOPSIS_KEYS = ("logline", "synopsis", "genre", "tone", "themes", "theme",
                  "core_conflict", "main_threads", "arc_summaries")
_SYNOPSIS_LABELS = {"logline": "一句话梗概", "synopsis": "梗概", "genre": "类型", "tone": "基调",
                    "themes": "主题", "theme": "主题", "core_conflict": "核心冲突",
                    "main_threads": "主线", "arc_summaries": "分段梗概"}
_EPISODE_LIMIT = 24
_CAPS = {"name": 80, "role": 80, "title": 80, "text": 300, "synopsis": 400, "episode": 200}


def _text(value, cap):
    """取单行纯文本；只截取摘要长度，绝不透传原文全篇。"""
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        parts = [_text(item, cap) for item in value]
        value = "；".join(part for part in parts if part)
    elif isinstance(value, dict):
        parts = [_text(item, cap) for item in value.values()]
        value = "；".join(part for part in parts if part)
    else:
        value = " ".join(str(value).split())
    return value[:cap]


def _clean(value) -> str:
    """压缩为单行文本；长度由 build_sheet_prompt 的总长上限与裁剪优先级控制。"""
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        value = "；".join(part for part in (_clean(item) for item in value) if part)
    elif isinstance(value, dict):
        value = "；".join(part for part in (_clean(item) for item in value.values()) if part)
    else:
        value = " ".join(str(value).split())
    return value


def style_inputs(*, synopsis: dict, bible: list[dict], episodes: list[dict], language: str) -> dict:
    """组装风格提案导演任务的输入：只放摘要，不放原文全文。

    - 梗概：只取已知的概括字段，逐字段截断。
    - 人物 / 场景 / 道具：只取名字、定位与外形或描述摘要；原文逐字摘录（excerpt）一律不带。
    - 集数与总时长：集数、预估总秒数，以及每集的集号、标题与剧情摘要。
    - 语言：开工确认里的语言（zh / en）。
    """
    summary = {}
    for key in _SYNOPSIS_KEYS:
        value = _text((synopsis or {}).get(key), _CAPS["synopsis"])
        if value:
            summary[_SYNOPSIS_LABELS[key]] = value

    grouped = {"character": [], "location": [], "prop": []}
    for item in bible or []:
        kind = item.get("kind")
        if kind not in grouped:
            continue
        name = _text(item.get("name"), _CAPS["name"])
        if not name:
            continue
        if kind == "character":
            grouped[kind].append({
                "name": name,
                "role": _text(item.get("role"), _CAPS["role"]),
                "appearance": _text(item.get("appearance") or item.get("description"), _CAPS["text"]),
                "needs_author": bool(item.get("needs_author")),
            })
        else:
            grouped[kind].append({"name": name,
                                  "description": _text(item.get("description") or item.get("appearance"),
                                                       _CAPS["text"])})

    episode_list, total_seconds = [], 0
    for episode in (episodes or [])[:_EPISODE_LIMIT]:
        try:
            seconds = int(episode.get("est_seconds") or 0)
        except (TypeError, ValueError):
            seconds = 0
        total_seconds += max(seconds, 0)
        episode_list.append({
            "no": episode.get("no"),
            "title": _text(episode.get("title"), _CAPS["title"]),
            "summary": _text(episode.get("change") or episode.get("hook") or episode.get("summary"),
                             _CAPS["episode"]),
        })

    label = {"zh": "中文", "en": "英文"}.get(str(language or "").strip().lower(),
                                             _text(language, _CAPS["role"]) or "中文")
    return {
        "language": label,
        "synopsis": summary,
        "characters": grouped["character"],
        "locations": grouped["location"],
        "props": grouped["prop"],
        "episode_count": len(episodes or []),
        "total_seconds": total_seconds,
        "episodes": episode_list,
    }


def reference_note(kind: str, derived: bool) -> str:
    """每张参考图「只取什么、不取什么」的说明；derived 表示由已选定版本派生。"""
    if kind == "character":
        note = ("只取身份、脸型、发型、体型，不取姿势与背景" if derived
                else "只取身份、脸型、发型、体型，不取背景、文字与无关元素")
    elif kind == "location":
        note = "只取建筑结构、陈设、朝向，不取人物与文字标签"
    elif kind == "prop":
        note = "只取结构、材质、颜色，不取场景与文字"
    else:
        raise ValueError("kind 必须是 character / location / prop")
    return ("由已选定版本派生，" if derived else "") + note


def _style_line(style: dict) -> str:
    parts = [(label, _clean(style.get(key)))
             for key, label in (("visual_style", "视觉风格"), ("palette", "色彩"),
                                ("lighting", "光线"), ("camera", "镜头"))]
    body = "；".join(f"{label}{value}" for label, value in parts if value)
    return f"风格：{body}" if body else ""


def _render(kind: str, name: str, appearance: str, description: str, locked_features: str,
            realism: str, style_line: str, reference_notes: list[str], extra_prompt: str) -> str:
    lines = [f"定妆{_KIND_LABELS[kind]}：{name}" if name else f"定妆{_KIND_LABELS[kind]}。",
             f"版式：{_LAYOUTS[kind]}。{_FRAME}"]
    if appearance:
        lines.append(f"外形：{appearance}")
    if description:
        lines.append(f"说明：{description}")
    if locked_features:
        lines.append(f"必须保持（锁定特征）：{locked_features}")
    positive, negative = _REALISM[realism]
    skin = f"；{_SKIN}" if realism == "photoreal" and kind == "character" else ""
    lines.append(f"写实度：{positive}{skin}")
    lines.append(f"负向：{negative}")
    lines.append(_ORIGINAL[kind])
    if style_line:
        lines.append(style_line)
    if reference_notes:
        lines.append(f"参考图说明（共 {len(reference_notes)} 张，按上传顺序逐张取用）：")
        lines.extend(f"{index}. {note}" for index, note in enumerate(reference_notes, 1))
    if extra_prompt:
        lines.append(f"补充要求：{extra_prompt}")
    return "\n".join(lines)


def build_sheet_prompt(*, kind: str, name: str, appearance: str, description: str, locked_features: str,
                       style: dict, extra_prompt: str = "", reference_notes: list[str] = ()) -> str:
    """定妆出图提示词：固定版式、写实度负向、原创声明、锁定特征、参考图说明与风格段。

    总长度 ≤ PROMPT_LIMIT；超长时按 extra_prompt → description → 风格段 → appearance 的
    顺序裁尾部，参考图说明只作最后的兜底（绝不先于 appearance 被裁）。
    版式、主体名称、locked_features、负向约束、原创声明这几部分始终完整保留，
    因此 locked_features 必须由调用方限长（PATCH 处校验 ≤600 字）。
    """
    if kind not in _LAYOUTS:
        raise ValueError("kind 必须是 character / location / prop")
    style = style or {}
    realism = _clean(style.get("realism")) or "photoreal"
    if realism not in _REALISM:
        raise ValueError("realism 必须是 photoreal / anime / 3d")

    name = _clean(name)
    appearance = _clean(appearance)
    description = _clean(description)
    locked_features = _clean(locked_features)
    notes = [note for note in (_clean(note) for note in (reference_notes or [])) if note]
    style_line = _style_line(style)
    extra_prompt = _clean(extra_prompt)

    def render() -> str:
        return _render(kind, name, appearance, description, locked_features,
                       realism, style_line, notes, extra_prompt)

    def short(value: str, over: int) -> str:
        """按超出量裁尾部；超出量不小于整段长度时整段去掉。"""
        return "" if over >= len(value) else value[:len(value) - over]

    # 裁剪优先级：extra_prompt → description → 风格段 → appearance → 参考图说明（兜底）。
    text = render()
    for stage in ("extra_prompt", "description", "style", "appearance", "reference_notes"):
        while len(text) > PROMPT_LIMIT:
            over = len(text) - PROMPT_LIMIT
            if stage == "extra_prompt":
                if not extra_prompt:
                    break
                extra_prompt = short(extra_prompt, over)
            elif stage == "description":
                if not description:
                    break
                description = short(description, over)
            elif stage == "style":
                if not style_line:
                    break
                style_line = short(style_line, over)
            elif stage == "appearance":
                if not appearance:
                    break
                appearance = short(appearance, over)
            else:
                if not notes:
                    break
                notes = notes[:-1] if over >= len(notes[-1]) else notes[:-1] + [short(notes[-1], over)]
            text = render()
    return text
