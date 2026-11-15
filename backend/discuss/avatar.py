"""分身成员的系统提示与生效模型。

分身两步（brief、view）共用同一段系统提示：身份、主人配置的分身资料、
主人的私有长期记忆与基础安全规则。提示里不拼账号名。
"""

from __future__ import annotations

import json

import agent_store
import persona
from novel.billing import NovelBilling
from novel.byok_bridge import ByokBridge

from . import roles


def _text(value) -> str:
    return value if isinstance(value, str) else ""


async def build_avatar_system(username: str) -> str:
    """Build the four-part system prompt shared by the avatar's two steps."""
    agent = await NovelBilling._drain(agent_store.get_my_agent(username))
    snapshot = await NovelBilling._drain(agent_store.get_memory_snapshot(username))
    profile = snapshot.get("profile") if isinstance(snapshot, dict) else None
    if not isinstance(profile, dict):
        profile = {}

    configured = {
        "名字": _text(agent.get("display_name")),
        "公开简介": _text(agent.get("bio")),
        "主人设置的表达风格": _text(agent.get("personality")),
    }
    identity_block = (
        "以下 JSON 是主人配置的分身资料：\n"
        + json.dumps(configured, ensure_ascii=False)
    )
    memory_block = (
        "以下是主人的私有长期记忆，只用来判断主人的偏好与背景：\n"
        + json.dumps(profile, ensure_ascii=False)
    )
    return "\n".join([
        roles.AVATAR_IDENTITY,
        identity_block,
        memory_block,
        persona.BASE_SAFETY_RULES,
    ])


async def system_for(username: str, task: str) -> str:
    """Return the system prompt for the avatar's ``brief`` or ``view`` step."""
    if task == "brief":
        prompt = roles.AVATAR_BRIEF
    elif task == "view":
        prompt = roles.AVATAR_VIEW
    else:
        raise ValueError(f"未知的分身任务：{task}")
    return await build_avatar_system(username) + "\n\n" + prompt + roles.JSON_RULE


async def effective_model(username: str, configured: str | None = None) -> str:
    """Author-provided model wins; otherwise use enabled BYOK or the platform default."""
    if configured:
        return configured
    try:
        await ByokBridge(username).describe()
    except Exception:
        return roles.DEFAULT_AVATAR_MODEL
    return "byok:self"


async def display_name(username: str) -> str:
    agent = await NovelBilling._drain(agent_store.get_my_agent(username))
    name = _text(agent.get("display_name")).strip()
    return name or "分身"
