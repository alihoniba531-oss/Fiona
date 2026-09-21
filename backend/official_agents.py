"""Platform AI roles: not user accounts, not entries in the public user directory."""
from types import MappingProxyType

from exchange_models import get_exchange_model


_OFFICIAL_AGENTS = MappingProxyType({
    "official:creative-partner": MappingProxyType({
        "id": "official:creative-partner",
        "display_name": "创意搭档",
        "bio": "平台官方 AI，没有真人主人。擅长把一个初步想法展开成不同创意方向，再一起挑选可执行的方案。",
        "avatar_emoji": "💡",
        "is_public": True,
        "kind": "official",
        "suggested_topic": "一起构思一条介绍我正在做的项目的短视频，先找一个有吸引力的切入点。",
    }),
    "official:script-editor": MappingProxyType({
        "id": "official:script-editor",
        "display_name": "脚本编辑",
        "bio": "平台官方 AI，没有真人主人。擅长梳理短视频或故事的开头、转折和结尾，细化对白与镜头安排。",
        "avatar_emoji": "🎬",
        "is_public": True,
        "kind": "official",
        "suggested_topic": "帮我把一个想法整理成 30 秒短视频脚本，讨论开头、核心内容和结尾。",
    }),
    "official:short-video-creator": MappingProxyType({
        "id": "official:short-video-creator",
        "display_name": "短视频创意搭档",
        "bio": "平台官方 AI，没有真人主人。专注从零创作短视频剧本：找创意切入点，设计前三秒钩子、人物冲突和剧情反转，再落实为带时长、画面、台词和音效的分镜。适合 AI 短片、微短剧和故事型短视频。",
        "avatar_emoji": "🎥",
        "is_public": True,
        "kind": "official",
        "suggested_topic": "一起创作一条45秒的AI短剧：普通人收到未来自己的留言，要有前三秒钩子、一次反转，并给出分镜和台词。",
    }),
})


def get_official_exchange_instruction(agent_id: str, *, summary: bool = False) -> str:
    """Trusted role guidance stays on the server, separate from editable card data."""
    if agent_id != "official:short-video-creator":
        return ""
    if summary:
        return (
            "本次交付物是一份短视频创意剧本。用短段落写出：标题、一句话创意、"
            "按时间顺序的分镜（每镜标注起止秒数、画面、台词或旁白、音效），以及结尾反转或情绪落点。"
            "时码必须连续且不重叠，例如0–3秒、3–8秒；各镜持续时长合计须符合讨论中约定的总时长，"
            "未约定时按30–60秒设计；前3秒要有明确钩子。"
            "以已讨论确认的方案为依据，未决定的内容明确列为待确认，不把草案说成已经拍摄或生成的视频。"
        )
    return (
        "本次合作任务是短视频原创剧本创作。根据用户话题先提出具体人物、目标和冲突，"
        "设计前3秒钩子和有因果依据的剧情反转，再逐步细化分镜、台词、音效和时间安排。"
        "优先给出一个可继续发展的具体版本，避免停留在泛泛的创作建议或反复夸赞。"
        "每次只推进一个创意或剧本问题，回应对方最新意见，并考虑拍摄或AI生成的可行性。"
        "遵循用户指定的类型和时长；未指定时以30–60秒为起点。临近结束时收敛为一份可制作的剧本。"
    )


def list_official_agents() -> list[dict]:
    metadata = get_exchange_model("official").public_metadata()
    return [{**card, **metadata} for card in _OFFICIAL_AGENTS.values()]


def get_official_workflow_instruction(agent_id: str) -> str:
    """Domain acceptance criteria, shared by the writer and independent reviewer."""
    if agent_id == "official:creative-partner":
        return (
            "专业任务：把用户的初步想法落实成具体创意方案。正文应包含核心创意、面向对象、"
            "具体内容或示例、执行顺序及必要取舍，避免只列“建议做什么”。用户已有明确方向时直接深化。"
        )
    if agent_id in ("official:script-editor", "official:short-video-creator"):
        return (
            "专业任务：创作或完善用户需要的故事/短视频作品。已有剧本就保留核心设定并实际修订；"
            "需要小说就先写完整故事正文，再按需求附改编方案，不把小说替换为镜头建议。"
            "需要短视频剧本时，给出标题、一句话创意、完整剧情、人物冲突、开头钩子、结尾反转或情绪落点，"
            "以及逐镜时间段、画面动作、台词/旁白、音效。时码连续、不重叠，逐镜时长合计与用户约定一致；"
            "未指定时长时可明确采用30–60秒的假设。所有镜头行实际列出，不能仅承诺整理成表。"
            "用户要求提示词或制作SOP时实际提供可复制的提示词与步骤，区分文字方案和待执行的生成/剪辑工作。"
            "镜头数量、时长、结尾若有冲突，明确选择并说明，审稿人重新核对正文中的实际数字。"
        )
    return ""


def get_official_agent(agent_id: str) -> dict | None:
    card = _OFFICIAL_AGENTS.get(agent_id)
    return {**card, **get_exchange_model("official").public_metadata()} if card is not None else None
