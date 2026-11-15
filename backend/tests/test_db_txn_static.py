# -*- coding: utf-8 -*-
"""静态门禁：后端打开数据库连接必须走 ``utils.db_txn.connect``。

扫描规则对应 ``docs/tasks/2026-11-15-write-txn-cancel-guard/02-spec.md``
第 4.4 节，并按复核报告 2.10 / 可优化项 1 补上别名和间接引用：

* 除 ``backend/utils/db_txn.py`` 外，后端非测试代码不得调用
  ``aiosqlite.connect(...)``，也不得出现 ``from aiosqlite import connect``；
* 不得通过 ``import aiosqlite as X``、``import aiosqlite.core``、
  ``import aiosqlite.core as Y``、``from aiosqlite import core [as Z]``
  绑定的名字去引用 ``.connect`` / ``.core.connect``，有没有调用都算；
* ``from aiosqlite import connect / Connection / *`` 与
  ``from aiosqlite.core import connect / Connection / *`` 算违规；
* ``getattr(X, "connect")``（``X`` 为上述名字或 ``aiosqlite.core``）算违规；
* 直接构造 ``X.Connection(...)`` / ``X.core.Connection(...)`` 算违规，
  只在类型标注等位置引用 ``aiosqlite.Connection`` 不算；
* 每一处 ``db_txn.connect(...)`` 都必须是 ``async with`` 的上下文表达式，
  例如 ``async with db_txn.connect(...) as db:``；
* 防空转：扫描到的文件数不少于 100，``db_txn.connect`` 调用数不少于 140。

断言失败时列出文件和行号（``_Site`` 格式），便于直接定位。
"""
from __future__ import annotations

import ast
import io
import os
import tokenize
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


_TEST_PATH = Path(__file__).resolve()
_BACKEND_ROOT = _TEST_PATH.parents[1]  # .../backend
_REPO_ROOT = _BACKEND_ROOT.parent  # 仓库根
_DB_TXN_PATH = (_BACKEND_ROOT / "utils" / "db_txn.py").resolve()

_SKIP_DIR_NAMES = frozenset({".venv", "tests", "__pycache__", "uploads"})
_MIN_SCANNED_FILES = 100
_MIN_DB_TXN_CALLS = 140

_AIOSQLITE_MODULE = "aiosqlite"
_AIOSQLITE_CORE_MODULE = "aiosqlite.core"
_UNSAFE_IMPORTED_NAMES = frozenset({"connect", "Connection", "*"})

_KIND_CONNECT_ATTRIBUTE = "connect-attribute"
_KIND_CORE_CONNECT_ATTRIBUTE = "core-connect-attribute"
_KIND_UNSAFE_IMPORT = "unsafe-import"
_KIND_GETATTR_CONNECT = "getattr-connect"
_KIND_CONNECTION_CONSTRUCTION = "connection-construction"

if not _DB_TXN_PATH.is_file():  # 防止测试文件被搬家后静默扫了空目录
    raise RuntimeError(
        f"静态门禁找不到封装实现 {_DB_TXN_PATH}；"
        f"由 __file__ 推导出的 backend 根目录是 {_BACKEND_ROOT}"
    )


@dataclass(frozen=True)
class _Site:
    """一处代码位置，用于拼出可直接定位的失败信息。"""

    path: Path
    lineno: int
    col_offset: int
    code: str = ""

    def __str__(self) -> str:
        return (
            f"{_shown_path(self.path)}:{self.lineno}:{self.col_offset + 1}"
            f"{'  ' + self.code if self.code else ''}"
        )


@dataclass(frozen=True)
class _Escape:
    """一处绕过统一封装打开 aiosqlite 连接的写法。"""

    kind: str
    site: _Site


@dataclass(frozen=True)
class _FileScan:
    """单个源文件的扫描结果。"""

    db_txn_calls: tuple[_Site, ...]
    db_txn_not_async_with: tuple[_Site, ...]
    db_txn_source_count: int
    direct_aiosqlite_calls: tuple[_Site, ...]
    aiosqlite_connect_imports: tuple[_Site, ...]
    aiosqlite_escapes: tuple[_Escape, ...]


@dataclass(frozen=True)
class _ScanResult:
    files: tuple[Path, ...]
    db_txn_calls: tuple[_Site, ...]
    db_txn_not_async_with: tuple[_Site, ...]
    direct_aiosqlite_calls: tuple[_Site, ...]
    aiosqlite_connect_imports: tuple[_Site, ...]
    aiosqlite_escapes: tuple[_Escape, ...]
    db_txn_source_count: int


