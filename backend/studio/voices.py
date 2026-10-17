"""块 B 提供的音色目录（§10.3）。

只描述引擎与音色，不含任何密钥；`FX_PRESETS` 在 ``studio.audio`` 里，
`/voice-catalog` 同时返回两者（只给档位清单，不给滤镜字符串）。
"""
from __future__ import annotations


# CosyVoice v2 只服务中文；edge-tts 主要服务英文，附带两个中文备选。
# note 为「待核实」表示官方定位尚未逐条确认，不阻塞使用。
VOICE_CATALOG: list[dict] = [
    # 豆包语音 2.0 是中文项目的默认引擎；note 取控制台官方描述。
    {"engine": "doubao", "voice": "zh_female_vv_uranus_bigtts", "label": "Vivi 2.0",
     "lang": "zh", "gender": "female", "note": "语调平稳、咬字柔和、自带治愈安抚力"},
    {"engine": "doubao", "voice": "zh_female_xiaohe_uranus_bigtts", "label": "小何 2.0",
     "lang": "zh", "gender": "female", "note": "声线甜美有活力"},
    {"engine": "doubao", "voice": "zh_female_wenroumama_uranus_bigtts", "label": "温柔妈妈 2.0",
     "lang": "zh", "gender": "female", "note": "语调舒缓、咬字温润"},
    {"engine": "doubao", "voice": "zh_female_sophie_uranus_bigtts", "label": "魅力苏菲 2.0",
     "lang": "zh", "gender": "female", "note": "高冷御姐，外冷内柔（官方标注指令遵循）"},
    {"engine": "doubao", "voice": "zh_female_meilinvyou_uranus_bigtts", "label": "魅力女友 2.0",
     "lang": "zh", "gender": "female", "note": "成熟妩媚的御姐"},
    {"engine": "doubao", "voice": "zh_male_wennuanahu_uranus_bigtts", "label": "温暖阿虎 2.0",
     "lang": "zh", "gender": "male", "note": "阳光温暖的少年音"},
    {"engine": "doubao", "voice": "zh_male_jieshuoxiaoming_uranus_bigtts", "label": "解说小明 2.0",
     "lang": "zh", "gender": "male", "note": "明快、中气十足的解说男声"},
    {"engine": "doubao", "voice": "zh_male_liufei_uranus_bigtts", "label": "刘飞 2.0",
     "lang": "zh", "gender": "male", "note": "逻辑清晰、理性稳重"},
    {"engine": "doubao", "voice": "zh_male_shaonianzixin_uranus_bigtts", "label": "少年梓辛 2.0",
     "lang": "zh", "gender": "male", "note": "清爽少年感"},
    {"engine": "doubao", "voice": "zh_male_taocheng_uranus_bigtts", "label": "小天 2.0",
     "lang": "zh", "gender": "male", "note": "清澈温润的男大学生"},
    {"engine": "doubao", "voice": "zh_male_m191_uranus_bigtts", "label": "云舟 2.0",
     "lang": "zh", "gender": "male", "note": "磁性、成熟理性"},
    {"engine": "cosyvoice", "voice": "longxiaocheng_v2", "label": "龙小诚",
     "lang": "zh", "gender": "male", "note": "官方定位待核实"},
    {"engine": "cosyvoice", "voice": "longjielidou_v2", "label": "龙杰力豆",
     "lang": "zh", "gender": "male", "note": "官方定位待核实（偏少年/卡通）"},
    {"engine": "cosyvoice", "voice": "longze_v2", "label": "龙泽",
     "lang": "zh", "gender": "male", "note": "官方定位待核实"},
    {"engine": "cosyvoice", "voice": "longyuan_v2", "label": "龙媛",
     "lang": "zh", "gender": "female", "note": "官方定位待核实"},
    {"engine": "cosyvoice", "voice": "longfei_v2", "label": "龙飞",
     "lang": "zh", "gender": "male", "note": "官方定位待核实"},
    {"engine": "cosyvoice", "voice": "longshu_v2", "label": "龙书",
     "lang": "zh", "gender": "male", "note": "官方定位待核实"},
    {"engine": "cosyvoice", "voice": "longlaotie_v2", "label": "龙老铁",
     "lang": "zh", "gender": "male", "note": "官方定位待核实（东北口音）"},
    {"engine": "cosyvoice", "voice": "longjing_v2", "label": "龙婧",
     "lang": "zh", "gender": "female", "note": "官方定位待核实"},
    {"engine": "cosyvoice", "voice": "longxiaoxia_v2", "label": "龙小夏",
     "lang": "zh", "gender": "female", "note": "官方定位待核实"},
    {"engine": "edge-tts", "voice": "en-US-AndrewNeural", "label": "Andrew",
     "lang": "en", "gender": "male", "note": "美式英文，叙事男声（WO0 实测可用）"},
    {"engine": "edge-tts", "voice": "en-US-BrianNeural", "label": "Brian",
     "lang": "en", "gender": "male", "note": "美式英文，男声"},
    {"engine": "edge-tts", "voice": "en-US-ChristopherNeural", "label": "Christopher",
     "lang": "en", "gender": "male", "note": "美式英文，男声"},
    {"engine": "edge-tts", "voice": "en-US-AriaNeural", "label": "Aria",
     "lang": "en", "gender": "female", "note": "美式英文，女声"},
    {"engine": "edge-tts", "voice": "en-US-JennyNeural", "label": "Jenny",
     "lang": "en", "gender": "female", "note": "美式英文，女声"},
    {"engine": "edge-tts", "voice": "zh-CN-YunyangNeural", "label": "云扬",
     "lang": "zh", "gender": "male", "note": "中文备选，新闻播报男声"},
    {"engine": "edge-tts", "voice": "zh-CN-XiaoxiaoNeural", "label": "晓晓",
     "lang": "zh", "gender": "female", "note": "中文备选，女声"},
]


def voices_for(engine: str) -> list[dict]:
    """按引擎筛选音色；块 A 校验 ``voice`` 归属时复用。"""
    return [entry for entry in VOICE_CATALOG if entry["engine"] == engine]


def lookup_voice(engine: str, voice: str) -> dict | None:
    return next((entry for entry in VOICE_CATALOG
                 if entry["engine"] == engine and entry["voice"] == voice), None)
