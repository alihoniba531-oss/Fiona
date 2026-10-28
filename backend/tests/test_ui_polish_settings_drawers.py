"""Source-only contracts for the settings drawer keys and embedded page headings.

The tests read frontend files inside the repository, never git history, network,
or files outside the worktree. No Node.js or TypeScript is needed.
"""

import re
import socket
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SETTINGS = ROOT / "frontend/app/settings/page.tsx"
PROFILE = ROOT / "frontend/app/profile/page.tsx"
NOVELS = ROOT / "frontend/app/novels/page.tsx"
NOVEL_SHELF = ROOT / "frontend/components/novel/NovelShelf.tsx"
MY_AGENT = ROOT / "frontend/components/MyAgentWorkspace.tsx"
EXCHANGE = ROOT / "frontend/components/AgentExchangeWorkspace.tsx"


@pytest.fixture(scope="module", autouse=True)
def block_real_network():
    patch = pytest.MonkeyPatch()

    def forbidden(*args, **kwargs):
        raise AssertionError("UI polish settings drawer tests forbid sockets and DNS")

    for name in ("connect", "connect_ex"):
        patch.setattr(socket.socket, name, forbidden)
    for name in ("create_connection", "getaddrinfo", "gethostbyname", "gethostbyname_ex"):
        patch.setattr(socket, name, forbidden)
    yield
    patch.undo()


def read(path):
    return path.read_text(encoding="utf-8")


def h1_tag(source, title):
    """Return the opening tag of the page's own h1 with the expected title."""
    match = re.search(r"<h1\b[^>]*>" + re.escape(title) + r"</h1>", source)
    assert match, f"main h1 {title!r} not found"
    return match.group(0)


def assert_heading_hides_when_embedded(path, title):
    source = read(path)
    tag = h1_tag(source, title)
    assert "embedded" in tag, f"{path.name} h1 must key off the embedded flag"
    assert "sr-only" in tag, f"{path.name} h1 must be visually hidden when embedded"
    # sr-only is added only by the embedded branch; standalone pages stay unchanged.
    conditional = re.search(
        r"\$\{\s*embedded\s*\?\s*\"([^\"]*)\"\s*:\s*\"([^\"]*)\"\s*\}", tag
    )
    assert conditional, f"{path.name} h1 needs an embedded-conditional className"
    assert "sr-only" in conditional.group(1)
    assert "sr-only" not in conditional.group(2)


def test_settings_sections_use_distinct_prefixed_keys():
    source = read(SETTINGS)
    assert "LocalWatchSection" in source
    assert "key={`chat-model:${username}`}" in source
    assert "key={`local-watch:${username}`}" in source
    chat_keys = re.findall(r"<ChatModelSection\b[^>]*\bkey=\{`([^`]*)`\}", source)
    watch_keys = re.findall(r"<LocalWatchSection\b[^>]*\bkey=\{`([^`]*)`\}", source)
    assert chat_keys == ["chat-model:${username}"]
    assert watch_keys == ["local-watch:${username}"]
    assert chat_keys != watch_keys
    # Every former sibling-level key={username} must be prefixed so React does
    # not warn about duplicate keys and drop one of the sections.
    assert re.findall(r"\bkey=\{username\}", source) == []


def test_settings_heading_hides_when_embedded():
    assert_heading_hides_when_embedded(SETTINGS, "设置")


def test_profile_heading_hides_when_embedded():
    assert_heading_hides_when_embedded(PROFILE, "社交画像（旧版）")


def test_my_agent_heading_hides_when_embedded():
    assert_heading_hides_when_embedded(MY_AGENT, "分身")


def test_agent_exchange_heading_hides_when_embedded():
    # Owned by the Beijing-time agent; this only asserts the shared contract.
    assert_heading_hides_when_embedded(EXCHANGE, "广场")


def test_novels_page_scopes_sr_only_to_the_shelf_heading_when_embedded():
    shelf = read(NOVEL_SHELF)
    shelf_heading = re.search(r"<h1\b[^>]*>书斋</h1>", shelf)
    if (
        shelf_heading
        and "embedded" in shelf_heading.group(0)
        and "sr-only" in shelf_heading.group(0)
    ):
        # If the heading owner learns to hide itself, the page needs no wrapper.
        return
    source = read(NOVELS)
    assert re.search(
        r"useSearchParams\(\)\.get\(\"embed\"\)\s*===\s*\"1\"", source
    ), "novels page must read the embed query string"
    conditional = re.search(r"embedded\s*\?\s*\"([^\"]*)\"\s*:\s*\"\"", source)
    assert conditional, "novels page must make the hidden heading conditional"
    classes = conditional.group(1)
    # NovelShelf renders the 书斋 h1 one level down and is outside this task's
    # file allow-list, so the page scopes the sr-only utility to that heading.
    assert re.search(r"header_h1\]:sr-only", classes)
    assert "[&_header_h1+*]:ml-auto" in classes, "新建一本 must stay right-aligned"
    assert "<NovelShelf" in source
