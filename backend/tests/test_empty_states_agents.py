"""Source contracts for the identity-pending empty states on the four agent pages.

The agent components have no existing offline React harness, and the required
change is a small, exact wiring pattern, so these checks intentionally read the
four sources only. They stay offline and do not depend on git history.
"""

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

ACCOUNT_IMPORT = (
    'import { useAccountIdentity, useAccountIdentityPending, useAccountRequest } '
    'from "@/lib/useAccountIdentity";'
)

# The whole `!owner ? (identityPending ? <确认中元素> : <原登录元素>) : ...`
# prefix, copied verbatim from each source. Asserting it as one substring pins
# the confirmation branch, the untouched original login copy and their order
# together, so a rewrite that only leaves the words in place cannot pass.
MY_AGENT_WIRING = (
    '!owner ? (identityPending ? <p className="text-fs-13 text-[color:var(--ink2)]" role="status">正在加载身份…</p>'
    ' : <p className="text-fs-13 text-[color:var(--ink2)]" role="status">请登录后管理自己的分身。'
    '<Link href="/login" className="ml-2 text-[color:var(--ink)] underline">前往登录</Link></p>)'
)

EXCHANGE_WIRING = (
    '!owner ? (identityPending ? <LoadingState>正在加载身份…</LoadingState>'
    ' : <EmptyState>请登录后查看分身和自己的交流记录。'
    '<Link href="/login" className="ml-2 text-[color:var(--ink)] underline">前往登录</Link></EmptyState>)'
)

MEMORY_WIRING = (
    '!owner ? (identityPending ? <p className="text-fs-12 text-[color:var(--ink2)]" role="status">正在加载身份…</p>'
    ' : <p className="text-fs-12 text-[color:var(--ink2)]" role="status">请登录后查看私有记忆。</p>)'
)

AGENT_CARD_WIRING = (
    '!owner ? (identityPending ? <p role="status" className="text-fs-13 text-[color:var(--ink2)]">正在加载身份…</p>'
    ' : <p role="status" className="text-fs-13 text-[color:var(--ink2)]">请登录后查看分身名片。'
    '<Link href="/login" className="ml-2 text-[color:var(--ink)] underline">前往登录</Link></p>)'
)


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def _import_statements(source: str) -> list[str]:
    return re.findall(r"(?ms)^import\b.*?;", source)


def _assert_identity_pending_wiring(
    relative_path: str,
    wiring: str,
    login_text: str,
    pending_element: str,
) -> None:
    source = _read(relative_path)
    assert "useAccountIdentityPending()" in source, f"{relative_path} must call useAccountIdentityPending()"
    assert "identityPending={identityPending}" in source, (
        f"{relative_path} must pass identityPending to its account-scoped child"
    )
    assert "identityPending = false" in source, (
        f"{relative_path} must default the inner identityPending prop to false"
    )
    assert ACCOUNT_IMPORT in source, f"{relative_path} must import useAccountIdentityPending"
    assert wiring in source, (
        f"{relative_path} must keep the exact "
        "`!owner ? (identityPending ? <确认中> : <原登录>)` branch verbatim"
    )
    assert source.count(pending_element) == 1, (
        f"{relative_path} must render the exact pending-identity element exactly once"
    )
    assert source.count(login_text) == 1, (
        f"{relative_path} must keep the original login copy exactly once"
    )
    assert source.index(pending_element) < source.index(login_text), (
        f"{relative_path} must render the pending element before the original login element"
    )


def test_my_agent_workspace_shows_pending_identity_before_login():
    source = _read("frontend/components/MyAgentWorkspace.tsx")
    assert "useAccountIdentityPending()" in source
    _assert_identity_pending_wiring(
        "frontend/components/MyAgentWorkspace.tsx",
        MY_AGENT_WIRING,
        "请登录后管理自己的分身。",
        '<p className="text-fs-13 text-[color:var(--ink2)]" role="status">正在加载身份…</p>',
    )


def test_agent_exchange_workspace_pending_identity_uses_local_loading_state():
    relative_path = "frontend/components/AgentExchangeWorkspace.tsx"
    source = _read(relative_path)
    # The pending branch must use the file's own LoadingState, not one borrowed
    # from another module: exactly one local definition and no import of it.
    assert source.count("function LoadingState(") == 1, (
        f"{relative_path} must define its own LoadingState exactly once"
    )
    assert not any("LoadingState" in statement for statement in _import_statements(source)), (
        f"{relative_path} must not import LoadingState from another module"
    )
    assert "useAccountIdentityPending()" in source
    _assert_identity_pending_wiring(
        relative_path,
        EXCHANGE_WIRING,
        "请登录后查看分身和自己的交流记录。",
        "<LoadingState>正在加载身份…</LoadingState>",
    )
    assert "<b className=\"readout\">" not in source
    assert source.count("平台官方 AI · 无真人用户") == 1


def test_agent_memory_panel_shows_pending_identity_before_login():
    relative_path = "frontend/components/AgentMemoryPanel.tsx"
    source = _read(relative_path)
    assert "useAccountIdentityPending()" in source
    _assert_identity_pending_wiring(
        relative_path,
        MEMORY_WIRING,
        "请登录后查看私有记忆。",
        '<p className="text-fs-12 text-[color:var(--ink2)]" role="status">正在加载身份…</p>',
    )
    assert source.count(
        "清空分身记忆和已有个人画像？聊天记录与分身设定会保留，后续交流可形成新的记忆。"
    ) == 1
    assert "useConfirm()" in source
    assert source.count("isCurrentOwner()") >= 2


def test_agent_card_page_shows_pending_identity_before_login():
    relative_path = "frontend/app/agents/[id]/page.tsx"
    source = _read(relative_path)
    assert "useAccountIdentityPending()" in source
    _assert_identity_pending_wiring(
        relative_path,
        AGENT_CARD_WIRING,
        "请登录后查看分身名片。",
        '<p role="status" className="text-fs-13 text-[color:var(--ink2)]">正在加载身份…</p>',
    )
