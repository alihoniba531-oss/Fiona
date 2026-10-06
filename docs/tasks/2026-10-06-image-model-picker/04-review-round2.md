# 复核 第 2 次：第 1 轮返修核验（2026-10-06）

- **复核方式**：Opus 5.5，只核验返修 1–7 是否做到、是否正确、有无回归。
- **主会话机械验证**：沙箱外全量 `2052 passed`；tsc、build 通过，lint 25 条警告；已有测试 0 改动。
- **主会话页面走查**：
  - 方舟不可用时自动显示 Qwen，但不覆盖保存的偏好，恢复后回到 Seedream；
  - 切到 Qwen 后点「重新生成」，请求带 `qwen-image-3.0`；
  - 失败日志为 `[image] provider=ark status=401 code=AuthenticationError`。

## 结论：通过

| 条目 | 结论 | 证据 |
|---|---|---|
| 返修1 _ark_size 新算法（重点1） | 符合 | image_generation.py:254-300 改为：目标面积附近取宽、高各 5 个 8 的倍数做候选，先筛比例误差 ≤1%，再选面积最接近的；第一轮无解时扩到全宽度扫描，仍无解才按比例误差最小。在 $TMPDIR 用脚本直接调 _ark_size 共 366384 次：200–2048 随机宽高 20 万组、7×11 网格、200–12000 大图 5 万组（走缩小分支）、4–16 倍极端比例 3 万组、1–119 全格点。结果：0 异常；全部落在 [921600, 2048²]；缩放结果全是 8 的倍数且比例在 [1/16,16] 内；比例误差最大 0.99999%，没有一例超过 1%（暴力反查也确认不存在「本有 1% 解却没选」的情况）；放大最多为下限的 1.0556 倍；缩小最少为上限的 0.974 倍；已在范围内的尺寸全部原样返回。用 MockTransport 端到端跑 edit_image(model_id=seedream)，实际发出的 size：959×961→960x960，1199×767→1200x768，1001×919→1008x920，1279×720→1280x720，512²→960x960，640×160→1920x480。单次调用约 3µs。 |
| 返修1 测试 | 符合 | test_image_model_choice.py 新增以下测试：:480 四组不规则小图端到端，断言面积 ≤921600×1.1；:497 断言范围内尺寸原样返回；:502 固定 6 种比例×64 档面积，断言非递减；:534 断言缩小后面积 ≥上限×0.9。与返修单要求一致。 |
| 返修2 删除 4000 万像素放宽（重点6） | 符合 | grep 后端已找不到 _ark_reference*/for_ark；剩下的 40_000_000 只出现在 utils/media.py 和 reference_images.py，是原有的上传输入上限。_png_dimensions、_reference_image_bytes、_persist_png 三个函数与 065e00a 逐字相同（diff 只差到下一个函数签名的边界行）。edit_image 两条供应商路径都走同一句 [_reference_image_bytes(p) ...]。实测 4000×2000 参考图：Qwen 和 Seedream 都返回「参考图片内容损坏或尺寸过大」，出网请求为 0。README:116、ARCHITECTURE:94 已改为「2048² 像素上限」。 |
| 返修3 data[0].error 映射（重点3） | 符合 | image_generation.py:342-347：没有 b64_json 时，把首个图片对象交给 _ark_error(status, first_image) 映射。按「状态 × 17 种 code × 两种形状（顶层 error / data[0].error）」驱动：审核 code 都得到审核文案；data[0] 里带 ModelNotOpen 时提示「Seedream 暂不可用」；error 是字符串或 data 为空时用通用文案；顶层 200 带 code=QuotaExceeded 时提示繁忙。文案里不含原文。测试见 :466。 |
| 返修4 日志与 trace 清洗（重点2） | 符合 | _ark_error 只保留 [A-Za-z0-9._-] 并截到 80 字（:127）；只有拿到 HTTP 响应后失败，才统一 print 一行（:364）。构造的 code 包括：内嵌换行并伪造「[image] … code=FORGED」、CRLF、500 字长串、中文、引号加 shell 片段、ANSI 转义、NUL、全角字符、带重音字母、int/list/dict/None/bool，覆盖 7 种状态 × 2 种形状共 238 例。每例 stdout 都恰好一行，且完整匹配 ^\[image\] provider=ark status=\d{3} code=[A-Za-z0-9._-]{0,80}$。伪造行被压成同一行里的一个记号，没有产生新行。message、request_id、提示词、密钥从未出现在日志或异常文案里。另测：非 JSON、b64 非法、非 PNG、超过 40MB、顶层 list 都只打一行 code 为空的日志；成功不打日志；ConnectError 不打日志，provider_* 为 None。通过 stream_generated_image 驱动 404 时，trace 写入 provider_status=404（int）和清洗后的 provider_code（无换行、中文、引号、ESC），SSE 事件也不含敏感原文。Qwen 失败时 trace 不出现 provider_* 键，也没有 print。 |
| 返修5 重试用当前选择（重点4） | 符合 | page.tsx:1497 改为 requestImageModel = imageModel（当前派生选择），不再读 imageRetry.imageModel；描述、比例、参考图仍沿用 imageRetry。onRetryImage 是每次渲染新建的内联箭头函数，memo(ChatBubble) 浅比较会随之更新，所以不会拿到旧闭包。ChatBubble:285 两种 title 都写明「以当前选择的模型」；报告说明了对 §4.4 的修改和理由。 |
| 返修6 不覆盖用户偏好（重点4） | 符合 | page.tsx:407-411 把 preferredImageModel（偏好）和 imageModels（可用性）分开：imageModel = 偏好可用 ? 偏好 : 默认。全文件只有 :2012 一处 localStorage.setItem，位于按钮 onClick 里；读取在 :514。列表响应只调用 setImageModels，原来那个写回 effect 已删除。之后某次列表返回 available=true，派生值自动回到保存的偏好。 |
| 返修7 共用片段/类型/第二道鉴权/测试/PLAN（重点4、5） | 符合 | aria-label="图片模型" 在 page.tsx 中只出现 1 次。imageModelGroup（:2006）在修图分支（:2265，「尺寸跟随图1」之后、「全部取消」之前）和生图分支（:2275，比例组之后、「返回聊天」之前）各引用一次，两分支互斥，渲染一致；外层 class 与比例组相同。ImageModelId 从 ChatBubble 导出，重试字段改用该类型。image_models.py:12 加了 Depends(get_current_user)。进程内 TestClient、DEV_MODE=0 实测：匿名 401，Bearer 200，Cookie 200，伪造 token 401，200 的结构不变。get_current_user 优先读中间件写入的 request.state.user，所以不会破坏原有的 200。Literal 与登记表一致性测试见 :200；正控 :604（成功扣 10）；多图透传 image_edit_multi 断言 (prompt,[图1,图2],None) 且 kwargs 为空。PLAN 小节已移到「2026-10-05：危机模型复核」之后、「## 已实现」之前。 |
| 硬规则与回归 | 符合 | git diff --stat 065e00a -- backend/tests 无输出，已有测试 0 改动。默认模型下 generate_image(prompt, ratio) / edit_image(prompt, refs, ratio) 的调用与基线逐字一致，只有非默认 id 才多传 model_id。ImageGenerationError 新增的参数都是仅关键字、可选，现有单参数构造不受影响。git diff --check 通过。diff、新文件、任务文档里都没有本机绝对路径（grep 先做了正控）。本次复核所有运行都设了 PYTHONDONTWRITEBYTECODE、临时 DB 和 uploads，工作树状态没有变化。工作树里的 .pyc 时间是 03:32，早于本次复核，是主会话跑全量时留下的，并且已被 gitignore。 |
| 文档同步（重点7） | 符合 | README:114/116、ARCHITECTURE:86/94、PLAN 新小节已同步改动后的行为：重试用当前选择；只在用户点击时保存偏好，暂时不可用只改界面选择，模型恢复后回到偏好；8 的倍数加 1% 约束、优先最接近面积；两个供应商都用 2048² 参考图上限；日志和 trace 只含状态与清洗后的 code。grep 已找不到「记下的模型」「4000 万」「单边」这类旧说法；DEPLOYMENT 和 CLAUDE.md 也没有与新行为冲突的句子。 |

