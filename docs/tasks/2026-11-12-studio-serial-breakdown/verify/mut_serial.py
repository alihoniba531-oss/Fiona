"""工作室续拆 · 变异测试（验收方脚本，不进产品代码）。

在工作树的写时复制克隆里逐项把实现改坏一处，跑对应的新测试，必须变红；每项结束按原字节还原。
用法：python3 -I mut_serial.py <工作树> <克隆目录> <结果文件> [--workers N] [--only M1,M2]
"""
import concurrent.futures
import json
import os
import re
import shutil
import subprocess
import sys
import time

SRC_T = "tests/test_studio_serial_sources.py"
CON_T = "tests/test_studio_serial_continue.py"
FE_T = "tests/test_studio_serial_frontend.py"
OLD_SRC_T = "tests/test_studio_sources.py"
DESELECT = "not zzz_none"
BACK = SRC_T; FRONT = CON_T; DESK = FE_T

SO = "backend/studio/sources.py"
NC = "backend/studio/novel_chat.py"
MA = "backend/studio/breakdown_material.py"
BD = "backend/studio/breakdown.py"
BP = "backend/studio/breakdown_plan.py"
PANEL = "frontend/components/studio/BreakdownPanel.tsx"
STAGE = "frontend/components/studio/BreakdownStage.tsx"
DIALOG = "frontend/components/studio/BreakdownQuoteDialog.tsx"
PLAN = "frontend/components/studio/EpisodePlan.tsx"
SP = "frontend/components/studio/SourcePanel.tsx"
SC = "frontend/components/studio/SourceChoices.tsx"
NWB = "frontend/components/novel/NovelWorkbench.tsx"
NFD = "frontend/components/novel/NovelFilmDialog.tsx"
LIB = "frontend/lib/studio-breakdown.ts"

