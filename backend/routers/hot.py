# -*- coding: utf-8 -*-
import json
import re
import time as _time

from fastapi import APIRouter, Depends, Query, Request

from auth_dep import get_current_user
from llm import QWEN_CLIENT, QWEN_MODEL, QWEN_EXTRA_BODY
from rate_limit import limiter
from tools.hot_topics import hot_topics

router = APIRouter()


@router.get("/hot/expand")
@limiter.limit("20/minute")
async def hot_expand(
    request: Request,
    title: str = Query(default="", max_length=200),
    _user: str = Depends(get_current_user),
):
    """把一个热搜标题展开成结构化内容卡（千问联网检索）。
    注意：此路由必须注册在 /hot/{source} 之前，否则被泛匹配吃掉。
    会触发 LLM 联网外呼，必须登录（中间件与本依赖双重校验），
    另限流 20/分钟/IP 防刷；request 供 slowapi 取 key。"""
    import asyncio
    from tools.topic_expand import topic_expand
    return await asyncio.to_thread(topic_expand, title)


@router.get("/hot/{source}")
@limiter.limit("20/minute")
async def hot_endpoint(request: Request, source: str = "微博"):
    """直接给前端拉热搜（广场角落 HUD 用）。source: 微博 / 知乎 / 抖音 / B站 / 头条
    限流 20/分钟/IP：匿名可访问且触发外呼，防刷爆；request 供 slowapi 取 key。"""
    import asyncio
    return await asyncio.to_thread(hot_topics, source)


# ── 热搜分类关键词表 ──────────────────────────────────────────────
# 顺序敏感：按从上到下的优先级匹配（"历史"放"文化"前，因为"考古文物"应归历史不是文化）
_CAT_KEYWORDS: dict[str, list[str]] = {
    "娱乐": ["明星","演员","电影","电视","综艺","音乐","歌","剧","艺人","娱乐","演唱会",
             "舞台","歌手","主持","直播","网红","粉丝","偶像","选秀","剧情","笑","搞笑"],
    "经济": ["经济","股","市场","企业","房价","就业","贸易","工资","GDP","美元","人民币",
             "基金","投资","楼市","消费","通货","价格","出口","进口","利率","银行","上市"],
    "生活": ["美食","吃","餐","菜","厨","饮","咖啡","奶茶","早餐","晚餐","外卖","美妆","穿搭",
             "衣","鞋","健身","跑步","瑜伽","养生","睡眠","旅行","旅游","民宿","景点","宠物",
             "猫","狗","婚","恋爱","母婴","育儿","健康","看病","医生","本田","汽车","品牌"],
    "历史": ["历史","朝代","古代","唐代","宋代","明代","清代","秦","汉","三国","春秋","战国",
             "史记","史书","古人","古迹","遗址","文物","考古","出土","王朝","皇帝","战役",
             # 高频帝王名（用全名避免单字误中）
             "朱棣","朱元璋","朱高炽","朱高煦","李世民","赵匡胤","康熙","乾隆","嘉靖","雍正",
             "嬴政","刘邦","项羽","曹操","孙权","刘备","诸葛亮","武则天","唐玄宗","赵高",
             # 高频朝代/政治词
             "传位","皇位","登基","太子","太监","宦官","江山","御史","封建","科举","丝绸之路",
             "鸦片战争","辛亥","太平天国","民国","军阀"],
    "哲学": ["哲学","思想","思考","人生","意义","本质","存在","自由","信仰","禅","佛","道家",
             "儒","释","老子","庄子","孔子","苏格拉底","柏拉图","尼采","形而上","悟","觉悟",
             # 思辨/价值类常见词（知乎热榜很多）
             "为什么","如何理解","怎么看待","怎么理解","真相","对错","善恶","价值观","伦理",
             "道理","道德","内心","选择","命运","活着","死亡","幸福","痛苦","孤独"],
    "科技": ["AI","人工智能","科技","手机","互联网","芯片","航天","火箭","卫星","苹果",
             "华为","特斯拉","机器人","算法","大模型","ChatGPT","数据","云","数字","无人机",
             "Token","物理","物理学","浮力","量子","光速","引力","元素"],
    "文化": ["文化","教育","学校","大学","考试","高考","传统","非遗","节日","博物",
             "读书","文学","艺术","诗词","成语","汉字","语言","中医","国潮","习俗"],
    "时事": [],  # 兜底：未匹配到上面任何类的全归到时事
}

