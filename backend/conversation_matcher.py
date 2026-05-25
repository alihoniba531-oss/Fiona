# -*- coding: utf-8 -*-
"""
对话内匹配引擎。

跟传统"用户点按钮看匹配"不同——这是在对话中识别用户的兴趣/烦恼，
跨用户找相关的人，命中后写 pending_matches 表，等前端拉取弹卡。

核心机制：
1. extract_interests: 从本轮对话抽出兴趣点 + 强度评分 + 类别（政治红线过滤）
2. find_cross_user_candidates: 跨用户 profile/messages 搜相关
3. evaluate_match: LLM 评估匹配质量
4. detect_and_save: 完整流程，给 main.py 的 /chat 后台调用
"""
import json
import asyncio
import aiosqlite
from database import (
    get_profile, get_all_profiles, was_recently_matched, save_match,
    save_pending_match, get_recent_user_messages, get_user_settings, DB_PATH,
)

# 上下文阈值——根据用户当前 openness_level 动态选择
INTEREST_STRENGTH_THRESHOLD_HIGH   = 7  # openness=high：正常阈值
INTEREST_STRENGTH_THRESHOLD_MEDIUM = 8  # openness=medium：提高一档，要求更强信号

# 政治红线类别——命中直接跳过整个匹配流
BLOCKED_CATEGORIES = {"政治", "宗教", "国家敏感"}

# 每次最多推 N 个匹配
MAX_MATCHES_PER_TURN = 2


EXTRACT_INTEREST_PROMPT = """你是兴趣点抽取器，只输出 JSON 数组。

从用户当前消息 + 最近对话上下文里，抽出他/她在意的兴趣/烦恼/事件/话题。

每项必须包含以下字段：
{
  "topic": "简短话题词，如 '骑行' / '失业焦虑' / '猫'",
  "strength": 1-10 整数，表达这个话题对用户当下的强度。轻飘飘提及=3-5，明显在意=6-8，反复纠结/强烈情绪=9-10,
  "category": 一个类别——'兴趣爱好' / '工作职业' / '情感关系' / '心理状态' / '健康' / '家庭' / '财务' / '政治' / '宗教' / '国家敏感' / '其他',
  "match_type": "interest" 或 "seeking"
    - interest：用户自身拥有/在意这个话题（如"我喜欢骑行"）
    - seeking：用户在寻找某类人（如"想找喜欢骑行的女生"）,
  "engagement_mode": 用户在这个话题上的参与方式，四选一：
    - "seeking"：有困惑/需要帮助/寻找答案/想学（"怎么做"、"不知道"、"好难"、问句）
    - "processing"：正在经历/消化/反复想这件事，有情绪（叙述性、情绪词、反复提及）
    - "sharing"：有经验/观点在主动分享（"我之前"、"我觉得"、"我的经验"）
    - "exploring"：轻度好奇，随口提到，没有深度投入
}

当 match_type 为 "seeking" 时，额外加两个字段：
  "seeking_gender": "male" / "female" / null（明确提到性别时填，否则 null）
  "seeking_traits": ["想找的对方的特征词列表，如 骑行、摄影、杭州"]

规则：
- 抽 0-3 个最显著的，宁缺勿滥
- 只看用户当前在意的，不抽寒暄/打招呼/对Chloe的元话术
- topic 要具体（"骑行"而不是"运动"）
- 严格 JSON 数组，不加解释

如果什么有质感的兴趣点都没有，返回 []
"""