MUTS = [
 ("S1", "资格不看 _rearchive", SO, [("    if editing or (book.get('config') or {}).get('_rearchive') is not None:", "    if editing:", None)], [SRC_T]),
 ("S2", "资格重新要求完结", SO, [("    if canonical_bible is None:\n        return False, '作品缺少故事圣经'", "    if book.get('status') != 'completed':\n        return False, '作品尚未完结'\n    if canonical_bible is None:\n        return False, '作品缺少故事圣经'", None)], [SRC_T]),
 ("S3", "资格不拒 0 章", SO, [("    if (book.get('chapters_done') or 0) < 1:", "    if (book.get('chapters_done') or 0) < 0:", None)], [SRC_T]),
 ("S4", "读取范围回到 max(章号, chapters_done)", SO, [("    maximum = book.get('chapters_done') or 0\n", "    maximum = max([item['chapter'] for item in book.get('chapters') or []] + [book.get('chapters_done') or 0])\n", None)], [SRC_T]),
 ("S5", "去掉章节范围校验", SO, [("    if type(maximum) is not int or not 0 <= maximum <= 300:", "    if False:", None)], [SRC_T]),
 ("S6", "签名重新含 updated_at", SO, [("    return (book.get('bible_version'), book.get('chapters_done'),", "    return (book.get('updated_at'), book.get('bible_version'), book.get('chapters_done'),", None)], [SRC_T]),
 ("S7", "签名漏 bible_version", SO, [("    return (book.get('bible_version'), book.get('chapters_done'),", "    return (None, book.get('chapters_done'),", None)], [SRC_T]),
 ("S8", "签名含 chapters_done 之后的行", SO, [("                  if isinstance(ch.get('chapter'), int) and ch['chapter'] <= chapters_done))", "                  ))", None)], [SRC_T]),
 ("S9", "签名漏 _rearchive", SO, [("            (book.get('config') or {}).get('_rearchive'),\n", "            None,\n", None)], [SRC_T]),
 ("S9b", "签名漏章状态", SO, [("            tuple((ch.get('chapter'), ch.get('status')) for ch in book.get('chapters') or []", "            tuple((ch.get('chapter'), None) for ch in book.get('chapters') or []", None)], [SRC_T]),
 ("S10", "漂移 stale 恒空", SO, [("                       'stale': stale, 'chapters_done': chapters_done}", "                       'stale': [], 'chapters_done': chapters_done}", None)], [SRC_T]),
 ("S11", "来源快照 stale 恒空", SO, [("    snapshot['stale'] = sorted(item['chapter'] for item in manifest['chapters'] if item.get('status') == 'stale')", "    snapshot['stale'] = []", None)], [SRC_T]),
 ("S12", "候选 stale 恒空", SO, [("            'stale': stale, 'projects': projects}", "            'stale': [], 'projects': projects}", None)], [SRC_T]),
 ("S13", "候选不带快照章数", SO, [("            s.chapters AS snapshot_chapters FROM studio_projects p", "            NULL AS snapshot_chapters FROM studio_projects p", None)], [SRC_T]),
 ("S14", "分身复用卡不提示同步", NC, [('            if type(snapshot_chapters) is int and snapshot_chapters < (candidate.get("chapters_done") or 0):', "            if False:", None)], [SRC_T]),
 ("S15", "分身复用卡仍写尚未花费", NC, [('            points.append("已有项目，打开即可继续")', '            points.append("已建项目，尚未花费")', None)], [SRC_T]),
 ("C1", "批号偏移不加到 depends", MA, [("            row['depends'] = [number + no_base for number in row['depends']]", "            row['depends'] = list(row['depends'])", None)], [CON_T]),
 ("C2", "批号偏移不加到 map_nos", MA, [("                row['source']['map_nos'] = [number + no_base for number in row['source']['map_nos']]", "                row['source']['map_nos'] = list(row['source']['map_nos'])", None)], [CON_T]),
 ("C3", "段号不接 segment_base", MA, [("            return segment_base + (chapter - start_chapter) // 10", "            return (chapter - 1) // 10", None)], [CON_T]),
 ("C4", "续拆末段终点按 entries 条数", MA, [("                   len(entries) if start_chapter == 1 and segment_base == 0 else last_chapter)", "                   len(entries))", None)], [CON_T]),
 ("C5", "次要来源不拒续拆参数", MA, [("    if not novel and (start_chapter != 1 or segment_base != 0 or no_base != 0):", "    if False:", None)], [CON_T]),
 ("C6", "读原文只用拆解快照号", BD, [("    snapshot_no = source.get('snapshot_no') or breakdown['snapshot_no']", "    snapshot_no = breakdown['snapshot_no']", None)], [CON_T]),
 ("C7", "续拆批仍带建议集数", BD, [("    if round_no == 0 and settings.get('target_episodes'):", "    if settings.get('target_episodes'):", None)], [CON_T]),
 ("C8", "首批不用已发布末集", BD, [("                          if item['status'] == 'succeeded'), None) if earlier else published_last)", "                          if item['status'] == 'succeeded'), None) if earlier else None)", None)], [CON_T]),
 ("C9", "不读已发布末集", BD, [("    if chunk['task'] != 'episode_plan' or round_no < 1:\n        return False", "    if True:\n        return False", None)], [CON_T]),
 ("C10", "续拆不沿用已有总表条目", BD, [("        if not continuing:\n            return key, derived, derived", "        if True:\n            return key, derived, derived", None)], [CON_T]),
 ("C11", "退役循环不跳过冻结行", BD, [("        if continuing and (old['id'] in frozen or old['id'] in alias.values()):\n            continue", "        if False:\n            continue", None)], [CON_T]),
 ("C12", "转向条目覆盖别名而非并集", BD, [("            merged_aliases = list(dict.fromkeys([*current_aliases,\n", "            merged_aliases = list(dict.fromkeys([\n", None)], [CON_T]),
 ("C13", "转向条目不补 ref_id", BD, [("        if not existing.get('ref_id') and item.get('ref_id'):\n            updates['ref_id'] = item['ref_id']", "        if False:\n            updates['ref_id'] = item['ref_id']", None)], [CON_T]),
 ("C14", "多行重名不警告", BD, [("            merge_warnings.append(f\"{item['name']} 与总表里多个同类条目重名，请手动合并\")", "            pass", None)], [CON_T]),
 ("C15", "拆解依据覆盖旧章", BD, [("        if chapter['chapter'] > payload['covered_through'] and key not in basis:", "        if True:", None)], [CON_T]),
 ("C16", "续拆不初始化 _published_max_seq", BD, [("    if type(result.get('_published_max_seq')) is not int:\n        result['_published_max_seq'] = pre_max_seq", "    if False:\n        result['_published_max_seq'] = pre_max_seq", None)], [CON_T]),
 ("C17", "旧批不补 snapshot_no", BD, [("            if chunk['source'].get('snapshot_no') is None:", "            if False:", None)], [CON_T]),
 ("C18", "确认不查 covered_through", BD, [("        if _covered_through(breakdown) != preview['covered_through']:", "        if False:", None)], [CON_T]),
 ("C19", "确认不查快照号（两处）", BD, [("        if project['snapshot_no'] != preview['snapshot_no']:", "        if False:", 2), ("        if manifest is None or payload['snapshot_no'] != project['snapshot_no']:", "        if manifest is None:", None)], [CON_T]),
 ("C20", "确认不查拆解状态", BD, [("        if (project.get('breakdown_id') != bid or breakdown is None or _retired(breakdown)\n                or breakdown['status'] != 'done'):", "        if (breakdown is None):", None)], [CON_T]),
 ("C21", "partial 也发布", BD, [("                if status == 'done':\n                    published_ids", "                if status in {'done', 'partial'}:\n                    published_ids", None)], [CON_T]),
 ("C22", "新增标记直接覆盖不取较小", BD, [("                        imported['_appended_from_unit'] = (first_new if type(appended) is not int\n                                                           else min(appended, first_new))", "                        imported['_appended_from_unit'] = first_new", None)], [CON_T]),
 ("C23", "发布后不更新 _published_max_seq", BD, [("                            imported['_published_max_seq'] = (await cursor.fetchone())[0] or 0", "                            (await cursor.fetchone())", None)], [CON_T]),
 ("C24", "取消不拦续拆", BD, [("        if _continuing(breakdown):\n            # 整本重新拆解", "        if False:\n            # 整本重新拆解", None)], [CON_T]),
 ("C25", "守卫放进 _cancel_unexecuted", BD, [("async def _cancel_unexecuted(db, breakdown, owner):\n", "async def _cancel_unexecuted(db, breakdown, owner):\n    if _continuing(breakdown):\n        raise HTTPException(409, '续拆进行中不能取消，可以等它完成或单批重跑')\n", None)], [CON_T]),
 ("C26", "改过的旧章要求快照号不同", BD, [("        if manifest is not None and (current is None or current.get('title') != info.get('title')", "        if manifest is not None and project['snapshot_no'] != breakdown['snapshot_no'] and (current is None or current.get('title') != info.get('title')", None)], [CON_T]),
 ("C27", "可续拆不看在途 job", BD, [("                       and not _retired(breakdown) and breakdown['status'] == 'done' and not active_jobs", "                       and not _retired(breakdown) and breakdown['status'] == 'done'", None)], [CON_T]),
 ("C28", "可续拆不看退役", BD, [("                       and not _retired(breakdown) and breakdown['status'] == 'done' and not active_jobs", "                       and breakdown['status'] == 'done' and not active_jobs", None)], [CON_T]),
 ("C29", "视图 continuing 恒假", BD, [("        'continuing': continuing}", "        'continuing': False}", None)], [CON_T]),
 ("C30", "报价保留 target_episodes", BD, [("'settings': {**settings, 'target_episodes': None},", "'settings': settings,", None)], [CON_T]),
 ("C31", "报价没新章也放行", BD, [("    if last <= covered:", "    if last < covered:", None)], [CON_T]),
 ("C32", "报价不查在途 job", BD, [("('uncertain','running','submitting','submitted','queued') LIMIT 1\"\"\", (breakdown['id'], owner)):", "('uncertain','running','submitting','submitted','queued') LIMIT 0\"\"\", (breakdown['id'], owner)):", None)], [CON_T]),
 ("C33", "新批 round 记 0", BD, [("                      'round': round_no}", "                      'round': 0}", None)], [CON_T]),
 ("C34", "报价不查拆解完成", BD, [("        if breakdown['status'] != 'done':\n            raise HTTPException(409, '拆解尚未全部完成，不能续拆')", "        if False:\n            raise HTTPException(409, '拆解尚未全部完成，不能续拆')", None)], [CON_T]),
 ("P1", "分集视图不过滤新单元", BP, [("        if breakdown and breakdown['imported'].get('_continuations'):", "        if False:", None)], [CON_T]),
 ("P2", "新增按集号判断", BP, [("                                  if episode['unit_to'] >= marker), None)", "                                  if episode['no'] >= marker), None)", None)], [CON_T]),
 ("P3", "批准不清新增标记", BP, [("        if imported.get('_appended_from_unit') is not None:\n            imported['_appended_from_unit'] = None", "        if False:\n            imported['_appended_from_unit'] = None", None)], [CON_T]),
 ("P4", "导出不过滤新单元", BP, [("        if decoded['imported'].get('_continuations'):", "        if False:", None)], [CON_T]),
 ("P5", "分集视图 continuing 恒假", BP, [("    result.update(continuing=continuing, appended_from=appended_from)", "    result.update(continuing=False, appended_from=appended_from)", None)], [CON_T]),
 ("P6", "已批准时仍给 appended_from", BP, [("    if breakdown is not None and not result['g0_approved']:", "    if breakdown is not None:", None)], [CON_T]),
 ("F1", "续拆中仍显示取消", PANEL, [("{continuing ? <p className=\"text-fs-13 text-[color:var(--ink2)]\" data-serial=\"\">续拆进行中不能取消，失败的批次可以单批重跑。</p> : canCancel && <button", "{canCancel && <button", None)], [FE_T]),
 ("F2", "确认续拆走整本接口", STAGE, [("chosen.continueRange ? startStudioContinuation(id, chosen.value.id, signal) : startStudioBreakdown", "chosen.continueRange ? startStudioBreakdown(id, chosen.value.id, signal) : startStudioBreakdown", None)], [FE_T]),
 ("F3", "续拆对话框显示目标时长", DIALOG, [("{!retry && !continueRange && targetMin != null", "{!retry && targetMin != null", None)], [FE_T]),
 ("F4", "分集页无续拆句", PLAN, [(" : continuing ? <p role=\"status\" className=\"mb-3 text-fs-13\">续拆进行中", " : false ? <p role=\"status\" className=\"mb-3 text-fs-13\">续拆进行中", None)], [FE_T]),
 ("F5", "新增标签放进 h3", PLAN, [("{episode.title}</h3>{addedTag(episode, \"tag\")}", "{episode.title}{addedTag(episode, \"tag\")}</h3>", None)], [FE_T]),
 ("F6", "连载提示条件只看 book_status", SP, [("source.kind === \"novel\" && typeof drift?.book_status === \"string\" && drift.book_status !== \"completed\"", "drift?.book_status !== \"completed\"", None)], [FE_T]),
 ("F7", "快照待复核只在 changed 时显示", SP, [("{source.kind === \"novel\" && source.snapshot?.stale?.length ?", "{source.kind === \"novel\" && drift?.state === \"changed\" && source.snapshot?.stale?.length ?", None)], [FE_T]),
 ("F8", "连载行不看可选", SC, [("  const serial = book.status !== \"completed\" && book.eligible;", "  const serial = book.status !== \"completed\";", None)], [FE_T]),
 ("F9", "工作台仍只对完结书", NWB, [("  const filmReady = (book?.chapters_done ?? 0) >= 1;", "  const filmReady = book?.status === \"completed\";", None)], [FE_T]),
 ("F10", "续拆报价 URL 错", LIB, [("`${project(id)}/breakdown/continue/quote`", "`${project(id)}/breakdown/quote`", None)], [FE_T]),
 ("F11", "改过旧章行只在可续拆时", PANEL, [("{!breakdown.continuable && changedCovered.length > 0 && <p", "{false && <p", None)], [FE_T]),
 ("F12", "章号不合并连续段", LIB, [("if (no === end + 1) end = no; else", "if (false) end = no; else", 2)], [FE_T]),
 ("F13", "续拆报价带时长设置", STAGE, [("setQuote({ value: result, continueRange:", "setQuote({ value: result, settings: { min: 180, max: 240 }, continueRange:", None)], [FE_T]),
 ("F14", "续拆 partial 说明不显示", PANEL, [("{continuing && breakdown.status === \"partial\" && <p", "{false && <p", None)], [FE_T]),
 ("F15", "快照落后判断反了", SC, [("snapshotChapters < chaptersDone;", "snapshotChapters > chaptersDone;", None)], [FE_T]),
 ("F16", "做成片对话框不显示连载提示", NFD, [("<SerialSourceHints book={book} />{!book.eligible", "{!book.eligible", None)], [FE_T]),
 ("F17", "续拆对话框不提示不能取消", DIALOG, [("<p data-serial=\"\">确认后不能取消；有批次失败时可以单批重跑。</p>", "", None)], [FE_T]),
 ("R1a", "同步不拦续拆进行中", SO, [("    return isinstance(imported, dict) and bool(imported.get('_continuations'))", "    return False", None)], [CON_T, SRC_T]),
 ("R1b", "快照读不出时不降级", BD, [("        except (HTTPException, OSError, ValueError):\n            warnings.append(", "        except ZeroDivisionError:\n            warnings.append(", None)], [CON_T]),
 ("R1c", "快照读不出仍可续拆", BD, [("    continuable = bool(manifest is not None and snapshot is not None", "    continuable = bool(snapshot is not None", None)], [CON_T]),
 ("R1d", "旧方案只在进行中过滤", BP, [("        if breakdown and breakdown['imported'].get('_continuations'):", "        if breakdown and breakdown['imported'].get('_continuations') and breakdown['status'] in {'running', 'partial'}:", None)], [CON_T]),
 ("R1e", "导出只在进行中过滤", BP, [("        if decoded['imported'].get('_continuations'):", "        if decoded['imported'].get('_continuations') and decoded['status'] in {'running', 'partial'}:", None)], [CON_T]),
 ("R1f", "可续拆时整本报价仍是主按钮", PANEL, [('className={breakdown?.continuable ? "btn btn-quiet min-h-10" : "btn btn-primary min-h-10"}', 'className="btn btn-primary min-h-10"', None)], [FE_T]),
 ("R1g", "表格新增标签无间距", PLAN, [('addedTag(episode, "tag ml-2")', 'addedTag(episode, "tag")', None)], [FE_T]),
 ("R1h", "续拆确认跳过 _confirmed_quote", BD, [("        payload = await _confirmed_quote(db, quote_id, pid, owner, 'breakdown_continue')", "        payload = preview", None)], [CON_T]),
 ("R1i", "续拆确认不查在途批次", BD, [("('uncertain','running','submitting','submitted','queued') LIMIT 1\"\"\", (bid, owner)):", "('uncertain','running','submitting','submitted','queued') LIMIT 0\"\"\", (bid, owner)):", None)], [CON_T]),
 ("R1j", "新增按 unit_from 判断", BP, [("                                  if episode['unit_to'] >= marker), None)", "                                  if episode['unit_from'] >= marker), None)", None)], [CON_T]),
 ("R1k", "块外改过旧章句不看可续拆", PANEL, [("{!breakdown.continuable && changedCovered.length > 0 && <p", "{changedCovered.length > 0 && <p", None)], [FE_T]),
]


