# -*- coding: utf-8 -*-
import contextlib
import json
import os
import re
import sqlite3
from datetime import datetime, timedelta, timezone

import database
from llm import MAIN_EXTRA_BODY, MAIN_MODEL

# pending intent 落库 chat_slot_state（不再是进程内裸 dict）：跨进程/重启都还在，
# 且按 PENDING_TTL_SECONDS 到期失效——几天前没答完的追问不该劫持今天的第一句话。
StateKey = str | tuple[str, str]

# chat_slot_state.kind 的取值，与 mode_switcher 的 "mode" 各占一行、互不干扰
SLOT_KIND = "pending"
# PENDING_TTL_SECONDS 缺失/为空/非整数时的回落值：10 分钟
DEFAULT_PENDING_TTL_SECONDS = 600

INTENT_PROMPT = """你是意图识别器，只输出JSON，不输出任何其他内容。

支持的意图：
  web_search      搜索信息         params: query(搜索词)
  hot_topics      看热搜/热门话题  params: source(可选: 微博/知乎/抖音, 默认 微博)
  route           查驾车导航(同城/同省短途) params: origin(起点), destination(终点)
  travel_plan     旅行/出差规划(跨城以上,含航班/高铁/签证) params: query(原话)
  get_datetime    查询时间日期     params: (无)
  fetch_card      读取网页内容做成卡片(默认在Chloe里呈现) params: query(网址 URL,如 https://...)
  generate_image  生成一张新图片   params: prompt(画面描述), aspect_ratio(可选: 1:1/16:9/9:16)

【核心原则 - 严格遵守】
1. 只有用户**当前消息明确要你执行一个新动作**时，才返回意图。
2. 用户在**抱怨/吐槽/反问/评价你刚才的行为**时，一律返回 intent=null。这是对话不是命令。
3. 用户**问问题、聊天、求分析、表达情绪**时，返回 intent=null。
4. 如果上下文显示你刚才已经做了某事，用户现在的消息提到同一个动作词（"打开"/"搜"/"发"等），**强烈倾向**是评价/抱怨而非新指令，返回 null。

口语识别示例（理解意图用，不要照搬）：
"帮我查一下今天天气" → web_search, query=今天天气
"搜搜最近有什么好电影" → web_search, query=最近好电影
"帮我看下明天的天气" → web_search, query=明天天气
"帮我查下比特币最新价格" → web_search, query=比特币价格
"搜一下怎么学Python" → web_search, query=怎么学Python
"查一下五月天演唱会" / "查查油价" → web_search, query=五月天演唱会 / 油价
"我查一下 XX" / "我看下 XX" / "我搜一下 XX" → web_search, query=XX
（注：用户用"我查/我看/我搜"是软性请求，本质还是要你帮查，不是在描述自己的动作）
"大麦网上有没有五月天演唱会" → web_search, query=大麦网 五月天 演唱会
"苹果有没有出新机型" → web_search, query=苹果 新机型
"XX上有没有YY" / "XX有没有YY的信息" → web_search, query=XX YY（信息核实类问句）
"看下热搜" / "现在热门话题" / "今天热门是啥" → hot_topics, source=微博
"知乎热榜有什么" / "知乎在聊啥" → hot_topics, source=知乎
"抖音热搜" / "刷下抖音热榜" → hot_topics, source=抖音
"从上海到杭州怎么开" / "上海到杭州怎么走" → route, origin=上海, destination=杭州
"中关村到北京西站怎么走" → route, origin=中关村, destination=北京西站
"我想从家出发去公司" → route, missing=[origin, destination]  （太模糊时缺参，需追问）
"怎么去机场" → route, missing=[origin], params={destination: 机场}

【route vs travel_plan】区分关键：
- route = 同城/同省 + 关键词含"开/驾车/导航/怎么走"，结果是地图驾车路线
- travel_plan = 跨城/跨省/跨国 + 关键词含"规划/出差/旅行/几天/什么时候去"，
  结果是航班+高铁+签证+预算+季节的综合方案
- 一旦提到外国地名、签证、航班、机票，铁定 travel_plan
- 一旦提到"X天后去"、"下周去"、"国庆去"、"规划"，也铁定 travel_plan

"我在宁波三天后要去新德里帮我规划路线" → travel_plan, query=我在宁波三天后要去新德里帮我规划路线
"下周从北京出差去东京怎么安排" → travel_plan, query=下周从北京出差去东京怎么安排
"国庆想去新疆玩 5 天" → travel_plan, query=国庆想去新疆玩5天
"从广州去拉萨怎么走比较方便" → travel_plan, query=从广州去拉萨怎么走比较方便（跨省+方式不限定）
"上海到迪拜机票多少钱" → travel_plan, query=上海到迪拜机票多少钱
"现在几点了" / "今天几号" → get_datetime

【图片生成】只有明确让你实际画图/生成图片才用 generate_image，默认只生成一张。
"帮我生成一张薄雾中的古庙图片" / "画一只趴在窗台的猫" → generate_image
"帮我做一张咖啡店海报" → generate_image
"帮我生成图片" → generate_image, missing=[prompt]
"你能生成图片吗" / "生图多少钱" / "怎么生成图片" / "帮我写生图提示词" → null
"不要画了" / "你刚才画的不好" / "我昨天画了一张图" → null
"修改刚才的图片" / "把这张图的天空改成黄昏" / "引用原图继续调整" → null（需要先点击图片上的「以此图修改」，不能当作没有参考图的文生图）
不要把解释、评价、教程、代码、提示词、搜索现有图片误判成实际生成。

【fetch_card 默认走这条 - 信息以卡片在Chloe里呈现,不打开浏览器】
"帮我看看 https://news.sina.com.cn 头条" → fetch_card, query=https://news.sina.com.cn
"读一下这个网页 https://..." → fetch_card, query=https://...
"看下这个商品 https://item.jd.com/xxx.html" → fetch_card, query=https://item.jd.com/xxx.html
"帮我看看这条微博 https://weibo.com/..." → fetch_card, query=https://weibo.com/...

【返回 null 的示例 - 这些都不是命令】
"今天心情不好" → null（聊天/情绪）
"你只会打开百度搜索啊" → null（抱怨）
"你这是干啥呀" / "你这是开的什么呀" → null（吐槽/疑问）
"我是说，你只懂得打开百度搜索吗？" → null（反问/批评）
"你刚才搜的不对" / "你打开错了" → null（评价上一次行为）
"你怎么又这样" / "你怎么只会这个" → null（抱怨）
"打不开吧" / "搜不到吧" → null（怀疑）
"能帮我分析一下..." / "能帮我看看..." → null（要分析/讨论，不是要打开/搜索）
"你能干啥啊" / "你都会什么" → null（问能力）
"我想了解下XX" → null（要讨论/求知，不是要你打开网页）
"听说苹果出了新东西" → null（聊天）
**注意区分**:
- "帮我看下/帮我查下/帮我搜下/帮我搜搜" → web_search（要具体信息）
- "我想了解下/你能分析下/帮我分析下" → null（要观点/讨论）
- "帮我看看/读一下 https://xxx" → fetch_card（有具体网址）

缺少参数时，把已提取的放params，缺的放missing数组（按执行顺序排）。

严格输出格式（只有JSON，不加任何说明）：
参数完整：{"intent": "web_search", "params": {"query": "今天天气"}, "missing": []}
缺少参数：{"intent": "route", "params": {"destination": "机场"}, "missing": ["origin"]}
普通对话：{"intent": null}
"""

