"""讨论群聊天互通（第三期）文档与设置页隐私句检查；只读仓库文件，离线运行。"""

import re
import socket
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
DOCUMENTS = (
    "README.md",
    "CLAUDE.md",
    "PLAN.md",
    "docs/ARCHITECTURE.md",
    "docs/DEPLOYMENT.md",
    "backend/.env.example",
)
MARKER = "讨论群聊天互通（第三期）"
LOCAL_PATH = re.compile(r"/Users/|/home/[^\s/]+|[A-Za-z]:[\\/](?![\\/])")
CJK = re.compile(r"[\u4e00-\u9fff]")
SETTINGS = ROOT / "frontend/components/ChatModelSection.tsx"
NOVEL_PRIVACY = "开启『聊天读小说』后，读到的章节原文会发送给当前聊天模型的厂商。"
DISCUSS_PRIVACY = "开启『聊天看讨论群』后，读到的讨论内容与成果会发送给当前聊天模型的厂商。"
CLAUDE_REGION = "Claude 的接口不对中国大陆提供服务。"
PRIVATE_MEMORY = "群里的发言可能包含分身根据私有记忆补充的主人背景。"
CARDS_BY_CLAUDE = "任务卡与意见卡的文字由作者自带的 Claude 起草"
THIRD_PHASE_HEADINGS = {
    "README.md": f"## {MARKER}",
    "docs/ARCHITECTURE.md": f"## {MARKER}",
    "docs/DEPLOYMENT.md": f"## {MARKER}部署",
}
# 第三期隐私段按原文逐句钉住（以「。」「；」切分）。这里是文档当前原文的
# 快照，不能从被测文档现拆——否则删掉一句后拆分结果也跟着变少，测试会恒真。
PRIVACY_SENTENCES = {
    "README.md": (
        "隐私：开启「聊天看讨论群」后，分身读到的群内容（方案、成员发言、成果）会发送给当前聊天模型的厂商；",
        "平台模型的分身读到的内容还会作为回复正文保存在本会话历史里。",
        "群里的发言可能包含分身根据私有记忆补充的主人背景。",
        "读到的内容只作为数据处理，不执行其中的指令。",
        "任务卡与意见卡的文字由作者自带的 Claude 起草，卡片只存在本地数据库，作者点按钮之前不建群、不进群、不扣费。",
    ),
    "docs/ARCHITECTURE.md": (
        "隐私：开启后分身读到的群内容（方案、成员发言、成果）会发给当前聊天模型的厂商，平台路径的正文还会落库到本会话历史；",
        "群里的发言可能包含分身根据私有记忆补充的主人背景。",
        "读到的内容只作为数据处理，不执行其中的指令。",
        "任务卡与意见卡的文字由作者自带的 Claude 起草，卡片只存在本地数据库，作者点按钮之前不建群、不进群、不扣费。",
    ),
    "docs/DEPLOYMENT.md": (
        "隐私：开启后分身读到的群内容（方案、成员发言、成果）会发给当前聊天模型的厂商，平台模型路径的正文还会落库到本会话历史；",
        "群里的发言可能包含分身根据私有记忆补充的主人背景。",
        "读到的内容作为数据处理，不执行其中指令；",
        "任务卡与意见卡的文字由作者自带的 Claude 起草，卡片只存在本地数据库，作者点按钮之前不建群、不进群、不扣费。",
    ),
}
ARCH_CLEANUP_SENTENCES = (
    "清理：删号按 `owner_username` 删两张卡片表；",
    "删会话与清空历史在各自事务里删对应卡片；",
    "删群把任务卡的 `group_id` 置回 NULL（卡回到可用），意见卡的 `group_id` 置 NULL（卡保留并显示群已删除）；",
    "单条删消息不清卡片表，卡片没有文件、不进清理队列。",
)


@pytest.fixture(scope="module", autouse=True)
def block_real_network():
    patch = pytest.MonkeyPatch()

    def forbidden(*args, **kwargs):
        raise AssertionError("讨论群聊天文档测试禁止网络与 DNS")

    for name in ("connect", "connect_ex"):
        patch.setattr(socket.socket, name, forbidden)
    for name in ("create_connection", "getaddrinfo", "gethostbyname", "gethostbyname_ex"):
        patch.setattr(socket, name, forbidden)
    yield
    patch.undo()


