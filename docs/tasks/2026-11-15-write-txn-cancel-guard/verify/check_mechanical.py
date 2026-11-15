# -*- coding: utf-8 -*-
"""门禁：核对「替换打开连接的调用」是不是纯机械替换。

用法（在仓库根目录运行）：
    python docs/tasks/2026-11-15-write-txn-cancel-guard/verify/check_mechanical.py <基线提交>

对基线提交以来 backend/ 下每个被修改的非测试 .py 文件（新增文件不算）：
把新内容里的 `from utils import db_txn` 整行去掉、把 `db_txn.connect(` 换回 `aiosqlite.connect(`，
结果必须与基线内容逐字节相同。唯一例外是 backend/novel/billing.py 里 `_drain` 的函数体。
新加的导入必须紧跟第一处 `import aiosqlite`、缩进相同。
同时核对：非测试代码里除 backend/utils/db_txn.py 外不再有 `aiosqlite.connect(`；
`db_txn.connect(` 的总数等于基线里 `aiosqlite.connect(` 的总数。

退出码 0 = 全部符合；1 = 有不符合项（逐条列出）。
"""
import subprocess
import sys

IMPORT_LINE = "from utils import db_txn"
DRAIN_FILE = "backend/novel/billing.py"
DRAIN_START = "    async def _drain(operation):"
DRAIN_END = "    async def reserve(self, call):"


def git(*args):
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout


def is_test(path):
    return "/tests/" in path or path.startswith("backend/tests/")


def strip_drain(text):
    start, end = text.find(DRAIN_START), text.find(DRAIN_END)
    if start < 0 or end < 0 or end < start:
        return None
    return text[:start] + text[end:]


def normalize(text):
    lines = [line for line in text.split("\n") if line.strip() != IMPORT_LINE]
    return "\n".join(lines).replace("db_txn.connect(", "aiosqlite.connect(")


def main():
    base = sys.argv[1]
    problems = []
    changed = [line[3:] for line in git("status", "--porcelain").splitlines()
               if line[:2].strip() == "M"]
    changed += git("diff", "--name-only", "--diff-filter=M", base, "HEAD").split()
    changed = sorted({path for path in changed
                      if path.startswith("backend/") and path.endswith(".py") and not is_test(path)})
    if not changed:
        problems.append("没有找到任何被修改的后端文件：门禁没有扫到东西")
    replaced = 0
    for path in changed:
        try:
            old = git("show", f"{base}:{path}")
        except subprocess.CalledProcessError:
            problems.append(f"{path}: 基线里不存在，却被当成修改文件")
            continue
        with open(path, encoding="utf-8") as handle:
            new = handle.read()
        replaced += new.count("db_txn.connect(")
        if new.count(IMPORT_LINE) != 1:
            problems.append(f"{path}: `{IMPORT_LINE}` 应恰好出现一次，实际 {new.count(IMPORT_LINE)} 次")
        else:
            # 新导入必须紧跟第一处 import aiosqlite，缩进相同。
            lines = new.split("\n")
            first = next((i for i, line in enumerate(lines) if line.strip() == "import aiosqlite"), None)
            indent = "" if first is None else lines[first][: len(lines[first]) - len(lines[first].lstrip())]
            if first is None or first + 1 >= len(lines) or lines[first + 1] != indent + IMPORT_LINE:
                problems.append(f"{path}: `{IMPORT_LINE}` 没有紧跟在第一处 import aiosqlite 的下一行（缩进相同）")
        if "import aiosqlite" in old and "import aiosqlite" not in new:
            problems.append(f"{path}: 原有的 import aiosqlite 被删掉了")
        if path == DRAIN_FILE:
            old, new = strip_drain(old), strip_drain(new)
            if old is None or new is None:
                problems.append(f"{path}: 找不到 _drain 的边界")
                continue
        if normalize(new) != old:
            problems.append(f"{path}: 除了替换调用和补一行导入之外还有别的改动")
    tracked = [path for path in git("ls-files", "backend").split()
               if path.endswith(".py") and not is_test(path) and path != "backend/utils/db_txn.py"]
    base_total = 0
    for path in tracked:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        if "aiosqlite.connect(" in text:
            problems.append(f"{path}: 仍有 aiosqlite.connect(")
        try:
            base_total += git("show", f"{base}:{path}").count("aiosqlite.connect(")
        except subprocess.CalledProcessError:
            pass
    if replaced != base_total:
        problems.append(f"db_txn.connect( 共 {replaced} 处，基线里 aiosqlite.connect( 共 {base_total} 处，两者应相等")
    print(f"CHECK_MECHANICAL files={len(changed)} replaced={replaced} base_sites={base_total} problems={len(problems)}")
    for problem in problems:
        print("  - " + problem)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