# 缺少参数时Chloe的追问话术
MISSING_QUESTIONS = {
    "query":       "搜啥？",
    "origin":      "从哪儿出发？",
    "destination": "去哪儿？",
    "prompt":      "想生成什么画面？可以告诉我主体、场景和风格。",
}


def image_aspect_ratio(message: str) -> str:
    if re.search(r"9\s*[:：]\s*16|竖[版屏幅]", message):
        return "9:16"
    if re.search(r"16\s*[:：]\s*9|横[版屏幅]", message):
        return "16:9"
    return "1:1"


def image_generation_discussion(message: str) -> bool:
    """Capabilities, explanations and cancellations do not authorize an image job."""
    text = message.strip()
    return bool(
        re.match(r"^(?:请)?(?:别|不要|不用|不需要|取消|停止)", text)
        or re.match(r"^(?:你)?(?:会|可以|能|能不能|能否)(?:帮我)?(?:生成|画|绘制|制作)(?:图片|图像|画画|图)(?:吗|么)?[？?。！!\s]*$", text)
        or re.match(r"^(?:怎么|如何|为什么|为啥|能否介绍|介绍一下)", text)
        or re.search(r"(?:生图|生成图片|生成图像|绘图)(?:的|有哪些|有什么|用什么|使用什么)?(?:功能|接口|API|模型|价格|费用|教程|方法)", text, re.I)
        or re.search(r"(?:写|提供|解释|优化|修改|生成)(?:一下|一段|一份|个|一[个份])?[^。！？!?]{0,12}(?:提示词|教程|代码)", text)
    )


