"""块 B 提供的音色目录（§10.3）。

只描述引擎与音色，不含任何密钥；`FX_PRESETS` 在 ``studio.audio`` 里，
`/voice-catalog` 同时返回两者（只给档位清单，不给滤镜字符串）。
"""
from __future__ import annotations


# CosyVoice v2 只服务中文；edge-tts 主要服务英文，附带两个中文备选。
# note 为「待核实」表示官方定位尚未逐条确认，不阻塞使用。
VOICE_CATALOG: list[dict] = [
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