def section(text, heading):
    """取出从 heading 到下一个二级标题（或文件末尾）的一节。"""
    assert heading in text, f"找不到小节：{heading}"
    start = text.index(heading)
    following = re.search(r"\n## ", text[start + len(heading):])
    end = len(text) if following is None else start + len(heading) + following.start() + 1
    assert start < end
    return text[start:end]


def third_phase_paragraph(text, heading, label):
    """取第三期小节里以 label：开头的一段（到空行为止），并确认非空。"""
    body = section(text, heading)
    assert body.startswith(heading), f"没有找到第三期小节：{heading}"
    marker = f"{label}："
    assert body.count(marker) == 1, f"第三期小节应有且只有一个「{marker}」段"
    paragraph = body[body.index(marker):]
    blank = paragraph.find("\n\n")
    if blank != -1:
        paragraph = paragraph[:blank]
    assert paragraph.strip(), f"「{marker}」段为空"
    return paragraph


@pytest.mark.parametrize("relative", DOCUMENTS)
def test_each_document_mentions_third_phase_and_has_no_local_path(relative):
    path = ROOT / relative
    assert path.is_file(), f"缺少文档：{relative}"
    text = path.read_text(encoding="utf-8")
    assert MARKER in text, f"{relative} 缺少「{MARKER}」"
    assert not LOCAL_PATH.search(text), f"{relative} 含本机绝对路径"


def test_env_template_declares_chat_switches_and_daily_cap():
    path = ROOT / "backend/.env.example"
    assert path.is_file(), "缺少 backend/.env.example"
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    assert f"# ── {MARKER}──" in text
    for pattern, name, keyword in (
        (r"^FIONA_DISCUSS_CHAT=0$", "FIONA_DISCUSS_CHAT", "聊天看讨论群"),
        (r"^FIONA_DISCUSS_CHAT_CARDS=0$", "FIONA_DISCUSS_CHAT_CARDS", "任务卡与意见卡"),
        (r"^# FIONA_DAILY_DISCUSS_READS=60$", "FIONA_DAILY_DISCUSS_READS", "每日成功读取"),
    ):
        matches = [index for index, line in enumerate(lines) if re.fullmatch(pattern, line)]
        assert len(matches) == 1, f"{name} 未按预期出现一次"
        index = matches[0]
        comments = [line for line in lines[max(0, index - 2):index] if line.startswith("#")]
        assert any(CJK.search(line) for line in comments), f"{name} 上方两行内缺少中文注释"
        assert index > 0, f"{name} 上方缺少注释行"
        adjacent = lines[index - 1]
        assert adjacent.startswith("#"), f"{name} 紧邻上一行不是注释：{adjacent!r}"
        assert CJK.search(adjacent), f"{name} 紧邻上一行缺少中文注释：{adjacent!r}"
        assert "──" not in adjacent, f"{name} 紧邻上一行是分节注释、不是专属注释：{adjacent!r}"
        assert keyword in adjacent, f"{name} 紧邻上一行缺少关键词「{keyword}」：{adjacent!r}"


def test_claude_md_size_and_third_phase_section_limits():
    path = ROOT / "CLAUDE.md"
    assert path.is_file(), "缺少 CLAUDE.md"
    raw = path.read_bytes()
    assert len(raw) <= 69_300, f"CLAUDE.md 为 {len(raw)} 字节"
    body = section(raw.decode("utf-8"), f"## {MARKER}")
    assert body.startswith(f"## {MARKER}")
    assert "\n## " not in body, "新节应当位于文件末尾"
    size = len(body.encode("utf-8"))
    assert size <= 260, f"CLAUDE.md 新节为 {size} 字节"
    for phrase in (
        "FIONA_DISCUSS_CHAT",
        "FIONA_DISCUSS_CHAT_CARDS",
        "backend/discuss/chat.py",
        "backend/discuss/cards.py",
        "docs/ARCHITECTURE.md",
    ):
        assert phrase in body, f"CLAUDE.md 新节缺少：{phrase}"


