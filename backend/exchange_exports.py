"""Render saved exchange snapshots as downloadable Markdown without model calls."""
import html
import re


STATUS_LABELS = {
    "pending": "等待接受", "running": "交流中", "completed": "已完成",
    "stopped": "已停止", "rejected": "已拒绝", "failed": "交流失败",
}


def export_filename(exchange_id: str, document: str = "readme") -> str:
    if document == "readme":
        return "README.md"
    if document not in ("discussion", "artifact"):
        raise ValueError("Unknown export document")
    safe_id = re.sub(r"[^A-Za-z0-9_-]", "", str(exchange_id))[:64] or "export"
    return f"{document}-{safe_id}.md"


def _inline(value) -> str:
    text = html.escape(" ".join(str(value or "").split()), quote=False)
    return re.sub(r"([\\`*_{}\[\]()#+.!|])", r"\\\1", text)


def _text_block(value: str) -> str:
    # A longer fence retains embedded Markdown fences inside literal text.
    text = str(value or "")
    longest = max((len(match) for match in re.findall(r"`+", text)), default=0)
    fence = "`" * max(3, longest + 1)
    return f"{fence}text\n{text}\n{fence}"


def render_exchange_markdown(detail: dict, document: str = "readme") -> str:
    if document not in ("readme", "discussion", "artifact"):
        raise ValueError("Unknown export document")
    exchange = detail["exchange"]
    if document == "artifact" and not str(exchange.get("artifact") or "").strip():
        raise ValueError("No saved artifact")
    if exchange.get("workflow_version") == "draft_review_v1" or document == "artifact":
        return _render_workflow_markdown(detail, document)
    messages = detail.get("messages", [])
    status = STATUS_LABELS.get(exchange.get("status"), "未知状态")
    summary = str(exchange.get("summary") or "")
    complete = exchange.get("status") == "completed" and bool(summary.strip())
    official = exchange.get("kind") == "official"
    title = "分身交流交付说明" if document == "readme" else "完整讨论记录"
    lines = [
        f"# {title}", "",
        f"> {'已完成讨论的文档交付。' if complete else '草稿快照：讨论尚未形成完整的最终交付。'}",
        "> 本文件导出已保存的内容；由 AI 生成的方案与建议可继续编辑。", "",
        "## 记录信息", "",
        f"- 状态：{status}",
        f"- 类型：{'单人体验' if official else '分身交流'}",
        f"- 已保存回复：{len(messages)} / {exchange['max_turns']} 次（双方合计）",
        f"- 创建时间（UTC）：{_inline(exchange.get('created_at'))}",
        f"- 最后更新时间（UTC）：{_inline(exchange.get('updated_at'))}", "",
        "## 参与分身", "",
    ]
    for key, role in (("initiator", "发起方 AI 分身"), ("recipient", "平台官方 AI" if official else "受邀方 AI 分身")):
        card = exchange[key]
        model = card.get("model_label") or card.get("model")
        lines.append(f"- {_inline(card['display_name'])}：{role}" + (f"；模型：{_inline(model)}" if model else ""))
    lines.extend(["", "## 原始话题与要求", "", _text_block(exchange["topic"]), ""])
    if document == "discussion":
        lines.extend(["## 完整讨论", ""])
        if not messages:
            lines.extend(["此快照尚无已保存的分身回复。", ""])
        for message in messages:
            lines.extend([
                f"### 第 {_inline(message['sequence'])} 次回复 · {_inline(message['display_name'])}", "",
                _text_block(message["content"]), "",
            ])
    lines.extend(["## 交流总结 · AI 生成", ""])
    if summary.strip():
        # Preserve Markdown structure while rendering raw HTML as literal text.
        lines.extend([html.escape(summary, quote=False), ""])
    else:
        lines.extend(["当前快照尚无交流总结。已保存内容见完整讨论记录。", ""])
    if document == "readme":
        discussion_name = export_filename(exchange["id"], "discussion")
        lines.extend([
            "## 文档说明", "",
            "- `README.md`：本次讨论的基本信息、原始要求与已保存总结。",
            f"- [{discussion_name}]({discussion_name})：完整逐轮讨论；请在页面另行下载并与本文件放在同一文件夹。", "",
        ])
    return "\n".join(lines).rstrip() + "\n"