def _classify_topic(title: str) -> str:
    # 优先级显式声明：具体类别先匹配，"哲学"放最后做思辨兜底
    # （"哲学"的关键词里有"为什么/如何理解"这种问题前缀，太宽，
    #  必须让具体类如"科技/历史"先抢走，否则一道"为什么浮力..."会被归到哲学）
    order = ["娱乐", "经济", "生活", "历史", "科技", "文化", "哲学"]
    for cat in order:
        kws = _CAT_KEYWORDS.get(cat, [])
        if any(kw in title for kw in kws):
            return cat
    return "时事"


# ── LLM 整批分类（5 分钟缓存）──────────────────────────────────────
# 关键词字典覆盖不全（新词跟不上 / 顺序敏感把模糊词归错），
# 用轻量模型整批理解一次，只返回编号，避免完整榜单重复输出标题耗尽预算。
CATEGORIES_DISPLAY = ["娱乐", "经济", "生活", "科技", "文化"]
_CLASSIFY_TTL = 300
_classify_cache: dict[int, tuple[float, dict[str, str]]] = {}

_BATCH_CLASSIFY_PROMPT = """你是热搜分类器，只输出 JSON 对象。

给你一批带编号的热搜标题，把每条归到下面 5 类之一：
- 娱乐：明星 / 影视 / 综艺 / 音乐 / 网红 / 八卦 / 选秀
- 经济：股市 / 楼市 / 企业 / 消费 / 就业 / 价格 / 货币 / 贸易 / 财报
- 科技：AI / 芯片 / 互联网 / 航天 / 汽车工业 / 新能源 / 机器人 / 5G/6G / 量子 / 工业制造
- 文化：教育 / 高考 / 读书 / 艺术 / 传统 / 历史 / 考古 / 文物 / 宗教 / 思想
- 生活：美食 / 健康 / 宠物 / 旅行 / 穿搭 / 运动 / 婚恋 / 家庭 / 灾难 / 政策 / 民生 / 法律 / 犯罪 / 外交 / 体育赛事 / 国际新闻

规则：
- 一条标题只能归一类，挑最贴的
- 严格输出 JSON：{"娱乐": [1, 6], "经济": [2], "科技": [3], "文化": [4], "生活": [5]}
- 列表只填输入中的整数编号，每个编号出现一次，不重复输出标题，不补充新闻
- 不解释，不 markdown，不加其他文字
- 标题列表为空时输出 {}
"""


def _classify_with_llm(titles: list[str]) -> dict[str, str]:
    """整批 LLM 分类。失败/超时 → 空 dict，调用方走关键词 fallback。"""
    if not titles:
        return {}
    key = hash(tuple(titles))
    now = _time.time()
    cached = _classify_cache.get(key)
    if cached and now - cached[0] < (_CLASSIFY_TTL if cached[1] else 30):
        return cached[1]
    clean: dict[str, str] = {}
    try:
        # 分类是辅助步骤；不能因模型重试而让已抓到的榜单一直不显示。
        resp = QWEN_CLIENT.with_options(timeout=8.0, max_retries=0).chat.completions.create(
            model=QWEN_MODEL,
            messages=[
                {"role": "system", "content": _BATCH_CLASSIFY_PROMPT},
                {"role": "user", "content": "\n".join(f"{i}. {title}" for i, title in enumerate(titles, 1))},
            ],
            response_format={"type": "json_object"},
            max_tokens=2000,
            temperature=0.1,
            extra_body=QWEN_EXTRA_BODY,
        )
        raw = resp.choices[0].message.content or "{}"
        data = json.loads(raw)
        if isinstance(data, dict):
            assignments: dict[int, set[str]] = {}
            for category, indices in data.items():
                if category not in CATEGORIES_DISPLAY or not isinstance(indices, list):
                    continue
                for index in indices:
                    if type(index) is int and 1 <= index <= len(titles):
                        assignments.setdefault(index, set()).add(category)
            clean = {titles[index - 1]: next(iter(categories))
                     for index, categories in assignments.items() if len(categories) == 1}
    except Exception as e:
        print(f"[hot/categorized] LLM classify failed type={type(e).__name__}", flush=True)
    if len(_classify_cache) >= 32:
        _classify_cache.pop(next(iter(_classify_cache)))
    _classify_cache[key] = (_time.time(), clean)
    return clean