def apply(data, pairs):
    for old, new, nth in pairs:
        o, n = old.encode(), new.encode()
        count = data.count(o)
        if nth is None:
            if count != 1:
                raise ValueError(f"锚点出现 {count} 次（应恰 1 次）：{old[:60]!r}")
            data = data.replace(o, n, 1)
        else:
            if count < nth:
                raise ValueError(f"锚点只出现 {count} 次（要第 {nth} 处）：{old[:60]!r}")
            idx = -1
            for _ in range(nth):
                idx = data.index(o, idx + 1)
            data = data[:idx] + n + data[idx + len(o):]
    return data


def run_tests(clone, tests):
    env = dict(os.environ, NO_PROXY="localhost,127.0.0.1,::1,.local", no_proxy="localhost,127.0.0.1,::1,.local")
    cmd = [os.path.join(clone, "backend/.venv/bin/python"), "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", "-k", DESELECT, *tests]
    started = time.time()
    proc = subprocess.run(cmd, cwd=os.path.join(clone, "backend"), env=env, capture_output=True, text=True, timeout=900)
    out = proc.stdout + proc.stderr
    summary = [line for line in out.splitlines() if re.search(r"\d+ (passed|failed|error)", line)]
    failed = re.findall(r"^FAILED (\S+)", out, re.M) + re.findall(r"^ERROR (\S+)", out, re.M)
    return proc.returncode, (summary[-1] if summary else out[-300:]), failed[:3], round(time.time() - started, 1)