async def extract_interests(client, current_msg: str, recent_msgs: list[dict]) -> list[dict]:
    """从对话抽兴趣点。返回 [{topic, strength, category}, ...]"""
    if not current_msg or not current_msg.strip():
        return []

    # 取最近 5 条对话作为上下文
    ctx_lines = [
        f"{m['role']}: {(m.get('content') or '')[:120]}"
        for m in recent_msgs[-5:]
        if m.get("content")
    ]
    ctx = "\n".join(ctx_lines) if ctx_lines else "（无）"

    try:
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": EXTRACT_INTEREST_PROMPT},
                {"role": "user", "content": f"上下文:\n{ctx}\n\n当前消息:\n{current_msg}"},
            ],
            response_format={"type": "json_object"},
            max_tokens=200,
            temperature=0.2,
        )
        raw = resp.choices[0].message.content
        data = json.loads(raw)
        # DeepSeek JSON mode 可能包在对象里
        if isinstance(data, list):
            items = data
        else:
            items = next((v for v in data.values() if isinstance(v, list)), [])
        # 过滤、归一化
        valid_modes = {"seeking", "processing", "sharing", "exploring"}
        result = []
        for item in items:
            if not isinstance(item, dict):
                continue
            topic = (item.get("topic") or "").strip()
            if not topic:
                continue
            strength = int(item.get("strength", 0) or 0)
            category = (item.get("category") or "其他").strip()
            match_type = item.get("match_type", "interest")
            engagement_mode = item.get("engagement_mode", "exploring")
            if engagement_mode not in valid_modes:
                engagement_mode = "exploring"
            entry: dict = {
                "topic": topic,
                "strength": strength,
                "category": category,
                "match_type": match_type,
                "engagement_mode": engagement_mode,
            }
            if match_type == "seeking":
                entry["seeking_gender"] = item.get("seeking_gender")
                entry["seeking_traits"] = [t for t in (item.get("seeking_traits") or []) if t]
            result.append(entry)
        return result
    except Exception as e:
        print(f"[matcher] extract_interests failed: {type(e).__name__}: {e}", flush=True)
        return []


def passes_threshold(interest: dict, threshold: int = INTEREST_STRENGTH_THRESHOLD_HIGH) -> bool:
    """通过阈值且不踩红线（threshold 由调用方根据 openness_level 传入）"""
    if interest.get("category") in BLOCKED_CATEGORIES:
        return False
    return interest.get("strength", 0) >= threshold


async def find_cross_user_candidates(my_username: str, topics: list[str]) -> list[dict]:
    """跨用户搜相关：用 profile_json + 最近 messages 关键词搜，按性别偏好过滤。返回候选用户列表"""
    # 我的匹配偏好（"male"/"female"/"both"）
    my_settings = await get_user_settings(my_username)
    my_pref = my_settings.get("match_pref", "both")

    all_profiles = await get_all_profiles()
    candidates = []

    for p in all_profiles:
        peer = p["username"]
        if peer == my_username:
            continue
        if await was_recently_matched(my_username, peer):
            continue

        # 性别过滤：若我有明确偏好，对方必须匹配该性别（未设性别的对方不通过）
        if my_pref in ("male", "female"):
            peer_gender = p.get("gender")
            if peer_gender != my_pref:
                continue

        profile = p["profile"]
        # 用 profile_json 序列化后的字符串做关键词搜
        profile_text = json.dumps(profile, ensure_ascii=False)

        # 也搜对方最近 5 条用户消息（兴趣可能没在 profile 里但在最近对话里）
        peer_recent = await get_recent_user_messages(peer, limit=5)
        peer_recent_text = " ".join(m.get("content", "") for m in peer_recent)

        full_text = profile_text + " " + peer_recent_text

        # 命中任一 topic 即列入候选
        hit_topics = [t for t in topics if t and t in full_text]
        if hit_topics:
            candidates.append({
                "peer_username": peer,
                "peer_profile": profile,
                "hit_topics": hit_topics,
                "recent_msgs_summary": peer_recent_text[:300],
            })

    return candidates


