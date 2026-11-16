"""讨论群界面的变异脚本：把实现逐处改坏，看新用例能不能靠断言失败发现。

用法：
    backend/.venv/bin/python <本脚本> <仓库根> <克隆目录（必须不存在）> <结果.json> [编号…]
做法：把仓库克隆一份（APFS 克隆），在克隆里逐条改坏、跑新用例、还原。
只有「有用例 failed」才算杀死；报错或超时单独标出来。
"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[0]
LOGIC = "frontend/lib/discussLogic.ts"
SIDEBAR = "frontend/components/Sidebar.tsx"
PAGE = "frontend/app/page.tsx"
SERVICE = "backend/discuss/service.py"
DOCUMENT = "frontend/components/discuss/DiscussDocument.tsx"
SHELF = "frontend/components/discuss/DiscussShelf.tsx"
LIST_PAGE = "frontend/app/discuss/page.tsx"
DIALOGS = "frontend/components/discuss/DiscussDialogs.tsx"
SHELL = "frontend/components/discuss/DiscussShell.tsx"
ROOM = "frontend/components/discuss/DiscussRoom.tsx"
TIMELINE = "frontend/components/discuss/DiscussTimeline.tsx"
COMPOSER = "frontend/components/discuss/DiscussComposer.tsx"
CREATEFORM = "frontend/components/discuss/DiscussCreateForm.tsx"
PLANPANEL = "frontend/components/discuss/DiscussPlanPanel.tsx"
SOURCES = "frontend/components/discuss/DiscussSourcesPanel.tsx"

MUTATIONS = [
    ("L1", "done 的两种文案对调", [(LOGIC, '? "你已接受" : "验收通过"', '? "验收通过" : "你已接受"', 1)]),
    ("L2", "预算用完显示成已暂停", [(LOGIC, 'budget: "预算用完",', 'budget: "已暂停",', 1)]),
    ("L3", "不认识的暂停原因文案变了", [(LOGIC, 'PAUSED_LABELS[group.stop_reason ?? ""] ?? "已暂停"', 'PAUSED_LABELS[group.stop_reason ?? ""] ?? "暂停"', 1)]),
    ("L4", "不认识的状态不再原样返回", [(LOGIC, "STATUS_LABELS[group.status] ?? group.status", 'STATUS_LABELS[group.status] ?? ""', 1)]),
    ("L5", "步骤失败没有提示", [(LOGIC, '  step_failed: "有一步连着几次没跑通。点继续会从断的地方接着跑。",\n', "", 1)]),
    ("L6", "你已接受的群也提示返工", [(LOGIC, 'if (group.status === "done" && group.stop_reason !== "accepted_by_user") {', 'if (group.status === "done") {', 1)]),
    ("L7", "立项中不算进行中", [(LOGIC, 'return status === "planning" || status === "running";', 'return status === "running";', 1)]),
    ("L8", "出错的群不算待处理", [(LOGIC, '\n    || group.status === "failed";', ";", 1)]),
    ("L9", "暂停时不能接受成果", [(LOGIC, '      if (group.output_version >= 1) actions.push("accept");\n', "", 1)]),
    ("L10", "轮数用尽时不能接受成果", [(LOGIC, '      if (group.output_version >= 1) actions.push("accept");\n', "", 2)]),
    ("L11", "完成的群多出结束", [(LOGIC, 'actions.push("rework");', 'actions.push("rework", "close");', 1)]),
    ("L12", "有一版成果时不能导出", [(LOGIC, 'if (group.output_version >= 1) actions.push("export");', 'if (group.output_version >= 2) actions.push("export");', 1)]),
    ("L13", "没有删除", [(LOGIC, '  actions.push("delete");\n  return actions;', "  return actions;", 1)]),
    ("L14", "等开工时默认不在方案", [(LOGIC, 'if (group.status === "awaiting_start") return "plan";', 'if (group.status === "awaiting_start") return "chat";', 1)]),
    ("L15", "没有成果也默认到成果", [(LOGIC, '&& group.output_version >= 1) return "output";', '&& group.output_version >= 0) return "output";', 1)]),
    ("L16", "验收的种类文案变了", [(LOGIC, 'verdict: "验收",', 'verdict: "验收结论",', 1)]),
    ("L17", "合并时旧消息优先", [(LOGIC, "for (const message of incoming) merged.set(message.id, message);", "for (const message of incoming) if (!merged.has(message.id)) merged.set(message.id, message);", 1)]),
    ("L18", "合并后不排序", [(LOGIC, "return [...merged.values()].sort((left, right) => left.id - right.id);", "return [...merged.values()];", 1)]),
    ("L19", "已读未读反了", [(LOGIC, "consumed: !unread.has(message.id)", "consumed: unread.has(message.id)", 1)]),
    ("L20", "未读条数不校验", [(LOGIC, "const count = Number.isInteger(pendingNotes) && pendingNotes > 0 ? pendingNotes : 0;", "const count = pendingNotes;", 1)]),
    ("L21", "把最早的插话当未读", [(LOGIC, ".sort((left, right) => right - left);", ".sort((left, right) => left - right);", 1)]),
    ("L22", "不同轮次并成一组", [(LOGIC, "if (last && last.round === message.round) {", "if (last) {", 1)]),
    ("L23", "立项的标题错位", [(LOGIC, 'label: message.round === 0 ? "立项"', 'label: message.round === 1 ? "立项"', 1)]),
    ("L24", "代码块里也找表格", [(LOGIC, 'if (line.startsWith("```")) {', 'if (line.startsWith("```") && false) {', 1)]),
    ("L25", "没有分隔行也算表格", [(LOGIC, "      && isSeparator(lines[index + 1])) {", "      && true) {", 1)]),
    ("L26", "数据行多出的列不截断", [(LOGIC, "const cells = tableCells(lines[rowIndex]).slice(0, header.length);", "const cells = tableCells(lines[rowIndex]);", 1)]),
    ("L27", "数据行缺的列不补", [(LOGIC, '        while (cells.length < header.length) cells.push("");\n', "", 1)]),
    ("L28", "空白块不丢", [(LOGIC, 'if (value.trim()) blocks.push({ kind: "markdown", text: value });', 'blocks.push({ kind: "markdown", text: value });', 1)]),
    ("L29", "五位数字也算编号", [(LOGIC, r"/\[S(\d{1,4})\]/g", r"/\[S(\d{1,5})\]/g", 1)]),
    ("L30", "小写 s 也算编号", [(LOGIC, r"/\[S(\d{1,4})\]/g", r"/\[[Ss](\d{1,4})\]/g", 1)]),
    ("L31", "相邻编号之间多出空文字块", [(LOGIC, 'if (start > last) blocks.push({ kind: "text", text: text.slice(last, start) });', 'blocks.push({ kind: "text", text: text.slice(last, start) });', 1)]),
    ("L32", "任何协议的网址都放行", [(LOGIC, 'return parsed.protocol === "http:" || parsed.protocol === "https:" ? parsed.href : null;', "return parsed.href;", 1)]),
    ("L33", "诉求太短不拦", [(LOGIC, "if (request.length < limits.request_min || request.length > limits.request_max) {", "if (request.length > limits.request_max) {", 1)]),
    ("L34", "成员重名不拦", [(LOGIC, 'if (seen.has(name)) return "成员的名字不能重复";', 'if (seen.has(name) && false) return "成员的名字不能重复";', 1)]),
    ("L35", "自定义成员缺职责不拦", [(LOGIC, "if (custom.some(item => !item.name.trim() || !item.does.trim())) {", "if (custom.some(item => !item.name.trim())) {", 1)]),
    ("L36", "自己组队不带成员", [(LOGIC, "    body.members = members;\n", "", 1)]),
    ("L37", "没改模型也带 models", [(LOGIC, "  if (Object.keys(models).length > 0) body.models = models;", "  body.models = models;", 1)]),
    ("L38", "没填身份也带 identities", [(LOGIC, "  if (Object.keys(identities).length > 0) body.identities = identities;\n  return body;", "  body.identities = identities;\n  return body;", 1)]),
    ("L39", "标题没改也带上", [(LOGIC, "  if (title !== detail.title.trim()) patch.title = title;", "  patch.title = title;", 1)]),
    ("L40", "已有成员不带 role", [(LOGIC, "      ? { role: pick.role, name: pick.name, does: pick.does, focus: pick.focus }", "      ? { name: pick.name, does: pick.does, focus: pick.focus }", 1)]),
    ("L41", "只改分工不算改动", [(LOGIC, "    && pick.does === right[index].does\n    && pick.focus === right[index].focus);", "    && pick.does === right[index].does);", 1)]),
    ("L42", "回答改了不带上", [(LOGIC, "  if (draft.answers !== detail.answers) patch.answers = draft.answers;\n", "", 1)]),
    ("L43", "只有版本号的补丁不算空", [(LOGIC, 'return Object.keys(patch).every(key => key === "expected_revision");', "return Object.keys(patch).length === 0;", 1)]),
    ("L44", "403 没有专门文案", [(LOGIC, '  if (status === 403) return "你的账号暂未开通讨论群";\n', "", 1)]),
    ("L45", "任何 404 都说尚未开放", [(LOGIC, 'if (status === 404 && typeof message === "string" && message.trim() === "Not Found") {', "if (status === 404) {", 1)]),
    ("L46", "已有查询串时仍用问号", [(LOGIC, '`${path}${path.includes("?") ? "&" : "?"}embed=1`', "`${path}?embed=1`", 1)]),
    ("L47", "调换成员顺序不算改动", [(LOGIC, "  && left.every((pick, index) => pick.role === right[index].role\n    && pick.name === right[index].name", "  && left.every((pick) => right.some(other => other.role === pick.role)\n    && right.some(other => other.name === pick.name)", 1), (LOGIC, "    && pick.does === right[index].does\n    && pick.focus === right[index].focus);", "    && right.some(other => other.does === pick.does)\n    && right.some(other => other.focus === pick.focus));", 1)]),
    ("S1", "没传属性时也显示书签", [(SIDEBAR, "const discussAllowed = discussAccessAllowed === true;", "const discussAllowed = discussAccessAllowed !== false;", 1)]),
    ("S2", "手机底栏出现讨论群", [(SIDEBAR, 'item.href !== "/studio" && item.href !== "/discuss"', 'item.href !== "/studio"', 1)]),
    ("S3", "抽屉打开时不高亮", [(SIDEBAR, ' || (href === "/discuss" && discussActive);', ";", 1)]),
    ("S4", "独立页面上不高亮", [(SIDEBAR, ' || (href === "/discuss" && pathname.startsWith("/discuss/"))', "", 1)]),
    ("S5", "点书签不调用回调", [(SIDEBAR, ': href === "/discuss" ? onDiscussClick : onSettingsClick;', ": onSettingsClick;", 1)]),
    ("S6", "侧栏自己去查访问权限", [(SIDEBAR, "const discussAllowed = discussAccessAllowed === true;", 'const discussAllowed = discussAccessAllowed === true;\n  useEffect(() => { void apiFetch(`${API}/discuss/access`).catch(() => {}); }, []);', 1)]),
    ("P1", "关闭消息不校验来源窗口", [(PAGE, "if (event.origin !== window.location.origin || event.source !== discussFrameRef.current?.contentWindow) return;", "if (event.origin !== window.location.origin) return;", 1)]),
    ("P2", "没权限也挂 iframe", [(PAGE, "{discussAllowed ? <iframe key={username} ref={discussFrameRef}", "{true ? <iframe key={username} ref={discussFrameRef}", 1)]),
    ("P3", "失去权限时不关抽屉", [(PAGE, '      if (!allowed) setDrawer(current => current === "discuss" ? null : current);\n', "", 1)]),
    ("P4", "iframe 不带 embed", [(PAGE, 'src="/discuss?embed=1"', 'src="/discuss"', 1)]),
    ("P5", "关闭消息不校验源", [(PAGE, "if (event.origin !== window.location.origin || event.source !== discussFrameRef.current?.contentWindow) return;", "if (event.source !== discussFrameRef.current?.contentWindow) return;", 1)]),
    ("B1", "回答不是字符串也原样返回", [(SERVICE, '"answers": (config_data.get("answers")\n                    if isinstance(config_data.get("answers"), str) else ""),', '"answers": config_data.get("answers"),', 1)]),
    ("B2", "回答永远是空", [(SERVICE, '"answers": (config_data.get("answers")\n                    if isinstance(config_data.get("answers"), str) else ""),', '"answers": "",', 1)]),
    ("G1", "出现字重写法", [(SHELF, 'className="', 'className="font-medium ', 1)]),
    ("G2", "用了 dangerouslySetInnerHTML", [(DOCUMENT, "<pre className=", "<pre dangerouslySetInnerHTML={{ __html: block.text }} className=", 1)]),
    ("G3", "外链缺 noreferrer", [(DOCUMENT, 'rel="noopener noreferrer"', 'rel="noopener"', 1)]),
    ("G4", "纯函数文件有运行时依赖", [(LOGIC, "// 讨论群的纯函数。", 'import { API_BASE } from "./config";\n// 讨论群的纯函数。', 1)]),
    ("G5", "页面文件不是客户端组件", [(LIST_PAGE, '"use client";', "", 1)]),
    ("G6", "CLAUDE.md 没有第二期小节", [("CLAUDE.md", "讨论群界面（第二期）", "讨论群界面", 1)]),
    ("T1", "表头去掉 font-normal（浏览器默认加粗）", [(DOCUMENT, "break-words font-normal text-[color:var(--ink2)]", "break-words text-[color:var(--ink2)]", 1)]),
    ("T2", "侧栏隐藏滚动条的类不带 !", [(SIDEBAR, "[scrollbar-width:none]! [&::-webkit-scrollbar]:hidden!", "[scrollbar-width:none] [&::-webkit-scrollbar]:hidden", 1)]),
    ("T3", "讨论群抽屉的类名又拆开拼接", [(PAGE, 'max-md:rounded-none max-md:pt-[env(safe-area-inset-top)] drawer-panel"\n        style={{\n          width: "calc((100vw - var(--rail-w) - 12px) * 2 / 3)",\n          borderLeft: "1px solid var(--rule)",\n          ...drawerStyle(discussOpen),', 'max-md:rounded-none max-md:pt-[env(safe-area-inset-top)] " + "drawer" + "-panel"\n        style={{\n          width: "calc((100vw - var(--rail-w) - 12px) * 2 / 3)",\n          borderLeft: "1px solid var(--rule)",\n          ...drawerStyle(discussOpen),', 1)]),
    ("T4", "新对话框不带 scrim-dialog", [(DIALOGS, "text-[color:var(--ink)] scrim-dialog\"", "text-[color:var(--ink)]\"", 1)]),
    ("T5", "新对话框退回手写弹层", [(DIALOGS, "    <dialog\n      ref={ref}", "    <div role=\"dialog\"\n      ref={ref as never}", 1), (DIALOGS, "        {children}\n      </div>\n    </dialog>", "        {children}\n      </div>\n    </div>", 1)]),
    # 返修 2：底部留白、消息区最小高度、对话框只在点遮罩时关闭
    ("U1", "外壳内容容器又写死 h-full", [(SHELL, "max-w-[1440px] flex-[1_0_auto] flex-col", "max-w-[1440px] h-full min-h-0 flex-col", 1)]),
    ("U2", "main 不再是纵向 flex（内容容器撑不满）", [(SHELL, "relative z-[1] flex min-h-0 min-w-0 flex-1 flex-col overflow-y-auto", "relative z-[1] min-h-0 min-w-0 flex-1 overflow-y-auto", 1)]),
    ("U3", "房间根节点又写死 h-full", [(ROOM, '"flex flex-[1_0_auto] min-w-0 flex-col" data-discuss-room', '"flex h-full min-h-0 min-w-0 flex-col" data-discuss-room', 1)]),
    ("U4", "房间根节点不再撑满", [(ROOM, '"flex flex-[1_0_auto] min-w-0 flex-col" data-discuss-room', '"flex min-w-0 flex-col" data-discuss-room', 1)]),
    ("U5", "消息区没有最小高度", [(TIMELINE, "min-h-[120px] flex-[1_1_0px] overflow-y-auto", "min-h-0 flex-[1_1_0px] overflow-y-auto", 1)]),
    ("U6", "消息区的基准退回百分比", [(TIMELINE, "min-h-[120px] flex-[1_1_0px] overflow-y-auto", "min-h-[120px] flex-1 overflow-y-auto", 1)]),
    ("U7", "宽布局两栏没有最小高度", [(ROOM, "grid flex-[1_1_0px] min-h-[320px]", "grid flex-[1_1_0px] min-h-0", 1)]),
    ("U8", "宽布局两栏的基准退回百分比", [(ROOM, "grid flex-[1_1_0px] min-h-[320px]", "grid flex-1 min-h-[320px]", 1)]),
    ("U9", "对话框自己又带内边距", [(DIALOGS, "text-[color:var(--ink)] scrim-dialog\"", "p-6 text-[color:var(--ink)] scrim-dialog\"", 1)]),
    ("U10", "对话框内容层没有内边距", [(DIALOGS, '<div className="p-6 mobile:p-4">', '<div className="">', 1)]),
    ("U11", "标签条以下的区域不再撑满", [(ROOM, 'className="mt-4 flex min-w-0 flex-[1_0_auto] flex-col"', 'className="mt-4 flex min-w-0 flex-col"', 1)]),
    ("U12", "群聊面板不再撑满", [(TIMELINE, '<section className="flex flex-[1_0_auto] flex-col" aria-label="群聊">', '<section className="flex flex-col" aria-label="群聊">', 1)]),
    ("U13", "窄布局的布局层不再撑满", [(ROOM, ': "flex flex-[1_0_auto] flex-col"}', ': "flex flex-col"}', 1)]),
    ("U14", "消息区外层不再撑满", [(TIMELINE, '<div className="relative flex min-h-0 flex-[1_0_auto] flex-col">', '<div className="relative flex min-h-0 flex-col">', 1)]),
    ("U15", "窄布局的群聊分区不再撑满", [(ROOM, ': "mt-4 flex min-w-0 flex-[1_0_auto] flex-col"}', ': "mt-4 flex min-w-0 flex-col"}', 1)]),
    ("U16", "群聊分区的内层不再撑满", [(ROOM, '<div className="flex min-w-0 flex-[1_0_auto] flex-col">', '<div className="flex min-w-0 flex-col">', 1)]),
    # 复核返修 1：读取游标、自定义成员模型、分工、字重守卫、多列表格、插话焦点、隐藏期间的新消息、外链
    ("V1", "轮询的 after 又取本地最大 id", [(ROOM, "getDiscussGroup(id, cursorRef.current, request.signal);\n      if (!request.isCurrent() || mutating.current) return;", "getDiscussGroup(id, Math.max(0, ...(detailRef.current?.messages ?? []).map(message => message.id)), request.signal);\n      if (!request.isCurrent() || mutating.current) return;", 1)]),
    ("V2", "发插话时也推动游标", [(ROOM, "const message = await addDiscussNote(id, { text }, request.signal);", "const message = await addDiscussNote(id, { text }, request.signal);\n      cursorRef.current = advanceDiscussCursor(cursorRef.current, [message]);", 1)]),
    ("V3", "游标可以往回退", [(LOGIC, "Number.isInteger(id) && id > next) next = id;", "Number.isInteger(id)) next = id;", 1)]),
    ("V4", "读回消息后不推动游标", [(ROOM, "    cursorRef.current = advanceDiscussCursor(cursorRef.current, next.messages);\n", "", 1)]),
    ("V5", "自定义成员的初始模型取了固定席位的默认值", [(LOGIC, 'if (role.kind !== "lens") continue;', 'if (role.kind !== "core") continue;', 1)]),
    ("V6", "自定义成员的模型只在与默认不同时才发", [(LOGIC, "models[`custom${index + 1}`] = member.model;", "if (member.model !== member.default_model) models[`custom${index + 1}`] = member.model;", 1)]),
    ("V7", "新建表单不用初始模型函数", [(CREATEFORM, 'defaultDiscussCustomMemberModel(catalog) || catalog.models[0]?.id || ""', 'catalog.models[0]?.id || ""', 1)]),
    ("V8", "分工只认角色池成员", [(LOGIC, '(member.kind === "lens" || member.kind === "custom")', '(member.kind === "lens")', 1)]),
    ("V9", "方案只读视图又用旧条件", [(PLANPANEL, "{discussMemberShowsFocus(member) && (", '{member.kind === "lens" && !!member.focus && (', 1)]),
    ("V10", "部件里出现带属性的 strong", [(DOCUMENT, '<div className="max-w-full overflow-x-auto">', '<div className="max-w-full overflow-x-auto"><strong className="x">x</strong>', 1)]),
    ("V11", "部件里出现任意属性写法的字重", [(DOCUMENT, 'className="tag mx-px align-middle whitespace-nowrap"', 'className="tag mx-px align-middle whitespace-nowrap [font-weight:600]"', 1)]),
    ("V12", "表格没有最小宽度", [(DOCUMENT, "\n        style={{ minWidth: `${discussTableMinWidth(block.header.length)}em` }}", "", 1)]),
    ("V13", "表格最小宽度不随列数变", [(LOGIC, "return count * 8;", "return 8;", 1)]),
    ("V14", "插话框发送中又用 disabled", [(COMPOSER, "readOnly={sending || busy}", "disabled={sending || busy}", 1)]),
    ("V15", "发送后不把焦点放回插话框", [(COMPOSER, "      textareaRef.current?.focus();\n", "", 1)]),
    ("V16", "不在群聊标签时不记新消息", [(TIMELINE, "if (arrived && !firstViewRef.current) pendingWhileHiddenRef.current = true;", "", 1)]),
    ("V17", "回到群聊标签时总是滚到最新", [(TIMELINE, "const shouldFollow = nearBottomRef.current;\n    const frame", "const shouldFollow = true;\n    const frame", 1)]),
    ("V18", "回到群聊标签时从不滚到最新", [(TIMELINE, "const shouldFollow = nearBottomRef.current;\n    const frame", "const shouldFollow = false;\n    const frame", 1)]),
    ("V19", "编号链接不过 safeExternalUrl", [(DOCUMENT, "const href = source ? safeExternalUrl(source.url) : null;", "const href = source ? source.url : null;", 1)]),
    ("V20", "来源链接不过 safeExternalUrl", [(SOURCES, "const href = safeExternalUrl(source.url);", "const href = source.url;", 1)]),
    # 第 2 轮复核指出的守卫缺口（R13、R14、R15、R19）与两条可优化（R02、R03、R18）
    ("W1", "表格最小宽度的单位从 em 改成 px", [(DOCUMENT, "discussTableMinWidth(block.header.length)}em`", "discussTableMinWidth(block.header.length)}px`", 1)]),
    ("W2", "表格最小宽度按行数算", [(DOCUMENT, "discussTableMinWidth(block.header.length)", "discussTableMinWidth(block.rows.length)", 1)]),
    ("W3", "只在发送成功时把焦点放回插话框", [(COMPOSER, "      setText(\"\");\n    } catch (caught) {", "      setText(\"\");\n      textareaRef.current?.focus();\n    } catch (caught) {", 1), (COMPOSER, "      // 成功或失败都把焦点留在插话框，键盘用户可以接着输入。\n      textareaRef.current?.focus();\n", "", 1)]),
    ("W4", "回到群聊标签处理完不清掉标记", [(TIMELINE, "      pendingWhileHiddenRef.current = false;\n", "", 1)]),
    ("W5", "编号链接带回落到原始地址", [(DOCUMENT, "const href = source ? safeExternalUrl(source.url) : null;", "const href = source ? (safeExternalUrl(source.url) ?? source.url) : null;", 1)]),
    ("W6", "来源链接带回落到原始地址", [(SOURCES, "const href = safeExternalUrl(source.url);", "const href = safeExternalUrl(source.url) || source.url;", 1)]),
    ("W7", "没看过群聊时也记下隐藏期间的新消息", [(TIMELINE, "if (arrived && !firstViewRef.current) pendingWhileHiddenRef.current = true;", "if (arrived) pendingWhileHiddenRef.current = true;", 1)]),
]


def replace_nth(text, old, new, nth):
    position = -1
    for _ in range(nth):
        position = text.find(old, position + 1)
        if position < 0:
            raise LookupError(f"找不到第 {nth} 处：{old[:60]!r}")
    return text[:position] + new + text[position + len(old):]


def run_tests(clone):
    env = dict(os.environ, NO_PROXY="localhost,127.0.0.1,::1,.local", no_proxy="localhost,127.0.0.1,::1,.local")
    env.pop("ANTHROPIC_BASE_URL", None)
    tests = sorted(str(path.relative_to(clone / "backend"))
                   for path in (clone / "backend/tests").glob("test_discuss_frontend_*.py"))
    tests.append("tests/test_discuss_ui_api.py")
    tests.append("tests/test_ui_polish_page_contracts.py")
    tests.append("tests/test_ui_closeout_dialog_scrim.py")
    command = [".venv/bin/python", "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", *tests]
    try:
        done = subprocess.run(command, cwd=clone / "backend", env=env, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        return 124, "timeout"
    lines = [line for line in done.stdout.splitlines() if line.strip()]
    return done.returncode, lines[-1] if lines else ""


def main():
    source, clone, out = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve(), Path(sys.argv[3]).resolve()
    wanted = set(sys.argv[4:])
    if clone.exists():
        raise SystemExit("克隆目录已存在，请换一个")
    subprocess.run(["cp", "-cR", str(source), str(clone)], check=True)
    code, summary = run_tests(clone)
    print(f"正控（未改动）：exit={code} {summary}", flush=True)
    if code != 0 or " skipped" in summary:
        raise SystemExit("正控没有全过或有跳过，结果无效")
    results = []
    for mutation_id, title, edits in MUTATIONS:
        if wanted and mutation_id not in wanted:
            continue
        originals = {}
        try:
            for path, old, new, nth in edits:
                target = clone / path
                originals.setdefault(path, target.read_text(encoding="utf-8"))
                target.write_text(replace_nth(target.read_text(encoding="utf-8"), old, new, nth), encoding="utf-8")
        except LookupError as error:
            for path, text in originals.items():
                (clone / path).write_text(text, encoding="utf-8")
            results.append({"id": mutation_id, "title": title, "killed": None, "summary": str(error)})
            print(f"{mutation_id:4} 锚点缺失  {title}  [{error}]", flush=True)
            continue
        code, summary = run_tests(clone)
        for path, text in originals.items():
            (clone / path).write_text(text, encoding="utf-8")
        killed = code != 0
        by_error = killed and " failed" not in f" {summary}"
        results.append({"id": mutation_id, "title": title, "killed": killed, "by_error": by_error, "summary": summary})
        label = "存活" if not killed else "杀死（非断言失败，需复核）" if by_error else "杀死"
        print(f"{mutation_id:4} {label}  {title}  [{summary}]", flush=True)
    code, summary = run_tests(clone)
    print(f"收尾正控（全部还原后）：exit={code} {summary}", flush=True)
    survived = [item["id"] for item in results if item["killed"] is False]
    missing = [item["id"] for item in results if item["killed"] is None]
    by_error = [item["id"] for item in results if item.get("by_error")]
    print(f"非断言失败的「杀死」：{by_error}")
    print(f"合计 {len(results)}，杀死 {sum(1 for item in results if item['killed'])}，存活 {survived}，锚点缺失 {missing}")
    out.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    raise SystemExit(0 if code == 0 else 1)


if __name__ == "__main__":
    main()
