"""Page-level contracts for the 2026-10-26 UI polish (T4, T7, T9).

The source-only assertions run everywhere.  The ``modelDisplayName`` mapping is
executed with Node + the frontend's TypeScript compiler when available and is
skipped gracefully in CI clones without ``node_modules``.
"""

import json
import re
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "frontend/app/page.tsx"
GLOBALS = ROOT / "frontend/app/globals.css"
CHAT_MODEL = ROOT / "frontend/lib/chatModel.ts"

DRAWER_IDS = ("agent", "exchange", "plaza", "settings", "novel", "studio")


def balanced_block(source, marker, start=0):
    """Return the marker and the balanced ``{...}`` block that follows it."""
    begin = source.index(marker, start)
    opening = source.index("{", begin)
    depth = 0
    for index in range(opening, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[begin : index + 1]
    raise AssertionError(f"Unclosed block after {marker}")


def test_page_merges_image_and_voice_controls():
    source = PAGE.read_text()
    assert 'title="语音转文字"' not in source
    assert 'aria-label="按住说话"' not in source
    assert ">上传参考图<" not in source
    assert "<ComposerImageMenu" in source
    assert source.count("<ComposerImageMenu") == 1
    assert "<VoiceButton" in source
    assert source.count("<VoiceButton") == 1
    # The removed standalone icon buttons must not survive.
    assert "<ImagePlus" not in source
    assert "<Mic" not in source
    assert "onClick={() => setImageMode(true)}" not in source
    # Both hidden file inputs stay; the menu drives them.
    assert source.count('type="file"') == 2


def test_composer_image_menu_items_match_the_spec():
    source = PAGE.read_text()
    for fragment in (
        "active={imageMode || hasReferenceImages}",
        'key: "see"',
        'key: "generate"',
        'key: "edit"',
        "发图给 Chloe 看",
        "Chloe 看图后回答",
        "用文字描述画一张新图",
        "改一张图",
        "上传 1–3 张参考图，再说明怎么改",
        "onSelect: () => fileInputRef.current?.click()",
        "onSelect: () => referenceFileInputRef.current?.click()",
        "onSelect: () => setImageMode(true)",
    ):
        assert fragment in source
    # Generate mode stays disabled while image/edit mode is already active.
    assert "|| imageMode || hasReferenceImages," in source
    # The mode chips, groups and exits are preserved.
    for fragment in (
        '<span className="chip chip-on"><PencilLine size={12} />修改图片</span>',
        '<span className="chip chip-on">生成图片</span>',
        'role="group" aria-label="图片比例"',
        "{hasReferenceImages ? (",
        'className="composer-mode-exit ml-auto',
        "先移除待发送图片，即可切换生成模式",
    ):
        assert fragment in source


def test_voice_button_props_preserve_recording_logic():
    source = PAGE.read_text()
    for fragment in (
        "disabled={conversationLoading || !currentConversation || isLoading}",
        "dictating={inlineRecording}",
        "holding={recording}",
        "onTap={toggleInlineVoice}",
        "onHoldStart={() => setRecording(true)}",
        "onHoldEnd={() => { asrSessionRef.current += 1; setRecording(false); }}",
        "const toggleInlineVoice = useCallback(async () => {",
        "window.addEventListener(\"mouseup\", up)",
        "window.addEventListener(\"touchend\", up)",
    ):
        assert fragment in source


def test_page_drawers_append_drawer_panel_exactly_six_times():
    source = PAGE.read_text()
    assert source.count("drawer-panel") == 6
    for drawer in DRAWER_IDS:
        match = re.search(
            rf'id="{drawer}-drawer"([\s\S]{{0,800}}?)className="([^"]*)"', source
        )
        assert match, f"missing Glaze for {drawer}-drawer"
        assert "drawer-panel" in match.group(2).split(), drawer
    assert source.index('id="agent-drawer"') < source.index('id="exchange-drawer"')
    assert source.index('id="exchange-drawer"') < source.index('id="plaza-drawer"')
    assert source.index('id="plaza-drawer"') < source.index('id="settings-drawer"')
    assert source.index('id="settings-drawer"') < source.index('id="novel-drawer"')
    assert source.index('id="novel-drawer"') < source.index('id="studio-drawer"')


def test_globals_css_smooths_drawer_materials_on_mobile_only():
    css = GLOBALS.read_text()
    assert ".drawer-panel" in css
    first = css.index(".drawer-panel")
    media_start = css.rindex("@media (width < 48rem)", 0, first)
    block = balanced_block(css, "@media (width < 48rem)", media_start)
    assert ":root:not([data-shell=desktop])" in block
    assert ":root:not([data-shell=desktop]) .drawer-panel > .glaze-blur" in block
    assert ":root:not([data-shell=desktop]) .drawer-panel > .glaze-tint" in block
    assert "-webkit-mask-image:none" in block
    assert "mask-image:none" in block
    assert ".drawer-panel > .glaze-lens { display:none; }" in block
    assert "background:var(--glass2)" in block
    # The overrides live in the mobile media query only; the desktop shell is
    # deliberately not targeted.
    assert ":root[data-shell=desktop] .drawer-panel" not in block


def test_page_uses_beijing_time_helpers_only():
    source = PAGE.read_text()
    assert "const key = formatBeijingDateLong(m.timestamp);" in source
    assert "formatBeijingDateTime(msg.timestamp)" in source
    assert (
        "beijingDateKey(msg.timestamp) !== beijingDateKey(messages[index - 1].timestamp)"
        in source
    )
    assert not re.search(
        r"toLocale(Date|Time)?String|toDateString\(", source
    ), "page.tsx must not format dates with device-local helpers"
    assert not re.search(
        r"\.get(Hours|Minutes|Date|Day|Month|FullYear)\(", source
    ), "page.tsx must not read device-local date fields"


def test_chat_model_footer_label_and_layout():
    page = PAGE.read_text()
    model = CHAT_MODEL.read_text()
    assert "export function modelDisplayName(id: string): string" in model
    assert "claude-(opus|sonnet|haiku)-" in model
    for mapping in ('"DeepSeek V4 Pro"', '"DeepSeek Flash"'):
        assert f"return {mapping};" in model
    assert "`${modelDisplayName(config.model)} · 不扣草莓`" in page
    assert (
        "`聊天：${provider?.name ?? config.provider} · ${config.model}（自带 Key，不扣草莓）`"
        in page
    )
    assert '"平台模型 · 每条 10 颗草莓"' in page
    assert "title={labelTitle}" in page
    assert "min-w-0 truncate" in page
    assert "break-all xl:truncate" not in page
    assert "改用平台" in page
    assert "改用我的模型" in page
    # The effort radiogroup and the switch stay in the same row as the label.
    assert "flex min-w-0 max-w-full items-center justify-end" in page
    assert "max-md:w-full max-md:items-start" in page


def test_page_readout_numbers_are_not_bold():
    source = PAGE.read_text()
    assert source.count('className="readout font-normal"') == 2
    assert not re.search(r"<b[ >]|</b>", source)


def test_globals_css_mobile_composer_rows():
    css = GLOBALS.read_text()
    assert 'grid-template-areas:"text text" "tools actions"' in css
    assert 'grid-template-areas:"text text" "tools tools" "models models" "exit actions"' in css
    assert ".composer-tools { grid-area:tools; }" in css
    assert ".composer-mode-exit { grid-area:exit; justify-self:start; }" in css
    assert ".composer-actions { grid-area:actions; justify-self:end; }" in css
    # Clickable mobile targets keep their 40px floor.
    assert "min-height:40px; min-width:40px;" in css


def test_page_keeps_protected_stream_and_poller_literals():
    source = PAGE.read_text()
    for fragment in (
        "interface ChatStreamEvent {",
        "if (data.text) {\n            reply += data.text;",
        "if (data.card && data.append === true)",
        "const requestImageModel = imageModel;",
        "image_model: requestImageModel,",
        "createLocalWatchPoller",
        "10_000",
        'document.visibilityState === "visible"',
        "studioAllowed ? <iframe",
        "key={username}",
        'src="/studio?embed=1"',
    ):
        assert fragment in source


def require_node_typescript():
    probe = """
try {
  require.resolve('typescript', {paths: [process.argv[1]]});
  process.stdout.write('ok');
} catch {
  process.stdout.write('missing');
}
"""
    try:
        result = subprocess.run(
            ["node", "-e", probe, str(ROOT / "frontend")],
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError:
        pytest.skip("modelDisplayName execution requires Node.js; source contracts still run")
    if result.stdout.strip() != "ok":
        pytest.skip("typescript is unavailable in frontend/node_modules")


def test_model_display_name_mapping_executes():
    require_node_typescript()
    runner = r"""
const fs = require('fs');
const ts = require('typescript');
const source = fs.readFileSync(process.argv[1], 'utf8');
const output = ts.transpileModule(source, {
  compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020},
}).outputText;
const module = {exports: {}};
const fakeRequire = name => name === '@/lib/auth'
  ? {apiFetch: () => { throw new Error('network is not used'); }}
  : name === '@/lib/config' ? {API_BASE: ''} : require(name);
new Function('require', 'module', 'exports', output)(fakeRequire, module, module.exports);
const {modelDisplayName} = module.exports;
const cases = [
  ['claude-haiku-5-5', 'Claude Haiku 5.5'],
  ['claude-opus-5-5', 'Claude Opus 5.5'],
  ['claude-sonnet-4-6', 'Claude Sonnet 4.6'],
  ['deepseek-v4-pro', 'DeepSeek V4 Pro'],
  ['deepseek-flash', 'DeepSeek Flash'],
  ['qwen3.8-max', 'qwen3.8-max'],
  ['', ''],
];
for (const [input, expected] of cases) {
  const actual = modelDisplayName(input);
  if (actual !== expected) {
    throw new Error(`${JSON.stringify(input)}: ${JSON.stringify(actual)} !== ${JSON.stringify(expected)}`);
  }
}
process.stdout.write(JSON.stringify(cases.map(([input]) => [input, modelDisplayName(input)])));
"""
    result = subprocess.run(
        ["node", "-e", runner, str(CHAT_MODEL)],
        cwd=ROOT / "frontend",
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    assert json.loads(result.stdout)[0] == ["claude-haiku-5-5", "Claude Haiku 5.5"]