def _shown_path(path: Path) -> str:
    """尽量显示成以仓库根开头的相对路径。"""
    try:
        return str(path.relative_to(_REPO_ROOT))
    except ValueError:
        return str(path)


def _iter_python_files(root: Path):
    """遍历 root 下全部非测试 .py 文件，目录结果保持排序稳定。"""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(
            name for name in dirnames if name not in _SKIP_DIR_NAMES
        )
        for filename in sorted(filenames):
            if filename.endswith(".py"):
                yield Path(dirpath) / filename


def _read_source(path: Path) -> str:
    # tokenize.open 会按文件里的 coding cookie 解码；后端源码统一用它读。
    with tokenize.open(path) as handle:
        return handle.read()


def _parse_source(path: Path, source: str) -> ast.AST:
    try:
        return ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        raise AssertionError(
            "无法解析待检查的后端文件 "
            f"{_shown_path(path)}:{exc.lineno}: {exc.msg}"
        ) from exc


def _is_owner_connect_call(node: ast.AST, owner: str) -> bool:
    """判断节点是否为 ``<owner>.connect(...)`` 形式的调用。"""
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "connect"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == owner
    )


def _is_db_txn_connect(node: ast.AST) -> bool:
    return _is_owner_connect_call(node, "db_txn")


def _is_aiosqlite_connect(node: ast.AST) -> bool:
    return _is_owner_connect_call(node, "aiosqlite")


def _site(path: Path, node: ast.AST, source: str) -> _Site:
    lineno = getattr(node, "lineno", 1)
    col_offset = getattr(node, "col_offset", 0)
    lines = source.splitlines()
    code = lines[lineno - 1].strip() if 0 < lineno <= len(lines) else ""
    if len(code) > 160:
        code = code[:157] + "..."
    return _Site(
        path=path, lineno=lineno, col_offset=col_offset, code=code
    )


def _count_db_txn_connect_tokens(source: str) -> int:
    """按 token 统计 ``db_txn.connect(``，忽略注释和字符串字面量。

    这是 AST 计数的独立旁路校验：源码里注释或文档字符串提到这个 API 时
    不应影响计数，所以用 token 流而不是裸文本 ``str.count``。
    """
    tokens = []
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type in (
            tokenize.NL,
            tokenize.COMMENT,
            tokenize.INDENT,
            tokenize.DEDENT,
            tokenize.ENCODING,
            tokenize.ENDMARKER,
        ):
            continue
        tokens.append(token)

    count = 0
    for index in range(len(tokens) - 3):
        first, second, third, fourth = tokens[index:index + 4]
        if not (
            first.type == tokenize.NAME
            and first.string == "db_txn"
            and second.type == tokenize.OP
            and second.string == "."
            and third.type == tokenize.NAME
            and third.string == "connect"
            and fourth.type == tokenize.OP
            and fourth.string == "("
        ):
            continue
        # 排除 ``obj.db_txn.connect(...)`` 这类属性链；AST 侧同样不会把它
        # 当成 Name('db_txn')，两边保持一致。
        if (
            index > 0
            and tokens[index - 1].type == tokenize.OP
            and tokens[index - 1].string == "."
        ):
            continue
        count += 1
    return count


def _format_sites(sites: tuple[_Site, ...]) -> str:
    return "\n".join(f"  {site}" for site in sites)


def _format_escapes(escapes: tuple[_Escape, ...]) -> str:
    return "\n".join(f"  [{escape.kind}] {escape.site}" for escape in escapes)


def _add_binding(
    bindings: dict[str, set[str]], name: str, module: str
) -> None:
    bindings.setdefault(name, set()).add(module)


