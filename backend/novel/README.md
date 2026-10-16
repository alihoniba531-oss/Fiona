# 小说工坊 P0

可复用的 asyncio 多智能体剧情推演原型，只有离线脚本与运行文件，不接数据库、接口或前端。智能体决定剧情，代码固定提案、互评、裁决、写作、审校与归档的顺序、校验和停止条件。

所有命令在仓库 `backend/` 目录执行，解释器固定为：

```bash
PY=/Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python
PYTHONDONTWRITEBYTECODE=1 "$PY" -m pytest -q -p no:cacheprovider tests/test_novel_*.py
"$PY" -m novel.pilot run --config novel/pilot_configs/expA.json --out /tmp/novel-p0-A --dry-run
"$PY" -m novel.pilot run --config novel/pilot_configs/expB.json --out /tmp/novel-p0-B --dry-run
"$PY" -m novel.pilot run --config novel/pilot_configs/expC.json --out /tmp/novel-p0-C --source-run /tmp/novel-p0-A --dry-run
"$PY" -m novel.pilot run --config novel/pilot_configs/expA2.json --out /tmp/novel-p0-A2 --dry-run
"$PY" -m novel.pilot report --out /tmp/novel-p0-B
```

`--dry-run` 全部使用本地 fake，不读取密钥、不构造真实客户端、不触发环境守卫。默认 B 在第 9 章完结。fake 的用量单位是字符，另生成并打印真实调用的 token 上界估算表：按观察到的调用轨迹，输入每字符算 1 token，输出取角色 `max_tokens`；实际模型改变章节数或修订次数时需要重新估算。

`panel_mode` 可选 `merge` 或 `critique`，缺省为 `merge`，只影响实验 A 的 panel 组及实验 B。merge 继续使用原提案、评分、裁决流程；solo 始终由主编独自构思。critique 依次执行主编初案 `01-plan-editor.json`、并行顾问挑错 `02-critique-plan-{role}.json`、主编定稿 `03-finalize-editor.json`，不打分。代码按配置顺序分配 O* 意见及 A* 替代走向，定稿必须逐条回应；后续写手只接收定稿细纲，两组写手输入键一致。

`expA2.json` 使用新的家庭悬疑思路、50–70章目标和每章2000字，两组各试写5章；panel 使用critique，人物代言人为豆包。章节会议保存初案、顾问意见及定稿，报告展示严重度、替代走向、回应和初案/定稿字段差异，盲读文件仍只有正文。主编decision、plan、finalize共享“每章最多一个关键揭示”的提示要求，不增加语义硬校验。

`--max-total-tokens` 默认为 3000000。每次调用前检查已用量、在途预留、本次输入字符数和输出上限；预算不足不会发出该调用。使用相同 `--out` 并放宽预算可续跑，成功步骤不会重复调用或重复记账。故事配置或 dry-run 模式变化时必须更换输出目录。不要在同一个输出目录同时启动两个进程。

`--prices prices.json` 是可选参数，`run` 与 `report` 都接受。格式如下，价格完全由使用者提供：

```json
{"provider:model": {"input_per_mtok": 0, "output_per_mtok": 0, "currency": "USD"}}
```

不传价格时只有用量表；支持 USD、CNY，缺少价格的模型会明确标注。退出码：0 完成，2 配置或环境错误，3 预算耗尽，4 步骤失败或裁决不合法。

提供方支持 `dashscope`、`deepseek`、`anthropic`、`ark` 和离线 `fake`。真实配置仅检查实际使用提供方的 `DASHSCOPE_API_KEY`、`DEEPSEEK_API_KEY`、`ANTHROPIC_API_KEY` 或 `ARK_API_KEY`。存在非空 `ANTHROPIC_BASE_URL`、`ANTHROPIC_AUTH_TOKEN`、`ANTHROPIC_CUSTOM_HEADERS`、`OPENAI_BASE_URL` 时，真实配置启动即拒绝。离线验证不需要任何密钥；本次交付没有执行真实提供方。

按作者要求，三份默认实验配置的写手和人物代言人改用 `deepseek:deepseek-flash`。DeepSeek 不设型号白名单，`deepseek-v4-pro` 仍可自行配置；价格继续由外部价格文件提供，不在代码中硬编码。

火山方舟（豆包 Doubao-Seed-2.1-pro）推荐模型规格为 `ark:doubao-seed-2-1-pro-260915`，也支持往期 `ark:doubao-seed-2-1-pro-260628`，密钥变量为 `ARK_API_KEY`。可将这两种规格分配给任意智能体，或填入实验C的 `reviewers_to_compare`。其余方舟型号以「火山方舟型号未在白名单内」退出2，dry-run也执行型号校验。默认expA/B/C未采用豆包，是否采用豆包由作者决定。

方舟走 `https://ark.cn-beijing.volces.com/api/v3` 的OpenAI兼容Chat Completions，显式传角色的 `max_tokens`，通过 `extra_body` 传 `thinking={"type":"disabled"}`；JSON输出使用 `response_format={"type":"json_object"}`，Markdown不传该字段，不传频率或存在惩罚。用量、缓存token、截断、拒答、预算与重试复用统一流程；价格仍只能由外部价格文件提供。dry-run的ark角色同样进入用量、成本和估算表。

