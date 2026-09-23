"""Small, deterministic crisis gate for the current private chat turn.

This is deliberately a conservative phrase detector rather than a diagnosis.
It is used to choose the support path and never logs the matched text.
"""

import re


CRISIS_GUIDANCE = """

【本轮危机支持：最高优先级】
对方本轮可能表达了自伤或自杀意图。立即停止打趣、挑逗、镜像语气、反问技巧和普通陪聊。
先认真、温和地回应对方的感受，再轻声询问对方现在是否安全。
鼓励对方立即联系当地紧急服务或身边信任的人，寻求当下的陪伴和帮助。
不评判、不说教，也不承诺保密。回复简短、温暖、直接。
"""

CRISIS_RESOURCE_NOTE = (
    "如果你现在有伤害自己的想法，或者正处在危险中，请立即拨打 120 或 110；"
    "也可以拨打全国心理援助热线 12356，或联系身边信任的人。你不必一个人扛着。"
)


_CRISIS_PATTERNS = tuple(re.compile(pattern) for pattern in (
    # Chinese: require intent or a sufficiently specific method, so everyday
    # expressions such as 笑死了、死机 and 死磕 do not trigger the gate.
    r"(?<![得快都])(?:我|自己|本人).{0,8}(?:想死(?![你他她它])|要死(?!了|[你他她它])|去死(?![记你他她它])|不想活(?!得)|活不下去)",
    r"(?:不想活|不想再活|活着没意思|活不下去)(?!得)",
    r"(?:自杀|轻生|结束自己(?:的)?生命|结束我(?:的)?生命)",
    r"(?:自残|自伤|伤害(?:我)?自己|割(?:了)?(?:我)?自己|了结(?:我)?自己|杀了(?:我)?自己|把(?:我)?自己杀了)",
    r"(?:我|自己|本人|想|要|准备|打算).{0,6}(?:跳河|跳江|跳海)",
    r"(?:想|要|准备|打算|计划|考虑).{0,6}(?:割腕|跳楼(?![价机])|跳下去|上吊|吞药)",
    r"(?:割腕|跳楼(?![价机])|上吊)",
    r"(?:楼上|楼顶|窗户|桥上).{0,8}跳下去",
    r"(?:攒|准备|买|吞|吃|服|一瓶|一把).{0,8}安眠药",
    r"安眠药.{0,8}(?:一瓶|一把|吞|吃|服)",
    # Whitespace is removed before matching, including between English words.
    r"(?:iwantto|imgoingto|iplanto|ithinkill|thinkingof|thinkingabout)(?:killmyself|endmylife|suicide)",
    r"(?:killmyself|endmylife|commitsuicide)",
    r"(?:iwantto|iwannato|iwanna|i'?mgoingto|iplanto|igonna)(?:die|hurtmyself|cutmyself)",
    r"(?:i)?don'?twanttolive|(?:hurt|cut)myself",
    r"suicidal|(?<![a-z])suicide(?![a-z])",
))


def detect_crisis(text: str) -> bool:
    """Identify explicit self-harm or suicide language in this turn."""
    normalized = re.sub(r"\s+", "", text or "").lower()
    return bool(normalized) and any(pattern.search(normalized) for pattern in _CRISIS_PATTERNS)