def _collect_aiosqlite_bindings(
    tree: ast.AST,
) -> tuple[dict[str, set[str]], tuple[ast.ImportFrom, ...]]:
    """收集绑定到 aiosqlite / aiosqlite.core 的名字与违规 import。

    ``import aiosqlite.core`` 没写 as 时，Python 绑定的是顶层包
    ``aiosqlite``，所以这个名字按 ``aiosqlite`` 模块记录；写了 as 才绑定
    ``aiosqlite.core`` 子模块。
    """
    bindings: dict[str, set[str]] = {}
    unsafe_imports: list[ast.ImportFrom] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == _AIOSQLITE_MODULE:
                    _add_binding(
                        bindings,
                        alias.asname or _AIOSQLITE_MODULE,
                        _AIOSQLITE_MODULE,
                    )
                elif alias.name == _AIOSQLITE_CORE_MODULE:
                    if alias.asname:
                        _add_binding(
                            bindings, alias.asname, _AIOSQLITE_CORE_MODULE
                        )
                    else:
                        _add_binding(
                            bindings, _AIOSQLITE_MODULE, _AIOSQLITE_MODULE
                        )
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            if node.module == _AIOSQLITE_MODULE:
                for alias in node.names:
                    if alias.name == "core":
                        _add_binding(
                            bindings,
                            alias.asname or "core",
                            _AIOSQLITE_CORE_MODULE,
                        )
                if any(
                    alias.name in _UNSAFE_IMPORTED_NAMES
                    for alias in node.names
                ):
                    unsafe_imports.append(node)
            elif node.module == _AIOSQLITE_CORE_MODULE:
                if any(
                    alias.name in _UNSAFE_IMPORTED_NAMES
                    for alias in node.names
                ):
                    unsafe_imports.append(node)

    return bindings, tuple(unsafe_imports)


def _name_has_any_binding(
    node: ast.AST, bindings: dict[str, set[str]]
) -> bool:
    """节点是否为绑定到 aiosqlite 或 aiosqlite.core 的名字。"""
    return isinstance(node, ast.Name) and node.id in bindings


def _is_aiosqlite_core_reference(
    node: ast.AST, bindings: dict[str, set[str]]
) -> bool:
    """节点是否为 ``<绑定到 aiosqlite 的名字>.core``。"""
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "core"
        and isinstance(node.value, ast.Name)
        and _AIOSQLITE_MODULE in bindings.get(node.value.id, ())
    )


def _is_getattr_connect_call(
    node: ast.Call, bindings: dict[str, set[str]]
) -> bool:
    """是否为 ``getattr(<上述名字或 aiosqlite.core>, "connect")``。"""
    if not (isinstance(node.func, ast.Name) and node.func.id == "getattr"):
        return False
    if len(node.args) < 2:
        return False
    name_arg = node.args[1]
    if not (
        isinstance(name_arg, ast.Constant) and name_arg.value == "connect"
    ):
        return False
    target = node.args[0]
    return _name_has_any_binding(target, bindings) or (
        _is_aiosqlite_core_reference(target, bindings)
    )


def _is_connection_construction(
    node: ast.Call, bindings: dict[str, set[str]]
) -> bool:
    """是否为 ``<上述名字>.Connection(...)`` / ``<aiosqlite 名字>.core.Connection(...)``。"""
    func = node.func
    if not (isinstance(func, ast.Attribute) and func.attr == "Connection"):
        return False
    return _name_has_any_binding(func.value, bindings) or (
        _is_aiosqlite_core_reference(func.value, bindings)
    )


def _collect_aiosqlite_escapes(
    tree: ast.AST, path: Path, source: str
) -> tuple[_Escape, ...]:
    """收集所有通过别名或间接引用打开 aiosqlite 连接的写法。"""
    bindings, unsafe_imports = _collect_aiosqlite_bindings(tree)
    escapes: list[_Escape] = [
        _Escape(_KIND_UNSAFE_IMPORT, _site(path, node, source))
        for node in unsafe_imports
    ]

    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "connect":
            if _name_has_any_binding(node.value, bindings):
                escapes.append(
                    _Escape(
                        _KIND_CONNECT_ATTRIBUTE,
                        _site(path, node, source),
                    )
                )
            elif _is_aiosqlite_core_reference(node.value, bindings):
                escapes.append(
                    _Escape(
                        _KIND_CORE_CONNECT_ATTRIBUTE,
                        _site(path, node, source),
                    )
                )
        elif isinstance(node, ast.Call):
            if _is_getattr_connect_call(node, bindings):
                escapes.append(
                    _Escape(
                        _KIND_GETATTR_CONNECT,
                        _site(path, node, source),
                    )
                )
            elif _is_connection_construction(node, bindings):
                escapes.append(
                    _Escape(
                        _KIND_CONNECTION_CONSTRUCTION,
                        _site(path, node, source),
                    )
                )

    escapes.sort(key=lambda escape: (
        escape.site.lineno,
        escape.site.col_offset,
        escape.kind,
    ))
    return tuple(escapes)


