# -*- coding: utf-8 -*-
import json
import re

# 内存缓存 pending intent（重启清空，轻量够用）
_pending: dict[str, dict] = {}

INTENT_PROMPT = """你是意图识别器，只输出JSON，不输出任何其他内容。

支持的意图：
  open_app        打开软件         params: app(软件名)
  send_wechat     微信发消息       params: contact(联系人), message(消息内容)
  wechat_voice    微信语音通话     params: contact(联系人)
  wechat_video    微信视频通话     params: contact(联系人)
  web_search      搜索信息         params: query(搜索词)
  hot_topics      看热搜/热门话题  params: source(可选: 微博/知乎/抖音, 默认 微博)
  route           查驾车导航(同城/同省短途) params: origin(起点), destination(终点)
  travel_plan     旅行/出差规划(跨城以上,含航班/高铁/签证) params: query(原话)
  set_reminder    设置提醒         params: text(提醒内容), minutes(几分钟后, 整数)
  take_screenshot 截图             params: (无)
  get_datetime    查询时间日期     params: (无)
  write_clipboard 复制内容到剪贴板 params: content(要复制的内容)
  fetch_card      读取网页内容做成卡片(默认在Chloe里呈现) params: query(网址 URL,如 https://...)
  open_in_browser 用浏览器外部打开(仅当用户明确说"用浏览器/打开浏览器/在浏览器里"时) params: site(网站名或网址)

【核心原则 - 严格遵守】
1. 只有用户**当前消息明确要你执行一个新动作**时，才返回意图。
2. 用户在**抱怨/吐槽/反问/评价你刚才的行为**时，一律返回 intent=null。这是对话不是命令。
3. 用户**问问题、聊天、求分析、表达情绪**时，返回 intent=null。
4. 如果上下文显示你刚才已经做了某事，用户现在的消息提到同一个动作词（"打开"/"搜"/"发"等），**强烈倾向**是评价/抱怨而非新指令，返回 null。

口语识别示例（理解意图用，不要照搬）：
"帮我打开微信" → open_app, app=微信
"打开计算器" → open_app, app=计算器
"给张三发消息说明天不去了" → send_wechat, contact=张三, message=明天不去了
"给妈发条消息" → send_wechat, contact=妈, missing=[message]
"给老王打电话" → wechat_voice, contact=老王
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
"半小时后提醒我开会" → set_reminder, text=开会, minutes=30
"10分钟后提醒我喝水" → set_reminder, text=喝水, minutes=10
"截个图" / "帮我截屏" → take_screenshot
"现在几点了" / "今天几号" → get_datetime
"帮我把这段话复制好：你好世界" → write_clipboard, content=你好世界

【fetch_card 默认走这条 - 信息以卡片在Chloe里呈现,不打开浏览器】
"帮我看看 https://news.sina.com.cn 头条" → fetch_card, query=https://news.sina.com.cn
"读一下这个网页 https://..." → fetch_card, query=https://...
"看下这个商品 https://item.jd.com/xxx.html" → fetch_card, query=https://item.jd.com/xxx.html
"帮我看看这条微博 https://weibo.com/..." → fetch_card, query=https://weibo.com/...

【open_in_browser 仅当用户明确提到"浏览器"或"在外部打开"才走这条】
"用浏览器打开淘宝" → open_in_browser, site=淘宝
"帮我在浏览器里看 b 站" → open_in_browser, site=b站
"打开浏览器搜一下天气" → open_in_browser, site=天气
"在浏览器里搜 xxx" → open_in_browser, site=xxx
**注意区分**:
- "看看 xxx / 读一下 xxx / 帮我查 xxx" → 走 fetch_card 或 web_search,在卡片里呈现,不打开浏览器
- 必须出现"浏览器"这个词,才走 open_in_browser

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

【复合指令规则】（很重要，避免漏识别）
当用户说"打开微信XX/找微信XX"时，重点看后面要做什么——微信工具会自动确保微信打开，不要拆成两步：
"打开微信给张三发消息说有空吗" → send_wechat, contact=张三, message=有空吗
"打开微信给老王打电话" → wechat_voice, contact=老王
"打开微信找小美打视频" → wechat_video, contact=小美
"打开微信找张三发消息" → send_wechat, contact=张三, missing=[message]
"先打开微信再给我妈打电话" → wechat_voice, contact=妈
（只有用户单纯说"打开微信"什么都不做，才用 open_app）

缺少参数时，把已提取的放params，缺的放missing数组（按执行顺序排）。

严格输出格式（只有JSON，不加任何说明）：
参数完整：{"intent": "open_app", "params": {"app": "微信"}, "missing": []}
缺少参数：{"intent": "send_wechat", "params": {"contact": "张三"}, "missing": ["message"]}
普通对话：{"intent": null}
"""

# 缺少参数时Chloe的追问话术
MISSING_QUESTIONS = {
    "message":     "发啥内容？",
    "contact":     "找谁？",
    "minutes":     "多久后提醒？",
    "text":        "提醒你啥？",
    "query":       "搜啥？",
    "app":         "打开什么软件？",
    "content":     "你要复制什么内容？",
    "site":        "打开哪个网站？",
    "origin":      "从哪儿出发？",
    "destination": "去哪儿？",
}


def get_pending(username: str) -> dict | None:
    return _pending.get(username)


def set_pending(username: str, data: dict):
    _pending[username] = data


def clear_pending(username: str):
    _pending.pop(username, None)


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
    """调用 DeepSeek 识别意图，返回 {intent, params, missing}

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
            model="deepseek-chat",
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
