# -*- coding: utf-8 -*-
"""生成内测邀请码，只打印本次创建的码。"""

import argparse
import asyncio
import sys

from admin_env import AdminConfigError, admin_options_parser, configure_database, parse_admin_options


async def main(argv: list[str] | None = None) -> int:
    options, remaining = parse_admin_options(argv)
    parser = argparse.ArgumentParser(
        description="生成 Fiona 内测邀请码", parents=[admin_options_parser()]
    )
    parser.add_argument("count", nargs="?", type=int, default=10, help="新建数量（1–200，默认 10）")
    args = parser.parse_args(remaining)
    if not 1 <= args.count <= 200:
        parser.error("数量必须在 1–200 之间")

    try:
        db_path = configure_database(options.env_file, init_db=options.init_db)
    except AdminConfigError as exc:
        print(exc, file=sys.stderr)
        return 2

    import database

    database.DB_PATH = str(db_path)

    await database.init_db()
    created = await database.create_tester_invites(args.count)
    print(f"新增 {len(created)} 个邀请码：")
    for code, username in created:
        print(f"{code}  {username}")

    invites = await database.list_invites()
    unused = sum(not row["revoked_at"] and not row["redeemed_at"] for row in invites)
    used = sum(not row["revoked_at"] and bool(row["redeemed_at"]) for row in invites)
    revoked = sum(bool(row["revoked_at"]) for row in invites)
    print(f"统计：总数 {len(invites)} / 未用 {unused} / 已用 {used} / 已撤销 {revoked}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