def _scan_source(path: Path, source: str, *, exempt: bool) -> _FileScan:
    """扫描单个源文件；``exempt`` 为真时只解析、不检查（db_txn 自身）。"""
    tree = _parse_source(path, source)
    if exempt:
        return _FileScan((), (), 0, (), (), ())

    # 第一遍：收集所有作为 async with 上下文表达式出现的 db_txn.connect。
    async_with_contexts: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncWith):
            for item in node.items:
                if _is_db_txn_connect(item.context_expr):
                    async_with_contexts.add(id(item.context_expr))

    db_txn_calls: list[_Site] = []
    db_txn_not_async_with: list[_Site] = []
    direct_aiosqlite_calls: list[_Site] = []
    aiosqlite_connect_imports: list[_Site] = []

    # 第二遍：检查所有调用与 import。
    for node in ast.walk(tree):
        if _is_db_txn_connect(node):
            site = _site(path, node, source)
            db_txn_calls.append(site)
            if id(node) not in async_with_contexts:
                db_txn_not_async_with.append(site)
        if _is_aiosqlite_connect(node):
            direct_aiosqlite_calls.append(_site(path, node, source))
        if (
            isinstance(node, ast.ImportFrom)
            and node.level == 0
            and node.module == _AIOSQLITE_MODULE
            and any(alias.name == "connect" for alias in node.names)
        ):
            aiosqlite_connect_imports.append(_site(path, node, source))

    return _FileScan(
        db_txn_calls=tuple(db_txn_calls),
        db_txn_not_async_with=tuple(db_txn_not_async_with),
        db_txn_source_count=_count_db_txn_connect_tokens(source),
        direct_aiosqlite_calls=tuple(direct_aiosqlite_calls),
        aiosqlite_connect_imports=tuple(aiosqlite_connect_imports),
        aiosqlite_escapes=_collect_aiosqlite_escapes(tree, path, source),
    )


def _scan_paths(paths, *, exempt_paths=()) -> _ScanResult:
    """扫描给定的一组源文件；供 backend 门禁和临时文件用例共用。"""
    files = tuple(paths)
    exempt = {path.resolve() for path in exempt_paths}
    db_txn_calls: list[_Site] = []
    db_txn_not_async_with: list[_Site] = []
    direct_aiosqlite_calls: list[_Site] = []
    aiosqlite_connect_imports: list[_Site] = []
    aiosqlite_escapes: list[_Escape] = []
    db_txn_source_count = 0

    for path in files:
        source = _read_source(path)
        file_scan = _scan_source(
            path, source, exempt=path.resolve() in exempt
        )
        db_txn_calls.extend(file_scan.db_txn_calls)
        db_txn_not_async_with.extend(file_scan.db_txn_not_async_with)
        direct_aiosqlite_calls.extend(file_scan.direct_aiosqlite_calls)
        aiosqlite_connect_imports.extend(
            file_scan.aiosqlite_connect_imports
        )
        aiosqlite_escapes.extend(file_scan.aiosqlite_escapes)
        db_txn_source_count += file_scan.db_txn_source_count

    return _ScanResult(
        files=files,
        db_txn_calls=tuple(db_txn_calls),
        db_txn_not_async_with=tuple(db_txn_not_async_with),
        direct_aiosqlite_calls=tuple(direct_aiosqlite_calls),
        aiosqlite_connect_imports=tuple(aiosqlite_connect_imports),
        aiosqlite_escapes=tuple(aiosqlite_escapes),
        db_txn_source_count=db_txn_source_count,
    )


def _scan_root(root: Path, *, exempt_paths=()) -> _ScanResult:
    """扫描任意根目录下的非测试 .py 文件。"""
    return _scan_paths(
        _iter_python_files(root), exempt_paths=exempt_paths
    )


def _scan_file(path: Path) -> _ScanResult:
    """扫描单个源文件（不走 backend 的 lru_cache）。"""
    return _scan_paths((path,))


@lru_cache(maxsize=1)
def _scan() -> _ScanResult:
    """扫描一次 backend 源码树；结果缓存给同一次 pytest 会话里的各用例。"""
    return _scan_root(_BACKEND_ROOT, exempt_paths=(_DB_TXN_PATH,))


