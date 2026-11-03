"""聊天建书（2026-11-02-chat-create-novel）机械门禁：按规格 §5 逐条核对。

用法：python3 -I gate_ccn.py <工作树> <HEAD 副本> [--skip-build] [--skip-pytest]
HEAD 副本用于「新测试在 HEAD 上必须失败」的对照：把两个新测试拷进去跑，跑完删掉。
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys

WT = os.path.abspath(sys.argv[1])
HEAD = os.path.abspath(sys.argv[2])
SKIP_BUILD = "--skip-build" in sys.argv
SKIP_PYTEST = "--skip-pytest" in sys.argv
PY = os.path.join(WT, "backend/.venv/bin/python")
ENV = {k: v for k, v in os.environ.items() if k.upper() not in {"HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"}}
ENV["npm_config_cache"] = "/tmp/fiona-npm-cache"
PYTEST = [PY, "-m", "pytest", "-q", "-p", "no:cacheprovider"]
BASE_PASSED = 7863
NEW_TESTS = ["test_novel_chat_create.py", "test_novel_chat_create_frontend.py"]
TRACKED_WHITELIST = {
    "backend/database.py", "backend/agent_store.py", "backend/novel/service.py", "backend/routers/novel.py",
    "backend/studio/sources.py", "backend/services/claude_agent.py", "backend/services/chat_service.py", "backend/.env.example",
    "frontend/components/ChatBubble.tsx", "frontend/lib/useConversations.ts", "frontend/app/page.tsx",
    "frontend/components/novel/NovelWizard.tsx", "frontend/lib/novels.ts",
    "CLAUDE.md", "README.md", "docs/ARCHITECTURE.md", "docs/DEPLOYMENT.md", "PLAN.md",
    "backend/tests/test_studio_sources_readonly_integration.py",  # v1.1 授权：恰两处
    "backend/tests/test_novel_p2_frontend.py",  # v1.2 授权：:40 一处
}
NEW_WHITELIST = {"backend/novel/drafts.py", "frontend/components/NovelDraftCard.tsx",
                 "backend/tests/test_novel_chat_create.py", "backend/tests/test_novel_chat_create_frontend.py"}
NEW_PREFIX = "docs/tasks/2026-11-02-chat-create-novel/"
RELATED_EXISTING = ["tests/test_novel_chat.py", "tests/test_song_agent_tools.py", "tests/test_claude_agent_runtime.py",
                    "tests/test_claude_agent_docs.py", "tests/test_novel_p1_api.py", "tests/test_novel_v2_compat.py",
                    "tests/test_novel_p21_frontend.py", "tests/test_novel_chat_frontend.py", "tests/test_claude_agent_client.py", "tests/test_novel_p2_frontend.py", "tests/test_studio_sources_readonly_integration.py"]

fails = 0
N = 0


def chk(name, ok, detail=""):
    global fails, N
    N += 1
    fails += 0 if ok else 1
    print(f"{'PASS' if ok else 'FAIL'} {name}  {detail}"[:400])


def run(cmd, cwd, timeout=1800):
    p = subprocess.run(cmd, cwd=cwd, env=ENV, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    return p.returncode, p.stdout + p.stderr


def git(args):
    return run(["git", "-c", "core.quotepath=off", *args], WT)[1]


def read(rel, root=WT):
    try:
        with open(os.path.join(root, rel), "rb") as fh:
            return fh.read()
    except FileNotFoundError:
        return b""


# ---- 1. 改动集合与白名单 ----
print("== 改动集合")
status = [line for line in git(["status", "--porcelain"]).splitlines() if line.strip()]
tracked = {line[3:].strip() for line in status if not line.startswith("??")}
untracked = []
for line in status:
    if line.startswith("??"):
        path = line[3:].strip()
        if path.endswith("/"):
            out = git(["ls-files", "--others", "--exclude-standard", "--", path])
            untracked.extend(out.split())
        else:
            untracked.append(path)
chk("已跟踪改动都在白名单", tracked <= TRACKED_WHITELIST, str(sorted(tracked - TRACKED_WHITELIST)))
bad_new = [p for p in untracked if p not in NEW_WHITELIST and not p.startswith(NEW_PREFIX)]
chk("未跟踪新文件都在白名单", not bad_new, str(bad_new))
chk("两个新模块存在", all(os.path.exists(os.path.join(WT, p)) for p in ("backend/novel/drafts.py", "frontend/components/NovelDraftCard.tsx")))
chk("两个新测试存在", all(os.path.exists(os.path.join(WT, "backend/tests", t)) for t in NEW_TESTS))
tests_diff = git(["diff", "HEAD", "--stat", "--", "backend/tests", ":!backend/tests/test_studio_sources_readonly_integration.py", ":!backend/tests/test_novel_p2_frontend.py"]).strip()
p2_diff = git(["diff", "-U0", "HEAD", "--", "backend/tests/test_novel_p2_frontend.py"])
chk("v1.2 授权测试恰一个 hunk", p2_diff.count("\n@@") == 1, str(p2_diff.count("\n@@")))
chk("v1.2 授权 hunk 内容", "+    assert \"src={novelFrameSrc}\" in drawer" in p2_diff and "not in drawer" in p2_diff and "-    assert 'src=\"/novels?embed=1\"' in drawer" in p2_diff)
chk("page.tsx 不再含 src=\"/novels?embed=1\" 字面量（含注释）", read("frontend/app/page.tsx").decode("utf-8-sig").count('src="/novels?embed=1"') == 0)
chk("既有测试零 diff（授权文件除外）", tests_diff == "", tests_diff[:200])
lock_diff = git(["diff", "-U0", "HEAD", "--", "backend/tests/test_studio_sources_readonly_integration.py"])
chk("授权测试恰两个 hunk", lock_diff.count("\n@@") == 2, str(lock_diff.count("\n@@")))
chk("授权 hunk 1：集合加 novel_drafts", '+                               "novel_drafts", "novel_notes", "novel_steps"}' in lock_diff)
chk("授权 hunk 2：novel.drafts 只放行三个名字", '"validate_draft_args", "create_draft", "count_open_drafts"}' in lock_diff and "novel.runner" in lock_diff)
chk("建表无条件（init_db 里无开关判断）", "if novel_create_enabled" not in read("backend/database.py").decode("utf-8") and "NOVEL_DRAFTS_DDL)" in read("backend/database.py").decode("utf-8"))
chk("无 importlib 绕行与表存在守卫", "import_module" not in read("backend/services/claude_agent.py").decode("utf-8") and all(w not in read(f).decode("utf-8") for f in ("backend/database.py", "backend/agent_store.py", "backend/novel/drafts.py", "backend/novel/service.py") for w in ("table_exists", "ensure_schema")))
# 常量不动：HEAD 与工作树的 CLAUDE_CLIENT_TOOLS 块逐字节相同
def tools_block(text):
    m = re.search(r"^CLAUDE_CLIENT_TOOLS = \[\n.*?^\]\n", text, re.S | re.M)
    return m.group(0) if m else None
head_agent = git(["show", "HEAD:backend/services/claude_agent.py"])
wt_agent = read("backend/services/claude_agent.py").decode("utf-8")
chk("CLAUDE_CLIENT_TOOLS 常量块与 HEAD 相同", tools_block(head_agent) is not None and tools_block(head_agent) == tools_block(wt_agent))
chk("page.tsx 保留 BOM", read("frontend/app/page.tsx")[:3] == b"\xef\xbb\xbf")
chk("文档里没有本机绝对路径（有文档时）", not re.search(r"/Users/|/private/tmp", "\n".join(read(p).decode("utf-8", "replace") for p in untracked if p.startswith(NEW_PREFIX) and p.endswith(".md"))))

# ---- 2. 计数（规格 §5.6）----
print("== 计数")
chk("claude_agent.py 含 draft_novel ≥ 3", wt_agent.count("draft_novel") >= 3, str(wt_agent.count("draft_novel")))
db = read("backend/database.py").decode("utf-8")
chk("messages.novel_draft_id 迁移恰 1 处", db.count("ALTER TABLE messages ADD COLUMN novel_draft_id") == 1)
chk("novel_drafts 建表存在", "CREATE TABLE IF NOT EXISTS novel_drafts" in db)
for rel in ("backend/studio/sources.py", "backend/.env.example", "CLAUDE.md"):
    chk(f"{rel} 含 FIONA_NOVEL_CHAT_CREATE", "FIONA_NOVEL_CHAT_CREATE" in read(rel).decode("utf-8"))
for rel in ("README.md", "CLAUDE.md", "PLAN.md", "docs/ARCHITECTURE.md", "docs/DEPLOYMENT.md", "backend/.env.example"):
    chk(f"{rel} 保留「卡片不落库」", "卡片不落库" in read(rel).decode("utf-8"))
wiz = read("frontend/components/novel/NovelWizard.tsx").decode("utf-8")
chk("NovelWizard 读 draft 参数", 'get("draft")' in wiz)
chk("NovelWizard 提交带 draft_id", "draft_id" in wiz)
chk("novels.ts 有 getNovelDraft", "getNovelDraft" in read("frontend/lib/novels.ts").decode("utf-8"))
page = read("frontend/app/page.tsx").decode("utf-8-sig")
chk("page.tsx 有 openNovelAt 与 novelFrameSrc", "openNovelAt" in page and "novelFrameSrc" in page)
chk("page.tsx 两处卡片复制都带 draft_id", page.count("draft_id") >= 2, str(page.count("draft_id")))
chk("useConversations 按 novel_draft_id 重建", "novel_draft_id" in read("frontend/lib/useConversations.ts").decode("utf-8"))
chk("ChatCard 有 novel_draft 分支", 'subtype === "novel_draft"' in read("frontend/components/ChatBubble.tsx").decode("utf-8"))
card = read("frontend/components/NovelDraftCard.tsx").decode("utf-8")
chk("NovelDraftCard 存在且不加粗", bool(card.strip()) and not re.search(r"font-(semibold|bold)|fontWeight\s*:\s*[6-9]00", card))
svc = read("backend/novel/service.py").decode("utf-8")
chk("CreateNovel 有 draft_id 字段", re.search(r"draft_id:\s*str\s*\|\s*None\s*=\s*None", svc) is not None)
chk("create 排除 draft_id 进 config", "exclude={'draft_id'}" in svc or 'exclude={"draft_id"}' in svc)

# ---- 3. 前端 ----
print("== 前端")
fe = os.path.join(WT, "frontend")
rc, out = run(["npx", "tsc", "--noEmit"], fe, timeout=600)
chk("tsc 退出码 0", rc == 0, out.strip().splitlines()[-1][:160] if out.strip() else "")
rc, out = run(["npm", "run", "lint"], fe, timeout=600)
mw = re.search(r"(\d+) problems? \((\d+) errors?, (\d+) warnings?\)", out)
chk("lint 0 errors 且 warnings ≤ 25", rc == 0 and mw is not None and int(mw.group(2)) == 0 and int(mw.group(3)) <= 25, mw.group(0) if mw else out[-200:])
if not SKIP_BUILD:
    rc, out = run(["npm", "run", "build"], fe, timeout=1200)
    chk("build 退出码 0", rc == 0, out.strip().splitlines()[-1][:160] if out.strip() else "")
else:
    print("SKIP build")

# ---- 4. 后端 ----
print("== 后端")
be = os.path.join(WT, "backend")
if not os.path.exists(PY):
    chk("backend/.venv 存在", False, PY)
    SKIP_PYTEST = True
    NEW_TESTS_OK = False
rc, out = run([*PYTEST, "--collect-only", *[f"tests/{t}" for t in NEW_TESTS]], be, timeout=300) if os.path.exists(PY) else (1, "")
m = re.search(r"(\d+) tests? collected", out) or re.search(r"collected (\d+) items?", out)
new_count = int(m.group(1)) if m else 0
chk("新测试可收集", new_count > 0, f"{new_count} collected")
rc, out = run([*PYTEST, "-rf", *[f"tests/{t}" for t in NEW_TESTS], *RELATED_EXISTING], be, timeout=900) if os.path.exists(PY) else (1, "")
chk("新测试 + 相关既有测试在候选上全过、无 skip", rc == 0 and " passed" in out and "skipped" not in out.splitlines()[-1], out.splitlines()[-1] if out.strip() else "")
if not SKIP_PYTEST:
    rc, out = run(PYTEST, be, timeout=1800)
    last = out.strip().splitlines()[-1] if out.strip() else ""
    mp = re.search(r"(\d+) passed", last); ms = re.search(r"(\d+) skipped", last); mf = re.search(r"(\d+) failed", last)
    passed = int(mp.group(1)) if mp else -1
    chk("全量 pytest 0 failed 0 skipped", rc == 0 and not mf and not ms, last)
    chk(f"passed = {BASE_PASSED} + {new_count}", passed == BASE_PASSED + new_count, f"passed={passed}")
else:
    print("SKIP full pytest")

# ---- 5. HEAD 对照 ----
print("== HEAD 对照")
head_tests = os.path.join(HEAD, "backend/tests")
if not all(os.path.exists(os.path.join(WT, "backend/tests", t)) for t in NEW_TESTS):
    chk("HEAD 对照：新测试缺失，无法对照", False)
    print(f"== FAIL {fails} / {N}")
    sys.exit(fails)
try:
    for t in NEW_TESTS:
        shutil.copyfile(os.path.join(WT, "backend/tests", t), os.path.join(head_tests, t))
    rc, out = run([*PYTEST, "-rf", "--tb=line", *[f"tests/{t}" for t in NEW_TESTS]], os.path.join(HEAD, "backend"), timeout=600)
    print(out[-3000:])
    failed_ids = re.findall(r"^FAILED (tests/\S+)", out, re.M)
    chk("HEAD: 后端契约测试有失败", any("test_novel_chat_create.py" in i for i in failed_ids), str(len(failed_ids)))
    chk("HEAD: 前端契约测试有失败", any("test_novel_chat_create_frontend.py" in i for i in failed_ids))
    chk("HEAD: 没有 ImportError / ModuleNotFoundError / 收集错误", not re.search(r"ImportError|ModuleNotFoundError|ERROR collecting|errors? during collection", out))
    chk("HEAD: 失败全是 AssertionError", not re.search(r"\b(NameError|TypeError|SyntaxError|FileNotFoundError|KeyError|AttributeError)\b", out))
    chk("HEAD: 无 skip", "skipped" not in (out.strip().splitlines()[-1] if out.strip() else ""))
finally:
    for t in NEW_TESTS:
        try:
            os.remove(os.path.join(head_tests, t))
        except FileNotFoundError:
            pass

print(f"== FAIL {fails} / {N}")
sys.exit(fails)
