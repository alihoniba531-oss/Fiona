// 讨论群界面的浏览器测量辅助。用法：把整段贴进 javascript_tool 执行一次，
// 之后用 window.__dq(w) 取测量器；w 是被测页面的 window（抽屉里是 iframe 的 contentWindow）。
// 隐藏的浏览器面板不出帧：导航后先截图，再测量。
window.__dqFrame = () => {
  const f = [...document.querySelectorAll('iframe')].find(i => (i.getAttribute('src') || '').startsWith('/discuss'));
  return f ? f.contentWindow : null;
};
window.__dq = (w) => {
  const d = w.document;
  const R = (e) => {
    if (!e) return null;
    const b = e.getBoundingClientRect();
    return { top: Math.round(b.top), bottom: Math.round(b.bottom), left: Math.round(b.left), right: Math.round(b.right), h: Math.round(b.height), w: Math.round(b.width) };
  };
  const main = () => d.querySelector('main');
  // 可视区下边缘：手机宽度下是底部导航栏的上边缘
  const floor = () => {
    const bar = d.querySelector('nav.mobile-tabbar');
    if (bar) {
      const b = bar.getBoundingClientRect();
      if (b.height > 0 && w.getComputedStyle(bar).display !== 'none') return Math.round(b.top);
    }
    return w.innerHeight;
  };
  const msg = () => {
    // 消息区：群聊面板里纵向滚动、且内容远高于自身的那个盒子（排除 main、textarea、表格外层）
    const ta = d.querySelector('textarea[aria-label="插话"]');
    if (!ta) return null;
    let root = ta;
    for (let i = 0; i < 12 && root.parentElement; i++) {
      root = root.parentElement;
      const hit = [...root.querySelectorAll('*')].find((e) => {
        if (e.tagName === 'TEXTAREA' || e.contains(ta)) return false;
        // 表格外层为了横向滚动也会算出 overflow-y:auto，要排除
        if (e.firstElementChild && e.firstElementChild.tagName === 'TABLE') return false;
        const cs = w.getComputedStyle(e);
        return /(auto|scroll)/.test(cs.overflowY) && e.clientHeight > 0;
      });
      if (hit) return hit;
    }
    return null;
  };
  const composer = () => {
    const ta = d.querySelector('textarea[aria-label="插话"]');
    return ta ? (ta.closest('form') || ta.parentElement) : null;
  };
  const grid = () => [...d.querySelectorAll('main *')].find((e) => w.getComputedStyle(e).display === 'grid' && e.className.toString().includes('grid-rows-['));
  const tabs = () => [...d.querySelectorAll('[role=tab]')].map((t) => t.textContent.trim() + (t.getAttribute('aria-selected') === 'true' ? '*' : ''));
  const toBottom = async () => {
    const m = main();
    m.scrollTop = 9999999;
    await new Promise((r) => setTimeout(r, 300));
    return Math.round(m.scrollTop);
  };
  const toTop = () => { main().scrollTop = 0; };
  const page = () => {
    const m = main();
    return { innerW: w.innerWidth, innerH: w.innerHeight, floor: floor(), scrollable: m.scrollHeight > m.clientHeight + 1, sh: m.scrollHeight, ch: m.clientHeight };
  };
  // 滚到底后，某个元素的底部留白
  const gapAfterScroll = async (el) => {
    if (!el) return { error: 'no element' };
    const st = await toBottom();
    const out = { scrolledBy: st, elBottom: Math.round(el.getBoundingClientRect().bottom), floor: floor(), gap: Math.round(floor() - el.getBoundingClientRect().bottom) };
    toTop();
    return out;
  };
  const room = () => {
    const m = msg();
    const c = composer();
    const g = grid();
    return {
      path: w.location.pathname,
      page: page(),
      tabs: tabs(),
      msg: m ? { h: m.clientHeight, sh: m.scrollHeight, gapToLatest: Math.round(m.scrollHeight - m.scrollTop - m.clientHeight), rect: R(m) } : null,
      composer: R(c),
      composerAboveFloor: c ? Math.round(floor() - c.getBoundingClientRect().bottom) : null,
      grid: g ? R(g) : null,
      tablist: R(d.querySelector('[role=tablist]')),
    };
  };
  const cards = () => [...d.querySelectorAll('main a.ceramic-card')];
  const submit = () => [...d.querySelectorAll('main button')].filter((b) => b.type === 'submit').pop() || null;
  const panel = () => d.querySelector('[role=tabpanel]:not([hidden])');
  const dialog = () => {
    const open = [...d.querySelectorAll('dialog')].find((x) => x.open);
    if (!open) return { open: false };
    const cs = w.getComputedStyle(open);
    const ae = d.activeElement;
    const first = open.querySelector('input, textarea, select');
    const inputs = [...open.querySelectorAll('input')];
    return {
      open: true, modal: open.matches(':modal'), scrim: open.classList.contains('scrim-dialog'),
      padding: [cs.paddingTop, cs.paddingRight, cs.paddingBottom, cs.paddingLeft],
      rect: R(open), focusOnFirstInput: !!first && first === ae,
      values: inputs.map((i) => i.value), inputRects: inputs.map(R),
    };
  };
  return { R, main, floor, msg, composer, grid, tabs, toBottom, toTop, page, gapAfterScroll, room, cards, submit, panel, dialog };
};
'installed';
