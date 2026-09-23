# -*- coding: utf-8 -*-
"""管理脚本共用的配置加载与数据库路径保护。"""

import argparse
import os
from pathlib import Path
import sys

from dotenv import load_dotenv


class AdminConfigError(Exception):
    """管理脚本无法安全地确定数据库时使用的错误。"""


def admin_options_parser() -> argparse.ArgumentParser:
    """共用参数也提供给各命令的帮助页。"""
    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument("--env-file", type=Path, metavar="PATH", help="加载指定的服务配置文件")
    parser.add_argument("--init-db", action="store_true", help="首次使用时初始化不存在的数据库")
    return parser


def parse_admin_options(argv: list[str] | None = None) -> tuple[argparse.Namespace, list[str]]:
    """允许公共参数放在管理命令的前面或后面。"""
    parser = admin_options_parser()
    return parser.parse_known_args(argv)


def configure_database(env_file: Path | None, *, init_db: bool) -> Path:
    """在导入 database 前加载配置，报告并核对实际数据库路径。"""
    backend_dir = Path(__file__).resolve().parent
    selected: Path | None = None
    explicit = env_file or os.environ.get("FIONA_ENV_FILE")
    if explicit:
        selected = Path(explicit).expanduser().resolve()
    else:
        for candidate in (Path("/etc/fiona/fiona.env"), backend_dir / ".env"):
            if candidate.is_file() and os.access(candidate, os.R_OK):
                selected = candidate.resolve()
                break

    config_error = None
    loaded: Path | None = None
    if selected:
        if not selected.is_file() or not os.access(selected, os.R_OK):
            config_error = f"配置文件不存在或不可读：{selected}"
        else:
            try:
                load_dotenv(dotenv_path=selected, override=False)
            except OSError:
                config_error = f"配置文件不存在或不可读：{selected}"
            else:
                loaded = selected

    db_path = Path(os.environ.get("FIONA_DB_PATH") or backend_dir / "fiona.db").expanduser().resolve()
    os.environ["FIONA_DB_PATH"] = str(db_path)
    print(f"配置：{loaded if loaded else '无'}", file=sys.stderr)
    print(f"数据库：{db_path}", file=sys.stderr)
    if config_error:
        raise AdminConfigError(config_error)
    if not db_path.is_file() and not init_db:
        raise AdminConfigError(
            f"数据库文件不存在：{db_path}。请确认 FIONA_DB_PATH，"
            "或用 --env-file 指定服务使用的配置文件；首次初始化才加 --init-db"
        )
    return db_path
