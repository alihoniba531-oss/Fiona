"""Traditional Chinese crisis routing without changing the original message."""

import asyncio
import ast
from pathlib import Path

import pytest

from _fakes import FakeStream
import safety
from utils.traditional_chinese import normalize_traditional


# This independent list covers only characters found in safety.py literals.
# Do not derive it from the production map: new rule characters must be reviewed.
RULE_CHARACTER_VARIANTS = {
    "了": "瞭", "业": "業", "个": "個", "么": "麼麽", "你": "妳", "义": "義",
    "书": "書", "买": "買", "价": "價", "会": "會", "伤": "傷", "伞": "傘", "优": "優",
    "它": "牠", "吃": "喫", "吊": "弔", "写": "寫", "准": "準", "划": "劃",
    "别": "別", "劝": "勸", "务": "務", "劲": "勁", "卖": "賣", "只": "隻", "励": "勵",
    "吓": "嚇", "困": "睏", "备": "備", "妈": "媽", "学": "學", "实": "實実",
    "对": "對対", "帮": "幫", "干": "幹", "并": "並併", "恋": "戀", "户": "戶",
    "报": "報", "据": "據", "搜": "蒐", "撑": "撐", "攒": "攢", "才": "纔",
    "图": "圖", "声": "聲", "处": "處", "寻": "尋", "应": "應", "当": "當",
    "数": "數", "断": "斷", "无": "無", "机": "機", "杀": "殺", "样": "樣",
    "桥": "橋", "楼": "樓", "残": "殘", "气": "氣気", "没": "沒", "热": "熱",
    "环": "環", "现": "現", "点": "點", "着": "著", "种": "種", "绳": "繩縄",
    "结": "結", "绝": "絕絶", "药": "藥葯薬", "营": "營", "虑": "慮", "计": "計",
    "记": "記", "论": "論", "请": "請", "这": "這", "遗": "遺", "让": "讓譲",
    "远": "遠", "里": "裡裏", "销": "銷", "问": "問", "闻": "聞", "队": "隊",
    "预": "預", "项": "項", "顶": "頂", "题": "題", "饿": "餓", "轻": "輕軽",
    "说": "說", "复": "復複", "国": "國", "拨": "撥", "温": "溫", "真": "眞",
    "简": "簡", "系": "係繫", "紧": "緊", "级": "級", "线": "線", "联": "聯",
    "认": "認", "评": "評", "询": "詢", "语": "語", "诺": "諾", "轮": "輪",
    "边": "邊", "达": "達", "镜": "鏡", "险": "險",
}

# Rule characters without a traditional/alternate form used by this classifier.
# This is intentionally a literal whitelist, independent of safety.py and of
# RULE_CHARACTER_VARIANTS, so any newly added Chinese rule character fails review.
NO_VARIANT_RULE_CHARACTERS = frozenset(
    "一上下不中主也事人什他以任伴何作保信停像先光全再切判到割助半危即去友反受可同吞否吧命和哈哥哪回在地多大天她好如妹姐子孩安完室害家密小少就工巧己式弟很得循心必忙快怎思急想意感我或所打扛承技把持挑接援支救教整文新方明是普暖最有朋服本束果某查根槽止正死永求江河法活海爸理瓶生甩由疼痛的目直看眠短研硬磕究窗立笑算累考者聊背能腕自致舞表要解象趣跳身逗通道那部都醒重防陪需高鼓"
)


@pytest.mark.parametrize("message", [
    "我想自殺",
    "我想了解怎麼自殺最快",
    "吃了一整瓶安眠藥",
    "剛吞了半瓶安眠藥",
    "我想跳樓",
    "我想結束這一切",
    "我想結束自己的生命",
    "我已經寫好遺書了",
    "我想寫遺書然後自殺",
    "哪種安眠藥吃了不會醒",
    "我想從樓上跳下去",
    "我媽媽走了我也不想活了",
    "活著沒意思，不如死了",
    "我在考慮結束生命",
    "我打算結束這一切了",
])
def test_traditional_explicit_risk_is_high(message):
    assert safety.assess_crisis(message) == "high"


@pytest.mark.parametrize("message", [
    "晚安，永別了",
    "活著沒意思",
    "剛吞了好多藥",
    "我真的撐不下去了",
    "他說他不想活了，我該怎麼勸",
    "幫我查下割腕的急救方法",
])
def test_traditional_related_talk_is_possible(message):
    assert safety.assess_crisis(message) == "possible"


@pytest.mark.parametrize("message", [
    "我睏得要死",
    "我要死磕這個bug",
    "《自殺小隊》好看嗎",
    "笑死我了",
    "會議結束一切按計劃推進",
    "疫情現在結束一切恢復正常",
    "我想跳槽到大廠",
])
def test_traditional_everyday_talk_is_not_crisis(message):
    assert safety.assess_crisis(message) is None