输出结构：

```text
<out>/manifest.json                配置、哈希、状态、时间与完结指标
<out>/setup/steps/                 setup 原始响应及校验结果
<out>/setup/compass.json
<out>/setup/bible_v1.json           A 两组共享的初始圣经
<out>/arm-{solo,panel}/ch001/       每次模型调用的原子步骤记录
  chapter.md                      最终正文
  bible_before.json               写本章之前的圣经（C 使用第4章的此版本）
  bible_v2.json                    归档之后的圣经
  flags.json
  chapter_record.json             可重建报告的章节结构化记录
<out>/usage.jsonl                  每次实际尝试一行，包括失败尝试
<out>/report.md                    章节过程、裁决及实验指标
<out>/cost.md                      按实验×角色×模型、按章节的两张表
<out>/estimate.md                  dry-run 观察轨迹的上界估算
<out>/blind/                       A 的纯正文甲乙版本、说明和随机 key.json
<out>/source/                      C 的原稿、章前圣经、细纲快照
<out>/control/                     C 的三处插入、污染稿和审校步骤
<out>/comparison.json              C 的抓到数与原稿误报数
```

A 的甲乙映射使用 `random.SystemRandom`，续跑复用已有 `key.json`。盲读文件不含推演记录；阅读说明只列四个评判维度。B 的完结指标以档案员处理完成后的圣经为准。C 的污染句不会作为答案发给审校，抓到与否只由正文证据的连续子串匹配计算。

`FakeLLM(script=...)` 支持 `callable(request, one_based_index)`、全局响应列表或按 `step_key`／`task`／`role` 索引的响应序列。返回 `None` 使用默认响应，返回字典生成 JSON，字符串保持原样，异常实例模拟失败；`calls` 与 `call_count` 可检查是否实际调用。续跑保留失败尝试的审计用量，最终正文和圣经由缓存结果重建。

模块不在导入时加载 `.env`、读取密钥或创建客户端。审校证据无效时丢弃；风格及改编问题不阻断；最多修订两轮。长度二次不达标、未解决审校、锁定冲突和细纲偏离只记录标记，P0 继续归档。真实创作质量、作者盲评、供应方实际模型可用性及用量成本需要后续人工验证。

第1轮返修后，Sonnet 5.5 使用 `thinking={"type":"between_tools"}`，Haiku 5.5 使用 `thinking={"type":"disabled"}`，均不传 `output_config`。Opus 5.5 无法关闭思考，会在真实配置启动时提示；未知 Claude 型号在检查密钥前退出2。上述请求参数只通过 SDK 与 MockTransport 离线验证。

`stop_reason` 同时保存在用量和步骤记录中。拒答不重试；截断提示模型压缩内容，并与 JSON/schema 修正共用一次机会。修正前回放上一轮 assistant 输出，空输出使用占位文本。失败时 manifest、报告和 stdout 都列出 `failed_step`；异常诊断只记异常类名和 HTTP 状态码。

推演输入只含简报及阶段所需字段；写手不接收裁决过程，A 两组的写手输入键一致。原始思路保留在罗盘；章节审校和 C 审校使用相同的临时圣经包携带一份罗盘，不改变持久化圣经。

进入校验前先复制并规范化整数年龄、可选空值、非收束状态下缺省的剩余章数及多条已知信息。生产写作先去代码围栏、规范或补齐章节标题，再验证规范格式；低层严格标题检查函数保留。审校证据与 C 匹配统一处理引号、省略号和空白。C 的引文类别核对只记录 `citation_check`，不因引文不足而停止；数量和唯一、互异的锚点仍须通过校验。

第2轮返修统一要求JSON角色在字符串值内部用中文直角引号「」引用，格式修正时再次提醒；Markdown写手不受这条JSON规则限制。审校顶层对象及issues列表仍严格校验，单条问题其他字段缺失或类型错误时仅记入dropped_issues，不阻断章节。仅缺blocking或其值为null时，合法问题保留为非阻断，并由代码标记blocking_defaulted。任一轮非空问题全部被丢弃时标记review_degraded；合法空issues不属于降级。章节记录和报告累计展示丢弃数及保留问题的blocking_defaulted数。审校提示只允许三类明显问题阻断，排除同义措辞、中文/阿拉伯数字和详略差异；复审携带上一轮有效阻断问题，优先核对修复，实验C仍为单轮。

写手每次收到具体的length_range及相同数字的系统提示，例如目标1500字时为900–2400字；长度重写另附上一稿去空白后的实测字数和超出/不足方向。审校最多修订两轮、长度最多重写一次和最终标记规则保持不变。证据目录不会被原型的离线验证改写；需要重新验证真实模型的误报和长度表现时，由作者另行授权。

标题规范化同时识别阿拉伯和常见中文章号；紧接首行、仅隔空行的同章同名重复标题只删一行。异章标题保留原文并前插规范首行，正文其余内容不改。