def test_scan_is_not_vacuous():
    """防空转：扫描范围与命中数必须达到规格下限。"""
    result = _scan()
    problems = []
    if len(result.files) < _MIN_SCANNED_FILES:
        problems.append(
            f"只扫描到 {len(result.files)} 个非测试 .py 文件"
            f"（{_shown_path(_BACKEND_ROOT)} 下），"
            f"少于防呆下限 {_MIN_SCANNED_FILES} 个；"
            "扫描目录或排除规则可能失效"
        )
    if len(result.db_txn_calls) < _MIN_DB_TXN_CALLS:
        problems.append(
            f"只扫描到 {len(result.db_txn_calls)} 处 db_txn.connect(...)，"
            f"少于防呆下限 {_MIN_DB_TXN_CALLS} 处；"
            "全站替换或扫描器可能不完整"
        )
    assert not problems, "；\n".join(problems)


def test_no_direct_aiosqlite_connect_calls():
    """除封装实现外，后端代码不得直接调用 aiosqlite.connect。"""
    result = _scan()
    assert not result.direct_aiosqlite_calls, (
        "除 backend/utils/db_txn.py 外，后端代码不得直接调用 "
        "aiosqlite.connect(...)，必须改用 utils.db_txn.connect(...)。"
        f"共 {len(result.direct_aiosqlite_calls)} 处违规：\n"
        + _format_sites(result.direct_aiosqlite_calls)
    )


def test_no_from_aiosqlite_import_connect():
    """后端代码不得用 from aiosqlite import connect 绕过统一封装。"""
    result = _scan()
    assert not result.aiosqlite_connect_imports, (
        "后端代码不得出现 `from aiosqlite import connect`，"
        "打开连接必须走 utils.db_txn.connect(...)。"
        f"共 {len(result.aiosqlite_connect_imports)} 处违规：\n"
        + _format_sites(result.aiosqlite_connect_imports)
    )


def test_no_aiosqlite_aliases_or_indirect_connection_openings():
    """别名、aiosqlite.core、getattr、间接引用和直接构造连接都算违规。"""
    result = _scan()
    assert not result.aiosqlite_escapes, (
        "除 backend/utils/db_txn.py 外，后端代码只能通过 "
        "utils.db_txn.connect(...) 打开连接；不得使用 aiosqlite 导入别名、"
        "aiosqlite.core、getattr(..., \"connect\")、间接引用 connect，"
        "也不得直接构造 Connection(...)。"
        f"共 {len(result.aiosqlite_escapes)} 处违规：\n"
        + _format_escapes(result.aiosqlite_escapes)
    )


def test_db_txn_connect_calls_are_async_with_context_expressions():
    """每一处 db_txn.connect 都必须是 async with 的上下文表达式。"""
    result = _scan()
    assert not result.db_txn_not_async_with, (
        "每一处 db_txn.connect(...) 都必须是 async with 的上下文表达式，"
        "例如 `async with db_txn.connect(...) as db:`；"
        "不得写成 `db = await db_txn.connect(...)` 或放进其他表达式。"
        f"共 {len(result.db_txn_not_async_with)} 处违规：\n"
        + _format_sites(result.db_txn_not_async_with)
    )


def test_db_txn_connect_ast_count_matches_source_tokens():
    """AST Call 计数与源码 token 计数一致，防止扫描器漏算或重复计算。"""
    result = _scan()
    assert result.db_txn_source_count == len(result.db_txn_calls), (
        "db_txn.connect(...) 的源码 token 计数与 AST Call 计数不一致："
        f"token={result.db_txn_source_count}，"
        f"AST={len(result.db_txn_calls)}；扫描器可能漏算或重复计算"
    )