@router.get("/hot/categorized/all")
@limiter.limit("5/minute")
async def hot_categorized(request: Request):
    """返回按类别分类的热搜，供广场分类卡片使用。
    源：微博 + 抖音 + 知乎 + B站 + 头条。
    多源并行拉，单源失败不影响其他。"""
    import asyncio
    results = await asyncio.gather(
        asyncio.to_thread(hot_topics, "微博"),
        asyncio.to_thread(hot_topics, "抖音"),
        asyncio.to_thread(hot_topics, "知乎"),
        asyncio.to_thread(hot_topics, "B站"),
        asyncio.to_thread(hot_topics, "头条"),
        return_exceptions=True,
    )

    all_titles: list[str] = []
    source_errors: list[str] = []
    updated_times: list[str] = []
    stale = False
    for source, d in zip(["微博", "抖音", "知乎", "B站", "头条"], results):
        if isinstance(d, Exception) or not isinstance(d, dict) or d.get("error"):
            source_errors.append(source)
            continue
        if d.get("stale"):
            stale = True
            source_errors.append(source)
        if isinstance(d.get("updated_at"), str):
            updated_times.append(d["updated_at"])
        items = d.get("items")
        if isinstance(items, list):
            titles = [it.get("title", "") for it in items if isinstance(it, dict)]
        else:
            # 兼容旧卡片，仅移除榜单序号与末尾热度，不截掉年份或标题里的中点。
            titles = [re.sub(r"\s+·\s+[\d.,]+\s*[万亿]?(?:\s*热度)?$", "",
                             re.sub(r"^\s*\d+\.\s+", "", pt)).strip()
                      for pt in d.get("points", []) if isinstance(pt, str)]
        for title in titles:
            if not isinstance(title, str):
                continue
            title = title.strip()
            if title:
                all_titles.append(title)

    # 去重保序
    seen: set[str] = set()
    unique: list[str] = []
    for t in all_titles:
        if t not in seen:
            seen.add(t)
            unique.append(t)

    # LLM 整批分类（带缓存）；漏归 / 失败的标题走关键词 fallback
    llm_map = await asyncio.to_thread(_classify_with_llm, unique)
    _fallback_map = {"历史": "文化", "哲学": "文化", "时事": "生活"}

    buckets: dict[str, list[str]] = {c: [] for c in CATEGORIES_DISPLAY}
    for title in unique:
        cat = llm_map.get(title)
        if cat not in CATEGORIES_DISPLAY:
            kw_cat = _classify_topic(title)
            cat = _fallback_map.get(kw_cat, kw_cat)
            if cat not in CATEGORIES_DISPLAY:
                cat = "生活"
        if len(buckets[cat]) < 5:
            buckets[cat].append(title)

    error = not unique
    message = ""
    if error:
        message = "热点暂时拉取失败，请稍后重试"
    elif stale:
        message = "部分榜单更新失败，保留上次成功获取的内容"
    elif source_errors:
        message = "部分来源暂不可用，已显示其他来源的热点"
    return {"categories": buckets, "error": error, "message": message,
            "stale": stale, "source_errors": source_errors,
            "updated_at": min(updated_times) if updated_times else None}
