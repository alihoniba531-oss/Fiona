"""R1 frontend regressions; all source comes from this checkout, without packages."""
import json
from pathlib import Path
import re
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]


def source(component):
    return (ROOT / "frontend/components/novel" / component).read_text(encoding="utf-8")


def node(script):
    executable = shutil.which("node")
    if not executable:
        pytest.skip("Node is unavailable; source-only contracts still run")
    result = subprocess.run(
        [executable, "-e", script], cwd=ROOT, capture_output=True,
        text=True, check=False, timeout=15,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.mark.parametrize("mode,expected", [
    ("solo", "主编独自构思时不请顾问参会；审校仍会按「场景太多、主要人物太多」这类硬伤要求重写。"),
    ("critique", "勾选后会请短剧改编顾问参会；审校发现「场景太多、主要人物太多」这类不好拍的硬伤时，会要求重写。每章可能多花一些草莓。"),
])
def test_adaptation_help_describes_the_selected_deliberation_mode(mode, expected):
    wizard = source("NovelWizard.tsx")
    help_text = re.search(r'id="novel-drama-help"[^>]*>\{(panelMode === "solo" \? "[^"]+" : "[^"]+")\}</p>', wizard)
    assert help_text
    assert node(
        "const panelMode=" + json.dumps(mode) + ";process.stdout.write(JSON.stringify("
        + help_text[1] + "));"
    ) == expected


def test_character_draft_is_discarded_when_editability_changes_and_does_not_return():
    panel = source("BiblePanel.tsx")
    assert "const [previousEditable, setPreviousEditable] = useState(editable)" in panel
    transition = re.search(r"if \(previousEditable !== editable\) \{(.*?)\n  \}", panel, re.S)
    assert transition
    assert "setError" not in transition[1]  # Keep a late 409 visible on the same card.
    assert node(
        "let previousEditable=true,editable=false,draft={appearance:'未保存的人物外形'};"
        "const setPreviousEditable=x=>previousEditable=x,setDraft=x=>draft=x;"
        "const render=()=>{if(previousEditable!==editable){" + transition[1] + "}};"
        "render();editable=true;render();"
        "process.stdout.write(JSON.stringify({draft,previousEditable}));"
    ) == {"draft": None, "previousEditable": True}


def save_probe(character, draft):
    panel = source("BiblePanel.tsx")
    handler = re.search(r"const save = async \(\) => \{(.*?)\n  \};\n  return <section", panel, re.S)
    assert handler
    body = handler[1].replace("const patch: NovelCharacterEdit", "const patch").replace("] as const", "]")
    count = re.search(r"const appearanceLength = \(appearance: string\) => (.*);", panel)
    assert count
    return node(
        "const character=" + json.dumps(character) + ";let draft=" + json.dumps(draft) + ";"
        "let error='',saving=false,saved=null;const busy=false,id='c1';"
        "const text=x=>typeof x==='string'?x:'',setError=x=>error=x,setSaving=x=>saving=x,setDraft=x=>draft=x;"
        "const appearanceLength=appearance=>" + count[1] + ";"
        "const onSave=async(id,patch)=>{saved={id,patch};return true;},novelErrorMessage=e=>e.message;"
        "const save=async()=>{" + body + "};"
        "save().then(message=>process.stdout.write(JSON.stringify({saved,error,draft,message:message??null})));"
    )


@pytest.mark.parametrize("field", ["appearance", "personality", "motivation"])
def test_whitespace_only_changes_send_no_patch_and_report_no_change(field):
    character = {"appearance": "短发", "personality": " 谨慎 ", "motivation": " 保护家人 "}
    draft = dict(character)
    draft[field] = "\t" + character[field].strip() + "\n"
    assert save_probe(character, draft) == {
        "saved": None, "error": "", "draft": None, "message": "没有改动",
    }


@pytest.mark.parametrize("field", ["personality", "motivation"])
def test_existing_empty_fields_remain_unchanged_after_whitespace_input(field):
    character = {"appearance": "短发", "personality": "", "motivation": ""}
    draft = {**character, field: " \n "}
    assert save_probe(character, draft) == {
        "saved": None, "error": "", "draft": None, "message": "没有改动",
    }


def test_no_change_message_is_shown_beside_the_character_card():
    panel = source("BiblePanel.tsx")
    assert 'return "没有改动"' in panel
    assert "void save().then(message => { if (message) setNotice(message); })" in panel
    assert re.search(r'\{notice && <p role="status"[^>]*>\{notice\}</p>\}', panel)


def test_real_changes_patch_only_the_trimmed_changed_field():
    character = {"appearance": "短发", "personality": " 谨慎 ", "motivation": " 保护家人 "}
    draft = {**character, "personality": " 稳重 "}
    assert save_probe(character, draft) == {
        "saved": {"id": "c1", "patch": {"personality": "稳重"}},
        "error": "", "draft": None, "message": None,
    }


def test_current_state_hides_unknown_keys_and_uses_the_existing_chinese_labels():
    panel = source("BiblePanel.tsx")
    expression = re.search(r"const visibleState = (.*);", panel)
    assert expression
    state = {
        "location": "车站", "condition": "疲惫", "knows": ["信已寄出"], "relationships": {"C2": "同伴"},
        "last_seen_chapter": 3, "future_provider_key": "不应呈现的未知字段", "internal_counter": 7,
    }
    assert node(
        "const currentState=" + json.dumps(state) + ";const before=JSON.stringify(currentState);"
        "const visible=" + expression[1] + ";"
        "process.stdout.write(JSON.stringify({visible,unchanged:before===JSON.stringify(currentState)}));"
    ) == {
        "visible": {key: state[key] for key in ("location", "condition", "knows", "relationships")},
        "unchanged": True,
    }
    labels = source("NovelContent.tsx")
    for field, label in (("location", "地点"), ("condition", "状态"), ("knows", "已知信息"), ("relationships", "人物关系")):
        assert f'{field}: "{label}"' in labels
    assert "value={Object.keys(visibleState).length ? visibleState : null}" in panel
    assert "<ContentValue value={state}" not in panel
    assert "最近出场：第" in panel
    assert "{text(currentState.last_seen_chapter)}" in panel
