// 规格作者的探针：只按规格 4.5 的文字写，不看实现。
// 用法：node probe_logic.cjs <仓库根>
// 输出一行 JSON：{ran, failed:[{name, error}]}；有失败时退出码 1。
const fs = require('fs'), path = require('path'), assert = require('assert/strict');
const root = process.argv[2];
const frontend = path.join(root, 'frontend');
const ts = require(path.join(frontend, 'node_modules/typescript'));
const file = path.join(frontend, 'lib/discussLogic.ts');
const source = fs.readFileSync(file, 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
}).outputText;
const mod = { exports: {} };
new Function('require', 'module', 'exports', compiled)(
  name => { throw new Error('discussLogic.ts 不应有运行时依赖：' + name); }, mod, mod.exports);
const L = mod.exports;

const failed = [];
let ran = 0;
function check(name, fn) {
  ran += 1;
  try { fn(); } catch (error) { failed.push({ name, error: String(error && error.message || error).slice(0, 400) }); }
}
const eq = (a, b) => assert.deepEqual(a, b);

// 1 状态文案
check('label: 六个固定状态', () => {
  eq(L.discussStatusLabel({ status: 'planning', stop_reason: null }), '立项中');
  eq(L.discussStatusLabel({ status: 'awaiting_start', stop_reason: null }), '等你开工');
  eq(L.discussStatusLabel({ status: 'running', stop_reason: null }), '讨论中');
  eq(L.discussStatusLabel({ status: 'awaiting_user', stop_reason: 'rounds_exhausted' }), '等你决定');
  eq(L.discussStatusLabel({ status: 'closed', stop_reason: 'user' }), '已结束');
  eq(L.discussStatusLabel({ status: 'failed', stop_reason: 'error' }), '出错了');
});
check('label: done 的两种原因', () => {
  eq(L.discussStatusLabel({ status: 'done', stop_reason: 'accepted_by_user' }), '你已接受');
  eq(L.discussStatusLabel({ status: 'done', stop_reason: 'accepted' }), '验收通过');
});
check('label: paused 各原因', () => {
  const table = { user: '已暂停', budget: '预算用完', insufficient_strawberries: '草莓不足',
    byok_unavailable: '自带模型不可用', step_failed: '有一步没跑通',
    search_unavailable: '联网搜索暂不可用', server_restart_failed: '恢复失败' };
  for (const [reason, label] of Object.entries(table)) {
    eq(L.discussStatusLabel({ status: 'paused', stop_reason: reason }), label);
  }
  eq(L.discussStatusLabel({ status: 'paused', stop_reason: 'whatever' }), '已暂停');
  eq(L.discussStatusLabel({ status: 'paused', stop_reason: null }), '已暂停');
});
check('label: 不认识的状态原样返回', () => {
  eq(L.discussStatusLabel({ status: 'weird', stop_reason: null }), 'weird');
});

// 2 提示
check('hint: 各状态', () => {
  eq(L.discussStopHint({ status: 'awaiting_start', stop_reason: null }),
    '方案已经出来了。看一眼、改一改，回答主持人的问题，然后开工。');
  eq(L.discussStopHint({ status: 'awaiting_user', stop_reason: 'rounds_exhausted' }),
    '轮数用完了，验收还没通过。你可以接受现在的成果，或者追加轮数让它继续。');
  eq(L.discussStopHint({ status: 'paused', stop_reason: 'budget' }), '预算用完了。继续之前先追加预算。');
  eq(L.discussStopHint({ status: 'paused', stop_reason: 'insufficient_strawberries' }), '草莓不够了。补充草莓后点继续。');
  eq(L.discussStopHint({ status: 'paused', stop_reason: 'byok_unavailable' }), '自带模型用不了。到设置里检查后点继续。');
  eq(L.discussStopHint({ status: 'paused', stop_reason: 'step_failed' }), '有一步连着几次没跑通。点继续会从断的地方接着跑。');
  eq(L.discussStopHint({ status: 'paused', stop_reason: 'search_unavailable' }), '联网搜索暂时拿不到结果。过一会儿点继续。');
  eq(L.discussStopHint({ status: 'paused', stop_reason: 'server_restart_failed' }), '服务重启后没能自动接上。点继续会从断的地方接着跑。');
  eq(L.discussStopHint({ status: 'paused', stop_reason: 'user' }), '');
  eq(L.discussStopHint({ status: 'failed', stop_reason: 'error' }), '出了意料之外的错误。点继续会从断的地方接着跑。');
  eq(L.discussStopHint({ status: 'done', stop_reason: 'accepted' }), '验收通过了。想再改，先在群聊里写下意见，再点按意见返工。');
  eq(L.discussStopHint({ status: 'done', stop_reason: 'accepted_by_user' }), '');
  eq(L.discussStopHint({ status: 'running', stop_reason: null }), '');
  eq(L.discussStopHint({ status: 'closed', stop_reason: 'user' }), '');
});