EVAL_MATCH_PROMPT = """你是匹配质量评估器，只输出 JSON。

给定：
- 目标用户（A）当前在聊的内容 + 参与模式 + 利益锚点（底色信号，内部使用）
- 候选用户（B）的画像 + 最近聊天片段

【第一步】从 B 的画像和近期消息里，推断 B 的参与模式 + 利益锚点：
参与模式：seeking / processing / sharing / exploring
利益锚点：emotional_value / resource_exchange / safety / recognition / intimate / light_connection

【第二步】角色互补矩阵（参与模式层）：
  seeking  → sharing   ✅ 精准对接
  processing → processing ✅ 互助伙伴
  exploring → 任意      ✅ 话题连接
  seeking  → seeking   ❌ 不推
  seeking  → processing ⚠️ 弱匹配，谨慎

【第三步】利益锚点互补矩阵（底色层，权重高于话题匹配）：
  emotional_value ↔ emotional_value    ✅ 互相滋养（话题连接）
  resource_exchange(seeking) ↔ resource_exchange(giving) ✅ 精准对接
  safety ↔ safety                      ✅ 互助伙伴（同样需要稳定感）
  recognition ↔ emotional_value        ✅ 中强匹配（一方需被看见，另一方会给）
  intimate ↔ intimate                  ✅ 强匹配（双向磁场）
  recognition ↔ recognition            ❌ 双方都需被选择，谁也给不了谁
  intimate ↔ 其他                      ⚠️ 单向磁场，谨慎

【第四步】综合输出：
{
  "b_mode": "seeking" | "processing" | "sharing" | "exploring",
  "role_compatible": true | false,
  "should_recommend": true | false,
  "type": "精准对接" | "互助伙伴" | "话题连接",
  "reason": "一句话，不超过 25 字，不透露对方隐私",
  "tags": ["最多 3 个简短标签"]
}

reason 写法规则（严格遵守）：
- 用直觉口吻，不用分析口吻（"我感觉">"系统判断"）
- 具体到细节，绝不套话（"她也在这个节点卡着">"有相似经历"）
- 绝对不能出现：需求、互补、利益、锚点、recognition、intimate、safety 等任何内部标签词
- intimate ↔ intimate 时，reason 必须极度模糊："说不清楚，就是感觉磁场对" / "不好解释，大概会有火花"，绝不出现浪漫、喜欢、吸引等可截图坐实的词
- 像朋友在饭桌上随口提起某人，不像推荐算法

其他规则：
- role_compatible 为 false 时，should_recommend 必须是 false
- 表面关键词命中但对方不是真的在意 → should_recommend: false
"""


async def evaluate_match(
    client,
    my_username: str,
    my_recent_msg: str,
    candidate: dict,
    a_engagement_mode: str = "exploring",
    a_interest_anchor: str = "light_connection",
    a_time_context: str = "",
) -> dict | None:
    """LLM 评估一对匹配是否值得推。返回 None 表示拒绝"""
    try:
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": EVAL_MATCH_PROMPT},
                {"role": "user", "content": (
                    f"目标用户「{my_username}」当前在聊的内容:\n{my_recent_msg}\n"
                    f"A 的参与模式: {a_engagement_mode}\n"
                    f"A 的利益锚点: {a_interest_anchor}\n"
                    f"A 的时段背景: {a_time_context}\n\n"
                    f"候选用户「{candidate['peer_username']}」:\n"
                    f"画像: {json.dumps(candidate['peer_profile'], ensure_ascii=False)}\n"
                    f"近期聊天片段: {candidate['recent_msgs_summary']}\n\n"
                    f"命中的话题词: {candidate['hit_topics']}"
                )},
            ],
            response_format={"type": "json_object"},
            max_tokens=250,
            temperature=0.3,
        )
        data = json.loads(resp.choices[0].message.content)
        if not data.get("role_compatible") or not data.get("should_recommend"):
            return None
        return {
            "type": data.get("type", "话题连接"),
            "reason": (data.get("reason") or "").strip(),
            "tags": data.get("tags", [])[:3],
        }
    except Exception as e:
        print(f"[matcher] evaluate_match failed: {type(e).__name__}: {e}", flush=True)
        return None


# ──────────────────────────────────────────
#  寻求型匹配（漂流瓶机制）
# ──────────────────────────────────────────