def test_settings_privacy_sentence_is_once_and_between_novel_and_region():
    assert SETTINGS.is_file(), "缺少 frontend/components/ChatModelSection.tsx"
    source = SETTINGS.read_text(encoding="utf-8")
    sentence = f"<p>{DISCUSS_PRIVACY}</p>"
    assert source.count(DISCUSS_PRIVACY) == 1
    assert source.count(sentence) == 1
    assert source.count("<details") == 1
    assert source.count("</details>") == 1
    details_start = source.index("<details")
    details_end = source.index("</details>")
    position = source.index(sentence)
    assert details_start < position < details_end, "隐私句必须位于「更多隐私与计费说明」折叠区内"
    novel = f"<p>{NOVEL_PRIVACY}</p>"
    region = f"<p>{CLAUDE_REGION}</p>"
    assert source.count(novel) == 1
    assert source.count(region) == 1
    assert source.index(novel) < position < source.index(region)


def test_existing_privacy_test_counts_eight_paragraphs():
    path = ROOT / "backend/tests/test_empty_states_settings_privacy.py"
    assert path.is_file(), "缺少既有设置页隐私测试"
    source = path.read_text(encoding="utf-8")
    assert 'assert fold.count("<p>") == 8' in source
    assert 'assert fold.count("</p>") == 8' in source
    assert 'assert fold.count("<p>") == 7' not in source
    assert 'assert fold.count("</p>") == 7' not in source


def test_readme_explains_switches_free_limit_and_privacy():
    path = ROOT / "README.md"
    assert path.is_file(), "缺少 README.md"
    body = section(path.read_text(encoding="utf-8"), f"## {MARKER}")
    for phrase in (
        "FIONA_DISCUSS=1",
        "FIONA_DISCUSS_USERS",
        "FIONA_DISCUSS_CHAT=1",
        "FIONA_DISCUSS_CHAT_CARDS=1",
        "FIONA_DAILY_DISCUSS_READS=60",
        "默认 60",
        "不扣草莓",
        "隐私",
        "读到的群内容",
    ):
        assert phrase in body, f"README 新节缺少：{phrase}"


def test_architecture_documents_both_channels_tables_routes_and_cleanup():
    path = ROOT / "docs/ARCHITECTURE.md"
    assert path.is_file(), "缺少 docs/ARCHITECTURE.md"
    body = section(path.read_text(encoding="utf-8"), f"## {MARKER}")
    for phrase in (
        "backend/discuss/chat.py",
        "backend/discuss/cards.py",
        "discuss_list",
        "discuss_read",
        "list_discuss_groups",
        "read_discuss_group",
        "draft_discuss_task",
        "draft_discuss_note",
        "discuss_task_cards",
        "discuss_note_cards",
        "discuss_task_id",
        "discuss_note_id",
        "GET /discuss/task-cards/{card_id}",
        "GET /discuss/note-cards/{card_id}",
        "POST /discuss/note-cards/{card_id}/send",
        "清理",
        "已知局限",
    ):
        assert phrase in body, f"ARCHITECTURE 新节缺少：{phrase}"


def test_architecture_messages_paragraph_lists_discuss_foreign_keys():
    path = ROOT / "docs/ARCHITECTURE.md"
    assert path.is_file(), "缺少 docs/ARCHITECTURE.md"
    text = path.read_text(encoding="utf-8")
    anchor = "`messages` 通过容错式 `ALTER TABLE` 新增可空列 `song_project_id`"
    assert anchor in text
    start = text.index(anchor)
    end = text.index("\n\n", start)
    paragraph = text[start:end]
    for phrase in (
        "novel_draft_id",
        "novel_feedback_id",
        "discuss_task_id",
        "discuss_note_id",
    ):
        assert phrase in paragraph, f"messages 可空列说明缺少：{phrase}"