// 3、4
check('active / needsAuthor', () => {
  const all = ['planning', 'awaiting_start', 'running', 'paused', 'awaiting_user', 'done', 'closed', 'failed'];
  eq(all.filter(status => L.discussIsActive(status)), ['planning', 'running']);
  eq(all.filter(status => L.discussNeedsAuthor({ status, stop_reason: null })),
    ['awaiting_start', 'paused', 'awaiting_user', 'failed']);
});

// 5 操作
check('actions: 每个状态', () => {
  const g = (status, output_version, pending_notes = 0) => L.discussActions({ status, stop_reason: null, output_version, pending_notes });
  eq(g('planning', 0), ['pause', 'delete']);
  eq(g('awaiting_start', 0), ['start', 'close', 'delete']);
  eq(g('running', 0), ['pause', 'delete']);
  eq(g('running', 1), ['pause', 'export', 'delete']);
  eq(g('paused', 0), ['resume', 'close', 'delete']);
  eq(g('paused', 1), ['resume', 'accept', 'close', 'export', 'delete']);
  eq(g('awaiting_user', 0), ['continue', 'close', 'delete']);
  eq(g('awaiting_user', 2), ['continue', 'accept', 'close', 'export', 'delete']);
  eq(g('done', 1), ['rework', 'export', 'delete']);
  eq(g('failed', 0), ['resume', 'close', 'delete']);
  eq(g('failed', 1), ['resume', 'close', 'export', 'delete']);
  eq(g('closed', 0), ['delete']);
  eq(g('closed', 3), ['export', 'delete']);
});

// 6 默认标签
check('defaultTab', () => {
  const t = (status, output_version) => L.discussDefaultTab({ status, output_version });
  eq(t('awaiting_start', 0), 'plan');
  eq(t('awaiting_start', 1), 'plan');
  eq(t('awaiting_user', 1), 'output');
  eq(t('done', 2), 'output');
  eq(t('closed', 1), 'output');
  eq(t('done', 0), 'chat');
  eq(t('closed', 0), 'chat');
  eq(t('running', 1), 'chat');
  eq(t('planning', 0), 'chat');
  eq(t('paused', 1), 'chat');
  eq(t('failed', 1), 'chat');
});

// 7 种类
check('kindLabel', () => {
  const table = { plan: '方案', brief: '主人背景', note: '调研笔记', notice: '说明', critique: '质疑',
    decision: '裁决', draft: '成稿', view: '主人视角', verdict: '验收', rework: '返工安排', user: '插话' };
  for (const [kind, label] of Object.entries(table)) eq(L.discussKindLabel(kind), label);
  eq(L.discussKindLabel('unknown'), '');
});

// 8 合并
check('merge: 去重、以新值为准、升序、不改入参', () => {
  const current = [{ id: 3, content: 'old3' }, { id: 1, content: 'a' }];
  const incoming = [{ id: 5, content: 'e' }, { id: 3, content: 'new3' }, { id: 2, content: 'b' }];
  const snapshotA = JSON.stringify(current), snapshotB = JSON.stringify(incoming);
  const merged = L.mergeDiscussMessages(current, incoming);
  eq(merged.map(item => [item.id, item.content]), [[1, 'a'], [2, 'b'], [3, 'new3'], [5, 'e']]);
  eq(JSON.stringify(current), snapshotA);
  eq(JSON.stringify(incoming), snapshotB);
  assert.notEqual(merged, current);
});

