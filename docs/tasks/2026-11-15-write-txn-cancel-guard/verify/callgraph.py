# -*- coding: utf-8 -*-
"""从「会被取消的入口」出发，沿调用关系找出它们能走到哪些写事务（静态近似，只读）。

用法：python callgraph.py <backend 目录> <txn_inventory.py 产出的 json> [--paths]

解析规则：模块别名调用（database.save_message）、同模块函数、self/cls 方法、导入的类的方法、
作为参数传递的函数引用都算调用边；对象方法（x.method()）只在方法名全库定义不超过 2 处且不是
常见名字时才连边。结果是「可能走到」，逐条的确认见调查文档。
"""
import ast
import json
import os
import sys
from collections import deque

STOP = {"get", "set", "close", "run", "start", "stop", "call", "execute", "commit", "rollback",
        "read", "write", "update", "delete", "create", "add", "append", "pop", "items", "keys",
        "values", "join", "format", "strip", "split", "encode", "decode", "send", "receive", "json",
        "dict", "copy", "cancel", "done", "result", "wait", "put", "submit", "state", "status",
        "save", "load", "list", "main", "connect", "connection", "transaction", "quote", "refresh",
        "retry", "recover", "patch", "note", "export", "detail", "approve", "transition", "group",
        "fetchone", "fetchall", "initialize", "render", "validate", "build", "parse", "open"}

# 会被取消的入口：名字 -> [(模块文件, 函数限定名)]
ROOTS = {
    "聊天流式回复·客户端断开(anyio 取消)": [
        ("services/chat_service.py", "run_chat"),
    ],
    "书斋写作任务·暂停/删除/改稿/关停(task.cancel)": [
        ("novel/runner.py", "_run"),
    ],
    "讨论群任务·暂停/删除/关停(task.cancel)": [
        ("discuss/runner.py", "_run"),
    ],
    "分身交流任务·停止/关停(task.cancel)": [
        ("services/exchange_service.py", "run_exchange"),
    ],
    "工作室调度的作业·关停(task.cancel)": [
        ("studio/scheduler.py", "Scheduler._guard"),
        ("studio/scheduler.py", "Scheduler._poll"),
        ("studio/scheduler.py", "Scheduler._download"),
        ("studio/scheduler.py", "Scheduler._submit"),
        ("studio/scheduler.py", "run_scheduler"),
        ("studio/scheduler.py", "Scheduler.tick"),
    ],
    "写歌轮询器·关停(task.cancel)": [
        ("song/jobs.py", "run_poller"),
    ],
    "上传清理·关停(task.cancel)": [
        ("main.py", "_run_upload_cleanup_periodically"),
    ],
}


def module_name(rel):
    name = rel[:-3].replace(os.sep, ".")
    return name[:-9] if name.endswith(".__init__") else name


def load(root):
    modules = {}
    skip = {".venv", "tests", "__pycache__", "uploads", "node_modules", ".pytest_cache"}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in skip)
        for filename in sorted(filenames):
            if filename.endswith(".py"):
                path = os.path.join(dirpath, filename)
                rel = os.path.relpath(path, root)
                try:
                    with open(path, encoding="utf-8") as handle:
                        modules[rel] = ast.parse(handle.read())
                except SyntaxError:
                    pass
    return modules


def collect(tree):
    """Return {qualname: node} for every function, {class: [method names]}."""
    functions, classes = {}, {}

    def visit(node, prefix, cls):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.AsyncFunctionDef, ast.FunctionDef)):
                functions[prefix + child.name] = (child, cls)
                visit(child, prefix + child.name + ".", cls)
            elif isinstance(child, ast.ClassDef):
                classes[child.name] = []
                visit(child, prefix + child.name + ".", child.name)
            else:
                visit(child, prefix, cls)

    visit(tree, "", None)
    for qual, (node, cls) in functions.items():
        if cls and qual.startswith(cls + ".") and qual.count(".") == 1:
            classes[cls].append(node.name)
    return functions, classes


def own_nodes(func_node):
    stack = list(ast.iter_child_nodes(func_node))
    while stack:
        node = stack.pop()
        yield node
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef, ast.ClassDef)):
            continue
        stack.extend(ast.iter_child_nodes(node))


