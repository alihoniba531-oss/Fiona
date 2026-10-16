"""P2.1 UI contracts and dependency-free probes of the actual event handlers."""
import json
from pathlib import Path
import re
import shutil
import subprocess

import pytest

from novel.schemas import compact


ROOT = Path(__file__).resolve().parents[2]


def source(relative):
    return (ROOT / "frontend" / relative).read_text(encoding="utf-8")


def node(script):
    executable = shutil.which("node")
    if not executable:
        pytest.skip("Node is unavailable; UI source contracts still run")
    result = subprocess.run(
        [executable, "-e", script], cwd=ROOT, capture_output=True,
        text=True, check=False, timeout=15,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_adaptation_checkbox_copy_summary_and_workbench_tag():
    wizard = source("components/novel/NovelWizard.tsx")
    assert 'const [dramaAdaptation, setDramaAdaptation] = useState(false)' in wizard
    assert 'type="checkbox" checked={dramaAdaptation}' in wizard
    assert "这本书要改编成短剧" in wizard
    assert "勾选后会请短剧改编顾问参会；审校发现「场景太多、主要人物太多」这类不好拍的硬伤时，会要求重写。每章可能多花一些草莓。" in wizard
    assert "drama_adaptation: dramaAdaptation" in wizard
    assert '>改编短剧</dt><dd>{dramaAdaptation ? "是" : "否"}</dd>' in wizard
    assert '<details open={adaptationOpen} onToggle=' in wizard
    assert '<ErrorNotice message={adaptationAdvisorError}' in wizard
    workbench = source("components/novel/NovelWorkbench.tsx")
    assert 'book.config.drama_adaptation && <span className="tag">改编短剧</span>' in workbench
    assert "drama_adaptation?: boolean" in source("lib/novels.ts")


@pytest.mark.parametrize("enabled,advisors,already_selected", [
    (True, 3, False), (True, 5, False), (True, 5, True), (False, 3, True),
])
def test_adaptation_toggle_preserves_choices_and_respects_advisor_limit(enabled, advisors, already_selected):
    wizard = source("components/novel/NovelWizard.tsx")
    handler = re.search(r"const toggleDramaAdaptation = \(enabled: boolean\) => \{(.*?)\n  \};", wizard, re.S)
    assert handler
    agents = {role: "chosen" for role in ["editor", "writer", "archivist", "reviewer"]}
    agents.update({f"advisor-{n}": "chosen" for n in range(advisors - int(already_selected))})
    if already_selected:
        agents["adaptation_advisor"] = "user-selected-model"
    result = node(
        "let agents=" + json.dumps(agents) + ";const catalog={};"
        "let checked=null,open=false,error='';"
        "const setDramaAdaptation=x=>checked=x,setAdaptationOpen=x=>open=x,"
        "setAdaptationAdvisorError=x=>error=x,setAgents=fn=>agents=fn(agents);"
        "const novelModelOptions=()=>[{value:'first-option'},{value:'second-option'}];"
        "const toggle=enabled=>{" + handler[1] + "};toggle(" + json.dumps(enabled) + ");"
        "process.stdout.write(JSON.stringify({agents,checked,open,error}));"
    )
    assert result["checked"] is enabled
    assert result["open"] is enabled
    if not enabled or already_selected:
        assert result["agents"] == agents
        assert result["error"] == ""
    elif advisors == 5:
        assert result["agents"] == agents
        assert result["error"] == "顾问已满 5 位，先取消一位才能加入短剧改编顾问"
    else:
        assert result["agents"] == {**agents, "adaptation_advisor": "first-option"}


def test_character_editing_is_local_and_only_available_in_permitted_states():
    panel = source("components/novel/BiblePanel.tsx")
    states = re.search(r"const editableStatuses: NovelStatus\[\] = \[(.*?)\];", panel)
    assert states
    assert re.findall(r'"([^"]+)"', states[1]) == [
        "awaiting_review", "awaiting_plan", "awaiting_end", "paused", "completed",
    ]
    assert "editable={editableStatuses.includes(status)}" in panel
    assert 'editable && !draft && <button' in panel and ">修改</button>" in panel
    assert "外形未写全，改编时需要补" in panel
    assert "appearanceLength(text(character.appearance)) < 20" in panel
    for label in ("外形", "性格", "动机"):
        assert f'label: "{label}"' in panel
    assert "appearanceLength(draft.appearance)" in panel
    assert '<ErrorNotice message={error}' in panel
    assert "min-h-10" in panel and "novelFieldClass" in panel
    assert "text-[16px]" in source("components/novel/NovelModelFields.tsx")


@pytest.mark.parametrize("appearance", [
    "", "短发", "长发高挑身穿深蓝色棉布长衫腰间系着旧皮带", "😀" * 20,
    '“短发” ‘瘦高’「灰衣」『布鞋』"疤痕"\'耳环\' ………...…',
    "甲\x1c乙\x85丙\ufeff丁\u3000戊\t己\n庚",
])
def test_character_appearance_count_matches_backend_compact(appearance):
    panel = source("components/novel/BiblePanel.tsx")
    expression = re.search(r"const appearanceLength = \(appearance: string\) => (.*);", panel)
    assert expression
    result = node(
        "const count=appearance=>" + expression[1] + ";"
        "process.stdout.write(JSON.stringify(count(" + json.dumps(appearance) + ")));"
    )
    assert result == len(compact(appearance))


@pytest.mark.parametrize("changes,expected,error", [
    ({"appearance": "长发高挑身穿深蓝色棉布长衫腰间系着旧皮带"}, {"appearance": "长发高挑身穿深蓝色棉布长衫腰间系着旧皮带"}, None),
    ({"personality": "谨慎"}, {"personality": "谨慎"}, None),
    ({"motivation": "找回家书"}, {"motivation": "找回家书"}, None),
    ({}, None, None),
    ({"appearance": "短衣"}, None, "外形至少写 20 个字"),
    ({"personality": "  "}, None, None),
    ({"motivation": "\n"}, None, None),
])
def test_character_patch_validates_only_fields_the_user_changes(changes, expected, error):
    panel = source("components/novel/BiblePanel.tsx")
    handler = re.search(r"const save = async \(\) => \{(.*?)\n  \};\n  return <section", panel, re.S)
    assert handler
    body = handler[1].replace("const patch: NovelCharacterEdit", "const patch").replace("] as const", "]")
    expression = re.search(r"const appearanceLength = \(appearance: string\) => (.*);", panel)
    submit = re.search(r'<form\b[^>]*onSubmit=\{event => \{(.*?)\}\}>', panel)
    notice = re.search(r'\{notice && (<p role="status"[^>]*>\{notice\}</p>)\}', panel)
    assert submit and notice
    character = {"id": "c1", "appearance": "短发", "personality": "", "motivation": ""}
    draft = {field: character[field] for field in ("appearance", "personality", "motivation")}
    draft.update(changes)
    result = node(
        "const character=" + json.dumps(character) + ";let draft=" + json.dumps(draft) + ";"
        "let error='',saving=false,saved=null,notice='',calls=0,prevented=false;const busy=false,id='c1';"
        "const text=x=>typeof x==='string'?x:'',setError=x=>error=x,setSaving=x=>saving=x,setDraft=x=>draft=x,setNotice=x=>notice=x;"
        "const appearanceLength=appearance=>" + expression[1] + ";"
        "const onSave=async(id,patch)=>{calls++;saved={id,patch};return true;},novelErrorMessage=e=>e.message;"
        "const save=async()=>{" + body + "},submit=event=>{" + submit[1] + "};"
        "submit({preventDefault:()=>prevented=true});"
        # Render the actual conditional JSX paragraph after the real submit
        # handler's promises settle, without importing a frontend package.
        "setImmediate(()=>{const notice_markup=notice?" + json.dumps(notice[1]) + ".replace('{notice}',notice):null;"
        "process.stdout.write(JSON.stringify({saved,error,draft,notice,calls,prevented,notice_markup}));});"
    )
    assert result["saved"] == ({"id": "c1", "patch": expected} if expected else None)
    assert result["error"] == (error or "")
    if not error:
        assert result["draft"] is None
    if changes in ({"personality": "  "}, {"motivation": "\n"}):
        assert result["error"] == ""
        assert result["saved"] is None
        assert result["calls"] == 0
        assert result["prevented"] is True
        assert result["notice"] == "没有改动"
        assert result["notice_markup"] == '<p role="status" className="text-[13px] text-[var(--ink2)]">没有改动</p>'


def test_character_api_returns_full_bible_and_workbench_cancels_old_reads():
    api = source("lib/novels.ts")
    update = re.search(r"export const updateNovelCharacter = (.*);", api)
    assert update and 'apiJson<NovelBible>' in update[1]
    assert 'bookPath(id) + "/characters/" + encodeURIComponent(characterId)' in update[1]
    assert 'json("PATCH", input, signal)' in update[1]
    workbench = source("components/novel/NovelWorkbench.tsx")
    save = workbench.split("const saveCharacter =", 1)[1].split("const currentChapter", 1)[0]
    for contract in ('mutate("character"', 'errorTarget: "local"', "isCurrentOwner()", "beginBible()", "bibleVersion.current = result.version", "setBible(result)"):
        assert contract in save
    assert "status={book.status} busy={!!busy} onSaveCharacter={saveCharacter}" in workbench


def test_character_save_conflict_stays_visible_when_book_resumes_running():
    panel = source("components/novel/BiblePanel.tsx")
    # The refreshed running status hides the form and its edit button, while the
    # same character card must still display the operation's local error.
    form = panel.split("{editable && draft ? <form", 1)[1].split("</form>", 1)[0]
    assert "ErrorNotice" not in form
    assert re.search(r"</form> : <ContentValue[^\n]+\n\s*\{error && <ErrorNotice message=\{error\} />\}", panel)
    assert "if (loading && !bible) return <LoadingState>" in panel
    assert "{loading && <LoadingState>正在加载完整圣经…</LoadingState>}" in panel
    assert "if (loading) return" not in panel
    handler = re.search(r"const save = async \(\) => \{(.*?)\n  \};\n  return <section", panel, re.S)
    assert handler
    body = handler[1].replace("const patch: NovelCharacterEdit", "const patch").replace("] as const", "]")
    result = node(
        "const character={appearance:'短发',personality:'',motivation:''},draft={...character,personality:'谨慎'};"
        "let editable=true,error='',saving=false;const busy=false,id='c1';"
        "const text=x=>typeof x==='string'?x:'',setError=x=>error=x,setSaving=x=>saving=x,setDraft=()=>{};"
        "const onSave=async()=>{editable=false;throw Error('书正在运行，请先暂停再改人物');},novelErrorMessage=e=>e.message;"
        "const save=async()=>{" + body + "};"
        "save().then(()=>process.stdout.write(JSON.stringify({editable,error,saving})));"
    )
    assert result == {"editable": False, "error": "书正在运行，请先暂停再改人物", "saving": False}
