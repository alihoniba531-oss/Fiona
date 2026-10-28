"""Novel workshop empty states: pending identity and a single new-book entrance.

The behavior probes reuse the R1 driver, which transpiles the checked-out TS in
memory and renders the owning component plus its inner component, so real
effects and request wrappers run against an in-memory API.
"""
from pathlib import Path

import pytest

from test_novel_p2_r1 import probe

ROOT = Path(__file__).resolve().parents[2]
NOVEL = ROOT / "frontend" / "components" / "novel"

WIRING_FILES = ("NovelWizard.tsx", "NovelShelf.tsx", "NovelWorkbench.tsx")
LOGIN_TEXT = {
    "NovelWizard.tsx": "请登录后新建小说。",
    "NovelShelf.tsx": "请登录后查看你的书架。",
    "NovelWorkbench.tsx": "请登录后打开你的书斋。",
}
WIRING_BRANCHES = {
    "NovelWizard.tsx": '!owner ? (identityPending ? <LoadingState>正在加载身份…</LoadingState> : <EmptyState>请登录后新建小说。</EmptyState>)',
    "NovelShelf.tsx": '!owner ? (identityPending ? <LoadingState>正在加载身份…</LoadingState> : <EmptyState>请登录后查看你的书架。<Link href="/login" target={embedded ? "_top" : undefined} className="ml-2 underline">前往登录</Link></EmptyState>)',
    "NovelWorkbench.tsx": '!owner ? (identityPending ? <LoadingState>正在加载身份…</LoadingState> : <EmptyState>请登录后打开你的书斋。<Link href="/login" target={embedded ? "_top" : undefined} className="ml-2 underline">前往登录</Link></EmptyState>)',
}
HEADER_ROW = '<div className="flex min-h-10 flex-wrap items-center justify-between gap-3">'


def test_shelf_empty_state_has_exactly_one_new_book_link():
    assert probe(r"""
const o=agents.apiJson;
agents.apiJson=async(u,i)=>u==='/api/novels'?[]:o(u,i);
const shelf=await screen('components/novel/NovelShelf.tsx');
function plain(node){if(Array.isArray(node))return node.map(plain).join('');if(node==null||typeof node==='boolean')return '';if(typeof node!=='object')return String(node);return plain(node.props?.children);}
const links=all(shelf.tree,n=>typeof n.props?.href==='string'&&n.props.href.includes('/novels/new'));
assert.equal(links.length,1);
assert.equal(plain(links[0]),'新建一本');
assert(plain(shelf.tree).includes('开始你的第一本书'));
process.stdout.write(JSON.stringify(true));
""") is True


def test_shelf_pending_identity_replaces_login_and_idles_refresh():
    # A separate node process: useAccountIdentityPending's module-level settled
    # flag may only flip from false to true, so the empty-username case must not
    # run after a render that already had a username.
    assert probe(r"""
env.owner='';
// Same two layers as screen(), kept apart so the outer-to-inner prop is visible.
const outer=mount(load('components/novel/NovelShelf.tsx').default,{});
await flush();
const shelf=outer.tree;
assert.equal(shelf.props.owner,'');
assert.equal(shelf.props.identityPending,true);
const inner=mount(shelf.type,shelf.props);
await flush();
function plain(node){if(Array.isArray(node))return node.map(plain).join('');if(node==null||typeof node==='boolean')return '';if(typeof node!=='object')return String(node);return plain(node.props?.children);}
const text=plain(inner.tree);
assert(text.includes('正在加载身份…'));
assert(!text.includes('请登录后查看你的书架'));
assert(!text.includes('前往登录'));
const refresh=all(inner.tree,n=>n.type==='button'&&String(n.props?.className??'').includes('btn-quiet'));
assert.equal(refresh.length,1);
assert.equal(plain(refresh[0]),'刷新');
assert.equal(refresh[0].props.disabled,true);
process.stdout.write(JSON.stringify(true));
""") is True


@pytest.mark.parametrize("filename", WIRING_FILES)
def test_novel_pages_wire_identity_pending_before_login(filename):
    source = (NOVEL / filename).read_text(encoding="utf-8")
    login = LOGIN_TEXT[filename]
    assert "useAccountIdentityPending()" in source
    assert "identityPending={identityPending}" in source
    assert "identityPending = false" in source
    assert "正在加载身份…" in source
    assert source.count(login) == 1
    assert source.index("正在加载身份…") < source.index(login)


@pytest.mark.parametrize("filename", ("NovelShelf.tsx", "NovelWorkbench.tsx"))
def test_novel_login_link_escapes_the_embedded_frame(filename):
    source = (NOVEL / filename).read_text(encoding="utf-8")
    login_line = next(line for line in source.splitlines() if "前往登录" in line)
    assert 'target={embedded ? "_top" : undefined}' in login_line
    assert "请登录后" in login_line
    assert "正在加载身份…" in login_line


def test_novel_shelf_hides_header_entry_only_in_empty_state_and_waits_for_identity():
    source = (NOVEL / "NovelShelf.tsx").read_text(encoding="utf-8")
    assert "!(owner && !error && !loading && books.length === 0)" in source
    assert 'loading && owner ? "刷新中…"' in source
    assert 'loading && owner ? "animate-spin"' in source
    assert "disabled={loading || !owner}" in source
    assert "disabled={loading}" not in source


