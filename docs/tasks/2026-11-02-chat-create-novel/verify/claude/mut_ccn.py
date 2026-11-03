"""聊天建书变异测试：把实现的关键处逐一改坏，对应新测试（非 selfcheck 的真实用例）必须变红；按字节还原。

用法：python3 -I mut_ccn.py <工作树>
每项先在未变异状态跑一次目标测试（必须绿），再变异跑一次（必须红，且至少一条 FAILED 是非 selfcheck 用例、含指定片段），最后还原并核对字节一致。
"""
from __future__ import annotations

import os
import subprocess
import sys

WT = os.path.abspath(sys.argv[1])
PY = os.path.join(WT, "backend/.venv/bin/python")
ENV = {k: v for k, v in os.environ.items() if k.upper() not in {"HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"}}
AGENT = "backend/services/claude_agent.py"
DB = "backend/database.py"
SVC = "backend/novel/service.py"
DRAFTS = "backend/novel/drafts.py"
ROUTER = "backend/routers/novel.py"
T_BE = "tests/test_novel_chat_create.py"
T_FE = "tests/test_novel_chat_create_frontend.py"
T_LOCK = "tests/test_novel_chat.py"

# (编号, 文件, 旧字节, 新字节, 目标测试, FAILED 行必须含的片段)
MUTS = [
    ("M1 开关失效：无条件追加 draft_novel", AGENT,
     b"    if novel_create_enabled(ctx.user):\n        tools.append(NOVEL_DRAFT_TOOL)\n",
     b"    tools.append(NOVEL_DRAFT_TOOL)\n", f"{T_BE} {T_LOCK}", "test_"),
    ("M2 每轮限一份失效", AGENT, b"                    if draft_written:\n", b"                    if False:\n", T_BE, "test_"),
    ("M3 50 份上限边界 >= 改 >", AGENT, b"if open_drafts >= 50:", b"if open_drafts > 50:", T_BE, "test_"),
    ("M4 落库不核对归属", DB,
     b"""                    \"\"\"SELECT 1 FROM novel_drafts
                       WHERE id = ? AND owner_username = ? AND conversation_id = ?\"\"\",""",
     b"""                    \"\"\"SELECT 1 FROM novel_drafts
                       WHERE id = ? AND (owner_username = ? OR 1) AND (conversation_id = ? OR 1)\"\"\",""", T_BE, "test_"),
    ("M5 config 不排除 draft_id", SVC, b"config = data.model_dump(exclude={'draft_id'})", b"config = data.model_dump()", T_BE, "test_"),
    ("M6 create 不消费草稿", SVC,
     b"if data.draft_id and not await consume_draft(db, username, data.draft_id, novel_id):", b"if False:", T_BE, "test_"),
    ("M7 草稿可重复消费", DRAFTS,
     b"WHERE id = ? AND owner_username = ? AND novel_id IS NULL", b"WHERE id = ? AND owner_username = ?", T_BE, "test_"),
    ("M8 路由不隔离本人（None 直接返回）", ROUTER,
     "    if result is None:\n        raise HTTPException(404,'草稿不存在')\n".encode(), b"    if result is None:\n        return {}\n", T_BE, "test_"),
    ("M9 刷新不重建草稿卡", "frontend/lib/useConversations.ts",
     """    if (message.role === "assistant" && message.novel_draft_id) {
      cards.push({ source: "书斋", points: [], subtype: "novel_draft", draft_id: message.novel_draft_id });
    }
""".encode(), b"", T_FE, "test_"),
    ("M10 ChatCard 不渲染草稿卡", "frontend/components/ChatBubble.tsx",
     b'  if (card.subtype === "novel_draft") {', b'  if (card.subtype === "novel_draft_disabled") {', T_FE, "test_"),
    ("M11 openNovelAt 去掉路径白名单", "frontend/app/page.tsx",
     b"""      && !/^\\/novels\\/[0-9a-f-]{36}\\?embed=1$/.test(path)) return;
""", b"""      && !/^\\/novels\\/[0-9a-f-]{36}\\?embed=1$/.test(path)) { /* mutated */ }
""", T_FE, "test_"),
    ("M12 向导提交不带 draft_id", "frontend/components/novel/NovelWizard.tsx",
     b"createNovel({ ...input, draft_id: draftId ?? undefined }, request.signal)", b"createNovel(input, request.signal)", T_FE, "test_"),
    ("M13 ChatBubble 不透传 onOpenNovel（两处）", "frontend/components/ChatBubble.tsx",
     b" onOpenNovel={onOpenNovel} songCardCompact", b" songCardCompact", T_FE, "test_chat_bubble_passes_open_novel"),
    ("M14 iframe 初值改掉（既有锁改法后仍能拦）", "frontend/app/page.tsx",
     b'useState("/novels?embed=1")', b'useState("/novels/new?embed=1")', "tests/test_novel_p2_frontend.py", "test_home_keeps_novel_iframe"),
]


def pytest(targets):
    p = subprocess.run([PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-rf", *targets.split()], cwd=os.path.join(WT, "backend"), env=ENV,
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900)
    return p.returncode, p.stdout + p.stderr


fails = 0
for mid, rel, old, new, target, want in MUTS:
    path = os.path.join(WT, rel)
    with open(path, "rb") as fh:
        orig = fh.read()
    if rel.endswith("page.tsx"):
        assert orig[:3] == b"\xef\xbb\xbf", "page.tsx 缺 BOM"
    expected_count = 2 if mid.startswith("M13") else 1
    if orig.count(old) != expected_count:
        print(f"FAIL {mid}: 旧串出现 {orig.count(old)} 次（期望 {expected_count}）"); fails += 1; continue
    rc0, out0 = pytest(target)
    if rc0 != 0:
        print(f"FAIL {mid}: 未变异时目标测试已红\n{out0[-600:]}"); fails += 1; continue
    mutated = orig.replace(old, new) if expected_count > 1 else orig.replace(old, new, 1)
    try:
        with open(path, "wb") as fh:
            fh.write(mutated)
        rc, out = pytest(target)
        failed = [l for l in out.splitlines() if l.startswith("FAILED")]
        real = [l for l in failed if "selfcheck" not in l]
        hit = [l for l in failed if want in l]
        ok = rc != 0 and bool(real) and bool(hit)
        print(f"{'PASS' if ok else 'FAIL'} {mid}  rc={rc} failed={len(failed)} real={len(real)} {real[0][:150] if real else (failed[0][:150] if failed else out.splitlines()[-1][:150])}")
        fails += 0 if ok else 1
    finally:
        with open(path, "wb") as fh:
            fh.write(orig)
        with open(path, "rb") as fh:
            assert fh.read() == orig, (mid, "还原失败")
print(f"== FAIL {fails} / {len(MUTS)}")
sys.exit(fails)