// 9 已读标记
check('applyPendingNotes', () => {
  const base = () => [
    { id: 1, sender: 'host', consumed: null },
    { id: 2, sender: 'user', consumed: false },
    { id: 3, sender: 'lens1', consumed: null },
    { id: 4, sender: 'user', consumed: false },
    { id: 6, sender: 'user', consumed: true },
  ];
  const flags = (list) => list.filter(m => m.sender === 'user').map(m => [m.id, m.consumed]);
  eq(flags(L.applyPendingNotes(base(), 0)), [[2, true], [4, true], [6, true]]);
  eq(flags(L.applyPendingNotes(base(), 1)), [[2, true], [4, true], [6, false]]);
  eq(flags(L.applyPendingNotes(base(), 2)), [[2, true], [4, false], [6, false]]);
  eq(flags(L.applyPendingNotes(base(), 3)), [[2, false], [4, false], [6, false]]);
  eq(flags(L.applyPendingNotes(base(), 9)), [[2, false], [4, false], [6, false]]);
  eq(flags(L.applyPendingNotes(base(), 'x')), [[2, true], [4, true], [6, true]]);
  eq(flags(L.applyPendingNotes(base(), -1)), [[2, true], [4, true], [6, true]]);
  const input = base();
  const frozen = JSON.stringify(input);
  const output = L.applyPendingNotes(input, 1);
  eq(JSON.stringify(input), frozen);
  eq(output.filter(m => m.sender !== 'user').map(m => m.consumed), [null, null]);
  eq(output.map(m => m.id), [1, 2, 3, 4, 6]);
});

// 10 分组
check('groupDiscussRounds', () => {
  const messages = [
    { id: 1, round: 0 }, { id: 2, round: 0 }, { id: 3, round: 1 }, { id: 4, round: 2 },
    { id: 5, round: 1 }, { id: 6, round: 1 },
  ];
  const groups = L.groupDiscussRounds(messages);
  eq(groups.map(g => [g.round, g.label, g.messages.map(m => m.id)]), [
    [0, '立项', [1, 2]], [1, '第 1 轮', [3]], [2, '第 2 轮', [4]], [1, '第 1 轮', [5, 6]],
  ]);
  eq(L.groupDiscussRounds([]), []);
});

// 11 文档拆块
check('splitDocument: 没有表格', () => {
  eq(L.splitDiscussDocument('# 标题\n\n一段话。'), [{ kind: 'markdown', text: '# 标题\n\n一段话。' }]);
});
check('splitDocument: 表格夹在中间', () => {
  const text = '前面一段。\n\n| 平台 | 类型 |\n|---|---|\n| TikTok | 公开 |\n| ReelShort | 独立 App |\n\n后面一段。';
  const blocks = L.splitDiscussDocument(text);
  eq(blocks.map(b => b.kind), ['markdown', 'table', 'markdown']);
  eq(blocks[1].header, ['平台', '类型']);
  eq(blocks[1].rows, [['TikTok', '公开'], ['ReelShort', '独立 App']]);
  assert.ok(blocks[0].text.includes('前面一段。'));
  assert.ok(blocks[2].text.includes('后面一段。'));
  assert.ok(!blocks[0].text.includes('|'));
  assert.ok(!blocks[2].text.includes('|'));
});
check('splitDocument: 列数多了截断、少了补空', () => {
  const blocks = L.splitDiscussDocument('| a | b | c |\n| --- | :---: | ---: |\n| 1 | 2 | 3 | 4 |\n| 5 |');
  eq(blocks.length, 1);
  eq(blocks[0].header, ['a', 'b', 'c']);
  eq(blocks[0].rows, [['1', '2', '3'], ['5', '', '']]);
});
check('splitDocument: 代码块里不找表格', () => {
  const text = '```\n| a | b |\n|---|---|\n| 1 | 2 |\n```';
  const blocks = L.splitDiscussDocument(text);
  eq(blocks.map(b => b.kind), ['markdown']);
  eq(blocks[0].text, text);
});
check('splitDocument: 只有表头没有分隔行不算表格', () => {
  const text = '| a | b |\n| 1 | 2 |';
  eq(L.splitDiscussDocument(text), [{ kind: 'markdown', text }]);
});
check('splitDocument: 行首有空白的表格、单元格里带编号', () => {
  const blocks = L.splitDiscussDocument('  | 平台 | 信息 |\n  |---|---|\n  | TikTok | 收益约 0.07 美元[S26] |');
  eq(blocks.length, 1);
  eq(blocks[0].kind, 'table');
  eq(blocks[0].rows, [['TikTok', '收益约 0.07 美元[S26]']]);
});
check('splitDocument: 入参不是字符串、空白', () => {
  eq(L.splitDiscussDocument(null), []);
  eq(L.splitDiscussDocument(undefined), []);
  eq(L.splitDiscussDocument(42), []);
  eq(L.splitDiscussDocument('   \n  '), []);
});

