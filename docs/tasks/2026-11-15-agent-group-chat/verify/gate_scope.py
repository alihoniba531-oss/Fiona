#!/usr/bin/env python3
"""第三期门禁：范围、既有测试哈希、白名单外文件哈希、授权改动的精确形状、CLAUDE.md 字节数、绝对路径。
用法：gate_scope.py <工作树根> <快照目录>
退出码 0 = 全过；1 = 有违规。每项先打印「扫到了多少」，防止空扫假绿。
"""
import fnmatch
import getpass
import hashlib
import pathlib
import re
import subprocess
import sys

root = pathlib.Path(sys.argv[1]).resolve()
snap = pathlib.Path(sys.argv[2]).resolve()

MOD_ALLOWED = {
    "backend/discuss/config.py", "backend/discuss/service.py", "backend/discuss/store.py",
    "backend/routers/discuss.py", "backend/database.py", "backend/agent_store.py",
    "backend/rate_limit.py", "backend/intent_router.py",
    "backend/services/chat_service.py", "backend/services/claude_agent.py",
    "frontend/lib/discuss.ts", "frontend/lib/discussLogic.ts", "frontend/lib/useConversations.ts",
    "frontend/components/ChatBubble.tsx", "frontend/app/page.tsx",
    "frontend/app/discuss/new/page.tsx", "frontend/components/discuss/DiscussCreateForm.tsx",
    "frontend/components/ChatModelSection.tsx",
    "backend/tests/test_empty_states_settings_privacy.py",
    "README.md", "CLAUDE.md", "PLAN.md", "docs/ARCHITECTURE.md", "docs/DEPLOYMENT.md",
    "backend/.env.example",
}
NEW_ALLOWED = [
    "backend/discuss/chat.py", "backend/discuss/cards.py",
    "frontend/components/DiscussTaskCard.tsx", "frontend/components/DiscussNoteCard.tsx",
    "backend/tests/test_discuss_chat_*.py",
    "docs/tasks/2026-11-15-agent-group-chat/impl/report*.md",
    # 规格作者自己放的
    "docs/tasks/2026-11-15-agent-group-chat/01-investigation.md",
    "docs/tasks/2026-11-15-agent-group-chat/02-spec.md",
    "docs/tasks/2026-11-15-agent-group-chat/03-dispatch.md",
    "docs/tasks/2026-11-15-agent-group-chat/0[4-9]-*.md",
    "docs/tasks/2026-11-15-agent-group-chat/1[0-9]-*.md",
]
AUTH_TEST = "backend/tests/test_empty_states_settings_privacy.py"
bad = []


def sha(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True).stdout


# 1. 改动集合
status = git("status", "--porcelain", "--untracked-files=all")
mods, news, other = [], [], []
for line in status.splitlines():
    code, path = line[:2], line[3:]
    if code == "??":
        news.append(path)
    elif code.strip() == "M":
        mods.append(path)
    else:
        other.append((code, path))
print(f"[1] 改动集合：修改 {len(mods)} 个、新增 {len(news)} 个、其他状态 {len(other)} 个")
if not mods and not news:
    bad.append("改动集合为空，门禁没扫到东西")
for code, path in other:
    bad.append(f"意外的 git 状态 {code!r}: {path}")
for p in mods:
    if p not in MOD_ALLOWED:
        bad.append(f"白名单外的修改：{p}")
for p in news:
    if not any(fnmatch.fnmatchcase(p, pat) for pat in NEW_ALLOWED):
        bad.append(f"白名单外的新文件：{p}")
untouched = sorted(MOD_ALLOWED - set(mods))
print(f"    白名单内没动的文件 {len(untouched)} 个：{untouched}")
new_tests = sorted(p for p in news if fnmatch.fnmatchcase(p, "backend/tests/test_discuss_chat_*.py"))
print(f"    新测试文件 {len(new_tests)} 个")

# 2. 既有测试哈希
lines = (snap / "baseline-tests.sha").read_text().splitlines()
changed = []
for line in lines:
    h, path = line.split("  ", 1)
    f = root / path
    if not f.exists():
        bad.append(f"既有测试文件被删：{path}")
    elif sha(f) != h:
        changed.append(path)
