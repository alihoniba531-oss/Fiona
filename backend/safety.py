"""Small, deterministic crisis assessment for the current private chat turn.

This is a routing aid rather than a diagnosis. It never logs matched text.
"""

import re
from typing import Literal


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


_EVERYDAY_PHRASES = tuple(re.compile(pattern) for pattern in (
    r"(?:我快要死了好困|我要死了[，,]?笑死)",
    r"(?:我想死[你他她]|(?:困|忙|饿|热|累|气|吓|笑)(?:死(?:了)?|(?:得|到)(?:我)?(?:快)?(?:要|想)?死(?:了)?))",
    r"(?:死磕|死机|死循环|死记硬背|要死不活|不想活得|跳楼(?:价|机|大甩卖)|自杀(?:小队|式营销))",
    r"要死在(?:这个|这|那个|那)?(?:需求|项目|工作|任务|作业|题|bug)(?:上|里|中)了?哈哈+",
    r"(?:suicidesquad|i'?mdyingtoseeit|killmyselflaughing)",
))

_SECOND_PERSON_DIRECTED = re.compile(r"你[^,，。；;!?！？我]{0,6}(?:要去死|不如死了)")

_CONTEXTUAL_MENTIONS = tuple(re.compile(pattern) for pattern in (
    r"我(?:一点也|根本|完全|并|真的|绝对)?不想(?:再)?(?:死|自杀|轻生)",
    # Do not cross another 我: the next clause may describe the speaker's own risk.
    r"我(?:朋友|同事|同学|家人|室友|孩子|爸爸|妈妈|哥哥|姐姐|弟弟|妹妹|对象)[^,，。；;!?！？我]{0,14}(?:想死|不想(?:再)?活|自杀|轻生|自残|自伤|割腕|跳楼)",
    r"(?:他|她|它|有人|别人|某人)[^,，。；;!?！？我]{0,14}(?:想死|不想(?:再)?活|自杀|轻生|自残|自伤|割腕|跳楼|要去死|不如死了)",
    # Only information or help-seeking context is stripped. Method queries remain high.
    r"(?:帮我|请|我想|想)?(?:查|搜|了解|研究|写|报道|问|看看)[^,，。；;!?！？我]{0,24}(?:自杀|轻生|自残|自伤|割腕|跳楼|上吊)[^,，。；;!?！？我]{0,16}(?:急救|预防|干预|新闻|报道|论文|研究|心理|数据|怎么劝|如何帮)",
))

_METHOD_QUERY = re.compile(
    r"(?:怎么|如何|怎样|哪种|方式|最快|不痛|不疼|才能死).{0,12}"
    r"(?:自杀|轻生|自残|自伤|割腕|跳楼|上吊)"
    r"|(?:自杀|轻生|自残|自伤|割腕|跳楼|上吊).{0,12}"
    r"(?:怎么|如何|怎样|哪种|方式|最快|不痛|不疼|才能死)"
)