async def find_seeking_candidates(
    my_username: str,
    my_gender: str | None,
    seeking: dict,
) -> list[dict]:
    """
    寻求型候选搜索：找「是被寻求那类人」的候选，而非找「也在寻求」的人。
    seeking 格式：{seeking_gender, seeking_traits, topic}
    """
    target_gender = seeking.get("seeking_gender")
    target_traits = seeking.get("seeking_traits") or []

    all_profiles = await get_all_profiles()
    candidates = []

    for p in all_profiles:
        peer = p["username"]
        if peer == my_username:
            continue
        if await was_recently_matched(my_username, peer, days=30):
            continue

        # 候选必须符合被寻求的性别（若有指定）
        if target_gender and p.get("gender") != target_gender:
            continue

        # 候选的 match_pref 需与发起人性别兼容
        peer_settings = await get_user_settings(peer)
        peer_pref = peer_settings.get("match_pref", "both")
        if my_gender and peer_pref not in ("both", my_gender):
            continue

        # 候选 profile + 近期消息里是否有目标特征词
        profile_text = json.dumps(p["profile"], ensure_ascii=False)
        peer_recent = await get_recent_user_messages(peer, limit=5)
        peer_text = profile_text + " " + " ".join(m.get("content", "") for m in peer_recent)

        hit_traits = [t for t in target_traits if t and t in peer_text]
        # 无特征词要求时，性别匹配即可；有特征词要求时至少命中一个
        if target_traits and not hit_traits:
            continue

        candidates.append({
            "peer_username": peer,
            "peer_profile": p["profile"],
            "hit_traits": hit_traits,
            "recent_msgs_summary": peer_text[:300],
        })

    return candidates


SEEKING_EVAL_PROMPT = """你是漂流瓶匹配评估器，只输出 JSON。

发起方正在寻找某类人，候选用户可能就是被寻找的那类人。
判断：候选用户是否真的符合发起方的寻求条件？

输出：
{
  "should_recommend": true | false,
  "reason": "一句话描述候选用户符合的特征（从被找到的角度，如'你骑了多年公路车'）——不超过25字，不暴露发起方信息",
  "tags": ["最多3个标签"]
}

规则：
- 候选用户真的是发起方想找的那类人 → true
- 只是关键词碰巧出现 → false
- reason 从候选用户视角说（"你..."），帮助候选用户知道自己为何被找到
"""


async def evaluate_seeking_match(
    client,
    my_username: str,
    seeking: dict,
    candidate: dict,
) -> dict | None:
    """评估候选是否符合寻求条件。"""
    try:
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": SEEKING_EVAL_PROMPT},
                {"role": "user", "content": (
                    f"发起方正在寻找：{seeking.get('topic', '某类人')}\n"
                    f"寻求的特征：{seeking.get('seeking_traits', [])}\n"
                    f"寻求的性别：{seeking.get('seeking_gender') or '不限'}\n\n"
                    f"候选用户画像：{json.dumps(candidate['peer_profile'], ensure_ascii=False)}\n"
                    f"近期聊天：{candidate['recent_msgs_summary']}\n"
                    f"命中特征词：{candidate['hit_traits']}"
                )},
            ],
            response_format={"type": "json_object"},
            max_tokens=150,
            temperature=0.2,
        )
        data = json.loads(resp.choices[0].message.content)
        if not data.get("should_recommend"):
            return None
        return {
            "reason": (data.get("reason") or "").strip(),
            "tags": data.get("tags", [])[:3],
        }
    except Exception as e:
        print(f"[matcher] evaluate_seeking_match failed: {type(e).__name__}: {e}", flush=True)
        return None


