"""Lock the settings privacy disclosure layout and copy, entirely offline."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SETTINGS = ROOT / "frontend/components/ChatModelSection.tsx"

FIRST = (
    "启用后，聊天回复会把分身设定、你的私有长期记忆、本会话最近 60 条消息"
    "（含平台看图生成的图片描述）和本条消息发送给你选择的厂商，账号名替换为「（账号已隐藏）」。"
)
CRISIS = (
    "危机复核、平台工具执行、朗读和画像提取仍由平台处理并读取对话；Claude 智能体模式由 Claude 决定工具并直接看图，"
    "其他情况的意图识别、模式判定和看图仍由平台处理。画像提取会读到你的模型回复，明确危机轮也由平台回复。"
)
IMAGE = (
    "生图：选 Claude 或 DeepSeek（deepseek-v4-pro、deepseek-flash）时，由你的模型决定何时生图并撰写画面描述；"
    "选其他厂商时，在你的消息或上一条回复涉及画图时，平台的生图判断器（阿里云 DashScope 千问 qwen3.8-flash）"
    "会读取最近 6 条对话来决定是否生图、撰写画面描述。生图由平台执行并扣草莓，默认使用 Seedream 5.0 Flash，"
    "画面描述会发送给字节跳动火山引擎（点名千问时发送给阿里云），可能包含对话中出现过的内容。"
)
CLAUDE = (
    "选 Claude 时，Claude 可以直接查看你本轮发送的图片，自行调用天气、旅行、路线、热榜和生图工具"
    "（工具由平台执行，天气只查询你亲口说过的城市，使用工具的回合按次扣草莓），并可使用 Anthropic 的联网搜索和网页读取"
    "（由 Anthropic 执行，按其价格计入你的 API 额度，搜索约每 1000 次 10 美元）。图片和工具结果会发送给 Anthropic。"
)
CLAUDE_NOTE = (
    '{provider.id === "anthropic" && <p className={noteClass}>已选 Claude：你在聊天里发的图片和工具结果也会发送给 '
    'Anthropic，详见下方「更多隐私与计费说明」。</p>}'
)
BYOK_TEXT = (
    "自带模型文字聊天不扣草莓，零余额也可聊天；平台模型回复、工具和生图照常扣费，平台看图照常扣费，"
    "Claude 智能体直接看图使用你的 API 额度，自带模型失败时不会改用平台模型，聊天和连接测试均有每日上限。"
)
KEY_STORAGE = "Key 加密保存，删除 Key 或删号时删除，数据库备份中最多保留 14 天，无服务端密钥无法解密。"
NOVEL = "开启『聊天读小说』后，读到的章节原文会发送给当前聊天模型的厂商。"
CLAUDE_REGION = "Claude 的接口不对中国大陆提供服务。"

ALL_PARAGRAPHS = (FIRST, CRISIS, IMAGE, CLAUDE, BYOK_TEXT, KEY_STORAGE, NOVEL, CLAUDE_REGION)
LOCKED_IN_FOLD = (IMAGE, CLAUDE, NOVEL)
FOLD_ORDER = (CRISIS, IMAGE, CLAUDE, BYOK_TEXT, KEY_STORAGE, NOVEL, CLAUDE_REGION)


def test_privacy_fold_follows_second_fieldset_and_holds_locked_paragraphs():
    source = SETTINGS.read_text(encoding="utf-8")
    first_end = source.index("</fieldset>")
    second_end = source.index("</fieldset>", first_end + len("</fieldset>"))
    assert source.count("<details") == 1
    assert source.count("</details>") == 1
    details_start = source.index("<details")
    details_end = source.index("</details>")
    assert details_start > second_end
    opening = source[details_start:source.index(">", details_start) + 1]
    assert opening == (
        "<details className={`${noteClass} border-t border-[color:var(--carve)] pt-3 "
        "shadow-[inset_0_1px_0_var(--etch)]`}>"
    )
    for paragraph in LOCKED_IN_FOLD:
        tag = f"<p>{paragraph}</p>"
        assert source.count(tag) == 1
        assert details_start < source.index(tag) < details_end
    fold = source[details_start:details_end]
    assert fold.index(f"<p>{IMAGE}</p>") < fold.index(f"<p>{CLAUDE}</p>")
    positions = [source.index(f"<p>{paragraph}</p>") for paragraph in FOLD_ORDER]
    assert positions == sorted(positions)
    assert details_start < positions[0]
    assert positions[-1] < details_end


def test_first_privacy_paragraph_is_outside_fold_before_switch_and_save():
    source = SETTINGS.read_text(encoding="utf-8")
    lines = source.splitlines()
    first_lines = [
        index for index, line in enumerate(lines)
        if line.strip().startswith("<p className={noteClass}>启用后，")
    ]
    assert len(first_lines) == 1
    first_index = first_lines[0]
    first_line = lines[first_index].strip()
    assert first_line.startswith("<p className={noteClass}>启用后，")
    assert first_line.endswith("</p>")
    assert first_index + 1 < len(lines)
    assert lines[first_index + 1].strip() == CLAUDE_NOTE
    assert source.count(CLAUDE_NOTE) == 1
    assert source.index(CLAUDE_NOTE) < source.index("启用我的聊天模型")
    paragraph = f"<p className={{noteClass}}>{FIRST}</p>"
    assert source.count(paragraph) == 1
    marker = source.index(paragraph)
    first_open = source.index("<fieldset")
    second_open = source.index("<fieldset", first_open + len("<fieldset"))
    second_end = source.index("</fieldset>", source.index("</fieldset>") + len("</fieldset>"))
    assert second_open < marker < second_end
    assert marker < source.index("<details")
    switch = source.index("启用我的聊天模型")
    save = source.index("onClick={() => void save()}")
    assert marker < switch
    assert marker < save
    assert switch < save


def test_summary_claude_note_and_switch_copy():
    source = SETTINGS.read_text(encoding="utf-8")
    assert (
        '<summary className="min-h-10 cursor-pointer py-2 text-sm tracking-[0.06em] '
        'text-[color:var(--ink)]">更多隐私与计费说明</summary>'
    ) in source
    assert source.count(CLAUDE_NOTE) == 1
    assert "已选 Claude：本轮图片" not in source
    note_start = source.index('<p id="chat-model-enabled-note"')
    note = source[note_start:source.index("</p>", note_start)]
    assert "首次保存后会直接启用；之后可以用这个开关停用或重新启用。" in note
    assert "先保存配置，才能启用。" not in source
    assert "请重新填写并保存 Key。" in note
    assert "开关使用已保存的配置；关闭后使用平台模型。" in note
    for bold in ("<strong", "<b ", "<b>", "font-bold", "font-semibold", "fontWeight", "font-weight"):
        assert bold not in source


def test_eight_privacy_paragraphs_appear_once_and_stay_unadorned():
    source = SETTINGS.read_text(encoding="utf-8")
    assert source.count("<details") == 1
    details_start = source.index("<details")
    details_end = source.index("</details>")
    fold = source[details_start:details_end]
    assert fold.count("<p>") == 7
    assert fold.count("</p>") == 7
    for paragraph in ALL_PARAGRAPHS:
        assert source.count(paragraph) == 1
    assert f"<p>{FIRST}</p>" not in source
    assert f"<p className={{noteClass}}>{FIRST}</p>" in source
    for paragraph in (CRISIS, BYOK_TEXT, KEY_STORAGE, CLAUDE_REGION):
        assert f"<p>{paragraph}</p>" in source
        assert f"<p className={{noteClass}}>{paragraph}</p>" not in source
    assert source.count("确定删除自带模型配置与 Key？之后聊天将使用平台模型。") == 1
    assert "useConfirm()" in source