def test_plan_entry_lists_third_phase_and_all_known_limitations():
    path = ROOT / "PLAN.md"
    assert path.is_file(), "缺少 PLAN.md"
    heading = f"## 2026-11-15：{MARKER}"
    body = section(path.read_text(encoding="utf-8"), heading)
    for phrase in (
        "FIONA_DISCUSS_CHAT",
        "FIONA_DISCUSS_CHAT_CARDS",
        "FIONA_DAILY_DISCUSS_READS",
        "discuss_task_cards",
        "discuss_note_cards",
        "discuss_task_id",
        "discuss_note_id",
        "已知局限",
        "卡片不轮询",
        "卡上的文字不能改",
        "同一个群可以有多张意见卡",
        "平台模型的分身不出卡片",
        "分身不能替作者开工",
        "读成果只读最新一版",
        "任务卡建议的队伍",
        "卡片不带队伍",
    ):
        assert phrase in body, f"PLAN 新节缺少：{phrase}"


def test_readme_documents_continuation_and_same_name_priority():
    path = ROOT / "README.md"
    assert path.is_file(), "缺少 README.md"
    body = section(path.read_text(encoding="utf-8"), f"## {MARKER}")
    for phrase in (
        "平台模型的分身",
        "继续读",
        "接着读",
        "30 分钟",
        "同名优先",
    ):
        assert phrase in body, f"README 新节缺少 v1.1 文案：{phrase}"


def test_architecture_documents_continuation_slot_and_lookup_order():
    path = ROOT / "docs/ARCHITECTURE.md"
    assert path.is_file(), "缺少 docs/ARCHITECTURE.md"
    body = section(path.read_text(encoding="utf-8"), f"## {MARKER}")
    for phrase in (
        "chat_slot_state",
        "kind=discuss_read",
        "30 分钟",
        "取较新的",
        "Claude 路径不存位置",
        "id → 同名 → 包含",
    ):
        assert phrase in body, f"ARCHITECTURE 新节缺少 v1.1 文案：{phrase}"


def test_plan_documents_continuation_position_retention_limit():
    path = ROOT / "PLAN.md"
    assert path.is_file(), "缺少 PLAN.md"
    heading = f"## 2026-11-15：{MARKER}"
    body = section(path.read_text(encoding="utf-8"), heading)
    for phrase in (
        "续读位置只保留 30 分钟",
        "换会话后不保留",
    ):
        assert phrase in body, f"PLAN 新节缺少 v1.1 已知局限：{phrase}"


def test_deployment_documents_new_variables_runtime_rules_and_privacy():
    path = ROOT / "docs/DEPLOYMENT.md"
    assert path.is_file(), "缺少 docs/DEPLOYMENT.md"
    text = path.read_text(encoding="utf-8")
    table_rows = (
        "| `FIONA_DISCUSS_CHAT` |",
        "| `FIONA_DISCUSS_CHAT_CARDS` |",
        "| `FIONA_DAILY_DISCUSS_READS` |",
    )
    for prefix in table_rows:
        assert prefix in text, f"变量表缺少：{prefix}"
    body = section(text, f"## {MARKER}部署")
    for phrase in (
        "FIONA_DISCUSS_CHAT",
        "FIONA_DISCUSS_CHAT_CARDS",
        "FIONA_DAILY_DISCUSS_READS",
        "默认 `0`",
        "默认 `60`",
        "调用时读取",
        "非法值回落",
        "只告警一次",
        "rate_limit",
        "不扣草莓",
        "隐私",
    ):
        assert phrase in body, f"DEPLOYMENT 新节缺少：{phrase}"


@pytest.mark.parametrize("relative", tuple(THIRD_PHASE_HEADINGS))
def test_third_phase_privacy_sentences_appear_exactly_once(relative):
    """README、ARCHITECTURE、DEPLOYMENT 的隐私段都含两句原文，且各一次。"""
    heading = THIRD_PHASE_HEADINGS[relative]
    path = ROOT / relative
    assert path.is_file(), f"缺少 {relative}"
    text = path.read_text(encoding="utf-8")
    body = section(text, heading)
    assert body.startswith(heading), f"{relative} 没有找到第三期小节"
    assert body.count("隐私：") == 1, f"{relative} 第三期小节应有且只有一个隐私段"
    start = body.index("隐私：")
    paragraph = body[start:]
    blank = paragraph.find("\n\n")
    if blank != -1:
        paragraph = paragraph[:blank]
    assert PRIVATE_MEMORY in paragraph, f"{relative} 隐私段缺少私有记忆句"
    assert CARDS_BY_CLAUDE in paragraph, f"{relative} 隐私段缺少 Claude 起草句"
    assert text.count(PRIVATE_MEMORY) == 1, f"{relative} 私有记忆句应恰好出现一次"
    assert text.count(CARDS_BY_CLAUDE) == 1, f"{relative} Claude 起草句应恰好出现一次"


