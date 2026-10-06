"""只跑数据库迁移；默认在临时副本上演练，不启动服务。"""

import argparse
import asyncio
from contextlib import redirect_stderr
import io
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile

from openai import OpenAIError

from admin_env import AdminConfigError, configure_database


def _quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _inventory(path: Path, stage: str) -> int:
    """只打印 schema 和计数，返回没有有效归属用户的消息数。"""
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
        tables = [row[0] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
        )]
        versions = []
        if "schema_migrations" in tables:
            versions = [row[0] for row in db.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            )]
        print(f"{stage} schema_migrations：{versions}")
        columns_by_table = {}
        for table in tables:
            quoted = _quote_identifier(table)
            columns = [row[1] for row in db.execute(f"PRAGMA table_info({quoted})")]
            columns_by_table[table] = columns
            count = db.execute(f"SELECT COUNT(*) FROM {quoted}").fetchone()[0]
            print(f"{stage} 表 {table}：行数={count} 列={columns}")
        if "messages" not in tables:
            return 0
        if "username" not in columns_by_table["messages"]:
            return db.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        if "username" not in columns_by_table.get("users", []):
            return db.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        return db.execute(
            "SELECT COUNT(*) FROM messages m "
            "WHERE NOT EXISTS (SELECT 1 FROM users u WHERE u.username = m.username)"
        ).fetchone()[0]


def _migrate(path: Path) -> None:
    orphan_count = _inventory(path, "迁移前")
    if orphan_count:
        print(
            f"提示：存在 {orphan_count} 条没有归属用户的消息；"
            "第①道迁移可能失败，请先在副本上核对并处理消息归属。",
            file=sys.stderr,
        )
    # configure_database 已加载服务环境；这里只调用 init_db，不启动 lifespan。
    import database

    previous_path = database.DB_PATH
    try:
        database.DB_PATH = str(path)
        asyncio.run(database.init_db())
        _inventory(path, "迁移后")
    finally:
        database.DB_PATH = previous_path


def _check_migration_configuration() -> None:
    if not os.environ.get("DASHSCOPE_API_KEY", "").strip() or (
        os.getenv("DEV_MODE", "0") != "1" and not os.environ.get("JWT_SECRET", "").strip()
    ):
        raise AdminConfigError("missing migration configuration")


def _is_io_error(error: Exception) -> bool:
    if isinstance(error, OSError):
        return True
    code = getattr(error, "sqlite_errorcode", None)
    return isinstance(error, sqlite3.Error) and code is not None and (code & 0xFF) in {
        sqlite3.SQLITE_IOERR, sqlite3.SQLITE_FULL, sqlite3.SQLITE_CANTOPEN,
        sqlite3.SQLITE_READONLY, sqlite3.SQLITE_PERM,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--env-file", type=Path, metavar="PATH", help="加载服务配置文件")
    parser.add_argument("--db", type=Path, metavar="PATH", help="直接指定数据库，优先级最高")
    parser.add_argument("--in-place", action="store_true", help="明确允许在原库上执行迁移")
    args = parser.parse_args(argv)
    try:
        if args.db is not None:
            os.environ["FIONA_DB_PATH"] = str(args.db.expanduser().resolve())
        # 管理脚本的配置诊断包含路径；本工具只输出结构、计数和安全失败提示。
        with redirect_stderr(io.StringIO()):
            original = configure_database(args.env_file, init_db=False)
        if args.in_place:
            print(f"原库迁移目标：{original.resolve()}", flush=True)
        _check_migration_configuration()
        if args.in_place:
            _migrate(original)
        else:
            with tempfile.TemporaryDirectory(prefix="fiona-migration-") as directory:
                copied = Path(directory) / "fiona.db"
                shutil.copy2(original, copied)
                for suffix in ("-wal", "-shm"):
                    sidecar = Path(str(original) + suffix)
                    if sidecar.exists():
                        shutil.copy2(sidecar, Path(str(copied) + suffix))
                _migrate(copied)
        return 0
    except (AdminConfigError, OpenAIError) as error:
        print(
            f"失败 type={type(error).__name__}：数据库不存在或配置不可用，请核对数据库，"
            "并用 --env-file 加载含 DASHSCOPE_API_KEY 和 JWT_SECRET 的服务配置。",
            file=sys.stderr,
        )
        return 2
    except Exception as error:
        hint = (
            "磁盘或 IO 错误，请核对剩余空间、文件权限及存储状态后重试。"
            if _is_io_error(error) else
            "迁移失败，请在副本上检查结构和消息归属后重试。"
        )
        print(
            f"失败 type={type(error).__name__}：{hint}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