def main():
    root = os.path.abspath(sys.argv[1])
    inventory = json.load(open(sys.argv[2], encoding="utf-8"))
    show_paths = "--paths" in sys.argv
    trees = load(root)
    by_modname = {module_name(rel): rel for rel in trees}
    defs = {rel: collect(tree) for rel, tree in trees.items()}

    # 方法名 -> [(rel, qualname)]
    method_index = {}
    for rel, (functions, classes) in defs.items():
        for qual in functions:
            method_index.setdefault(qual.split(".")[-1], []).append((rel, qual))

    def imports_of(rel, tree):
        package = module_name(rel).rsplit(".", 1)[0] if "." in module_name(rel) else ""
        if rel.endswith("__init__.py"):
            package = module_name(rel)
        table = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    target = alias.name
                    if target in by_modname:
                        table[alias.asname or target.split(".")[0]] = ("mod", by_modname[target])
            elif isinstance(node, ast.ImportFrom):
                base = node.module or ""
                if node.level:
                    parts = package.split(".") if package else []
                    parts = parts[: len(parts) - (node.level - 1)] if node.level > 1 else parts
                    base = ".".join([p for p in parts if p] + ([node.module] if node.module else []))
                for alias in node.names:
                    name = alias.asname or alias.name
                    full = f"{base}.{alias.name}" if base else alias.name
                    if full in by_modname:
                        table[name] = ("mod", by_modname[full])
                    elif base in by_modname:
                        table[name] = ("obj", by_modname[base], alias.name)
        return table

    imports = {rel: imports_of(rel, tree) for rel, tree in trees.items()}
    edges = {}

    def resolve(rel, qual, cls, expr):
        functions, classes = defs[rel]
        out = []
        if isinstance(expr, ast.Name):
            name = expr.id
            nested = f"{qual}.{name}"
            parent = qual.rsplit(".", 1)[0] + "." + name if "." in qual else None
            if nested in functions:
                out.append((rel, nested))
            elif parent and parent in functions:
                out.append((rel, parent))
            elif name in functions:
                out.append((rel, name))
            elif name in imports[rel]:
                kind = imports[rel][name]
                if kind[0] == "obj" and kind[2] in defs[kind[1]][0]:
                    out.append((kind[1], kind[2]))
        elif isinstance(expr, ast.Attribute):
            attr = expr.attr
            value = expr.value
            if isinstance(value, ast.Name):
                base = value.id
                if base in ("self", "cls") and cls and f"{cls}.{attr}" in functions:
                    out.append((rel, f"{cls}.{attr}"))
                    return out
                if base in imports[rel]:
                    kind = imports[rel][base]
                    if kind[0] == "mod" and attr in defs[kind[1]][0]:
                        out.append((kind[1], attr))
                        return out
                    if kind[0] == "obj" and f"{kind[2]}.{attr}" in defs[kind[1]][0]:
                        out.append((kind[1], f"{kind[2]}.{attr}"))
                        return out
                if base in classes and f"{base}.{attr}" in functions:
                    out.append((rel, f"{base}.{attr}"))
                    return out
            elif isinstance(value, ast.Call) and isinstance(value.func, ast.Name):
                # ClassName(...).method(...)
                base = value.func.id
                if base in classes and f"{base}.{attr}" in functions:
                    out.append((rel, f"{base}.{attr}"))
                    return out
                if base in imports[rel]:
                    kind = imports[rel][base]
                    if kind[0] == "obj" and f"{kind[2]}.{attr}" in defs[kind[1]][0]:
                        out.append((kind[1], f"{kind[2]}.{attr}"))
                        return out
            candidates = [c for c in method_index.get(attr, []) if "." in c[1]]
            if attr not in STOP and 0 < len(candidates) <= 2:
                out.extend(candidates)
        return out

    for rel, (functions, classes) in defs.items():
        for qual, (node, cls) in functions.items():
            targets = set()
            for n in own_nodes(node):
                if isinstance(n, ast.Call):
                    for target in resolve(rel, qual, cls, n.func):
                        targets.add(target)
                    for arg in list(n.args) + [k.value for k in n.keywords]:
                        if isinstance(arg, (ast.Name, ast.Attribute)):
                            for target in resolve(rel, qual, cls, arg):
                                targets.add(target)
            edges[(rel, qual)] = targets

    risky = {}
    writes = {}
    for row in inventory:
        key = (row["module"], row["function"])
        if row["owner"] and row["write"]:
            writes[key] = row
            if row["risks"]:
                risky[key] = row

    reach = {}
    for label, starts in ROOTS.items():
        seen, prev = set(), {}
        queue = deque()
        for start in starts:
            if start in edges:
                seen.add(start)
                queue.append(start)
            else:
                print(f"!! 入口不存在: {start}")
        while queue:
            current = queue.popleft()
            for target in edges.get(current, ()):
                if target not in seen:
                    seen.add(target)
                    prev[target] = current
                    queue.append(target)
        reach[label] = (seen, prev)

    print(f"写事务函数 {len(writes)} 个，其中带风险标记 {len(risky)} 个\n")
    covered = set()
    for label, (seen, prev) in reach.items():
        hit_all = sorted(k for k in writes if k in seen)
        hit_risky = [k for k in hit_all if k in risky]
        covered.update(hit_all)
        print(f"=== {label}: 能走到写事务 {len(hit_all)} 个，其中带风险标记 {len(hit_risky)} 个")
        for key in hit_all:
            row = writes[key]
            tags = ",".join(sorted({r[0] for r in row["risks"]})) or "ok"
            line = f"  [{tags:<9s}] {key[0]}:{key[1]}:{row['line']}"
            if show_paths:
                path, cur = [], key
                while cur in prev:
                    cur = prev[cur]
                    path.append(f"{cur[0].rsplit('/', 1)[-1][:-3]}.{cur[1]}")
                line += "   ← " + " ← ".join(path[:5])
            print(line)
        print()
    rest = sorted(k for k in risky if k not in covered)
    print(f"=== 上述入口都走不到、但带风险标记的写事务 {len(rest)} 个（只从普通接口或启动流程调用）")
    by_mod = {}
    for key in rest:
        by_mod.setdefault(key[0], []).append(key[1])
    for mod in sorted(by_mod):
        print(f"  {mod}: {len(by_mod[mod])} 个  " + ", ".join(by_mod[mod][:12]) + (" ..." if len(by_mod[mod]) > 12 else ""))


if __name__ == "__main__":
    main()