def test_crisis_rule_character_variants_normalize_back_to_rule_characters():
    """Account for every safety literal character, including inline regexes."""
    source = Path(safety.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    rule_characters = {
        char for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
        for char in node.value if "\u4e00" <= char <= "\u9fff"
    }
    oracle_characters = set(RULE_CHARACTER_VARIANTS) | NO_VARIANT_RULE_CHARACTERS
    assert not set(RULE_CHARACTER_VARIANTS) & NO_VARIANT_RULE_CHARACTERS
    assert rule_characters == oracle_characters, (
        f"unlisted rule chars: {''.join(sorted(rule_characters - oracle_characters)) or 'none'}; "
        f"oracle chars absent from rules: {''.join(sorted(oracle_characters - rule_characters)) or 'none'}"
    )
    for simplified, variants in RULE_CHARACTER_VARIANTS.items():
        for variant in variants:
            assert normalize_traditional(variant) == simplified, (simplified, variant)


@pytest.mark.parametrize("traditional,simplified", [
    ("殺", "杀"), ("輕", "轻"), ("樓", "楼"), ("結", "结"),
    ("遺", "遗"), ("書", "书"), ("藥", "药"), ("別", "别"),
    ("麼", "么"), ("麽", "么"), ("這", "这"), ("會", "会"),
    ("經", "经"), ("剛", "刚"), ("睏", "困"), ("著", "着"),
    ("撐", "撑"), ("說", "说"), ("該", "该"), ("勸", "劝"),
    ("幫", "帮"), ("種", "种"), ("從", "从"), ("嗎", "吗"),
    ("媽", "妈"), ("還", "还"), ("準", "准"), ("備", "备"),
    ("覺", "觉"), ("慮", "虑"), ("劃", "划"), ("後", "后"),
    ("裡", "里"), ("裏", "里"), ("為", "为"), ("爲", "为"),
    ("讓", "让"), ("傘", "伞"), ("繩", "绳"), ("遠", "远"),
    ("葯", "药"), ("喫", "吃"), ("瞭", "了"), ("纔", "才"),
    ("弔", "吊"), ("妳", "你"), ("牠", "它"),
    ("薬", "药"), ("譲", "让"), ("縄", "绳"), ("気", "气"),
    ("軽", "轻"), ("対", "对"), ("実", "实"), ("絶", "绝"),
    ("眞", "真"),
])
def test_specified_traditional_variants_are_mapped(traditional, simplified):
    assert normalize_traditional(traditional) == simplified


@pytest.mark.parametrize("traditional,simplified,level", [
    ("吃了一整瓶安眠葯", "吃了一整瓶安眠药", "high"),
    ("剛吞了好多葯", "刚吞了好多药", "possible"),
    ("喫了一整瓶安眠藥", "吃了一整瓶安眠药", "high"),
    ("讓我去死吧哈哈哈", "让我去死吧哈哈哈", "possible"),
    ("他說想跳樓，我想跳傘散心", "他说想跳楼，我想跳伞散心", "possible"),
    ("他說想跳樓，我想跳繩散心", "他说想跳楼，我想跳绳散心", "possible"),
    ("他說想跳樓，我想跳遠散心", "他说想跳楼，我想跳远散心", "possible"),
    ("我想瞭解自殺的預防方法", "我想了解自杀的预防方法", "possible"),
])
def test_traditional_variants_match_simplified_crisis_level(traditional, simplified, level):
    assert safety.assess_crisis(simplified) == level
    assert safety.assess_crisis(traditional) == level


@pytest.mark.parametrize("message,expected", [
    ("計畫下週跳樓", "possible"),
    ("我想死妳", None),
])
def test_word_level_plan_and_second_person_variant(message, expected):
    assert safety.assess_crisis(message) == expected


@pytest.mark.parametrize("variant,expected", [
    ("計畫", "计畫"),
    ("計画", "计画"),
    ("计畫", "计畫"),
    ("计画", "计画"),
])
def test_plan_word_does_not_cross_word_boundaries(variant, expected):
    assert normalize_traditional(variant) == expected


@pytest.mark.parametrize("message,expected", [
    ("游戏设计画面里加一段跳海的动画", None),
    ("我在做设计画面，主角最后跳河", None),
    ("这部片的设计画面有自杀镜头", "possible"),
    ("统计画面显示上吊人数", "possible"),
    ("遊戲設計畫面裡加一段跳海的動畫", None),
    ("電影設計畫面有自殺鏡頭", "possible"),
])
def test_design_frame_mentions_keep_baseline_crisis_level(message, expected):
    assert safety.assess_crisis(message) == expected


def test_crisis_normalization_keeps_original_message_available():
    message = "我已經寫好遺書了"
    assert normalize_traditional(message) == "我已经写好遗书了"
    assert safety.assess_crisis(message) == "high"
    assert message == "我已經寫好遺書了"


def test_traditional_crisis_chat_persists_and_sends_original(client, dev_headers, monkeypatch):
    import database
    import services.chat_service as chat

    original = "我已經寫好遺書了"
    seen_model_messages = []

    def capture_model_input(use_qwen, messages, **kwargs):
        seen_model_messages.extend(messages)
        return FakeStream(), False

    monkeypatch.setattr(chat, "_create_stream_with_fallback", capture_model_input)
    response = client.post("/conversations", json={}, headers=dev_headers)
    assert response.status_code in (200, 201)
    conversation_id = response.json()["conversation"]["id"]
    response = client.post("/chat", headers=dev_headers, json={
        "conversation_id": conversation_id,
        "message": original,
    })
    assert response.status_code == 200
    assert '"crisis": true' in response.text
    assert any(entry["role"] == "user" and entry["content"] == original
               for entry in seen_model_messages)
    history = asyncio.run(database.get_messages(
        dev_headers["X-Dev-User"], conversation_id=conversation_id,
    ))
    assert any(entry["role"] == "user" and entry["content"] == original
               for entry in history)
