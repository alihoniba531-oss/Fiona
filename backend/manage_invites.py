# -*- coding: utf-8 -*-
"""本机管理内测邀请码：查看、撤销和轮换。

用法：
    python manage_invites.py list
    python manage_invites.py revoke ABCD2345
    python manage_invites.py rotate ABCD2345
"""
import argparse
import asyncio
import secrets

from database import init_db, list_invites, revoke_invite, rotate_invite

_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def _new_code(length: int = 8) -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))


async def main() -> int:
    parser = argparse.ArgumentParser(description="管理 Fiona 内测邀请码")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("list")
    revoke_parser = subparsers.add_parser("revoke")
    revoke_parser.add_argument("code")
    rotate_parser = subparsers.add_parser("rotate")
    rotate_parser.add_argument("code")
    rotate_parser.add_argument("--new-code")
    args = parser.parse_args()

    await init_db()
    if args.command == "list":
        for invite in await list_invites():
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
        if not await revoke_invite(old_code):
            print("邀请码不存在或已经撤销")
            return 1
        print(f"已撤销 {old_code}")
        return 0

    new_code = (args.new_code or _new_code()).strip().upper()
    if not await rotate_invite(old_code, new_code):
        print("轮换失败：旧码无效/已撤销，或新码已存在")
        return 1
    print(f"旧码已撤销，新邀请码：{new_code}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
