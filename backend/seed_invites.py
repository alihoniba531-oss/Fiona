# -*- coding: utf-8 -*-
"""生成内测邀请码。

用法：
    python3 seed_invites.py [数量]      # 默认 10

每个码绑定一个用户名（tester01、tester02…），打印出来发给测试者。
重复运行只新增、不重建已有码；末尾会列出全部码 + 是否已用。
"""
import asyncio
import secrets
import sys

from database import init_db, create_invite, list_invites

# 去掉易混字符 0/O/1/I/L，避免测试者输错
_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def _gen_code(n: int = 8) -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(n))


async def main() -> None:
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    await init_db()

    existing = await list_invites()
    start = len(existing) + 1

    created = []
    for i in range(start, start + count):
        username = f"tester{i:02d}"
        # 极小概率撞码，撞了就重抽，保证拿到 count 个
        while True:
            code = _gen_code()
            if await create_invite(code, username, note=f"内测 #{i}"):
                break
        created.append((code, username))

    print(f"\n新增 {len(created)} 个邀请码：\n")
    for code, username in created:
        print(f"  {code}   →  {username}")

    print("\n当前全部邀请码：")
    for r in await list_invites():
        status = "已用" if r["redeemed_at"] else "未用"
        print(f"  {r['code']}   {r['username']:<10} [{status}]")
    print()


if __name__ == "__main__":
    asyncio.run(main())