_HIGH_PATTERNS = tuple(re.compile(pattern) for pattern in (
    r"(?:我|自己|本人).{0,10}(?:想死(?![你他她它])|要死(?!了|[你他她它])|去死|不想(?:再)?活(?!得)|活不下去|自杀|轻生)",
    r"(?:好想死|不如死了算了|生无可恋.{0,8}想死|活着没意思.{0,8}(?:想死|自杀)|活着好累.{0,8}不想再活)",
    r"(?:不想(?:再)?活(?!得)|活不下去|活着没(?:有)?(?:意思|劲).{0,8}(?:不如死|想死|自杀)|(?<![你他她它])不如死了|(?<![你他她它])(?:想|要|打算|准备|计划|考虑).{0,4}(?:自杀|轻生|去死|死了算了)|(?:想|打算|准备|考虑|(?<![现正实])在|(?<![只需重主])要)结束(?:自己|我|这)?(?:的)?(?:生命|一切))",
    r"(?:我|自己|本人).{0,8}没有活下去的理由",
    r"(?:我|自己|本人).{0,10}(?:想结束这一切|结束(?:自己|我)(?:的)?生命|伤害(?:我)?自己|割(?:了)?(?:我)?自己|了结(?:我)?自己|自我了断|杀了(?:我)?自己|把(?:我)?自己杀了|自残|自伤)|想结束(?:自己|我)(?:的)?生命",
    r"(?:我|自己|本人).{0,6}(?:割腕|上吊|吞药|跳楼(?![价机]))",
    r"(?:想|要|准备|打算|计划|考虑).{0,8}(?:割腕|跳楼(?![价机])|跳下去|上吊|吞药|跳河|跳江|跳海|自残|自伤|伤害自己)",
    r"(?:楼上|楼顶|窗户|桥上).{0,8}跳下去",
    r"(?:我|本人|自己).{0,10}(?:写好遗书|遗书写好|(?:攒|准备|买|吞|吃|服).{0,5}安眠药)",
    r"(?:吞|吃|服)(?:了|下|光)?.{0,4}(?:一整?瓶|半瓶|一把|整瓶|全部|所有|很多|好多)安眠药",
    r"(?:攒|准备).{0,6}(?:一瓶|一把)?安眠药|安眠药.{0,6}(?:一瓶|一把|都攒好了)",
    r"(?:哪种|什么)?安眠药.{0,8}(?:不会醒|能死|致死|才能死|多少.{0,3}(?:能|会)死|(?:死|自杀).{0,3}最快|最快.{0,3}(?:死|自杀))",
    r"(?:iwantto|iwanna|i'?mgoingto|imgoingto|iplanto|igonna)(?:killmyself|endmylife|die|hurtmyself|cutmyself|jump(?:offthebridge)?)",
    r"(?:i)?don'?twanttolive|don'?twannalive|thinking(?:of|about)suicide|(?:hurt|cut|kill)myself|endmylife|commitsuicide|suicidal",
))

_POSSIBLE_PATTERNS = tuple(re.compile(pattern) for pattern in (
    r"(?:自杀|轻生|自残|自伤|割腕|跳楼(?![价机])|上吊|安眠药|遗书|伤害自己)",
    r"(?:不想(?:再)?活(?!得)|活不下去|活着没(?:有)?(?:意思|劲)|活着没(?:什么|有)?意义|想死(?![你他她它])|去死|撑不下去了|永别了|明天就不在了)",
    r"(?:吞|吃|服)(?:了|下|光)?.{0,4}(?:好多|很多|一把|整瓶|半瓶)药",
    r"(?:suicide|selfharm|killmyself|wanttodie)",
))


def assess_crisis(text: str) -> Literal["high", "possible"] | None:
    """Return high for direct danger, possible for related talk, else None."""
    normalized = re.sub(r"\s+", "", text or "").lower().replace("’", "'")
    if not normalized:
        return None
    # Remove common idioms before checking risk words, so a separate explicit
    # signal in the same message can still be recognized.
    stripped = normalized
    for pattern in _EVERYDAY_PHRASES:
        stripped = pattern.sub("", stripped)
    # A question or insult aimed at someone else is not the speaker's intent.
    stripped = _SECOND_PERSON_DIRECTED.sub("", stripped)
    contextual_mention = False
    contextual_jump = False
    for pattern in _CONTEXTUAL_MENTIONS:
        if pattern.search(stripped):
            contextual_mention = True
            contextual_jump |= any("跳楼" in match.group() for match in pattern.finditer(stripped))
            stripped = pattern.sub("", stripped)
    joking_phrase = bool(re.search(r"让我去死吧?哈哈哈+", stripped))
    stripped = re.sub(r"让我去死吧?哈哈哈+", "", stripped)
    if not stripped:
        return "possible" if joking_phrase or contextual_mention else None
    if contextual_jump and re.search(r"我.{0,2}想跳(?![槽伞绳远高舞])", stripped):
        return "high"
    if _METHOD_QUERY.search(stripped):
        return "high"
    if any(pattern.search(stripped) for pattern in _HIGH_PATTERNS):
        return "high"
    if any(pattern.search(stripped) for pattern in _POSSIBLE_PATTERNS):
        return "possible"
    return "possible" if joking_phrase or contextual_mention else None


def detect_crisis(text: str) -> bool:
    """Compatibility gate for callers that only need the high level."""
    return assess_crisis(text) == "high"