# 每一行是一处独立写法；第三项是该行应当被报出的违规类别。
# 空的第三项表示 import 绑定本身或只引用不构造，不应被判违规。
_PROOF_CASES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("import-functools", "import functools", ()),
    ("import-aiosqlite", "import aiosqlite", ()),
    ("import-alias", "import aiosqlite as aio", ()),
    ("import-core", "import aiosqlite.core", ()),
    ("import-core-alias", "import aiosqlite.core as aio_core", ()),
    ("from-core", "from aiosqlite import core", ()),
    ("from-core-alias", "from aiosqlite import core as core_alias", ()),
    (
        "alias-call",
        "aio.connect('alias.db')",
        (_KIND_CONNECT_ATTRIBUTE,),
    ),
    (
        "direct-call",
        "aiosqlite.connect('direct.db')",
        (_KIND_CONNECT_ATTRIBUTE,),
    ),
    (
        "core-connect",
        "aiosqlite.core.connect('core.db')",
        (_KIND_CORE_CONNECT_ATTRIBUTE,),
    ),
    (
        "alias-core-connect",
        "aio.core.connect('alias-core.db')",
        (_KIND_CORE_CONNECT_ATTRIBUTE,),
    ),
    (
        "core-alias-call",
        "aio_core.connect('core-alias.db')",
        (_KIND_CONNECT_ATTRIBUTE,),
    ),
    (
        "from-core-call",
        "core.connect('from-core.db')",
        (_KIND_CONNECT_ATTRIBUTE,),
    ),
    (
        "from-core-alias-call",
        "core_alias.connect('from-core-alias.db')",
        (_KIND_CONNECT_ATTRIBUTE,),
    ),
    (
        "connect-reference",
        "connect_ref = aio.connect",
        (_KIND_CONNECT_ATTRIBUTE,),
    ),
    (
        "partial",
        "functools.partial(aiosqlite.connect, 'partial.db')",
        (_KIND_CONNECT_ATTRIBUTE,),
    ),
    (
        "from-connect",
        "from aiosqlite import connect",
        (_KIND_UNSAFE_IMPORT,),
    ),
    (
        "from-core-connect",
        "from aiosqlite.core import connect",
        (_KIND_UNSAFE_IMPORT,),
    ),
    (
        "from-connection",
        "from aiosqlite import Connection",
        (_KIND_UNSAFE_IMPORT,),
    ),
    (
        "from-core-connection",
        "from aiosqlite.core import Connection as _Connection",
        (_KIND_UNSAFE_IMPORT,),
    ),
    (
        "from-star",
        "from aiosqlite import *",
        (_KIND_UNSAFE_IMPORT,),
    ),
    (
        "from-core-star",
        "from aiosqlite.core import *",
        (_KIND_UNSAFE_IMPORT,),
    ),
    (
        "getattr-module",
        "getattr(aiosqlite, 'connect')",
        (_KIND_GETATTR_CONNECT,),
    ),
    (
        "getattr-core-alias",
        "getattr(aio_core, 'connect')",
        (_KIND_GETATTR_CONNECT,),
    ),
    (
        "getattr-core",
        "getattr(aiosqlite.core, 'connect')",
        (_KIND_GETATTR_CONNECT,),
    ),
    (
        "construct-alias",
        "aio.Connection('construct.db')",
        (_KIND_CONNECTION_CONSTRUCTION,),
    ),
    (
        "construct-core",
        "aiosqlite.core.Connection('construct-core.db')",
        (_KIND_CONNECTION_CONSTRUCTION,),
    ),
    (
        "construct-core-alias",
        "aio_core.Connection('construct-core-alias.db')",
        (_KIND_CONNECTION_CONSTRUCTION,),
    ),
    ("type-only", "connection_type = aiosqlite.Connection", ()),
    ("getattr-dynamic", "getattr(aiosqlite, attr_name)", ()),
)


def test_scanner_catches_alias_and_indirect_forms(tmp_path):
    """临时源文件里每种绕过写法各一处，同一套扫描逻辑必须逐行报出。"""
    lines: list[str] = []
    labels: dict[int, str] = {}
    expected: set[tuple[int, str]] = set()

    for key, code, kinds in _PROOF_CASES:
        lines.append(code)
        line_no = len(lines)
        labels[line_no] = key
        for kind in kinds:
            expected.add((line_no, kind))

    target = tmp_path / "aiosqlite_bypass_probe.py"
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")

    result = _scan_file(target)
    assert result.files == (target,), (
        "单文件扫描不应走 backend 的缓存扫描："
        f"实际扫描文件为 {[str(path) for path in result.files]}"
    )
    actual = {
        (escape.site.lineno, escape.kind)
        for escape in result.aiosqlite_escapes
    }

    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    assert not missing and not unexpected, (
        f"绕过写法扫描结果与预期不一致（{target}）：\n"
        "漏报（行号:类别  源码）：\n"
        + (
            "\n".join(
                f"  {line}:{kind} [{labels[line]}]  {lines[line - 1]}"
                for line, kind in missing
            )
            or "  （无）"
        )
        + "\n误报（行号:类别  源码）：\n"
        + (
            "\n".join(
                f"  {line}:{kind} [{labels[line]}]  {lines[line - 1]}"
                for line, kind in unexpected
            )
            or "  （无）"
        )
        + "\n实际报出：\n"
        + (
            "\n".join(
                f"  {escape.site}" for escape in result.aiosqlite_escapes
            )
            or "  （无）"
        )
    )