def test_architecture_documents_v12_cleanup_original_text():
    """架构文档的清理说明按原文钉住两张卡片表、会话删除与删群后的归属。"""
    path = ROOT / "docs/ARCHITECTURE.md"
    assert path.is_file(), "缺少 docs/ARCHITECTURE.md"
    body = section(path.read_text(encoding="utf-8"), f"## {MARKER}")
    assert body.startswith(f"## {MARKER}")
    assert body.count("清理：") == 1, "第三期小节应有且只有一个清理段"
    start = body.index("清理：")
    cleanup = body[start:]
    blank = cleanup.find("\n\n")
    if blank != -1:
        cleanup = cleanup[:blank]
    for phrase in (
        "删号按 `owner_username` 删两张卡片表",
        "删会话与清空历史在各自事务里删对应卡片",
        "删群把任务卡的 `group_id` 置回 NULL",
        "意见卡的 `group_id` 置 NULL（卡保留并显示群已删除）",
        "单条删消息不清卡片表",
    ):
        assert phrase in cleanup, f"ARCHITECTURE 清理说明缺少：{phrase}"


@pytest.mark.parametrize("relative", tuple(PRIVACY_SENTENCES))
def test_privacy_paragraph_matches_every_original_sentence(relative):
    """隐私段原文逐句断言；删掉任意一句都要让某条断言失败。"""
    paragraph = third_phase_paragraph(
        (ROOT / relative).read_text(encoding="utf-8"),
        THIRD_PHASE_HEADINGS[relative],
        "隐私",
    )
    for sentence in PRIVACY_SENTENCES[relative]:
        assert sentence in paragraph, f"{relative} 隐私段缺少原句：{sentence}"


def test_architecture_cleanup_matches_every_original_sentence():
    """清理段原文逐句断言；删掉任意一句都要让某条断言失败。"""
    paragraph = third_phase_paragraph(
        (ROOT / "docs/ARCHITECTURE.md").read_text(encoding="utf-8"),
        THIRD_PHASE_HEADINGS["docs/ARCHITECTURE.md"],
        "清理",
    )
    for sentence in ARCH_CLEANUP_SENTENCES:
        assert sentence in paragraph, f"ARCHITECTURE 清理段缺少原句：{sentence}"


def test_architecture_documents_v12_reading_and_lookup_details():
    """架构文档按 v1.2 说明成员名、未验收、空成果、32 位 id 与续读失败删位置。"""
    path = ROOT / "docs/ARCHITECTURE.md"
    assert path.is_file(), "缺少 docs/ARCHITECTURE.md"
    body = section(path.read_text(encoding="utf-8"), f"## {MARKER}")
    assert body.startswith(f"## {MARKER}")
    for phrase in (
        "最近发言",
        "发言人用成员显示名",
        "`service.detail` 返回的 `sender_name`",
        "最新成果还没验收。",
        "按「还没有成果」处理",
        "32 位十六进制",
        "没找到这个讨论群，它可能已经删除。",
        "不把这串 id 原样写给作者",
        "读成果（`part=output`）失败时也删除续读位置",
        "最近更新的 50 个群",
    ):
        assert phrase in body, f"ARCHITECTURE 新节缺少 v1.2 文案：{phrase}"


def test_plan_documents_recent_fifty_groups_lookup_limit():
    """PLAN 的已知局限写明按名字或 id 只查最近更新的 50 个群。"""
    path = ROOT / "PLAN.md"
    assert path.is_file(), "缺少 PLAN.md"
    heading = f"## 2026-11-15：{MARKER}"
    body = section(path.read_text(encoding="utf-8"), heading)
    assert body.startswith(heading)
    assert body.count("已知局限：") == 1
    limitations = body[body.index("已知局限："):]
    assert "按名字或 id 找群时只在最近更新的 50 个群里找" in limitations

