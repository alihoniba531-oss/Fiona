# -*- coding: utf-8 -*-
import json
import time as _time

from fastapi import APIRouter, Query, Request

from llm import QWEN_CLIENT, client
from rate_limit import limiter
from tools.hot_topics import hot_topics

router = APIRouter()


@router.get("/hot/expand")
@limiter.limit("20/minute")
async def hot_expand(request: Request, title: str = Query(default="", max_length=200)):
    """把一个热搜标题展开成结构化内容卡（千问联网检索）。
    注意：此路由必须注册在 /hot/{source} 之前，否则被泛匹配吃掉。
    限流 20/分钟/IP：匿名可访问且触发 LLM 联网外呼，防钱包型 DoS；request 供 slowapi 取 key。"""
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
# 用 qwen-plus 整批理解一次。同批标题 5 分钟内不重复调。
CATEGORIES_DISPLAY = ["娱乐", "经济", "生活", "科技", "文化"]
_CLASSIFY_TTL = 300
_classify_cache: dict[int, tuple[float, dict[str, str]]] = {}

_BATCH_CLASSIFY_PROMPT = """你是热搜分类器，只输出 JSON 对象。

给你一批热搜标题（每行一个），把每条归到下面 5 类之一：
- 娱乐：明星 / 影视 / 综艺 / 音乐 / 网红 / 八卦 / 选秀
- 经济：股市 / 楼市 / 企业 / 消费 / 就业 / 价格 / 货币 / 贸易 / 财报
- 科技：AI / 芯片 / 互联网 / 航天 / 汽车工业 / 新能源 / 机器人 / 5G/6G / 量子 / 工业制造
- 文化：教育 / 高考 / 读书 / 艺术 / 传统 / 历史 / 考古 / 文物 / 宗教 / 思想
- 生活：美食 / 健康 / 宠物 / 旅行 / 穿搭 / 运动 / 婚恋 / 家庭 / 灾难 / 政策 / 民生 / 法律 / 犯罪 / 外交 / 体育赛事 / 国际新闻

规则：
- 一条标题只能归一类，挑最贴的
- 严格输出 JSON：{"标题原文": "类别", ...}
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
    if cached and now - cached[0] < _CLASSIFY_TTL:
        return cached[1]
    try:
        resp = QWEN_CLIENT.chat.completions.create(
            model="qwen-plus",
            messages=[
                {"role": "system", "content": _BATCH_CLASSIFY_PROMPT},
                {"role": "user", "content": "\n".join(titles)},
            ],
            response_format={"type": "json_object"},
            max_tokens=2000,
            temperature=0.1,
        )
        raw = resp.choices[0].message.content or "{}"
        data = json.loads(raw)
        if not isinstance(data, dict):
            return {}
        clean = {str(k): str(v) for k, v in data.items() if str(v) in CATEGORIES_DISPLAY}
        _classify_cache[key] = (now, clean)
        return clean
    except Exception as e:
        print(f"[hot/categorized] LLM classify failed: {type(e).__name__}: {e}", flush=True)
        return {}


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
    for d in results:
        if isinstance(d, Exception) or not isinstance(d, dict):
            continue
        for pt in d.get("points", []):
            # 去掉 "1. 标题 · 热度" 里的序号
            title = pt.split("·")[0].strip().lstrip("0123456789. ")
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

    return {"categories": buckets}