// 12 来源编号
check('splitCitations', () => {
  eq(L.splitDiscussCitations('没有编号'), [{ kind: 'text', text: '没有编号' }]);
  eq(L.splitDiscussCitations(''), []);
  eq(L.splitDiscussCitations('[S1]开头'), [{ kind: 'cite', id: 'S1' }, { kind: 'text', text: '开头' }]);
  eq(L.splitDiscussCitations('中间[S26]有'), [
    { kind: 'text', text: '中间' }, { kind: 'cite', id: 'S26' }, { kind: 'text', text: '有' }]);
  eq(L.splitDiscussCitations('结尾[S1234]'), [{ kind: 'text', text: '结尾' }, { kind: 'cite', id: 'S1234' }]);
  eq(L.splitDiscussCitations('相邻[S26][S119]。'), [
    { kind: 'text', text: '相邻' }, { kind: 'cite', id: 'S26' }, { kind: 'cite', id: 'S119' },
    { kind: 'text', text: '。' }]);
  eq(L.splitDiscussCitations('[S12345]'), [{ kind: 'text', text: '[S12345]' }]);
  eq(L.splitDiscussCitations('[s3] 和 [S]'), [{ kind: 'text', text: '[s3] 和 [S]' }]);
});

// 13 网址
check('safeExternalUrl', () => {
  assert.ok(String(L.safeExternalUrl('https://example.com/a?b=1')).startsWith('https://example.com/a'));
  assert.ok(String(L.safeExternalUrl('http://example.com')).startsWith('http://example.com'));
  for (const bad of ['javascript:alert(1)', 'JAVASCRIPT:alert(1)', 'data:text/html,<b>x</b>', '/relative/path',
    'example.com', '', '   ', null, undefined, 7, {}, 'ftp://example.com/file', 'vbscript:x', 'file:///etc/passwd']) {
    eq(L.safeExternalUrl(bad), null);
  }
});

// 18 错误文案
check('errorMessage', () => {
  eq(L.discussErrorMessage({ status: 404, message: 'Not Found' }), '讨论群尚未开放');
  eq(L.discussErrorMessage({ status: 403, message: '讨论群暂未对该账号开放' }), '你的账号暂未开通讨论群');
  eq(L.discussErrorMessage({ status: 404, message: '讨论群不存在' }), '讨论群不存在');
  eq(L.discussErrorMessage({ status: 409, message: '你有一个讨论群正在进行，等它停下来再建新的' }),
    '你有一个讨论群正在进行，等它停下来再建新的');
  eq(L.discussErrorMessage({ status: 500, message: 'Internal Server Error' }), '请求未完成，请稍后重试。');
  eq(L.discussErrorMessage(new Error('Failed to fetch')), '请求未完成，请稍后重试。');
  eq(L.discussErrorMessage(null), '请求未完成，请稍后重试。');
  eq(L.discussErrorMessage('boom'), '请求未完成，请稍后重试。');
});

// 19 链接
check('discussHref', () => {
  eq(L.discussHref('/discuss', false), '/discuss');
  eq(L.discussHref('/discuss', true), '/discuss?embed=1');
  eq(L.discussHref('/discuss/abc?x=1', true), '/discuss/abc?x=1&embed=1');
  eq(L.discussHref('/discuss/abc?x=1', false), '/discuss/abc?x=1');
});

// 20 模型名
check('modelLabel', () => {
  eq(L.discussModelLabel('dashscope:qwen3.8-max'), '千问 3.8 Max');
  eq(L.discussModelLabel('deepseek:deepseek-flash'), 'DeepSeek Flash');
  eq(L.discussModelLabel('ark:doubao-seed-2-1-pro-260915'), '豆包 Seed 2.1 Pro');
  eq(L.discussModelLabel('byok:self'), '我的模型');
  eq(L.discussModelLabel('other:model'), 'other:model');
});

// 文件自身的约束
check('只有 import type', () => {
  const imports = source.split('\n').filter(line => /^\s*import\b/.test(line));
  for (const line of imports) assert.ok(/^\s*import\s+type\b/.test(line), '不是 import type：' + line);
});
check('导出齐全', () => {
  for (const name of ['discussStatusLabel', 'discussStopHint', 'discussIsActive', 'discussNeedsAuthor',
    'discussActions', 'discussDefaultTab', 'discussKindLabel', 'mergeDiscussMessages', 'applyPendingNotes',
    'groupDiscussRounds', 'splitDiscussDocument', 'splitDiscussCitations', 'safeExternalUrl',
    'validateDiscussCreate', 'buildDiscussCreateBody', 'buildDiscussPlanPatch', 'discussPlanPatchIsEmpty',
    'discussErrorMessage', 'discussHref', 'discussModelLabel']) {
    eq(typeof L[name], 'function', name + ' 没有导出');
  }
});

process.stdout.write(JSON.stringify({ ran, failed }) + '\n');
process.exitCode = failed.length ? 1 : 0;
