# -*- coding: utf-8 -*-
"""清点后端里每一个 aiosqlite 事务的语句序列（静态扫描，只读）。

用法：python txn_inventory.py <backend 目录> [--json out.json]

对每个函数，按源码顺序列出它在连接上做的事，并把「把连接传给别的函数」的调用就地展开：

  B   BEGIN IMMEDIATE / EXCLUSIVE        b   BEGIN（延迟）
  S   取行语句，写成 cur = await db.execute(...)（游标要另外取、另外关）
  Sw  取行语句，写成 async with db.execute(...) as cur
  Sa  execute_fetchall / execute_insert（在工作线程里取完，不留游标）
  D   写语句（INSERT/UPDATE/DELETE/REPLACE/DDL）
  R   带 RETURNING 的写语句（既拿写锁又留游标）
  X   语句文本运行时才确定，无法静态判断
  C   commit        K   rollback
  A   事务期间等待了别的东西（网络、文件、睡眠等）
  H?  把连接传给了一个解析不到的函数

每个事件后的记号：! = 处在「出任何异常(BaseException/裸 except/finally)都回滚」的范围里；
~ = 只在 except Exception 的回滚范围里（接不住取消）；无记号 = 没有回滚保护。

风险判定（见 mechanism_probe.py 的实测）：写事务已开始（B，或出现过 D/R/X）之后、提交之前，
出现没有 ! 保护的 S / Sw / R，就标 W1；其中写成 S 且只 fetchone 的另标 W2?（需人工看是否可能多行）。
"""
import ast
import json
import os
import sys

DB_METHODS = {"execute", "executemany", "executescript", "execute_fetchall",
              "execute_insert", "commit", "rollback"}
ROW_KEYWORDS = ("SELECT", "WITH", "PRAGMA", "VALUES", "EXPLAIN")
WRITE_KEYWORDS = ("INSERT", "UPDATE", "DELETE", "REPLACE", "CREATE", "DROP", "ALTER")