def explicit_image_intent(message: str) -> dict | None:
    """仅抢先识别明确绘图命令，避免长画面描述被陪聊模式或搜索吞掉。"""
    text = message.strip()
    if image_generation_discussion(text):
        return None
    # 提示词、教程和能力咨询是普通对话；否定/引述也不能触发付费生成。
    if re.search(r"(?:提示词|教程|接口|API|代码|方法|功能)(?:怎么|如何|能否|是否|[？?]|$)", text, re.I):
        return None
    if re.match(r"^(?:请)?(?:别|不要|不用|不需要|取消|停止)", text):
        return None
    prefix = r"^(?:(?:请|麻烦你?|能不能|能否|可以|能)(?:帮我|给我|为我)?|帮我|给我|为我|替我|我想让你|我想要你|你帮我)?\s*"
    matched = re.match(prefix + r"(?:生成|绘制|画|做|创作|制作)(?:一下|一幅|一张|一个|一只|一副|个|张|幅)?\s*(.*)", text, re.S)
    if not matched:
        return None
    if re.search(r"(?:提示词|教程|接口|API|代码|方法|功能)", matched.group(1)[:30], re.I):
        return None
    if not re.match(prefix + r"(?:画|绘制)", text) and not re.search(r"图片|图像|海报|插画|壁纸|头像|封面|照片|一[张幅副].*图", text, re.S):
        return None
    subject = re.sub(r"^(?:一[张幅副个])?(?:图片|图像|画|图)?[。！!？?，,:：\s]*$", "", matched.group(1)).strip()
    return {"intent": "generate_image", "params": {
        "prompt": text, "aspect_ratio": image_aspect_ratio(text),
    }, "missing": [] if subject else ["prompt"]}


def image_edit_requires_reference(message: str) -> bool:
    """An edit mentioning a prior image needs explicit selection, never a guessed source."""
    text = message.strip()
    if image_generation_discussion(text) or re.search(r"提示词|教程|代码", text):
        return False
    reference = re.search(
        r"参考图|原图|这(?:一)?张(?:图片|照片|图)|这个图|"
        r"(?:刚才|之前|上面|上一张|上张)(?:生成的?|的|那张|这张)?(?:图片|照片|图)", text,
    )
    change = re.search(r"修改|调整|改变|替换|换成|改成|改为|改一下|编辑|变成|去掉|去除|添加|加上|改图", text)
    return bool(reference and change)


# ── 槽位持久化（chat_slot_state）─────────────────────
# 与 mode_switcher 里的同名 helper 是刻意各自一份：两个模块互不 import，
# 谁被 reload / 打桩都不牵连另一个。改这里记得同步改那边。


def _slot_identity(key: StateKey) -> tuple[str, str]:
    """StateKey → (state_key, owner_username)。

    str 是账号级；(username, conversation_id) 是会话级，用 \\x1f（US 控制符）拼接
    ——用户名和会话 id 里都不会出现该字符，所以拼接无歧义。
    owner_username 单独存一列，"清空某用户全部槽位"才能写成等值匹配。
    """
    if isinstance(key, tuple):
        username, conversation_id = key
        return f"{username}\x1f{conversation_id}", username
    return key, key


def _pending_ttl_seconds() -> int:
    """每次调用现读环境变量（不得在导入时固化），否则测试无法用 setenv 覆盖。"""
    try:
        return int(str(os.getenv("PENDING_TTL_SECONDS")).strip())
    except (TypeError, ValueError):
        return DEFAULT_PENDING_TTL_SECONDS


@contextlib.contextmanager
def _slot_conn():
    """开一次 chat_slot_state 连接。

    路径必须在函数体内现读 database.DB_PATH：conftest 靠 monkeypatch 该模块全局做隔离，
    一旦在模块顶层缓存路径，测试就会写进真库 backend/fiona.db。
    每次都先跑一遍建表 DDL 兜底——部分调用点（含既有测试）不经 init_db() 就直接读写槽位。
    sqlite3 的 with 只管事务不管关闭，所以外面套 closing。
    """
    with contextlib.closing(sqlite3.connect(database.DB_PATH, timeout=5.0)) as conn:
        conn.execute(database.CHAT_SLOT_STATE_DDL)
        yield conn


def _expiry_of(raw) -> datetime | None:
    """expires_at 一律按 UTC 解读；解析不出来返回 None（当作不过期，别误删有效槽位）。"""
    if raw is None:
        return None
    if isinstance(raw, datetime):
        parsed = raw
    else:
        try:
            parsed = datetime.fromisoformat(str(raw))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _is_expired(raw, now_utc: datetime) -> bool:
    expiry = _expiry_of(raw)
    return expiry is not None and expiry <= now_utc


