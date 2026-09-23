# -*- coding: utf-8 -*-
"""本机管理内测邀请码：查看、撤销和轮换。

用法：
    python manage_invites.py list --env-file /etc/fiona/fiona.env
    python manage_invites.py revoke ABCD2345 --env-file /etc/fiona/fiona.env
    python manage_invites.py rotate ABCD2345 --env-file /etc/fiona/fiona.env
    python manage_invites.py list --env-file /etc/fiona/fiona.env --init-db  # 首次初始化
"""
import argparse
import asyncio
import secrets
import sys

from admin_env import AdminConfigError, admin_options_parser, configure_database, parse_admin_options

_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def _new_code(length: int = 8) -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))


async def main(argv: list[str] | None = None) -> int:
    options, remaining = parse_admin_options(argv)
    parser = argparse.ArgumentParser(
        description="管理 Fiona 内测邀请码", parents=[admin_options_parser()]
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("list", parents=[admin_options_parser()])
    revoke_parser = subparsers.add_parser("revoke", parents=[admin_options_parser()])
    revoke_parser.add_argument("code")
    rotate_parser = subparsers.add_parser("rotate", parents=[admin_options_parser()])
    rotate_parser.add_argument("code")
    rotate_parser.add_argument("--new-code")
    args = parser.parse_args(remaining)

    try:
        db_path = configure_database(options.env_file, init_db=options.init_db)
    except AdminConfigError as exc:
        print(exc, file=sys.stderr)
        return 2

    import database

    database.DB_PATH = str(db_path)
    await database.init_db()
    if args.command == "list":
        for invite in await database.list_invites():
            if invite["revoked_at"]:
                status = "已撤销"
            elif invite["redeemed_at"]:
                status = f"有效 / 已登录 {invite['use_count']} 次"
            else:
                status = "有效 / 未使用"
            print(f"{invite['code']}  {invite['username']}  [{status}]")
        return 0

    old_code = args.code.strip().upper()
    if args.command == "revoke":
        if not await database.revoke_invite(old_code):
            print("邀请码不存在或已经撤销")
            return 1
        print(f"已撤销 {old_code}")
        return 0

    new_code = (args.new_code or _new_code()).strip().upper()
    if not await database.rotate_invite(old_code, new_code):
        print("轮换失败：旧码无效/已撤销，或新码已存在")
        return 1
    print(f"旧码已撤销，新邀请码：{new_code}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
