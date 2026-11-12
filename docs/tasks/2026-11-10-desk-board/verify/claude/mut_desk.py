"""案头第一期 · 变异测试（Claude 在执行者沙箱外、工作树的克隆副本里运行）。

用法：python3 -I mut_desk.py <克隆副本根目录>
每项：把实现改坏一处 → 跑 backend/tests/test_desk_*.py → 必须有「非自检」用例变红 → 按字节还原。
副本用 `cp -cR <工作树> <副本>` 得到（APFS 克隆），不碰真实工作树。
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
PY = str(ROOT / "backend/.venv/bin/python")
D = "frontend/lib/desk.ts"
CH = "frontend/components/desk/DeskChaptersView.tsx"
EP = "frontend/components/desk/DeskEpisodesView.tsx"
FR = "frontend/components/desk/DeskFrame.tsx"
ID = "frontend/components/desk/DeskIdeaView.tsx"
PG = "frontend/app/page.tsx"
DK = "frontend/components/desk/DeskDock.tsx"
SEAL = '"tag text-[color:var(--seal)] border-[color:var(--seal)]"'
DG = "frontend/components/desk/DeskDialogs.tsx"
# 这些变异改的是视图，但要靠容器竞态用例才抓得到，所以也跑容器用例
FULL = ("M64 ",)

MUTATIONS = [
    ("M01 并排阈值 1440→1400", D, 'if (width >= 1440) return "dock";', 'if (width >= 1400) return "dock";', 1),
    ("M02 抽屉阈值 768→700", D, 'if (width >= 768) return "drawer";', 'if (width >= 700) return "drawer";', 1),
    ("M03 项目卡路径放行多段", D, r'const PROJECT_PATH = /^\/studio\/([A-Za-z0-9_-]{1,64})$/;', r'const PROJECT_PATH = /^\/studio\/([A-Za-z0-9_\/-]{1,64})$/;', 1),
    ("M04 出错的项目卡也定位", D, "    if (candidate.error) return null;\n", "", 1),
    ("M05 记忆里放行置灰阶段", D, "DESK_STAGES.find(item => item.enabled && item.id === record.stage)", "DESK_STAGES.find(item => item.id === record.stage)", 1),
    ("M06 open 非严格 true", D, "open: record.open === true,", "open: !!record.open,", 1),
    ("M07 空用户名也写记忆", D, 'if (storage && username !== "") {', "if (storage) {", 1),
    ("M08 章号超过已完成章也算定稿", D, "return chapter.chapter <= chaptersDone\n", "return true\n", 1),
    ("M09 待复核不再排除出当前章", D, 'chapter.status !== "done" && chapter.status !== "stale"', 'chapter.status !== "done"', 1),
    ("M10 重新拆解中不锁编辑", D, "const editsBlocked = regenerating || !!plan.rebreakdown_pending;", "const editsBlocked = regenerating;", 1),
    ("M11 拆解未完成也能批准", D, 'const approvalBlocked = editsBlocked || (plan.status !== undefined && plan.status !== "done");', "const approvalBlocked = editsBlocked;", 1),
    ("M12 并列项目取靠后的", D, "project.created_at > latest.created_at", "project.created_at >= latest.created_at", 1),
    ("M13 引子丢掉冒号", D, "第 ${target.episode} 集：`", "第 ${target.episode} 集`", 1),
    ("M14 留言满 5 条不禁用输入框", CH, "disabled={noteBusy || notesFull} placeholder", "disabled={noteBusy} placeholder", 1),
    ("M15 所有章节标签都上朱色", CH, f"tag.settled ? {SEAL} : \"tag\"", SEAL, 1),
    ("M16 完结的书仍显示留言", CH, '{book.status !== "completed" && <div className="shrink-0 border-t', '{true && <div className="shrink-0 border-t', 1),
    ("M17 读正文不看已完成章数", CH, "{chapter.chapter <= book.chapters_done && <button", "{true && <button", 1),
    ("M18 批准按钮不看 approvalBlocked", EP, "disabled={busy || approvalBlocked || plan.episodes.length === 0 || plan.g0_approved}", "disabled={busy || plan.episodes.length === 0 || plan.g0_approved}", 1),
    ("M19 已批准仍可再批", EP, "disabled={busy || approvalBlocked || plan.episodes.length === 0 || plan.g0_approved}", "disabled={busy || approvalBlocked || plan.episodes.length === 0}", 1),
    ("M20 拆解未完成的提示文案改掉", EP, "                  拆解还没全部完成，暂时不能修改或批准，去工作室看进度。\n", "                  拆解中。\n", 1),
    ("M21 已批准标签不上朱色", EP, f"plan.g0_approved ? {SEAL} : \"tag\"", '"tag"', 1),
    ("M22 最后一集也能合并", EP, "disabled={isLast || busy || editsBlocked}", "disabled={busy || editsBlocked}", 1),
    ("M23 置灰阶段不禁用", FR, "disabled={!item.enabled}", "disabled={false}", 2),
    ("M24 每个阶段都 aria-selected", FR, "aria-selected={selected}", "aria-selected={true}", 2),
    ("M25 置灰阶段的提示改掉", FR, 'title={item.enabled ? undefined : "后续开放"}', 'title={item.enabled ? undefined : "敬请期待"}', 2),
    ("M26 头部开关丢 aria-controls", PG, ' aria-pressed={deskOpen} aria-controls="desk-panel">', " aria-pressed={deskOpen}>", 1),
    ("M27 视图里直接读 localStorage", ID, 'import type { NovelDetail } from "@/lib/novels";\n', 'import type { NovelDetail } from "@/lib/novels";\nconst leaked = typeof window === "undefined" ? null : window.localStorage;\nvoid leaked;\n', 1),
    ("M28 新代码出现加粗类", CH, '"readout text-fs-18 text-[color:var(--ink2)]"', '"readout text-fs-18 font-medium text-[color:var(--ink2)]"', 1),
    ("M31 抽屉方式面板不加纸色底", FR, '${mode === "drawer" ? " bg-[color:var(--paper)]" : ""}', "", 1),
    ("M32 半屏方式面板不加纸色底", FR, 'border-t border-[color:var(--rule)] bg-[color:var(--paper)] outline-none"', 'border-t border-[color:var(--rule)] outline-none"', 1),
    ("M33 抽屉宽度退回 488", FR, '"fixed top-3 bottom-3 right-3 z-[50] w-[476px] flex"', '"fixed top-3 bottom-3 right-3 z-[50] w-[488px] flex"', 1),
    ("M34 半屏高度退回 56dvh", FR, "min(45dvh, calc(", "min(56dvh, calc(", 1),
    ("M35 冲突提示不渲染", EP, '{notice && <p role="alert"', '{false && <p role="alert"', 1),
    ("M36 空分集仍显示汇总与批准栏", EP, ") : plan === null || plan.episodes.length === 0 ? (", ") : plan === null ? (", 1),
    ("M37 对话框文件里多一处 <dialog 字面量", "frontend/components/desk/DeskDialogs.tsx", '"use client";\n', '"use client";\n// 第二处 <dialog 字面量\n', 1),
    ("M38 用 createElement 生成对话框（躲扫描）", ID, 'import type { NovelDetail } from "@/lib/novels";\n', 'import type { NovelDetail } from "@/lib/novels";\nimport { createElement } from "react";\nexport const hidden = () => createElement("dialog", null);\n', 1),
    ("M39 任何 409 都算版本冲突", D, "return !!refreshed && refreshed.plan_revision !== previousRevision;", "return true;", 1),
    ("M40 手机宽度也自动打开", D, 'return deskMode(width) !== "sheet";', "return true;", 1),
    ("M41 写后刷新不先判所选书", DK, "    if (selectedBookRef.current !== id || !openRef.current) return;\n    const request = beginDetailRead();", "    const request = beginDetailRead();", 1),
    ("M42 候选与分集方案共用一个读作用域", DK, "    const request = beginCandidateRead();", "    const request = beginEpisodeRead();", 1),
    ("M43 关闭时不让读请求失效且不拦链式刷新", DK, "    if (open) return;\n    cancelReadScopes();\n", "    if (open) return;\n", 1, [(DK, "    if (selectedBookRef.current !== id || !openRef.current) return;\n    const request = beginDetailRead();", "    if (selectedBookRef.current !== id) return;\n    const request = beginDetailRead();", 1)]),
    ("M44 竖排 tablist 丢 aria-orientation", FR, ' aria-orientation="vertical"', "", 1),
    ("M45 章节行按钮丢 aria-label", CH, ' aria-label={`第 ${chapter.chapter} 章　${title}`}', "", 1),
    ("M46 分集行按钮丢 aria-label", EP, "aria-label={`第 ${episode.no} 集　${episode.title}`}", "", 1),
    ("M47 朱色从「已批准」标签挪到汇总行", EP, 'plan.g0_approved ? "tag text-[color:var(--seal)] border-[color:var(--seal)]" : "tag"', '"tag"', 1, [(EP, '<p className="min-w-0 text-fs-13">', '<p className={plan.g0_approved ? "min-w-0 text-fs-13 text-[color:var(--seal)] border-[color:var(--seal)]" : "min-w-0 text-fs-13"}>', 1)]),
    ("M48 没有 reason 时自拟后半句", EP, 'candidate?.reason?.trim() || ""', 'candidate?.reason?.trim() || "暂时还不能建短片项目。"', 1),
    ("M49 取数时书名显示未命名", FR, 'const bookLabel = book ? (bookTitle ? `《${bookTitle}》` : "未命名") : "";', 'const bookLabel = bookTitle ? `《${bookTitle}》` : "未命名";', 1),
    ("M50 聊天页不用 deskAutoOpens", PG, "if (deskAutoOpens(window.innerWidth)) setDeskOpenPersisted(true);", "if (window.innerWidth >= 768) setDeskOpenPersisted(true);", 1),
    ("M51 竖排上下键方向反了", D, '(key === "ArrowDown" ? 1 : key === "ArrowUp" ? -1 : 0)', '(key === "ArrowDown" ? -1 : key === "ArrowUp" ? 1 : 0)', 1),
    ("M52 竖排也认左右键", D, 'const delta = orientation === "vertical"\n    ? (key === "ArrowDown" ? 1 : key === "ArrowUp" ? -1 : 0)', 'const delta = orientation === "vertical"\n    ? (key === "ArrowDown" || key === "ArrowRight" ? 1 : key === "ArrowUp" || key === "ArrowLeft" ? -1 : 0)', 1),
    ("M53 置灰阶段也能当方向键起点", D, "  if (index < 0) return null;\n  if (key === \"Home\")", "  if (key === \"Home\")", 1),
    ("M54 卡片定位不记已处理（重开会再定位）", DK, "    if (handledFocusNonceRef.current === focus.nonce) return;\n", "", 1),
    ("M55 每个阶段标签都是 tabIndex 0", FR, "tabIndex={item.enabled && selected ? 0 : -1}", "tabIndex={0}", 2),
    ("M56 阶段标签丢 data-stage", FR, "            data-stage={item.id}\n", "", 2),
    ("M57 修改对话框 busy 又把锁定算进去", EP, "episode={editing}\n              busy={busy}\n", "episode={editing}\n              busy={busy || editsBlocked}\n", 1),
    ("M58 合并确认框 busy 又把锁定算进去", EP, "busy={busy}\n              disabled={editsBlocked}\n", "busy={busy || editsBlocked}\n              disabled={editsBlocked}\n", 1),
    ("M59 批准确认框 busy 又把锁定算进去", EP, "busy={busy}\n              disabled={approvalBlocked}\n", "busy={busy || approvalBlocked}\n              disabled={approvalBlocked}\n", 1),
    ("M60 锁定时合并确认按钮不禁用", EP, "              disabled={editsBlocked}\n              onClose={() => setMerging(null)}\n", "              onClose={() => setMerging(null)}\n", 1),
    ("M61 锁定时批准确认按钮不禁用", EP, "              disabled={approvalBlocked}\n              onClose={() => setApproving(false)}\n", "              onClose={() => setApproving(false)}\n", 1),
    ("M62 锁定时修改保存仍发请求", EP, "                if (editsBlocked) {\n", "                if (false) {\n", 1),
    ("M63 面板里收起后不还焦点", DK, "\n    onOpenChange(false);\n    window.requestAnimationFrame(focusVisibleDeskToggle);\n", "\n    onOpenChange(false);\n", 1),
    ("M64 分集对话框不通知容器", EP, "    onDialogOpenChange?.(dialogOpen);\n", "", 1),
    ("M65 容器不把分集对话框并入判断", DK, "dialogOpenRef.current = planDialog !== null || readerDialog !== null || value;", "dialogOpenRef.current = planDialog !== null || readerDialog !== null;", 1),
    ("M66 细纲对话框忙碌时关闭不禁用", DG, 'disabled={busy} onClick={onClose}>关闭</button>', 'onClick={onClose}>关闭</button>', 1),
    ("M67 收起时不清空呈现方式", DK, "      setMode(null);\n", "", 1),
    ("M68 aria-orientation 从 tablist 挪到外层容器", FR, '<nav role="tablist" aria-label="创作阶段" aria-orientation="vertical" className', '<nav role="tablist" aria-label="创作阶段" className', 1, [(FR, '    <div\n      className={mode === "dock"', '    <div\n      aria-orientation="vertical"\n      className={mode === "dock"', 1)]),
    ("M69 章回展开按钮的 aria-label 挪到整行", CH, ' aria-label={`第 ${chapter.chapter} 章　${title}`}', "", 1, [(CH, '          role="listitem"\n          ref={node => {', '          role="listitem"\n          aria-label={`第 ${chapter.chapter} 章　${title}`}\n          ref={node => {', 1)]),
    ("M70 分集展开按钮的 aria-label 挪到整行", EP, "                          aria-label={`第 ${episode.no} 集　${episode.title}`}\n", "", 1, [(EP, '                      role="listitem"\n', '                      role="listitem"\n                      aria-label={`第 ${episode.no} 集　${episode.title}`}\n', 1)]),
    ("M71 选中态钉在第一个标签", FR, "const selected = index === stageIndex;", "const selected = index === 0;", 2),
    ("M72 Home 跳到最后一个可用阶段", D, 'if (key === "Home") return enabled[0].id;', 'if (key === "Home") return enabled[enabled.length - 1].id;', 1),
    ("M73 End 跳到第一个可用阶段", D, 'if (key === "End") return enabled[enabled.length - 1].id;', 'if (key === "End") return enabled[0].id;', 1),
    ("M74 定位没回来就收起也算处理过（重开不再定位）", DK, "    focusRequestRef.current = { nonce: focus.nonce, request };\n", "    focusRequestRef.current = { nonce: focus.nonce, request };\n    handledFocusNonceRef.current = focus.nonce;\n", 1),
    ("M75 非冲突 409 刷新后不替换方案（只在真冲突时替换）", DK, "      setPlan(next);\n      setPlanLoading(false);\n      setPlanError(null);\n      return next;\n", "      return next;\n", 1, [(DK, "          setPlanNotice(PLAN_CONFLICT_TEXT);\n", "          if (refreshed) setPlan(refreshed);\n          setPlanNotice(PLAN_CONFLICT_TEXT);\n", 2)]),
    ("M76 容器里任何 409 都当版本冲突", DK, "isRevisionConflict(currentPlan.plan_revision, refreshed)", "true", 2),
    ("M77 容器里任何 409 都不当版本冲突", DK, "isRevisionConflict(currentPlan.plan_revision, refreshed)", "false", 2),
    ("M29 新代码出现十六进制色", ID, 'import type { NovelDetail } from "@/lib/novels";\n', 'import type { NovelDetail } from "@/lib/novels";\nconst tint = "#A8322A";\nvoid tint;\n', 1),
]

import os
ONLY = tuple(x for x in os.environ.get('MUT_ONLY', '').split(',') if x)
if ONLY:
    MUTATIONS = [m for m in MUTATIONS if m[0].startswith(ONLY)]
if os.environ.get('MUT_DOCK_ONLY'):
    # 只跑会用到容器竞态用例的变异（改到 DeskDock 的，或名字在 FULL 里的）
    MUTATIONS = [m for m in MUTATIONS if m[0].startswith(FULL) or any(e[0] == DK for e in [(m[1],)] + [(x[0],) for x in (m[5] if len(m) > 5 else [])])]
results = []
for item in MUTATIONS:
    name, rel, old, new, count = item[:5]
    edits = [(rel, old, new, count)] + (list(item[5]) if len(item) > 5 else [])
    originals = {r: (ROOT / r).read_bytes() for r, *_ in edits}
    texts = {r: b.decode("utf-8") for r, b in originals.items()}
    bad = [(r, o[:40], texts[r].count(o), c) for r, o, n, c in edits if texts[r].count(o) != c]
    if bad:
        results.append(False)
        print(f"FAIL {name}  锚点次数不符（变异没装上）：{bad}")
        continue
    path = ROOT / rel
    original = originals[rel]
    try:
        for r, o, n, c in edits:
            texts[r] = texts[r].replace(o, n)
        for r in texts:
            (ROOT / r).write_bytes(texts[r].encode("utf-8"))
        # 容器竞态用例较慢（约 25 秒），只在改到容器时才跑
        touched_dock = any(r == DK for r, *_ in edits) or name.startswith(FULL)
        files = sorted(str(p) for p in (ROOT / "backend/tests").glob("test_desk_*.py") if touched_dock or "dock_races" not in p.name)
        proc = subprocess.run([PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-rf", "--no-header", *files],
                              cwd=ROOT / "backend", capture_output=True, text=True, timeout=900)
        failed = re.findall(r"^FAILED (\S+)", proc.stdout, re.M)
        real = [f for f in failed if not re.search(r"self_?check", f, re.I)]
        ok = proc.returncode != 0 and bool(real)
        results.append(ok)
        print(f"{'PASS' if ok else 'FAIL'} {name}  变红 {len(failed)} 条（非自检 {len(real)} 条）  {(real or failed or [proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ''])[0][:120]}")
    finally:
        for r, b in originals.items():
            (ROOT / r).write_bytes(b)
            assert (ROOT / r).read_bytes() == b

if (ROOT / PG).read_bytes()[:3] == b"\xef\xbb\xbf":
    path = ROOT / PG
    original = path.read_bytes()
    try:
        path.write_bytes(original[3:])
        proc = subprocess.run([PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-rf", "--no-header", *sorted(str(p) for p in (ROOT / "backend/tests").glob("test_desk_*.py"))],
                              cwd=ROOT / "backend", capture_output=True, text=True, timeout=900)
        failed = re.findall(r"^FAILED (\S+)", proc.stdout, re.M)
        real = [f for f in failed if not re.search(r"self_?check", f, re.I)]
        ok = proc.returncode != 0 and bool(real)
        results.append(ok)
        print(f"{'PASS' if ok else 'FAIL'} M30 page.tsx 去掉 BOM  变红 {len(failed)} 条（非自检 {len(real)} 条）  {(real or failed or [''])[0][:120]}")
    finally:
        path.write_bytes(original)

proc = subprocess.run([PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--no-header", *sorted(str(p) for p in (ROOT / "backend/tests").glob("test_desk_*.py"))],
                      cwd=ROOT / "backend", capture_output=True, text=True, timeout=900)
tail = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
ok = proc.returncode == 0 and "failed" not in tail
results.append(ok)
print(f"{'PASS' if ok else 'FAIL'} 还原后新测试重新全绿  {tail}")
print(f"== FAIL {results.count(False)} / {len(results)}")