async def detect_and_save(
    client,
    username: str,
    current_msg: str,
    recent_msgs: list[dict],
    triggered_by_message_id: int | None = None,
    message_count: int = 0,
) -> int:
    """完整流程：抽兴趣 → 分流（interest/seeking）→ 跨用户搜 → 评估 → 入库。返回入库的匹配数"""
    if not current_msg or not current_msg.strip():
        return 0

    # 0. 镜子模式下不触发匹配——用户在发泄/情绪中，推匹配只会被忽略或觉得被打扰
    from mode_switcher import get_user_mode
    if get_user_mode(username).get("mode") == "mirror":
        return 0

    # 0.1. 阶段门控：对话越深，匹配越精
    # < 10 条：信号太稀，任何话题抽取都不可靠，直接跳过
    if message_count < 10:
        return 0
    # 10-29 条：只推极强信号（首次匹配必须是高质量的）
    _phase_strict = (message_count < 30)

    # 0.5. 运行底色探针（在后台任务内顺序执行，await 保证写完再匹配）
    from state_probe import run_state_probe
    user_state = await run_state_probe(client, username, recent_msgs)

    # 0.6. openness 门控：情绪激烈/发泄中直接跳过，节省后续 LLM 调用
    openness = user_state.get("openness_level", "medium")
    if openness == "low":
        return 0

    # 阶段限制：10-29 条时 openness 必须是 high，且阈值强制升到 9
    if _phase_strict:
        if openness != "high":
            return 0
        strength_threshold = 9
    else:
        # 30+ 条：正常动态阈值
        strength_threshold = (
            INTEREST_STRENGTH_THRESHOLD_HIGH if openness == "high"
            else INTEREST_STRENGTH_THRESHOLD_MEDIUM
        )

    # 稳定主信号：来自底色探针，比 per-message engagement_mode 更稳定
    stable_a_mode   = user_state.get("connection_mode", "exploring")
    a_anchor        = user_state.get("interest_anchor", "light_connection")

    # 当前时段 + 时段标签（作为额外匹配信号）
    from database import get_time_slot, get_time_tag_prefs
    current_slot  = get_time_slot()
    time_top_tags = sorted(
        (await get_time_tag_prefs(username)).items(),
        key=lambda x: x[1], reverse=True
    )[:3]
    a_time_context = f"{current_slot}，常在此时聊的话题：{[t for t, _ in time_top_tags]}" if time_top_tags else current_slot

    # 1. 抽兴趣点（含 match_type + engagement_mode 字段）
    interests = await extract_interests(client, current_msg, recent_msgs)
    if not interests:
        return 0

    # 分离兴趣型 vs 寻求型（使用动态阈值）
    regular = [
        i for i in interests
        if i.get("match_type") != "seeking"
        and passes_threshold(i, strength_threshold)
    ]
    seeking_list = [i for i in interests if i.get("match_type") == "seeking" and i.get("strength", 0) >= 6]

    saved = 0
    my_settings = await get_user_settings(username)
    my_gender = my_settings.get("gender")

    # ── 兴趣型匹配 ──
    if regular:
        topics = [i["topic"] for i in regular]
        candidates = await find_cross_user_candidates(username, topics)
        for candidate in candidates[:5]:
            if saved >= MAX_MATCHES_PER_TURN:
                break
            # 使用底色探针的稳定信号，而非 per-topic 临时 engagement_mode
            result = await evaluate_match(
                client, username, current_msg, candidate,
                a_engagement_mode=stable_a_mode,
                a_interest_anchor=a_anchor,
                a_time_context=a_time_context,
            )
            if not result:
                continue
            hit = candidate["hit_topics"]
            main_topic = hit[0] if hit else topics[0]

            # A 的卡片
            await save_pending_match(
                username=username,
                peer_username=candidate["peer_username"],
                interest_topic=main_topic,
                reason=result["reason"],
                match_type=result["type"],
                tags=result["tags"],
                triggered_by_message_id=triggered_by_message_id,
            )
            # B 的卡片（匿名）
            await save_pending_match(
                username=candidate["peer_username"],
                peer_username=username,
                interest_topic=main_topic,
                reason="Chloe觉得你们可能聊得来",
                match_type=result["type"],
                tags=result["tags"],
                triggered_by_message_id=None,
            )
            await save_match(username, candidate["peer_username"])
            saved += 1

    # ── 寻求型匹配（漂流瓶机制）──
    for seeking in seeking_list[:2]:
        if saved >= MAX_MATCHES_PER_TURN:
            break
        candidates = await find_seeking_candidates(username, my_gender, seeking)
        for candidate in candidates[:3]:
            if saved >= MAX_MATCHES_PER_TURN:
                break
            result = await evaluate_seeking_match(client, username, seeking, candidate)
            if not result:
                continue

            seeking_topic = seeking.get("topic", "在找某类人")

            # A 的卡片：找到了符合条件的人
            await save_pending_match(
                username=username,
                peer_username=candidate["peer_username"],
                interest_topic=seeking_topic,
                reason=f"Chloe找到了一个符合你条件的人",
                match_type="精准对接",
                tags=result["tags"],
                triggered_by_message_id=triggered_by_message_id,
            )
            # B 的卡片：有人在找你这样的人（匿名，只说特征）
            await save_pending_match(
                username=candidate["peer_username"],
                peer_username=username,
                interest_topic=seeking_topic,
                reason=result["reason"],  # 从 B 视角：「你骑了多年公路车」
                match_type="精准对接",
                tags=result["tags"],
                triggered_by_message_id=None,
            )
            await save_match(username, candidate["peer_username"])
            saved += 1

    return saved


