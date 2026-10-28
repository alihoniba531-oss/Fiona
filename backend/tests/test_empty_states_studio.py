"""Offline contracts for the studio identity-loading empty states.

The assertions cover only the three studio components in this task. The probes
read checkout TSX through the existing test drivers; they never touch the
network, git history, or files outside the worktree.
"""

from pathlib import Path

from test_studio_frontend_shell import SETUP, probe as shell_probe
from test_studio_kb_frontend import SETUP as KB_SETUP, probe as kb_probe
from test_ui_polish_settings_drawers import assert_heading_hides_when_embedded

ROOT = Path(__file__).resolve().parents[2]
SHELF = ROOT / "frontend/components/studio/StudioShelf.tsx"
WORKBENCH = ROOT / "frontend/components/studio/StudioWorkbench.tsx"
KB_WORKBENCH = ROOT / "frontend/components/studio/kb/KbWorkbench.tsx"

SHELF_LOGIN_BRANCH = (
    '!owner ? (identityPending ? <LoadingState>正在加载身份…</LoadingState> : '
    '<EmptyState>请登录后打开工作室。<Link href="/login" target={embedded ? "_top" : undefined} '
    'className="ml-2 underline">前往登录</Link></EmptyState>)'
)
WORKBENCH_LOGIN_BRANCH = (
    '!owner ? (identityPending ? <LoadingState>正在加载身份…</LoadingState> : '
    '<EmptyState>请登录后打开工作室。</EmptyState>)'
)
KB_WORKBENCH_LOGIN_BRANCH = (
    '!owner ? (identityPending ? <LoadingState>正在加载身份…</LoadingState> : '
    '<EmptyState>请登录后打开导演知识库。</EmptyState>)'
)
SHELF_HEADER_ROW = '<div className="flex min-h-10 flex-wrap items-center justify-between gap-3">'


def read(path):
    return path.read_text(encoding="utf-8")


def test_embedded_shelf_hides_heading_and_keeps_create_button_right_aligned():
    assert_heading_hides_when_embedded(SHELF, "短片工作室")
    assert shell_probe(SETUP + r"""
env.search='embed=1';
const shelf=await screen('components/studio/StudioShelf.tsx');
const buttons=all(shelf.tree,n=>n.type==='button'&&JSON.stringify(n.props.children).includes('新建项目'));
assert.equal(buttons.length,1);
assert.equal(buttons[0].type,'button');
assert.equal(buttons[0].props.type,'button');
assert(buttons[0].props.className.includes('ml-auto'),buttons[0].props.className);
assert(buttons[0].props.className.includes('btn-primary'),buttons[0].props.className);
shelf.close();process.stdout.write('true');
""") is True


def test_studio_page_ssr_shows_identity_loading_instead_of_login():
    html = kb_probe(KB_SETUP + r"""
env.mode='ssr';cache.clear();
const Page=load('app/studio/page.tsx').default;
const html=renderToStaticMarkup(realReact.createElement(Page));
process.stdout.write(JSON.stringify(html));
""")
    assert "正在加载身份…" in html
    assert "请登录后打开工作室。" not in html


def test_studio_identity_pending_wiring_and_embedded_login_target():
    sources = {
        "StudioShelf": SHELF,
        "StudioWorkbench": WORKBENCH,
        "KbWorkbench": KB_WORKBENCH,
    }
    for name, path in sources.items():
        source = read(path)
        assert source.count("useAccountIdentityPending()") == 1, name
        assert source.count("identityPending={identityPending}") == 1, name
        assert source.count("identityPending = false") == 1, name
        assert source.count("identityPending?: boolean") == 1, name

    assert read(SHELF).count(SHELF_LOGIN_BRANCH) == 1
    assert read(WORKBENCH).count(WORKBENCH_LOGIN_BRANCH) == 1
    assert read(KB_WORKBENCH).count(KB_WORKBENCH_LOGIN_BRANCH) == 1


def test_shelf_header_reserves_height_and_non_embedded_button_is_not_right_aligned():
    assert read(SHELF).count(SHELF_HEADER_ROW) == 1
    assert shell_probe(SETUP + r"""
env.search='';
const shelf=await screen('components/studio/StudioShelf.tsx');
const buttons=all(shelf.tree,n=>n.type==='button'&&JSON.stringify(n.props.children).includes('新建项目'));
assert.equal(buttons.length,1);
assert.equal(buttons[0].type,'button');
assert(!buttons[0].props.className.includes('ml-auto'),buttons[0].props.className);
shelf.close();process.stdout.write('true');
""") is True


def test_identity_pending_workbenches_show_loading_instead_of_login():
    assert shell_probe(SETUP + r"""
const flat=n=>Array.isArray(n)?n.map(flat).join(''):n&&typeof n==='object'?flat(n.props?.children):n==null?'':String(n);
const page=mount(load('components/studio/StudioWorkbench.tsx').AccountStudioWorkbench,{id:'project',owner:'',embedded:false,identityPending:true});await flush();
const rendered=flat(page.tree);
assert(rendered.includes('正在加载身份…'),rendered);
assert(!rendered.includes('请登录后'),rendered);
page.close();process.stdout.write('true');
""") is True
    assert kb_probe(KB_SETUP + r"""
const flat=n=>Array.isArray(n)?n.map(flat).join(''):n&&typeof n==='object'?flat(n.props?.children):n==null?'':String(n);
const page=mount(load('components/studio/kb/KbWorkbench.tsx').AccountKbWorkbench,{owner:'',embedded:false,identityPending:true});await flush();
const rendered=flat(page.tree);
assert(rendered.includes('正在加载身份…'),rendered);
assert(!rendered.includes('请登录后'),rendered);
page.close();process.stdout.write('true');
""") is True