def get_pending(username: StateKey) -> dict | None:
    """读回待补参槽位。已过期 / payload 损坏或结构不对 → 当作不存在，并顺手删掉那行。"""
    state_key, _owner = _slot_identity(username)
    with _slot_conn() as conn:
        row = conn.execute(
            "SELECT payload_json, expires_at FROM chat_slot_state WHERE state_key = ? AND kind = ?",
            (state_key, SLOT_KIND),
        ).fetchone()
        if row is None:
            return None
        try:
            data = json.loads(row[0])
        except (TypeError, ValueError):
            data = None
        if not isinstance(data, dict) or _is_expired(row[1], datetime.now(timezone.utc)):
            conn.execute(
                "DELETE FROM chat_slot_state WHERE state_key = ? AND kind = ?",
                (state_key, SLOT_KIND),
            )
            conn.commit()
            return None
        return data


def set_pending(username: StateKey, data: dict):
    """写入/覆盖槽位，expires_at = now(UTC) + PENDING_TTL_SECONDS。"""
    state_key, owner_username = _slot_identity(username)
    now_utc = datetime.now(timezone.utc)
    expires_at = now_utc + timedelta(seconds=_pending_ttl_seconds())
    with _slot_conn() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO chat_slot_state
                   (state_key, kind, owner_username, payload_json, expires_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                state_key,
                SLOT_KIND,
                owner_username,
                json.dumps(data, ensure_ascii=False),
                expires_at.isoformat(),
                now_utc.isoformat(),
            ),
        )
        conn.commit()


def clear_pending(username: StateKey):
    """清单个槽位（账号级或某个会话级）。"""
    state_key, _owner = _slot_identity(username)
    with _slot_conn() as conn:
        conn.execute(
            "DELETE FROM chat_slot_state WHERE state_key = ? AND kind = ?",
            (state_key, SLOT_KIND),
        )
        conn.commit()


def clear_user_pending(username: str):
    """删号时清理默认会话和所有独立会话的临时状态。

    必须是 owner_username 等值匹配：改用 LIKE / GLOB 前缀匹配 state_key 的话，
    用户名里的 % _ * ? 会误删别人的槽位。
    """
    with _slot_conn() as conn:
        conn.execute(
            "DELETE FROM chat_slot_state WHERE kind = ? AND owner_username = ?",
            (SLOT_KIND, username),
        )
        conn.commit()


def ask_missing(key: str) -> str:
    return MISSING_QUESTIONS.get(key, "还需要什么信息？")


def fill_param(pending: dict, message: str) -> dict:
    """把用户回答填入 pending intent 的第一个缺失参数"""
    key = pending["missing"][0]
    if key == "minutes":
        nums = re.findall(r'\d+', message)
        # 支持"半小时"、"一小时"等口语
        if not nums:
            if "半小时" in message:
                nums = ["30"]
            elif "一小时" in message or "1小时" in message:
                nums = ["60"]
        value = int(nums[0]) if nums else 5
    else:
        value = message.strip()

    pending["params"][key] = value
    pending["missing"] = pending["missing"][1:]
    return pending


def recognize_intent(client, message: str, history: list[dict] | None = None) -> dict:
    """调用主力大脑识别意图，返回 {intent, params, missing}

    history: 最近的对话历史，用于让分类器看到"她刚做了什么"，区分新指令 vs 抱怨/吐槽
    """
    # 取最近 2 条作为上下文（更多没必要，避免 token 浪费）
    user_content = message
    if history:
        recent = history[-2:]
        ctx_lines = [
            f"{m['role']}: {(m.get('content') or '')[:80]}"
            for m in recent
            if m.get("content")
        ]
        if ctx_lines:
            ctx = "\n".join(ctx_lines)
            user_content = f"【对话上下文】\n{ctx}\n\n【当前消息】\n{message}"

    try:
        resp = client.chat.completions.create(
            model=MAIN_MODEL,
            extra_body=MAIN_EXTRA_BODY,
            messages=[
                {"role": "system", "content": INTENT_PROMPT},
                {"role": "user", "content": user_content},
            ],
            response_format={"type": "json_object"},
            max_tokens=150,
            temperature=0.1,
        )
        result = json.loads(resp.choices[0].message.content)
        if result.get("intent") is None:
            return {"intent": None}
        return {
            "intent": result["intent"],
            "params": result.get("params", {}),
            "missing": result.get("missing", []),
        }
    except Exception:
        return {"intent": None}