def leading_text(node, consts):
    """Best-effort static text of an SQL expression (None when unknown)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        parts = []
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                parts.append(value.value)
            else:
                parts.append(" ? ")
        return "".join(parts)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = leading_text(node.left, consts)
        right = leading_text(node.right, consts)
        if left is None:
            return None
        return left + (right or " ? ")
    if isinstance(node, ast.Name) and node.id in consts:
        return consts[node.id]
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in ("format", "join"):
        return leading_text(node.func.value, consts)
    return None


def sql_kind(text):
    if text is None:
        return "X"
    stripped = text.strip().upper()
    if not stripped or stripped.startswith("?"):
        return "X"
    if stripped.startswith("BEGIN"):
        return "B" if ("IMMEDIATE" in stripped or "EXCLUSIVE" in stripped) else "b"
    if stripped.startswith("COMMIT") or stripped.startswith("END"):
        return "C"
    if stripped.startswith("ROLLBACK"):
        return "K"
    if stripped.startswith("SAVEPOINT") or stripped.startswith("RELEASE"):
        return "D"
    if stripped.startswith(WRITE_KEYWORDS):
        return "R" if "RETURNING" in stripped else "D"
    if stripped.startswith(ROW_KEYWORDS):
        if stripped.startswith("PRAGMA") and "=" in stripped:
            return "D0"  # 设置型 PRAGMA，不取行、不开事务
        return "S"
    return "X"


class FunctionInfo:
    def __init__(self, module, qualname, node, path):
        self.module, self.qualname, self.node, self.path = module, qualname, node, path
        self.events = []        # (line, code, guard, detail)
        self.conn_vars = set()
        self.owner_vars = set()  # 在本函数里打开的连接
        self.params = [a.arg for a in node.args.args + node.args.kwonlyargs + node.args.posonlyargs]
        self.fetchone_only = False


def collect_functions(tree, module, path):
    functions = []

    def visit(node, prefix):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.AsyncFunctionDef, ast.FunctionDef)):
                qual = f"{prefix}{child.name}"
                functions.append(FunctionInfo(module, qual, child, path))
                visit(child, qual + ".")
            elif isinstance(child, ast.ClassDef):
                visit(child, f"{prefix}{child.name}.")
            else:
                visit(child, prefix)

    visit(tree, "")
    return functions


def own_nodes(func_node):
    """Yield nodes of this function, not descending into nested defs/lambdas/classes."""
    stack = list(ast.iter_child_nodes(func_node))
    while stack:
        node = stack.pop()
        yield node
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef, ast.Lambda, ast.ClassDef)):
            continue
        stack.extend(ast.iter_child_nodes(node))


def call_name(call):
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return "?"


def dotted(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{dotted(node.value)}.{node.attr}"
    if isinstance(node, ast.Call):
        return dotted(node.func) + "()"
    return "?"


def analyse(info, consts):
    node = info.node
    nodes = list(own_nodes(node))
    # 1) 连接变量：出现过 v.execute / v.commit ... 的名字
    for n in nodes:
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in DB_METHODS:
            if isinstance(n.func.value, ast.Name):
                info.conn_vars.add(n.func.value.id)
    # 把「async with xxx() as v」里 v 被传给别的函数的也算上（只转手不直接用）
    with_targets = {}
    for n in nodes:
        if isinstance(n, ast.AsyncWith):
            for item in n.items:
                if isinstance(item.optional_vars, ast.Name):
                    with_targets[item.optional_vars.id] = item.context_expr
    for name, expr in with_targets.items():
        text = dotted(expr)
        if any(key in text for key in ("connect", "get_db", "_db(", "database")) and "execute" not in text:
            info.conn_vars.add(name)
            info.owner_vars.add(name)
    for n in nodes:
        if isinstance(n, ast.Assign) and isinstance(n.value, ast.Await):
            text = dotted(n.value.value)
            if "connect" in text:
                for target in n.targets:
                    if isinstance(target, ast.Name):
                        info.conn_vars.add(target.id)
                        info.owner_vars.add(target.id)
    for name in info.params:
        if name in ("db", "conn", "connection"):
            info.conn_vars.add(name)
    # 事务封装：connection(transaction=True) 自带 BEGIN 与「任何异常都回滚」；
    # xxx.transaction() 是书斋步骤存储的封装：BEGIN、核对令牌（在回滚范围之外）、主体在回滚范围内。
    guarded_bodies, synthetic = [], []
    for n in nodes:
        if not isinstance(n, ast.AsyncWith):
            continue
        for item in n.items:
            call = item.context_expr
            if not isinstance(call, ast.Call) or not isinstance(item.optional_vars, ast.Name):
                continue
            name = item.optional_vars.id
            txn_true = any(k.arg == "transaction" and isinstance(k.value, ast.Constant) and k.value.value is True
                           for k in call.keywords)
            store_txn = isinstance(call.func, ast.Attribute) and call.func.attr == "transaction" and not call.args
            if txn_true:
                info.conn_vars.add(name); info.owner_vars.add(name)
                guarded_bodies.append(n)
                synthetic.append((n.lineno, -2, "B", "!", "connection(transaction=True)"))
                synthetic.append((n.end_lineno, 10**6, "C", "!", "封装自动提交"))
            elif store_txn:
                info.conn_vars.add(name); info.owner_vars.add(name)
                guarded_bodies.append(n)
                synthetic.append((n.lineno, -2, "B", "", "store.transaction()"))
                synthetic.append((n.lineno, -1, "Sw", "", "令牌核对 is_current（在回滚范围之外）"))
                synthetic.append((n.end_lineno, 10**6, "C", "!", "封装自动提交"))
    if not info.conn_vars:
        return
    # 2) try 结构：每个节点处在哪些回滚保护里
    parents = {}
    for n in [node] + nodes:
        for child in ast.iter_child_nodes(n):
            parents[child] = n

    def has_rollback(body):
        for stmt in body:
            for sub in ast.walk(stmt):
                if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute):
                    if sub.func.attr == "rollback":
                        return True
                    if sub.func.attr == "execute" and sub.args:
                        text = leading_text(sub.args[0], consts)
                        if text and text.strip().upper().startswith("ROLLBACK"):
                            return True
        return False

    def guard_of(n):
        best = ""
        cur = n
        while cur in parents:
            parent = parents[cur]
            if parent in guarded_bodies and cur in parent.body:
                return "!"
            if isinstance(parent, ast.Try) and cur in parent.body:
                if has_rollback(parent.finalbody):
                    return "!"
                for handler in parent.handlers:
                    if not has_rollback(handler.body):
                        continue
                    names = []
                    if handler.type is None:
                        return "!"
                    types = handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]
                    names = [dotted(t) for t in types]
                    if any(name.endswith("BaseException") or name.endswith("CancelledError") for name in names):
                        return "!"
                    best = "~"
            cur = parent
        return best

    # 3) 事件
    with_ctx = set()
    for n in nodes:
        if isinstance(n, ast.AsyncWith):
            for item in n.items:
                with_ctx.add(id(item.context_expr))
    awaited = set()
    for n in nodes:
        if isinstance(n, ast.Await):
            awaited.add(id(n.value))
    fetch_calls = {"fetchone": 0, "fetchall": 0, "fetchmany": 0}
    events = []
    for n in nodes:
        if not isinstance(n, ast.Call):
            continue
        line = n.lineno
        func = n.func
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) \
                and func.value.id in info.conn_vars and func.attr in DB_METHODS:
            attr = func.attr
            if attr == "commit":
                code, detail = "C", ""
            elif attr == "rollback":
                code, detail = "K", ""
            elif attr in ("execute_fetchall", "execute_insert"):
                text = leading_text(n.args[0], consts) if n.args else None
                kind = sql_kind(text)
                code = "Sa" if kind in ("S", "X") else ("D" if attr == "execute_insert" else "Sa")
                if attr == "execute_insert":
                    code = "D"
                detail = (text or "")[:60]
            elif attr in ("executemany", "executescript"):
                text = leading_text(n.args[0], consts) if n.args else None
                code, detail = "D", (text or "")[:60]
            else:
                text = leading_text(n.args[0], consts) if n.args else None
                code = sql_kind(text)
                detail = " ".join((text or "<dynamic>").split())[:70]
                if code == "S" and id(n) in with_ctx:
                    code = "Sw"
                if code == "R" and id(n) in with_ctx:
                    code = "Rw"
            events.append((line, n.col_offset, code, guard_of(n), detail))
            continue
        if isinstance(func, ast.Attribute) and func.attr in fetch_calls:
            fetch_calls[func.attr] += 1
            continue
        # 把连接传给别的函数
        passed = [a for a in list(n.args) + [k.value for k in n.keywords]
                  if isinstance(a, ast.Name) and a.id in info.conn_vars]
        if passed:
            kind = ""
            for a in n.args:
                text = leading_text(a, consts)
                if text is not None:
                    kind = sql_kind(text)
                    break
            events.append((line, n.col_offset, "H", guard_of(n), f"{dotted(func)}|{kind}"))
            continue
        if id(n) in awaited:
            name = dotted(func)
            if name.endswith((".fetchone", ".fetchall", ".fetchmany", ".close")):
                continue
            if "connect" in name and "aiosqlite" in name:
                continue
            events.append((line, n.col_offset, "A", "", name))
    events.extend(synthetic)
    events.sort()
    info.events = [(line, code, guard, detail) for line, _, code, guard, detail in events]
    info.fetch_calls = fetch_calls


def flatten(info, table, depth=0, seen=()):
    """Inline helper calls that receive the connection."""
    out = []
    for line, code, guard, detail in info.events:
        if code != "H":
            out.append((line, code, guard, detail, depth))
            continue
        detail, _, call_kind = detail.partition("|")
        name = detail.split(".")[-1]
        candidates = [f for f in table.get(name, []) if f.conn_vars and f is not info]
        if not candidates or depth >= 5 or name in seen:
            out.append((line, "H?", guard, detail, depth))
            continue
        # 同名多个定义时优先同模块
        same = [f for f in candidates if f.module == info.module]
        chosen = same[0] if same else candidates[0]
        inner = flatten(chosen, table, depth + 1, seen + (name,))
        db_events = [e for e in inner if e[1] != "A"]
        if len(db_events) == 1 and db_events[0][1] == "X" and call_kind:
            code = {"S": "Sw", "R": "Rw"}.get(call_kind, call_kind)
            out.append((line, code, guard, f"经 {name}()", depth))
            for iline, icode, iguard, idetail, idepth in inner:
                if icode == "A":
                    out.append((iline, icode, "", idetail, idepth))
            continue
        out.append((line, "(", guard, f"{chosen.module}:{chosen.qualname}", depth))
        for iline, icode, iguard, idetail, idepth in inner:
            if icode == "A":
                out.append((iline, icode, "", idetail, idepth))
            else:
                out.append((iline, icode, guard or iguard if guard == "!" else (iguard or guard), idetail, idepth))
        out.append((line, ")", guard, "", depth))
    return out


def assess(flat, owner):
    """Return (is_write, risks) for a flattened event list."""
    in_write = not owner   # 接收连接的辅助函数：按最坏情况假设调用方已在写事务里
    is_write = False
    risks = []
    awaits_in_write = []
    for line, code, guard, detail, depth in flat:
        if code in ("B",):
            in_write, is_write = True, True
        elif code in ("D", "X", "R", "Rw"):
            if code in ("R", "Rw") and guard != "!":
                risks.append(("W1", line, code, detail))
            if code == "X" and in_write and guard != "!":
                risks.append(("W1?", line, code, detail))
            in_write, is_write = True, True
        elif code in ("S", "Sw"):
            if in_write and guard != "!":
                risks.append(("W1", line, code, detail))
        elif code in ("C", "K"):
            if code == "C":
                is_write = True
            in_write = False if owner else in_write
        elif code == "A":
            if in_write:
                awaits_in_write.append((line, detail))
        elif code == "H?":
            if in_write and guard != "!":
                risks.append(("H?", line, code, detail))
    return is_write, risks, awaits_in_write


def main():
    root = os.path.abspath(sys.argv[1])
    out_json = sys.argv[sys.argv.index("--json") + 1] if "--json" in sys.argv else None
    skip_dirs = {".venv", "tests", "__pycache__", "uploads", "node_modules", ".pytest_cache"}
    all_functions = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in skip_dirs)
        for filename in sorted(filenames):
            if not filename.endswith(".py"):
                continue
            path = os.path.join(dirpath, filename)
            rel = os.path.relpath(path, root)
            with open(path, encoding="utf-8") as handle:
                source = handle.read()
            try:
                tree = ast.parse(source)
            except SyntaxError as error:
                print(f"!! 解析失败 {rel}: {error}")
                continue
            consts = {}
            for stmt in tree.body:
                if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
                    text = leading_text(stmt.value, consts)
                    if text is not None:
                        consts[stmt.targets[0].id] = text
            for info in collect_functions(tree, rel, path):
                analyse(info, consts)
                if info.events:
                    all_functions.append(info)
    table = {}
    for info in all_functions:
        table.setdefault(info.qualname.split(".")[-1], []).append(info)

    rows = []
    for info in all_functions:
        owner = bool(info.owner_vars)
        flat = flatten(info, table)
        is_write, risks, awaits = assess(flat, owner)
        seq = " ".join(
            (code + guard) if code not in ("(", ")") else code for _, code, guard, _, _ in flat)
        rows.append({
            "module": info.module, "function": info.qualname, "line": info.node.lineno,
            "owner": owner, "is_async": isinstance(info.node, ast.AsyncFunctionDef),
            "write": is_write, "seq": seq,
            "risks": [list(r) for r in risks], "awaits_in_write": awaits,
            "fetch": info.fetch_calls,
            "events": [list(e) for e in flat],
        })
    if out_json:
        with open(out_json, "w", encoding="utf-8") as handle:
            json.dump(rows, handle, ensure_ascii=False, indent=1)

    owners = [r for r in rows if r["owner"]]
    helpers = [r for r in rows if not r["owner"]]
    write_owners = [r for r in owners if r["write"]]
    risky = [r for r in write_owners if r["risks"]]
    print(f"扫描目录: {os.path.basename(root)}  有连接操作的函数 {len(rows)} 个；"
          f"自己开连接的 {len(owners)} 个，其中写事务 {len(write_owners)} 个，"
          f"其中有风险标记的 {len(risky)} 个；接收连接的辅助函数 {len(helpers)} 个")
    by_module = {}
    for r in write_owners:
        by_module.setdefault(r["module"], []).append(r)
    for module in sorted(by_module):
        items = by_module[module]
        flagged = [r for r in items if r["risks"]]
        print(f"\n=== {module}: 写事务 {len(items)}，有风险标记 {len(flagged)}")
        for r in items:
            tags = sorted({risk[0] for risk in r["risks"]})
            mark = ",".join(tags) if tags else "ok"
            extra = f"  等待外部:{[a[1] for a in r['awaits_in_write']][:3]}" if r["awaits_in_write"] else ""
            print(f"  [{mark:<8s}] {r['function']}:{r['line']}  {r['seq']}{extra}")
    print("\n=== 接收连接的辅助函数里含取行语句的（被写事务调用时要看调用方有没有保护）")
    for r in helpers:
        codes = {e[1] for e in r["events"]}
        if codes & {"S", "Sw", "R", "Rw", "X"}:
            print(f"  {r['module']}:{r['function']}:{r['line']}  {r['seq']}")


if __name__ == "__main__":
    main()