def _render_workflow_markdown(detail: dict, document: str) -> str:
    exchange = detail["exchange"]
    messages = detail.get("messages", [])
    artifact = str(exchange.get("artifact") or "")
    approved = (exchange.get("status") == "completed"
                and exchange.get("artifact_status") == "approved" and bool(artifact.strip()))
    review_status = "AI 审稿通过 · 待用户验收" if approved else (
        "草稿 · 待修订" if exchange.get("artifact_status") == "needs_revision" else "草稿")
    reason = {
        "review_approved": "AI 审稿通过，提前结束；仍需用户核对和验收。",
        "turn_limit": "达到回复次数上限，当前稿件保留为草稿。",
        "no_progress": "修订没有发生实质变化，已停止反复讨论，当前稿件保留为草稿。",
        "output_limit": "模型输出达到长度上限，当前稿件可能不完整，请检查后继续编辑。",
        "incomplete_output": "模型输出未正常结束，当前稿件保留为草稿。",
    }.get(exchange.get("completion_reason"), "")
    title = {"readme": "创作交付说明", "discussion": "完整讨论记录", "artifact": "作品稿件"}[document]
    lines = [
        f"# {title}", "", f"> {review_status}",
        "> 本文件仅交付已保存的文字稿件；文内提及的图片、视频、CSV 等附件不代表已生成对应文件。", "",
        "## 记录与审核状态", "",
        f"- 创作状态：{STATUS_LABELS.get(exchange.get('status'), '未知状态')}",
        f"- 稿件状态：{review_status}",
        f"- 已用回复：{len(messages)} 次；上限：{exchange['max_turns']} 次（双方合计）",
        "- 流程：主创初稿 → 官方审稿 → 主创修订；审稿通过后提前结束。",
        f"- 创建时间（UTC）：{_inline(exchange.get('created_at'))}",
        f"- 最后更新时间（UTC）：{_inline(exchange.get('updated_at'))}",
    ]
    if reason:
        lines.append(f"- 结束原因：{reason}")
    if document != "artifact":
        lines.extend(["", "## 参与分身", ""])
        for key, role in (("initiator", "主创 AI 分身"), ("recipient", "官方审稿搭档")):
            card = exchange[key]
            model = card.get("model_label") or card.get("model")
            lines.append(f"- {_inline(card['display_name'])}：{role}" + (f"；模型：{_inline(model)}" if model else ""))
        lines.extend(["", "## 原始话题与要求", "", _text_block(exchange["topic"])])
    if document in ("readme", "artifact"):
        lines.extend(["", "## 当前完整作品", "", html.escape(artifact, quote=False) if artifact.strip() else "尚无已保存的作品稿件。"])
    if document == "discussion":
        lines.extend(["", "## 完整讨论", ""])
        if not messages:
            lines.append("此快照尚无已保存的分身回复。")
        for message in messages:
            stage = {"draft": "主创初稿", "review": "官方审稿", "revision": "主创修订"}.get(message.get("stage"), "交流")
            lines.extend([
                f"### 第 {_inline(message['sequence'])} 次回复 · {stage} · {_inline(message['display_name'])}", "",
                _text_block(message["content"]), "",
            ])
    if document != "artifact" and str(exchange.get("summary") or "").strip():
        lines.extend(["", "## 创作说明", "", html.escape(exchange["summary"], quote=False)])
    if document == "readme":
        discussion_name = export_filename(exchange["id"], "discussion")
        lines.extend(["", "## 文档说明", "", "- `README.md`：原始要求、当前完整稿件与审核状态。"])
        if artifact.strip():
            artifact_name = export_filename(exchange["id"], "artifact")
            lines.append(f"- [{artifact_name}]({artifact_name})：当前作品和审核状态。")
        lines.extend([
            f"- [{discussion_name}]({discussion_name})：完整写稿、审稿与修订过程。",
            "- 作品和完整讨论可在页面另行下载，与本文件放在同一文件夹。",
        ])
    return "\n".join(lines).rstrip() + "\n"
