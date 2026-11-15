# -*- coding: utf-8 -*-
"""讨论群的结构不变量（场景 19）。

模块级导入 ``discuss.store``：基线提交没有 ``backend/discuss/``，本文件在
收集阶段就会 ImportError，不会出现部分结构断言照样通过。
不依赖 HTTP 接口，也不导入 ``discuss.service`` 或 ``routers.discuss``。
"""
import asyncio
import ast
import re
import sqlite3
from pathlib import Path

import database

# 基线提交（859e2c5）没有 backend/discuss/，这行让本文件在收集阶段直接 ImportError。
from discuss import store as discuss_store


DISCUSS_DIR = Path(__file__).parents[1] / "discuss"


def _init_fresh_db(monkeypatch, tmp_path):
    import database as database_module

    monkeypatch.setattr(database_module, "DB_PATH", str(tmp_path / "structure.db"))
    asyncio.run(database_module.init_db())
    return database_module.DB_PATH


def _table_names(db_path):
    with sqlite3.connect(db_path) as db:
        return [row[0] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]


def test_init_db_is_idempotent_and_keeps_migration_count(monkeypatch, tmp_path):
    """场景 19：init_db 连跑两次不报错；schema_migrations 恰好 5 项。"""
    db_path = _init_fresh_db(monkeypatch, tmp_path)
    asyncio.run(database.init_db())
    with sqlite3.connect(db_path) as db:
        versions = db.execute("SELECT version FROM schema_migrations ORDER BY rowid").fetchall()
    assert len(versions) == 5, versions


def test_discuss_tables_created_by_init_db(monkeypatch, tmp_path):
    """场景 19 前置：init_db 后五张 discuss 表存在，供流程与清理使用。"""
    db_path = _init_fresh_db(monkeypatch, tmp_path)
    tables = set(_table_names(db_path))
    assert {"discuss_groups", "discuss_messages", "discuss_sources",
            "discuss_steps", "discuss_outputs"} <= tables
    ddl_tables = {
        name for statement in discuss_store.DISCUSS_TABLES_DDL
        for name in re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", statement)
    }
    assert {"discuss_groups", "discuss_messages", "discuss_sources",
            "discuss_steps", "discuss_outputs"} <= ddl_tables


def test_novel_table_count_is_unchanged(monkeypatch, tmp_path):
    """场景 19：名为 novels 或 novel_* 的表恰好 7 张。"""
    db_path = _init_fresh_db(monkeypatch, tmp_path)
    with sqlite3.connect(db_path) as db:
        tables = {row[0] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND (name='novels' OR name GLOB 'novel_*')")}
    assert tables == {
        "novels", "novel_bible_versions", "novel_chapters",
        "novel_drafts", "novel_feedback", "novel_notes", "novel_steps",
    }


def test_discuss_package_does_not_import_studio():
    """场景 19：backend/discuss/ 下的 .py 不导入 studio。"""
    import_lines = re.compile(r"^\s*(?:from|import)\s+([A-Za-z_][\w.]*)")
    relative_studio = re.compile(r"^\s*from\s+\.+\s+import\s+.*\bstudio\b")
    offenders = []
    for path in sorted(DISCUSS_DIR.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        for node in ast.walk(ast.parse(source)):
            modules = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [node.module or ""]
                if node.level:
                    modules.extend(alias.name for alias in node.names)
            for module in modules:
                if module == "studio" or module.startswith("studio."):
                    offenders.append((path.name, module))
        for line in source.splitlines():
            match = import_lines.match(line)
            if match and (match.group(1) == "studio" or match.group(1).startswith("studio.")):
                offenders.append((path.name, line.strip()))
            if relative_studio.match(line):
                offenders.append((path.name, line.strip()))
    assert offenders == []
