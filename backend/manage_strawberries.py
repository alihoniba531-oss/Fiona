# -*- coding: utf-8 -*-
"""本机查看、补充和设置内测用户草莓余额。"""

import argparse
import asyncio
import sys

from admin_env import AdminConfigError, admin_options_parser, configure_database, parse_admin_options


def _amount(value: str, *, minimum: int) -> int:
    try:
        amount = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("数量必须是整数") from exc
    if not minimum <= amount <= 100000:
        raise argparse.ArgumentTypeError(f"数量必须在 {minimum}–100000 之间")
    return amount


async def main(argv: list[str] | None = None) -> int:
    options, remaining = parse_admin_options(argv)
    parser = argparse.ArgumentParser(
        description="管理 Fiona 内测草莓余额", parents=[admin_options_parser()]
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("list", parents=[admin_options_parser()])
    grant_parser = subparsers.add_parser("grant", parents=[admin_options_parser()])
    grant_parser.add_argument("username")
    grant_parser.add_argument("amount", type=lambda value: _amount(value, minimum=1))
    set_parser = subparsers.add_parser("set", parents=[admin_options_parser()])
    set_parser.add_argument("username")
    set_parser.add_argument("amount", type=lambda value: _amount(value, minimum=0))
    args = parser.parse_args(remaining)

    try:
        db_path = configure_database(options.env_file, init_db=options.init_db)
    except AdminConfigError as exc:
        print(exc, file=sys.stderr)
        return 2

    import aiosqlite

    if args.command == "list":
        if options.init_db:
            import database

            database.DB_PATH = str(db_path)
            await database.init_db()
        async with aiosqlite.connect(f"{db_path.as_uri()}?mode=ro", uri=True) as db:
            async with db.execute("PRAGMA table_info(users)") as cursor:
                columns = {row[1] for row in await cursor.fetchall()}
            if not {"username", "strawberry_balance"} <= columns:
                print(
                    "数据库缺少 users.username 或 users.strawberry_balance；"
                    "请先备份并使用 --init-db 初始化或迁移",
                    file=sys.stderr,
                )
                return 2
            date_column = "strawberry_refill_date" if "strawberry_refill_date" in columns else "NULL"
            async with db.execute(
                f"SELECT username, strawberry_balance, {date_column} "
                "FROM users ORDER BY username"
            ) as cursor:
                rows = await cursor.fetchall()
        for username, balance, refill_date in rows:
            print(f"{username}  {balance}  {refill_date or '-'}")
        return 0

    import database

    database.DB_PATH = str(db_path)
    await database.init_db()
    if args.command == "grant":
        await database.get_strawberry_balance(args.username)
        # add_strawberry returns 0 if no row was updated; granted balances are positive.
        balance = await database.add_strawberry(args.username, args.amount)
        if balance == 0:
            print("用户不存在", file=sys.stderr)
            return 1
    else:
        await database.get_strawberry_balance(args.username)
        async with aiosqlite.connect(database.DB_PATH) as db:
            async with db.execute(
                "UPDATE users SET strawberry_balance = ? WHERE username = ? "
                "RETURNING strawberry_balance",
                (args.amount, args.username),
            ) as cursor:
                row = await cursor.fetchone()
            await db.commit()
        if row is None:
            print("用户不存在", file=sys.stderr)
            return 1
        balance = row[0]

    print(f"{args.username}  {balance}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