def worker(clone, items):
    rows = []
    for mid, desc, rel, pairs, tests in items:
        path = os.path.join(clone, rel)
        original = open(path, "rb").read()
        try:
            mutated = apply(original, pairs)
        except ValueError as error:
            rows.append({"id": mid, "desc": desc, "status": "ANCHOR", "detail": str(error)})
            continue
        try:
            open(path, "wb").write(mutated)
            code, summary, failed, secs = run_tests(clone, tests)
        finally:
            open(path, "wb").write(original)
        status = "KILLED" if code == 1 and failed else ("SURVIVED" if code == 0 else f"EXIT{code}")
        rows.append({"id": mid, "desc": desc, "status": status, "summary": summary, "failed": failed, "secs": secs})
        print(f"{mid:4} {status:9} {secs:6}s {desc} | {summary} | {failed[:1]}", flush=True)
    return rows


def main():
    wt, clones, out = sys.argv[1], sys.argv[2], sys.argv[3]
    workers = 6
    only = None
    args = sys.argv[4:]
    if "--workers" in args:
        workers = int(args[args.index("--workers") + 1])
    if "--only" in args:
        only = set(args[args.index("--only") + 1].split(","))
    muts = [m for m in MUTS if only is None or m[0] in only]
    if "--dry" in args:
        bad = 0
        for mid, desc, rel, pairs, tests in muts:
            try:
                apply(open(os.path.join(wt, rel), "rb").read(), pairs)
            except ValueError as error:
                bad += 1; print("ANCHOR", mid, error)
        print("dry", len(muts), "bad", bad); return
    os.makedirs(clones, exist_ok=True)
    paths = []
    for i in range(workers):
        dest = os.path.join(clones, f"w{i}")
        if os.path.exists(dest):
            shutil.rmtree(dest)
        subprocess.run(["cp", "-cR", wt, dest], check=True)
        paths.append(dest)
    # 正控：未变异时，排除自检后的三个文件必须全绿
    code, summary, failed, secs = run_tests(paths[0], [SRC_T, CON_T, FE_T])
    print(f"POSITIVE-CONTROL exit={code} {summary} {secs}s", flush=True)
    if code != 0:
        print("正控失败，停止", failed)
        sys.exit(3)
    buckets = [[] for _ in range(workers)]
    for i, m in enumerate(muts):
        buckets[i % workers].append(m)
    rows = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        for part in pool.map(worker, paths, buckets):
            rows.extend(part)
    order = {m[0]: i for i, m in enumerate(MUTS)}
    rows.sort(key=lambda r: order[r["id"]])
    json.dump({"positive_control": summary, "rows": rows}, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    counts = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print("TOTAL", len(rows), counts)
    for r in rows:
        if r["status"] != "KILLED":
            print("NOT-KILLED", r["id"], r["status"], r["desc"], r.get("summary") or r.get("detail"))


if __name__ == "__main__":
    main()