## 可优化（留待以后）

- _ark_size 只在缩放目标附近 ±2 个 8 的倍数里找候选，不保证全局面积最优。抽 2675 例和全量暴力搜索对比，有 57 例（约 2%）存在面积更接近、比例也 ≤1% 的远处候选，差距约 0.5%–3%。这符合返修单写的「就近取 8 的倍数」，也没超出 1.1 倍与 0.9 倍的界限，只作记录。
- 单调性只对精确固定比例成立。随机比例下按 round(s*r) 递增采样，400 条序列出现 838 次面积回落，最大回落 1.6%。报告已经说明没有宣称全域单调，影响可以忽略。
- 规格 §5.8 原例把 4000×1000 当作需要缩小的图；本轮按返修单的 [921600, 2048²] 改为按总像素判断，4000×1000 原样发出（每边可大于 2048），并已写进报告的未决问题。上传参考图每边不超过 2048、比例不超过 4:1，生产上走不到这条路径。建议 A5 真实验收时，顺带确认 Seedream 5.0 Flash 是否另有单边上限。
- code 不是字符串时（None、dict、list），会被 str() 后再清洗，日志里出现 code=None 或 code=xRateLimit 这类无意义记号。可以只在 code 是 str 时才记录，其余记为空。纯属美观问题。
- 供应商自己返回的 code 里如果含字母数字内容（比如回显密钥或提示词的字母部分），清洗后仍会保留。这依赖方舟的 code 是枚举值，按规格可以接受。
- 超时和连接错误不会打 [image] 日志，trace 里也没有 provider_* 字段，排查时只能看到 ImageGenerationError。可以考虑记一行 status=- code=timeout/connect，但不能伪造 HTTP 状态。
- DEPLOYMENT.md 没写 `[image] provider=ark status=… code=…` 这行日志的用途和 journalctl 检索方法；可以仿照 crisis-model 那一段补一句，方便 A5 验收和运维排查。
- 退款测试的正控是写成单独一个成功扣 10 的测试，并没有在同一个退款测试里断言中途余额。两者用的是同一套生产态夹具，已能证明预扣生效，只作记录。
- 管理员恢复密钥后，要等下一次页面加载或换账号才会重新拉列表并恢复偏好，期间不轮询。报告已说明。
