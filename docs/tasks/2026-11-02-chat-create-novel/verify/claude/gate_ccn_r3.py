"""R3 门禁：聊天建书前端契约测试的 node_modules 守卫。

用法：python gate_ccn_r3.py <worktree> <no-node_modules 副本>
副本由 rsync 排除 node_modules/.venv/.git 得到；脚本会把 worktree 里修好的
测试文件拷进副本再跑，并在副本里做两处变异（不碰 worktree）。
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

WT = Path(sys.argv[1]).resolve()
NOMOD = Path(sys.argv[2]).resolve()
PY = WT / "backend/.venv/bin/python"
REL = "backend/tests/test_novel_chat_create_frontend.py"
NODE_TESTS = [
    "test_novel_draft_component_renders_loading_state",
    "test_use_conversations_rebuilds_song_and_draft_cards",
    "test_page_open_novel_at_accepts_only_two_shapes",
]
ORIGINAL_TESTS = NODE_TESTS + [
    "test_chat_card_renders_novel_draft_with_draft_id",
    "test_chat_bubble_passes_open_novel_to_every_chat_card",
    "test_novel_draft_component_states_paths_and_weights",
    "test_page_stream_cards_copy_draft_id_and_iframe_uses_state",
    "test_wizard_reads_draft_prefills_and_submits_draft_id",
    "test_novels_lib_exposes_draft_lookup_and_input_field",
]
results = []


def check(name, ok, detail=""):
    results.append((name, ok))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""))


def sh(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def pytest_in(root, extra=()):
    env = {k: v for k, v in __import__("os").environ.items() if k.lower() not in {"http_proxy", "https_proxy", "all_proxy", "no_proxy"}}
    proc = subprocess.run([str(PY), "-m", "pytest", "tests/test_novel_chat_create_frontend.py", "-q", "-p", "no:cacheprovider", "-rsf", *extra],
                          cwd=root / "backend", capture_output=True, text=True, env=env)
    out = proc.stdout + proc.stderr
    summary = re.findall(r"(\d+) (passed|failed|skipped|error)", out)
    counts = {kind: int(num) for num, kind in summary}
    failed_names = re.findall(r"^FAILED [^:]+::(\w+)", out, re.M)
    return counts, failed_names, out


def chunks(source):
    """按模块顶层 def / 装饰器切块，键为函数名。"""
    out, current = {}, []
    for line in source.splitlines(keepends=True):
        if (line.startswith("def ") or line.startswith("@")) and current and not current[-1].startswith("@"):
            text = "".join(current)
            m = re.search(r"^def (\w+)\(", text, re.M)
            if m:
                out[m.group(1)] = text
            current = []
        current.append(line)
    text = "".join(current)
    m = re.search(r"^def (\w+)\(", text, re.M)
    if m:
        out[m.group(1)] = text
    return out


# 1. 改动集合
status = sh(["git", "-c", "core.quotepath=off", "status", "--porcelain"], WT).stdout.splitlines()
changed = sorted(l[3:] for l in status)
allowed = {REL, "docs/tasks/2026-11-02-chat-create-novel/05-fix-r3.md", "docs/tasks/2026-11-02-chat-create-novel/impl/主代理.md"}
check("改动集合只含测试文件 + 返修单 + 报告", set(changed) <= allowed and REL in changed, ", ".join(changed))

head = sh(["git", "show", f"HEAD:{REL}"], WT).stdout
new = (WT / REL).read_text(encoding="utf-8")
check("测试文件确有改动", head != new)

# 2. 守卫 helper：模块级、调用 pytest.skip 的约定文案
helper = None
for name, body in chunks(new).items():
    if not name.startswith("test_") and 'pytest.skip("frontend dependencies unavailable: "' in body:
        helper = name
check("存在模块级守卫 helper（约定文案）", helper is not None, helper or "-")
check("守卫含 node 缺失分支", helper is not None and 'pytest.skip("node is unavailable")' in chunks(new)[helper])
deps = re.search(r"^DEPENDENCIES\s*=\s*(\{.*?\})\s*$", new, re.M | re.S)
check("DEPENDENCIES 含 typescript/react/react-dom/server 入口文件", bool(deps) and all(k in deps.group(1) for k in ("typescript/lib/typescript.js", "react/index.js", "react-dom/server.js")))

# 3. 三条 node 用例：守卫调用在首个 subprocess.run 之前
new_chunks, head_chunks = chunks(new), chunks(head)
for t in NODE_TESTS:
    body = new_chunks.get(t, "")
    call = body.find(f"{helper}()") if helper else -1
    first_node = body.find("subprocess.run(")
    check(f"{t}: 守卫在首个 node 调用之前", helper is not None and 0 <= call < first_node, f"call@{call} node@{first_node}")

# 4. 既有 9 条用例除插入守卫行外逐字节不变
for t in ORIGINAL_TESTS:
    before = head_chunks.get(t)
    after = new_chunks.get(t, "")
    stripped = re.sub(rf"^\s*{re.escape(helper or '§')}\(\)\s*\n", "", after, flags=re.M)
    check(f"{t}: 原断言与坏副本逻辑未动", before is not None and stripped == before)

# 5. 自检用例存在并 parametrize 遍历 DEPENDENCIES
selfcheck = [n for n in new_chunks if n.startswith("test_") and n not in ORIGINAL_TESTS]
check("新增自检用例恰 1 个", len(selfcheck) == 1, ", ".join(selfcheck))
if selfcheck:
    sc = new_chunks[selfcheck[0]]
    check("自检 parametrize DEPENDENCIES、monkeypatch subprocess.run、断言 skip", all(s in sc for s in ('@pytest.mark.parametrize("missing", DEPENDENCIES)', "subprocess", "pytest.skip.Exception", f"{helper}()")))

# 6. 有 node_modules：全绿 0 跳过
counts, failed, out = pytest_in(WT)
check("worktree 有 node_modules：12 passed / 0 failed / 0 skipped", counts.get("passed") == 12 and not counts.get("failed") and not counts.get("skipped"), str(counts))

# 7. 无 node_modules 副本：0 failed，三条 node 用例 + 共享渲染用例 skip
assert not (NOMOD / "frontend/node_modules").exists(), "副本里居然有 node_modules"
target = NOMOD / REL
shutil.copyfile(WT / REL, target)
counts, failed, out = pytest_in(NOMOD)
skipped_names = re.findall(r"^SKIPPED \[\d+\] [^:]+:\d+: (.*)$", out, re.M)
check("副本无 node_modules：0 failed / 8 passed / 4 skipped", not counts.get("failed") and counts.get("passed") == 8 and counts.get("skipped") == 4, str(counts))
skip_rows = re.findall(r"^SKIPPED \[(\d+)\] [^:]+:\d+: (.*)$", out, re.M)
convention = sum(int(n) for n, text in skip_rows if text.startswith("frontend dependencies unavailable: typescript, react, react-dom/server"))
check("副本 skip 文案是约定文案（恰 3 条）", convention == 3, " | ".join(f"[{n}] {t}" for n, t in skip_rows)[:240])

# 8. 变异 M1：去掉一条 node 用例的守卫 → 该用例在副本里必须红
fixed = target.read_text(encoding="utf-8")
body = new_chunks[NODE_TESTS[1]]
mutated_body = re.sub(rf"^\s*{re.escape(helper or '§')}\(\)\s*\n", "", body, count=1, flags=re.M)
assert mutated_body != body
target.write_text(fixed.replace(body, mutated_body, 1), encoding="utf-8")
counts, failed, out = pytest_in(NOMOD)
check("M1 去守卫：恰该用例 failed", failed == [NODE_TESTS[1]] and counts.get("failed") == 1, f"failed={failed} counts={counts}")

# 9. 变异 M2：守卫不再 skip → 三条 node 用例 + 三条自检都红
m2 = fixed.replace('pytest.skip("frontend dependencies unavailable: " + ", ".join(missing))', "pass", 1)
assert m2 != fixed
target.write_text(m2, encoding="utf-8")
counts, failed, out = pytest_in(NOMOD)
check("M2 守卫失效：node 用例与自检全红（≥6 failed）", counts.get("failed", 0) >= 6 and set(NODE_TESTS) <= set(failed), f"failed={sorted(set(failed))} counts={counts}")
target.write_text(fixed, encoding="utf-8")

# 10. 相关子集在 worktree 全绿
env = {k: v for k, v in __import__("os").environ.items() if k.lower() not in {"http_proxy", "https_proxy", "all_proxy", "no_proxy"}}
proc = subprocess.run([str(PY), "-m", "pytest", "-q", "-p", "no:cacheprovider",
                       "tests/test_novel_chat_create_frontend.py", "tests/test_novel_chat_create.py", "tests/test_novel_chat_frontend.py",
                       "tests/test_claude_agent_frontend.py", "tests/test_studio_frontend_dependencies.py", "tests/test_novel_p2_frontend.py"],
                      cwd=WT / "backend", capture_output=True, text=True, env=env)
tail = (proc.stdout + proc.stderr).strip().splitlines()[-1]
check("相关子集全绿 0 skipped", proc.returncode == 0 and "failed" not in tail and "skipped" not in tail, tail)

bad = [n for n, ok in results if not ok]
print(f"\n== {len(results) - len(bad)}/{len(results)} 通过 ==")
sys.exit(1 if bad else 0)