print(f"[2] 既有测试：比对 {len(lines)} 个文件，变化 {len(changed)} 个：{changed}")
if len(lines) < 300:
    bad.append("既有测试基线不足 300 个文件，快照不对")
for p in changed:
    if p != AUTH_TEST:
        bad.append(f"既有测试被改：{p}")

# 3. 白名单外的其余跟踪文件
lines = (snap / "baseline-tracked.sha").read_text().splitlines()
changed2 = []
for line in lines:
    h, path = line.split("  ", 1)
    f = root / path
    if not f.exists():
        bad.append(f"跟踪文件被删：{path}")
    elif sha(f) != h:
        changed2.append(path)
print(f"[3] 其余跟踪文件：比对 {len(lines)} 个，变化 {len(changed2)} 个")
if len(lines) < 2000:
    bad.append("跟踪文件基线不足 2000 个，快照不对")
for p in changed2:
    if p not in MOD_ALLOWED:
        bad.append(f"白名单外的跟踪文件变了：{p}")
# 交叉核对：哈希变化的集合应与 git 报告的修改集合一致
if set(changed) | set(changed2) != set(mods):
    bad.append(f"哈希变化集合与 git 修改集合不一致：{sorted((set(changed) | set(changed2)) ^ set(mods))}")

# 4. 授权改动的精确形状
diff = git("diff", "-U0", "--", AUTH_TEST)
minus = [l[1:] for l in diff.splitlines() if l.startswith("-") and not l.startswith("---")]
plus = [l[1:] for l in diff.splitlines() if l.startswith("+") and not l.startswith("+++")]
print(f"[4] 授权测试的改动：删 {len(minus)} 行、加 {len(plus)} 行")
want_minus = ['    assert fold.count("<p>") == 7', '    assert fold.count("</p>") == 7']
want_plus = ['    assert fold.count("<p>") == 8', '    assert fold.count("</p>") == 8']
if [m.rstrip() for m in minus] != want_minus or [p.rstrip() for p in plus] != want_plus:
    bad.append(f"授权测试的改动不是那两处数字：-{minus} +{plus}")

# 5. CLAUDE.md
size = (root / "CLAUDE.md").stat().st_size
text = (root / "CLAUDE.md").read_bytes()
marker = "## 讨论群聊天互通（第三期）".encode()
idx = text.find(marker)
sec = len(text) - idx if idx >= 0 else -1
print(f"[5] CLAUDE.md {size} 字节（上限 69300）；新一节 {sec} 字节（上限 260）；标题出现 {text.count(marker)} 次")
if size > 69300:
    bad.append("CLAUDE.md 超过 69300 字节")
if idx < 0 or sec > 260 or text.count(marker) != 1:
    bad.append("CLAUDE.md 新一节缺失、重复或超过 260 字节")
base_claude = subprocess.run(["git", "-C", str(root), "show", "HEAD:CLAUDE.md"], check=True, capture_output=True).stdout
if not text.startswith(base_claude.rstrip(b"\n")):
    bad.append("CLAUDE.md 原有内容被改动（应只在末尾追加）")

# 6. 绝对路径与账号名
_user = re.escape(getpass.getuser())  # 运行时取本机账号名，脚本里不写死任何账号
pat = re.compile(r"/Users/[A-Za-z0-9._-]|/private/tmp/|/home/[a-z]|" + _user)  # 只认真实路径与本机账号名
scanned = 0
for p in mods + news:
    f = root / p
    if not f.is_file():
        continue
    scanned += 1
    try:
        body = f.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        bad.append(f"读不了 {p}: {exc}")
        continue
    if p in mods:
        # 只看新增行
        added = [l[1:] for l in git("diff", "-U0", "--", p).splitlines() if l.startswith("+") and not l.startswith("+++")]
        body = "\n".join(added)
    for m in pat.finditer(body):
        line = body[: m.start()].count("\n") + 1
        bad.append(f"疑似本机路径或账号名：{p} 新增内容第 {line} 行附近：{body[max(0, m.start()-30): m.end()+30]!r}")
print(f"[6] 绝对路径扫描：{scanned} 个文件")
if scanned == 0:
    bad.append("绝对路径扫描没扫到文件")

print()
if bad:
    print(f"门禁不通过，{len(bad)} 条：")
    for b in bad:
        print("  -", b)
    sys.exit(1)
print("范围门禁通过")