# ─────────────────────────────────────────────
#  Layer 2：画像级匹配（Chloe与Chloe的比对）
# ─────────────────────────────────────────────

def _keyword_overlap(list_a: list, list_b: list) -> int:
    """两个词组列表之间的关键词交集数（子串匹配）"""
    count = 0
    for a in list_a:
        for b in list_b:
            if a and b and (a in b or b in a):
                count += 1
                break
    return count


def score_profile_compatibility(my_profile: dict, peer_profile: dict) -> tuple[int, list[str]]:
    """
    结构化字段评分，返回 (score, match_reasons)。
    score >= 3 才值得进 LLM 评估。
    """
    score = 0
    reasons = []

    my_interests   = my_profile.get("interests", [])
    peer_interests = peer_profile.get("interests", [])
    interest_hits  = _keyword_overlap(my_interests, peer_interests)
    if interest_hits:
        score += interest_hits
        reasons.append(f"兴趣交集({interest_hits}个)")

    my_needs    = my_profile.get("needs", [])
    peer_skills = peer_profile.get("skills", [])
    if _keyword_overlap(my_needs, peer_skills):
        score += 2
        reasons.append("对方技能契合我的需求")

    my_skills    = my_profile.get("skills", [])
    peer_needs   = peer_profile.get("needs", [])
    if _keyword_overlap(my_skills, peer_needs):
        score += 2
        reasons.append("我的技能契合对方需求")

    my_struggles   = my_profile.get("struggles", [])
    peer_struggles = peer_profile.get("struggles", [])
    struggle_hits  = _keyword_overlap(my_struggles, peer_struggles)
    if struggle_hits:
        score += min(struggle_hits, 2)
        reasons.append("相似困境共鸣")

    my_stage   = (my_profile.get("stage") or "").strip()
    peer_stage = (peer_profile.get("stage") or "").strip()
    if my_stage and peer_stage and (my_stage in peer_stage or peer_stage in my_stage):
        score += 1
        reasons.append(f"人生阶段相近({my_stage})")

    my_city   = (my_profile.get("city") or "").strip()
    peer_city = (peer_profile.get("city") or "").strip()
    if my_city and peer_city and my_city == peer_city:
        score += 1
        reasons.append(f"同城({my_city})")

    return score, reasons


async def find_profile_candidates(my_username: str, my_profile: dict) -> list[dict]:
    """画像级跨用户候选搜索，按兼容度评分排序，返回 score >= 3 的前 5 个。"""
    my_settings = await get_user_settings(my_username)
    my_pref = my_settings.get("match_pref", "both")

    all_profiles = await get_all_profiles()
    scored = []

    for p in all_profiles:
        peer = p["username"]
        if peer == my_username:
            continue
        if await was_recently_matched(my_username, peer, days=30):
            continue
        if my_pref in ("male", "female"):
            if p.get("gender") != my_pref:
                continue

        peer_profile = p["profile"]
        score, reasons = score_profile_compatibility(my_profile, peer_profile)
        if score >= 3:
            scored.append({
                "peer_username": peer,
                "peer_profile": peer_profile,
                "score": score,
                "match_reasons": reasons,
            })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:5]