def test_novel_shelf_new_book_entry_sits_in_header_unless_the_shelf_is_empty():
    # Empty shelf: the only /novels/new entry belongs to the empty-state card,
    # and the header has none at all.
    assert probe(r"""
const original=agents.apiJson;
agents.apiJson=async(u,i)=>u==='/api/novels'?[]:original(u,i);
const shelf=await screen('components/novel/NovelShelf.tsx');
const {EmptyState}=load('components/novel/NovelStates.tsx');
const header=all(shelf.tree,n=>n.type==='header')[0];
assert(header);
assert.equal(all(header,n=>typeof n.props?.href==='string'&&n.props.href.includes('/novels/new')).length,0);
const entries=[];
(function walk(node,ancestors){
  if(Array.isArray(node)){node.forEach(child=>walk(child,ancestors));return;}
  if(!node||typeof node!=='object')return;
  if(typeof node.props?.href==='string'&&node.props.href.includes('/novels/new'))entries.push({node,ancestors});
  walk(node.props?.children,[...ancestors,node]);
})(shelf.tree,[]);
assert.equal(entries.length,1);
assert(entries[0].ancestors.some(ancestor=>ancestor.type===EmptyState));
function plain(node){if(Array.isArray(node))return node.map(plain).join('');if(node==null||typeof node==='boolean')return '';if(typeof node!=='object')return String(node);return plain(node.props?.children);}
assert.equal(plain(entries[0].node),'新建一本');
assert(plain(shelf.tree).includes('开始你的第一本书'));
process.stdout.write(JSON.stringify(true));
""") is True

    # Default data with one book: the header keeps exactly one entry.
    assert probe(r"""
const shelf=await screen('components/novel/NovelShelf.tsx');
const header=all(shelf.tree,n=>n.type==='header')[0];
assert(header);
const entries=all(header,n=>typeof n.props?.href==='string'&&n.props.href.includes('/novels/new'));
assert.equal(entries.length,1);
assert.equal(entries[0].props.href,'/novels/new');
function plain(node){if(Array.isArray(node))return node.map(plain).join('');if(node==null||typeof node==='boolean')return '';if(typeof node!=='object')return String(node);return plain(node.props?.children);}
assert.equal(plain(entries[0]),'新建一本');
process.stdout.write(JSON.stringify(true));
""") is True

    # API failure: the error branch owns the body; the header still has one entry.
    assert probe(r"""
env.failures.set('GET /api/novels',{status:500,message:'故障'});
const shelf=await screen('components/novel/NovelShelf.tsx');
env.failures.delete('GET /api/novels');
const header=all(shelf.tree,n=>n.type==='header')[0];
assert(header);
const entries=all(header,n=>typeof n.props?.href==='string'&&n.props.href.includes('/novels/new'));
assert.equal(entries.length,1);
const notices=all(shelf.tree,n=>n.type?.name==='ErrorNotice');
assert.equal(notices.length,1);
assert.equal(notices[0].props.message,'故障');
assert.equal(all(shelf.tree,n=>typeof n.props?.href==='string'&&n.props.href.includes('/novels/new')).length,1);
process.stdout.write(JSON.stringify(true));
""") is True


def test_novel_shelf_pending_identity_settles_to_embedded_login_link():
    # A fresh process starts without a settled identity recovery: the outer
    # passes identityPending=true to the inner before the recovery resolves.
    assert probe(r"""
env.owner='';env.search='embed=1';
const NovelShelf=load('components/novel/NovelShelf.tsx').default;
const pending=mount(NovelShelf,{});
assert.equal(pending.tree.props.owner,'');
assert.equal(pending.tree.props.identityPending,true);
await flush();
const settled=mount(NovelShelf,{});
assert.equal(settled.tree.props.owner,'');
assert.equal(settled.tree.props.identityPending,false);
const inner=mount(settled.tree.type,settled.tree.props);
await flush();
function plain(node){if(Array.isArray(node))return node.map(plain).join('');if(node==null||typeof node==='boolean')return '';if(typeof node!=='object')return String(node);return plain(node.props?.children);}
const text=plain(inner.tree);
assert(text.includes('请登录后查看你的书架'));
assert(!text.includes('正在加载身份…'));
const login=all(inner.tree,n=>n.props?.href==='/login');
assert.equal(login.length,1);
assert.equal(login[0].props.target,'_top');
process.stdout.write(JSON.stringify(true));
""") is True


@pytest.mark.parametrize("filename", WIRING_FILES)
def test_novel_pages_wire_the_verbatim_pending_identity_branch(filename):
    source = (NOVEL / filename).read_text(encoding="utf-8")
    assert source.count(WIRING_BRANCHES[filename]) == 1


def test_novel_shelf_header_row_reserves_min_height():
    source = (NOVEL / "NovelShelf.tsx").read_text(encoding="utf-8")
    assert source.count(HEADER_ROW) == 1
    assert '<div className="flex flex-wrap items-center justify-between gap-3">' not in source