PROFILE_EVAL_PROMPT = """你是两个Chloe的中介人——每个Chloe深度了解自己的用户。
现在你要判断：把用户 A 和用户 B 连起来，对他们有没有真实价值？

输出 JSON：
{
  "should_recommend": true | false,
  "type": "精准对接" | "互助伙伴" | "话题连接",
  "reason": "一句话说为什么连——具体，不超过25字，不透露隐私",
  "tags": ["最多3个标签"]
}

规则：
- 精准对接：一方的技能/经历恰好是另一方的需求
- 互助伙伴：双方处境相似，能互相理解和支持
- 话题连接：共同兴趣/价值观，聊起来自然
- 表面数字碰巧（如都有某个词但背景完全不同）→ should_recommend: false
- reason 要具体：不是"兴趣相似"，是"她/他也在做产品转型"
"""


async def evaluate_profile_match(
    client,
    my_username: str,
    my_profile: dict,
    candidate: dict,
) -> dict | None:
    """用双方完整画像请 LLM 评估是否值得推荐。"""
    try:
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": PROFILE_EVAL_PROMPT},
                {"role": "user", "content": (
                    f"用户 A「{my_username}」的画像：\n"
                    f"{json.dumps(my_profile, ensure_ascii=False)}\n\n"
                    f"用户 B「{candidate['peer_username']}」的画像：\n"
                    f"{json.dumps(candidate['peer_profile'], ensure_ascii=False)}\n\n"
                    f"初步评分理由：{', '.join(candidate['match_reasons'])}"
                )},
            ],
            response_format={"type": "json_object"},
            max_tokens=200,
            temperature=0.3,
        )
        data = json.loads(resp.choices[0].message.content)
        if not data.get("should_recommend"):
            return None
        return {
            "type": data.get("type", "话题连接"),
            "reason": (data.get("reason") or "").strip(),
            "tags": data.get("tags", [])[:3],
        }
    except Exception as e:
        print(f"[matcher] evaluate_profile_match failed: {type(e).__name__}: {e}", flush=True)
        return None


async def _has_recent_layer2_match(username: str, hours: int = 24) -> bool:
    """检查该用户在最近 N 小时内是否已有画像级（layer2）匹配推送，避免频繁打扰。
    早期版本用 triggered_by_message_id IS NULL 判定，但 layer1 给 B 端的卡片也是 NULL，
    会让经常被人匹配的用户自己的 layer2 永远跑不起来。改用显式 match_layer 字段。"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """SELECT COUNT(*) FROM pending_matches
               WHERE username = ? AND match_layer = 'layer2'
               AND created_at > datetime('now', ?)""",
            (username, f"-{hours} hours")
        ) as cursor:
            row = await cursor.fetchone()
    return (row[0] if row else 0) > 0


async def detect_and_save_from_profile(client, username: str) -> int:
    """
    Layer 2 完整流程：画像级匹配。
    由 extractor.py 每次更新画像后后台调用。
    返回入库的匹配数（通常 0 或 1）。
    """
    # 1. 读取画像，字段不足则跳过
    my_profile = await get_profile(username)
    filled_fields = sum(
        1 for k in ("interests", "values", "needs", "skills", "struggles", "stage")
        if my_profile.get(k)
    )
    if filled_fields < 3:
        return 0

    # 2. 24 小时冷却：避免每 5 轮就推一次
    if await _has_recent_layer2_match(username, hours=24):
        return 0

    # 3. 找画像级候选
    candidates = await find_profile_candidates(username, my_profile)
    if not candidates:
        return 0

    # 4. 评估（Layer 2 更克制，最多推 1 个）
    for candidate in candidates:
        result = await evaluate_profile_match(client, username, my_profile, candidate)
        if not result:
            continue

        main_topic = candidate["match_reasons"][0] if candidate["match_reasons"] else "画像匹配"

        await save_pending_match(
            username=username,
            peer_username=candidate["peer_username"],
            interest_topic=main_topic,
            reason=result["reason"],
            match_type=result["type"],
            tags=result["tags"],
            triggered_by_message_id=None,  # Layer 2 不关联具体消息
            match_layer="layer2",
        )
        await save_match(username, candidate["peer_username"])
        return 1

    return 0
