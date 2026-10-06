# 复核 第 1 次：生图模型选择（2026-10-06）

- **复核方式**：Opus 5.5，4 个视角（规格与测试、方舟实现、前端、路由与计费），「必须修复」由反方核实。
- **主会话机械验证**：全量 `2026 passed`；tsc、build 通过，lint 25 条警告；无本机路径。
- **主会话页面走查**（隔离环境 8031/3031）：
  - 未配置 ARK 时 Seedream 按钮为灰并有提示；
  - 选择会被记住；
  - 假密钥下的错误提示与重新生成按钮正常；
  - trace 记录了 image_model，且不含提示词；
  - 375 宽下按钮高 40px，没有横向溢出。

## 结论：通过（唯一一条必须修复经反方核实降为可优化）

| 视角 | 结论 | 必须修复 | 可优化 |
|---|---|---|---|
| spec-tests | 不通过 | 1 | 6 |
| ark | 通过 | 0 | 5 |
| frontend | 通过 | 0 | 7 |
| routing | 通过 | 0 | 6 |

## 「必须修复」及反方核实

### [spec-tests] MF1：Seedream 修图「尺寸跟随图1」选尺寸时先比比例、后比面积，尺寸不规则的参考图会被放大到远超所需（最高 4.5 倍面积），且结果随输入跳变（核实：降为可优化）

- **位置**：backend/tools/image_generation.py:266-286（_ark_size：候选元组按 (ratio_error, size_error, …) 排序，286 行 min(candidates) 取最小）
- **证据**：用 httpx.MockTransport 端到端驱动 edit_image(model_id="seedream-5.0-flash")，读取实际发给方舟的 size：图1 为 959×961（921599 像素，只比下限少 1 个像素）时发出 2040x2048（4177920 像素，约为下限的 4.53 倍）；而 960×960 原样发出 960x960。1199×767 发出 1976x1264（约 2.71 倍），1001×919 发出 1856x1704（约 3.43 倍）。对 200–2048 的随机宽高抽样，1093 个需要缩放的输入里有 511 个结果面积超过下限的 1.5 倍；需要缩小的大图也同样跳变，例如 4108×4613 只缩到 976x1096，约为允许面积的 29%。原因是 8 的倍数在小尺寸下难以精确表示比例，尺寸越大比例误差越小，于是「比例最接近」压过了「面积最接近」。这类输入在生产里会出现：normalize_reference_upload 对 262144–4000000 像素、边长不超过 2048 的上传图保留原尺寸，任意裁剪图或截图都可能是 1199×767 这样的不规则尺寸。规格 §4.3 的要求是保持宽高比「缩放到范围内」，界面也写着「尺寸跟随图1」，实际却可能把只差 1 个像素的图放大 4.5 倍，属于行为错误。实施方报告「未决问题」第 2 条写了排序优先级，但没写会造成这么大的放大。§5.8 的测试只断言上下限、8 的倍数和比例误差 1% 以内，所以没有拦住。
- **修法提示**：把比例当作约束而不是首要排序键：先筛出比例误差不超过某个容差（例如 1%，或在目标面积附近能达到的最小误差加一点余量）的候选，再按与均匀缩放目标面积的差距选；也可以只在 round(width*scale/8)*8 和 round(height*scale/8)*8 附近各试几个 8 的倍数。在 test_image_model_choice.py 补断言：959×961、1199×767、1001×919 的结果面积不小于 921600，且不超过下限的约 1.1 倍；需要缩小时，结果面积接近允许上限；结果随输入单调变化。
- **反方核实**：【复现结论】放大部分属实，缩小部分在生产里走不到；规格没有要求「最小缩放」，也没有造成失败、计费或安全问题，应降为「可优化」（建议本轮顺手修）。

一、属实的部分（亲自复现）
1. backend/tools/image_generation.py:283 的候选元组是 (ratio_error, size_error, w, h)，:286 用 min(candidates) 取最小，所以比例误差排在面积之前。:274-275 的注释也明说「先取最接近的比例，再取最接近目标的面积」。实施方在 03-report.md「未决问题」第 2 条已经说明了这个优先级。
2. 用 httpx.MockTransport 端到端驱动 edit_image(model_id="seedream-5.0-flash")（打桩模型配置，假密钥，不出网）。实际发出的 size 如下：
   - 959×961 → 2040x2048，落盘也是 2040×2048；
   - 960×968 → 原样 960x968；
   - 1199×767 → 1976x1264；
   - 1001×919 → 1856x1704。
   直接调用 _ark_size：1279×720 → 2032x1144，而 1280×719 → 1296x728，结果随输入跳变。
3. 换来的比例收益可以忽略。以 959×961 为例，取 960x960 时比例误差 0.209%，面积 1.0 倍；实际选中的 2040x2048 误差 0.183%，面积 4.53 倍。1199×767 取 1200x768 时误差 0.047%，面积 1.0 倍；实际却选了 1976x1264，面积 2.71 倍。
4. 能触发的范围：utils/reference_images.py:21-23、:59-64 对 262144–4000000 像素、边长不超过 2048 的上传图保留原尺寸，更小的图用 ceil 放大到 512² 左右，产生的尺寸往往不规则。抽样结果：
   - 在 4:1 以内、262144–921599 像素的随机尺寸中，5000 个里有 2314 个超过 1.5 倍，399 个超过 3 倍，中位数 1.45 倍；
   - 小图经 ceil 放大后再送方舟，约一半超过 1.5 倍；
   - 常见规整尺寸基本不受影响，结果在 1.00–1.06 倍：640×480、800×600、1024×768、1080×720、1000×667、900×900、960×540、1024×576；
   - 1136×640 会到 1.77 倍。

二、推翻或减弱的部分
1. 缩小的例子在生产里走不到。4108×4613 → 976x1096 只是直接调用的结果，实际的参考图到不了这么大：
   - 上传图经 normalize_reference_upload 后，边长不超过 2048、像素不超过 4000000（reference_images.py:21-23、:59-64）；
   - 生成图经 _png_dimensions 校验，像素不超过 4194304（image_generation.py:355）。
   所以 edit_image 实际只会走到放大分支，「大图只缩到允许面积的 29%」不能作为生产伤害的证据。
2. 规格没有要求最小缩放。§4.3 只要求做到以下几点，实际输出全部满足：
   - 保持宽高比；
   - 「缩放到范围内」；
   - 宽高各取 8 的倍数；
   - 不超过 4624220 像素和 2048×2048。
   §5.8 的验收也只写「≥921600」。现有测试 test_image_model_choice.py:428-445 按规格断言，同样通过。因此这不是违反规格硬规则。
3. 伤害轻微：
   - 计费：方舟按张计价（规格 §2.1 写的是 0.12 元/张）；本应用按条扣固定数量的草莓（chat_service.py:27、:1242 的 STRAWBERRY_COST_PER_REPLY），与尺寸无关。
   - 体积：2040×2048 用纯噪声 PNG 测最坏情况为 12.55MB，低于 _MAX_IMAGE_BYTES（20MB）；b64 后约 16.7MB，低于 40MB 的读取上限，不会因此失败或丢图。
   - 结果：输出仍是比例正确的合法 PNG，只是分辨率高于必要。
   - 代价：文件和下载流量最多约 4.5 倍；耗时可能略增，但没有真实接口无法量化，150 秒超时余量充足。
   - 安全与隐私：无影响。

三、结论
缺陷真实存在，而且与界面上「尺寸跟随图1」的预期不符：只差 1 个像素也可能被放大 4.5 倍，结果随输入跳变。但它是一项已在报告中披露的实现取舍，符合规格字面要求，没有失败、计费、安全或隐私后果，按复核规则应归为「可优化」。

修复成本很低，建议本轮一起改：
- 改法：比例误差不超过 1%（与现有测试的 rel=0.01 一致）作为过滤条件，再按与目标面积的差距选。
- 补测：959×961、1199×767、1001×919 的面积在 921600 到约 1.1×921600 之间。

## 可优化

- [spec-tests] **O1 测试缺口：§5.9 退款测试没有正控，§5.4 没覆盖聊天层多图修图**（backend/tests/test_image_model_choice.py:483-515；:210-266）：退款测试只断言余额仍是 10，没有证明确实发生过预扣：如果 DEV_MODE 没有真正生效，余额本来就是 10，测试照样通过。我用打桩脚本补了正控：生产态下 reserve_strawberries 被调用，参数 10；Seedream 不可用时失败并退款，余额复原；换成成功桩后余额扣 10，所以现有实现没问题，只是测试本身不够硬。另外 §5.4 的 image_edit 只测了单图（字符串），聊天层多图透传成列表这一形状没有断言；我自己用 2 张参考图驱动，结果是 (prompt, [图1, 图2], None)，默认模型下没有多传任何关键字，同样没问题。
- [spec-tests] **O2 方舟参考图单独放宽到 4000 万像素，但应用管理的文件实际到不了这个上限，等于死代码**（backend/tools/image_generation.py:46、363-377、411）：生成图不超过 2048×2048；上传参考图由 utils/reference_images.py 归一化到边长不超过 2048、总像素不超过 4000000。所以新增的 _ark_reference_png_dimensions 放宽的 4000 万像素边界，以及「参考图超过项目像素上限再缩小」这条分支，在现有数据下都不会触发，徒增攻击面和维护面。规格 §4.3 原文是「沿用 _reference_image_bytes」。实施方已在报告「未决问题」第 3 条说明，建议主会话决定是删掉，还是保留并注明只为兼容旧文件。
- [spec-tests] **O3 PLAN.md 新小节放错位置**（PLAN.md:7）：其他按日期写的 ### 小节（2026-09-05 到 2026-10-05，第 17–145 行）都在「## 产品定位」下面、按时间先后排列；新的「### 2026-10-06：生图模型选择」却直接放在 H1 引言之后、「## 产品定位」之前，标题层级和时间顺序都不一致。建议挪到第 145 行「2026-10-05：危机模型复核」之后。实施方报告第 9 条说明这是有意放在前部。
- [spec-tests] **O4 两组模型按钮的 JSX 重复**（frontend/app/page.tsx:2258-2264、2274-2280）：修图分支和生图分支的「图片模型」按钮组逐字重复了 7 行。可以抽成一个局部渲染函数或小组件，以后改文案或可用性逻辑时就不会只改到一处。
- [spec-tests] **O5 列表一返回「不可用」，用户的偏好就被永久覆盖**（frontend/app/page.tsx:553 一带（setImageModel 回落）以及 527-533（写回 localStorage 的 effect））：/image-models 返回 Seedream available=false 时，界面切回默认，这一步符合规格。但随后持久化 effect 会把 qwen-image-3.0 写回 localStorage，之后管理员配好 ARK 密钥，用户原先选的 Seedream 也找不回来了。规格只要求自动切回默认，没要求保留原偏好，所以只是体验问题。如果想保留，可以只改内存里的状态，不覆盖存储。
- [spec-tests] **O6 报告的验收输出只给了尾部**（docs/tasks/2026-10-06-image-model-picker/03-report.md:59-167）：规格 §6 要求附上第 7 节验收命令的「原样输出」，报告只截了尾部；理由是避开本机路径，这个理由成立。另外 A1 在实施方沙箱里退出码为 1（6 项因绑定端口受限而失败），主会话已在正常环境重跑，全部 2026 项通过，不影响结论，仅记录在此。
- [ark] **O1 修图「尺寸跟随图1」先挑比例最准、再挑面积，结果常被放大到接近上限（最多约 4.5 倍），没有按「刚好缩放进范围」处理**（backend/tools/image_generation.py:266-286（candidates 元组 (ratio_error, size_error, w, h) 取 min，比例误差排第一））：打桩直接调用 _ark_size 实测：959×961（921599 像素，只比下限少 1）→ 2040x2048（4177920 像素）；1000×921 → 2024x1864（3772736）；1279×720 → 2032x1144（2324608）；1003×701 → 1488x1040。随机扫描 3000 个真实上传形状（26 万到 400 万像素、长边不超过 2048、比例不超过 4:1）：需要放大的图，面积最多到下限的 4.34 倍。这些结果都在 [921600, 4194304] 内、都是 8 的倍数、比例误差小于 0.2%，所以不违反规格和硬判据。但用户在「尺寸跟随图1」下拿到的输出比原图大好几倍，生成更慢、PNG 也更大。报告未决问题第 2 条已自述这一取舍。建议给比例误差设一个容差（例如 0.5% 以内都算等价），容差内选面积最接近 desired_pixels 的那个。
- [ark] **O2 方舟 200 响应里 data[0] 自带 error（例如图片未过审）时，不按审核文案提示**（backend/tools/image_generation.py:328-335）：用 MockTransport 返回 200 {"data":[{"error":{"code":"OutputImageSensitiveContentDetected"}}]}，得到的是「图片生成失败，请稍后再试。」，不是「描述或参考图未通过内容审核，请修改后再试。」。规格 §2.1 只写了顶层 error，所以不算违规。不过方舟图片接口在组图场景里会把单张图的失败放进 data[].error，单图会不会这样我拿不准。建议 encoded 为空时，如果 images[0] 带 error，就用 _ark_error(status, images[0]) 映射，等 A5 真实验收时再确认。
- [ark] **O3 只给方舟的参考图把像素上限放宽到 4000 万；当前代码产生的文件到不了这个范围，等于一条用不上的放宽**（backend/tools/image_generation.py:46、363-377、411、508）：规格 §4.3 原文是「沿用 _reference_image_bytes」。实现新增了 _ark_reference_png_dimensions（上限 40M 像素）。但应用自己管理的 PNG 已经有上限：上传参考图在 utils/reference_images.py:21-23、57-63 统一缩到不超过 400 万像素、长边不超过 2048、比例不超过 4:1；生成图在 image_generation.py:355 校验不超过 2048²。所以只有遗留文件或手工放进去的文件会走到这条放宽。实测一张 6300×6300（3969 万像素）的参考 PNG 会被方舟路径接受，并整张以 data URL 发出去；按我记得的 Seedream 4.x 文档，方舟输入上限约 6000×6000（5.0 Flash 是否相同未核实），超了只会得到泛化的「图片生成失败」，Qwen 路径则照旧拒绝。实现方已在未决问题第 3 条说明。建议删掉这条放宽，回到 _png_dimensions；或把上限降到方舟文档写的输入上限。
- [ark] **O4 把「2048×2048」理解成每边不超过 2048，比例在约 4.55:1 到 16:1 之间的参考图会被拒**（backend/tools/image_generation.py:49、253-265、299-303）：实测：4096×256、1600×100、160×10、8000×500 都报「参考图片比例无法适配 Seedream 图片尺寸」。原因是长边不超过 2048 时，像素总数要达到 921600，短边至少 450，比例最多约 4.55。规格 §4.3 写的是比例在 [1/16,16] 之内；同时 §5.8 要求 4000×1000 缩小，与按每边理解一致，所以这里有歧义，不算违规。上传的参考图已经限制在 4:1 以内（utils/reference_images.py:83-84），生成图比例也在 16:9 以内，现实中碰不到。实现方已在未决问题第 1 条说明，请主会话确认这一理解。
- [ark] **O5 方舟失败不打任何诊断日志，401/403/404/ModelNotOpen 这几种原因无法区分**（backend/tools/image_generation.py:121-134、326-327；backend/services/chat_service.py 中 except ImageGenerationError 只写 trace.error='ImageGenerationError'）：规格 §4.3 写的是「如需打印，只打印供应商名、HTTP 状态和 code」，不打印不违规。但用户开通模型后做 A5 真实验收时，鉴权失败、欠费、未开通、模型名错误在界面上是同一句文案，trace 里只有 image_model 和 'ImageGenerationError'。建议在 _ark_error 里按规格允许的范围记一行 provider=ark、status、code（code 截断并只保留白名单字符），不记 message 和请求 ID。
- [frontend] **O1 模型按钮组 JSX 原样复制了两份，以后容易改了一处忘了另一处**（frontend/app/page.tsx:2258-2264 与 frontend/app/page.tsx:2274-2280）：两段 <div role="group" aria-label="图片模型"> 逐字相同（disabled/title/onClick/className 全部重复）。行为没有问题，只是维护上的隐患。可以在 render 前抽成一个 const imageModelGroup = (...) 两处共用。
- [frontend] **O2 服务端报不可用时自动切回默认，会把 localStorage 里的偏好永久覆盖**（frontend/app/page.tsx:554 联动 :525-532）：setImageModel(current => ...available ? current : DEFAULT_IMAGE_MODEL) 改了状态以后，写入 effect 会立即把 "qwen-image-3.0" 写进 fiona_image_model。管理员临时撤掉 ARK_API_KEY 再配回来时，用户原来选的 Seedream 已经丢了。规格只要求「自动切回默认」，没有说要不要保留偏好，所以按规格不算错，可以考虑只改内存状态、不回写存储。
- [frontend] **O3 Seedream 不可用时，失败气泡上的「重新生成」仍沿用 Seedream，点了只会重复同样的失败**（frontend/app/page.tsx:1507、:1814；frontend/components/ChatBubble.tsx:87、:284）：requestImageModel = imageRetry?.imageModel ?? imageModel，重试固定用记下的模型（规格 §4.4 就是这么要求的）。但当错误本身是「Seedream 生图暂不可用，请改选 Qwen Image 3.0。」时，重试按钮没法改选模型，每次都是预扣、失败、退款，然后再出一个同样的重试按钮。按钮 title「使用相同的描述和比例重新生成」也没提到模型。主会话走查看到的「有重新生成按钮」正是这种状态。可以考虑：/image-models 已标为不可用的模型，其重试按钮置灰，或者 title 里注明所用模型。
- [frontend] **O4 按钮不可用的原因只写在 title 里，手机触屏看不到**（frontend/app/page.tsx:2259-2260、:2275-2276）：title={model.available ? model.label : "管理员尚未配置此模型"} 配合 disabled。触屏设备没有悬停提示，375 宽下用户只能看到一个灰按钮，不知道为什么不能选。规格只要求写 title，所以算达标，这一条仅属体验建议。
- [frontend] **O5 重试字段的类型写得偏宽**（frontend/components/ChatBubble.tsx:87；frontend/app/page.tsx:1507）：imageModel?: string 让 requestImageModel 退化成 string。page.tsx 里已有 ImageModelId 联合类型，可以导出后在 ImageGenerationRetry 里复用，由 TS 挡住非法值。目前值都来自 requestImageModel，运行时不会出错。
- [frontend] **O6 默认模型本身不可用时，选中且灰显的状态会一直留着（主要影响开发环境）**（frontend/app/page.tsx:554）：DASHSCOPE_API_KEY 为空时 Qwen 的 available=false，回落目标仍是 DEFAULT_IMAGE_MODEL。结果 Qwen 按钮同时是 chip-on 和 disabled，title 显示「管理员尚未配置此模型」，用户还能照常发送（服务端会报「图片生成服务尚未配置」）。生产环境必须配置 DashScope，所以影响很小。
- [frontend] **O7 聊天模式下自然语言生图会用隐藏的模型选择，界面上看不出来**（frontend/app/page.tsx:1610；frontend/components/ChatBubble.tsx:190）：chat 模式也会带 image_model（规格 D3 要求如此），但模型按钮只在生图或修图那一行显示，GeneratedImage 也没展示 generatedImage.model。用户在生图模式选了 Seedream 后回到聊天说「帮我画……」，走的是 Seedream，界面上没有任何提示。这一点符合规格，只作为体验观察记录。
- [routing] **O1 方舟失败在日志和 trace 里都没留下 HTTP 状态和 code，排查时分不清是哪一种不可用**（backend/tools/image_generation.py:121-133、:321-335；backend/services/chat_service.py 中 stream_generated_image 的 except ImageGenerationError 分支）：_ark_error/_fetch_ark_png 不打印任何内容，失败 trace 只记 error="ImageGenerationError" 和 image_model。我用 MockTransport 驱动了三种情况：方舟返回 404 ModelNotOpen（E 例）、没配 ARK_API_KEY（B 例），以及按规格同样归入这一类的 401/403。三者的用户文案、trace 字段完全相同（E 例 trace：{..."image_model":"seedream-5.0-flash","error":"ImageGenerationError"}）。用户账号现在就是 ModelNotOpen：密钥已配置，/image-models 会显示可用，但每次请求都会先预扣再退款，运维从事件表看不出是哪种原因。规格 §4.3 写的是「如需打印，只打印供应商名、HTTP 状态和 code」，所以不算违规。建议加一行安全日志，例如 [image] provider=ark status=404 code=ModelNotOpen，或者在 trace 里加 provider_status/provider_code（不含 message 和 request_id）。
- [routing] **O2 失败后点「重新生成」仍用之前记下的 Seedream，与提示「请改选 Qwen」相矛盾**（frontend/app/page.tsx:1507（requestImageModel = imageRetry?.imageModel ?? imageModel）、:1814）：界面提示「Seedream 生图暂不可用，请改选 Qwen Image 3.0。」并给出重新生成按钮。用户即使按提示把选择器切到 Qwen，点重试仍会带 image_model=seedream-5.0-flash，必然再失败一次，又是一次预扣加退款。这正是规格 §4.4「重试时优先用记下的模型」的字面要求，所以列为可优化。请主会话或用户拍板：遇到「暂不可用」这类错误时，重试改用当前选择，或者不显示重试按钮。
- [routing] **O3 方舟参考图的像素上限放宽到 4000 万，实际用不上，文档说法也有误**（backend/tools/image_generation.py:46、:363-377、:508；docs/ARCHITECTURE.md:94）：上传的参考图都会先规范化，落盘时不超过 4,000,000 像素、单边不超过 2048（backend/utils/reference_images.py:21-23、:60）；生成图按 _png_dimensions 校验，不超过 2048²。所以应用自己产生的文件根本到不了 _ark_reference_png_dimensions 放宽后的 4000 万边界。ARCHITECTURE 写「沿用上传流程的 4000 万输入像素安全边界」，把上传前的输入上限当成了落盘文件的上限。另外 _reference_image_bytes 是在 async edit_image 里同步解码的，放宽上限只会让旧文件阻塞事件循环的上限变成原来的 10 倍。实施方已把这点写进未决问题第 3 条。建议保持原有的 _png_dimensions 校验，或改正文档措辞。
- [routing] **O4 /image-models 只靠全局中间件鉴权，没有像其他路由那样再加 Depends(get_current_user)**（backend/routers/image_models.py:10-11）：实测符合规格：生产态未登录返回 401，带 JWT 返回 200，结构是 {default, models:[{id,label,available}]}，不含真实模型名和密钥变量名。不过其他需要登录的路由都用了 Depends(get_current_user)，例如 me.py 9 处、agent_exchanges.py 9 处，只有这个文件是 0 处。以后若有人调整公开前缀，这里没有第二道防线。可选：加上 user: str = Depends(get_current_user)。
- [routing] **O5 image_model 的合法取值写死在三个地方，将来容易不一致**（backend/routers/chat.py:47（Literal）；backend/tools/image_generation.py:84-95（_IMAGE_MODELS）；frontend/app/page.tsx 中 FALLBACK_IMAGE_MODELS）：现在三处一致。但如果以后登记表增删了 id 而 Literal 没同步，请求会被 422 拒绝；而且按 ARCHITECTURE 的说法，422 发生在 /chat 路由之前，危机求助资源附不上。可选：加一个测试断言 get_args(ChatRequest.image_model) 与 _IMAGE_MODELS 的键一致。
- [routing] **O6 生产态退款测试缺正控，只断言最终余额是 10**（backend/tests/test_image_model_choice.py:483-515）：测试没有证明预扣真的发生过：余额从头到尾没动过时，这条断言同样成立。我在临时目录写了脚本独立复测（TestClient 进程内运行、DEV_MODE=0、真实 JWT、余额 100、MockTransport），正控和各失败路径的结果如下。A 例（Seedream 成功）余额 -10，证明确实扣费；B 例（mode=image，没配密钥）、C 例（自然语言生图）、D 例（待补参数）、E 例（方舟 404 ModelNotOpen）、F 例（image_edit）余额变化都是 0，也就是全额退回；E 例没有残留 generated 文件。建议补一个成功扣 10 的正控，或在流中途断言余额，再补一例「方舟返回 404 走 /chat 退款」。

## 逐条核验记录

### spec-tests

- 白名单：git status --porcelain --untracked-files=all 共 15 项，都在规格 §3 白名单内；02-spec.md 是主会话提供的输入，main.py 只改了路由的导入和注册，ChatBubble.tsx 只加了 imageModel?: string 一行
- 已有测试 0 改动：git diff --stat -- backend/tests 无输出；backend/tests 下的未跟踪文件只有 test_image_model_choice.py
- 调用点穷举：grep 整个后端（不含测试），generate_image/edit_image 只在 services/chat_service.py:611/613 和 628/630 被调用，都在 stream_generated_image 里；stream_pending(825)、stream_intent(917)、mode=image/image_edit 分支(1086) 都经由这个函数。None 或默认 id 时走的那一行与 065e00a 逐字一致
- 实际驱动四条路径：用离线 TestClient 加严格签名桩 gen(prompt, ratio) 和 edit(prompt, refs, aspect_ratio=None)，在 image_model 省略或为 qwen-image-3.0 时，分别驱动 mode=image(9:16)、image_edit（1 张和 2 张）、chat 自然语言（意图桩返回 generate_image）、pending 补参，10 次全部成功且 kwargs 为空；选 seedream-5.0-flash 时 5 条路径都只多传 model_id；trace.image_model 正确且不含提示词；普通聊天不触发生图
- Qwen 路径不变：把 065e00a 版 image_generation.py 和新版放在同一个 MockTransport 下，对比 5 种生图/修图调用（默认比例、16:9、单图、三图乱序、9:16 修图），请求的方法、URL、Authorization/Content-Type 头、body 以及返回的 model/宽高完全一致；结果域名白名单相同；model_id=qwen 时走 DashScope
- 方舟契约（离线打桩）：URL、Bearer 头、body 与 §2.1 完全一致（watermark=false、output_format=png、response_format=b64_json），生图请求没有 image 字段；修图 1 张传字符串，2–3 张传有序数组，与文件字节一致；超时 Timeout(read=150)，follow_redirects=False；没有新增 print
- 错误映射补测：OutputImageSensitiveContentDetected→审核文案，429 ServerOverloaded→繁忙，403 AccountOverdueError 和 404 InvalidEndpointOrModel→不可用，InvalidParameter/502/200 空数据→通用失败；非 JSON 的 401/404/500/200 也都映射正确，文案不含原文
- 计费正控：生产态（DEV_MODE=0、JWT）下预扣确实发生（reserve 参数为 10）；未配置 ARK 时选 Seedream 返回规定文案，不出网，余额复原；成功时扣 10。计费代码没有改动
- GET /image-models：生产态匿名请求返回 401；登录后返回 {default, models:[{id,label,available}]}，未配置 ARK 时 available=false；main.py 没有把它加进公开路径
- §5 十项逐条对照测试代码：1 登记表/可用性/调用时读环境变量（122、137、149，断言了位置参数里的 model）；2 鉴权与不泄露（173）；3 未知值 422、省略为 None（193、200）；4 用 args/kwargs 严格相等断言覆盖四条路径（210）；5 用 body 全等断言方舟请求（270、300）；6 落盘与异常响应不留文件（270、328、343、355、371、380）；7 每类错误文案且不含原文（403）；8 只断言了上下限、8 的倍数和比例，没断言接近最小缩放（429、449，见 MF1）；9 退款（483，缺正控，见 O1）；10 trace（519、541、483）
- 文档：README、ARCHITECTURE、DEPLOYMENT、PLAN、CLAUDE 只改了相关句子，内容与代码一致（列表失败时两项都可选、缩放取 8 的倍数、4000 万像素、火山引擎消费告警、第二供应商隐私说明、草莓计费不变）；扫描 diff 和新文件未发现本机绝对路径（已做正控）；git diff --check 通过
- 前端：两组按钮位置符合规格（修图组在「尺寸跟随图1」之后、「全部取消」之前；生图组在比例组之后、「返回聊天」之前）；role=group、aria-label=图片模型、chip h-6 px-2 max-md:h-10、aria-pressed、disabled={isLoading || !available}、不可用时的 title 都对；localStorage 读写包了 try/catch，非法值回落默认；chat、image、image_edit 三种模式的请求体都带 image_model；重试优先用记下的 imageModel
- 复核产生的临时数据目录已清理；本次运行都设了 PYTHONDONTWRITEBYTECODE=1，工作树里最新的 .pyc 时间早于本次运行，git status 没有变化

### ark

- 通读 02-spec.md；git diff 基线 065e00a；读了 image_generation.py 全文、routers/image_models.py、chat.py/chat_service.py/main.py 的 diff、新测试中与方舟相关的部分、03-report.md、utils/reference_images.py（上传参考图的尺寸规范化）
- 自写脚本 drive.py 把 httpx.AsyncClient 替换成 MockTransport，假密钥、临时上传目录、PYTHON_DOTENV_DISABLED=1，不出网；共 100 项检查全部通过
- 生图 1:1/16:9/9:16：URL 是 https://ark.cn-beijing.volces.com/api/v3/images/generations，方法 POST；Authorization 是 Bearer <假密钥>，Content-Type 是 application/json；body 与 {model, prompt(已去首尾空格), size, response_format:b64_json, output_format:png, watermark:false} 逐字相等，键顺序与 §2.1 一致，size 用小写 x，没有 image 字段；follow_redirects=False，Timeout 为 read150/connect10/write15/pool10
- 修图：1 张时 image 是 data:image/png;base64 字符串，传单元素列表也转成字符串；2 张、3 张时是数组，顺序与输入一致，其他字段不变；指定 aspect_ratio=16:9 时 size=1536x864
- SEEDREAM_IMAGE_MODEL 在调用时读取（改环境变量立即生效，为空白时回到默认值）；可用性只看密钥是否非空，纯空白算不可用；/image-models 返回内容不含真实模型名和密钥变量名
- b64 校验：JPEG、非法 base64、带换行、带 data URL 前缀、不是字符串或为空、缺 data、data 为空列表或不是列表、元素不是 dict、像素超过 2048²（2049×2048）、PNG 头后是垃圾数据、超过 _MAX_IMAGE_BYTES、顶层是 list、非 JSON，全部变成 ImageGenerationError；上传目录前后对比无新文件，也没有 .generated_ 临时文件残留（12 次成功正好对应 12 个文件）
- _read_bounded 上限：方舟 41943040（40MB），Qwen 生成 POST 仍是 1048576，Qwen 结果下载仍是 20MB；content-length 超过 40MB 时拒绝
- 错误映射 18 例：五类审核 code、429/RateLimit/QuotaExceeded、401/403/404/ModelNotOpen/AccountOverdue/InvalidEndpointOrModel.*（包括 400 状态和 200 状态带 error 体）、InvalidParameter/500/502 非 JSON，文案都符合规格；文案里不含原始 code、message、请求 ID、提示词、密钥；每次只发一个请求，不重试
- 超时与网络异常：ReadTimeout/ConnectTimeout/asyncio 超时都提示等待超时（修图提示「图片编辑等待超时」），ConnectError/RemoteProtocolError 都提示连接不上；方舟和 Qwen 两条路径文案一致，异常链被 from None 清掉
- 不可用：没有 ARK_API_KEY 时，生图和修图都给规定文案，且不创建客户端、不发请求
- 密钥：只出现在 Authorization 头，不在 URL、body 和其他头里；在 DEBUG 级别抓取 logging，日志里没有方舟或 DashScope 的假密钥（httpx 只记请求行）
- 用 _ark_size 扫描尺寸：512×512 得到 960x960；4000×1000 和 4096×1024 得到 2048x512；960×960、1280×720 在边界上原样返回；1×4096 和 4096×1 因比例越界被拒；3000×3000、4096×4096、6000×4000 缩小后满足上限；随机 3000 个真实上传形状结果全部在 [921600,4194304] 内、都是 8 的倍数、比例误差不超过 0.18%、比例在 [1/16,16] 内；已在范围内的原尺寸按规格原样返回（可能不是 8 的倍数）
- Qwen 默认路径：_fetch_generated_bytes、_request_body、_result_image_url、_validated_result_url、_provider_error、_png_dimensions、_persist_png 的 diff 都是零；_reference_image_bytes 默认 for_ark=False 时行为不变；只有非默认 id 时 chat_service 才多传 model_id
- 40M 像素参考图实测：6300×6300 的纯色 PNG 读取约 63ms，方舟路径接受，Qwen 路径拒绝

### frontend

- 通读规格 02-spec.md §3 硬规则、§4.4 前端要求；git diff 确认前端只改了 frontend/app/page.tsx 与 frontend/components/ChatBubble.tsx（ChatBubble 只在 :87 增加 imageModel?: string，符合「只改重试类型」）
- imageModel 状态默认值：page.tsx:408 默认为 DEFAULT_IMAGE_MODEL='qwen-image-3.0'（:70）
- localStorage 读取（page.tsx:507-523）：包在 try/catch 里，用 FALLBACK_IMAGE_MODELS.find 校验，非法值回落默认；放在 microtask 里执行，并有 cancelled 守卫，StrictMode 下双挂载也安全
- localStorage 写入（page.tsx:525-532）：包在 try/catch 里，并以 imageModelLoaded 为门，避免默认值抢在读取之前覆盖旧选择；setImageModel 与 setImageModelLoaded 在同一个 microtask 里批处理，写入的就是读到的值
- 换账号或会话不重置：setImageModel 只出现在 :519、:554 和两个 onClick；换账号的重置 effect（:1253-1270）会重置 aspectRatio，但没有碰 imageModel；lib/auth.ts:111-112 退出登录只删 fiona_user 和 fiona_balance
- /image-models 拉取（page.tsx:534-560）：使用 apiFetch，等 hydrated 且有 username 后才请求；!ok、JSON 结构不对、缺少已知 id、available 或 label 类型不对时都抛错，进入 catch 后用 FALLBACK 兜底，两项都算可用；有 cancelled 守卫；依赖为 [hydrated, username]，没有遗漏
- available=false 的处理：按钮 disabled={isLoading || !model.available}，title 为「管理员尚未配置此模型」；当前选中项不可用时，用函数式 setImageModel 切回默认
- 按钮组位置：修图分支在「尺寸跟随图1」(:2257) 之后、「全部取消」(:2265) 之前；生图分支在比例组 (:2268-2273) 之后、「返回聊天」(:2281) 之前；role=group、aria-label=图片模型、aria-pressed、类名 cn("chip h-6 px-2 max-md:h-10", selected && "chip-on") 与比例按钮逐字一致；文字为 Qwen 3.0 / Seedream 5.0 Flash，title 为完整显示名；没有新增颜色或类，靠外层原有的 gap-2 分隔
- 请求体：对照 065e00a 的 page.tsx:1532-1539，conversation_id、message、image_base64、mode、aspect_ratio、reference_images 都没变，只新增 image_model: requestImageModel，chat、image、image_edit 三种模式都带；全前端只有 page.tsx:1601 一个 /chat 调用方
- 重试：page.tsx:1507 优先用 imageRetry.imageModel；:1814 失败时把 requestImageModel 写进 imageGenerationRetry；:1697 参考图归一化用 { ...imageRetry } 展开，会保留 imageModel；自然语言生图（chat 模式）失败后的重试会以 image 模式加原模型重发
- 闭包旧值：handleSend（:1495）是每次渲染都重建的普通函数，没有包 useCallback；handleSendRef 由 :1840-1842 的 effect 每次渲染后更新，所以语音路径 handleSendRef.current 和 onRetryImage 都拿到最新的 imageModel，没有依赖遗漏
- lint：在本地 node_modules 里对 page.tsx 和 ChatBubble.tsx 跑 eslint -f json，共 24 条警告，全部是旧行（未使用变量、:1495 handleSend 的 exhaustive-deps、:2230 img），本次改动的行（70-84、408-410、507-560、1507、1610、1814、2258-2280）没有新警告
- 后端衔接（只核对前端依赖的部分）：ChatRequest.image_model 用 Literal 写死两个 id，与前端 ImageModelId 一致；get_image_models 返回 id、label、available，标签与前端兜底一致；/api rewrite 与 proxy matcher 都排除了 api，sw.js 没有 fetch 缓存，不会缓存 /image-models
- 只做了读文件和对两个文件跑 eslint：未跑 pytest，未启动服务，未用浏览器，未读 .env*，未调用真实接口

### routing

- 通读 02-spec.md 和 03-report.md；git diff 065e00a 涉及 backend 4 个文件和 frontend 2 个文件，另直接读了 image_models.py 和 test_image_model_choice.py
- 硬规则「已有测试一律不改」：git diff --stat 065e00a -- backend/tests 为空，git ls-files -m backend/tests 为 0，新测试文件处于未跟踪状态
- ChatRequest.image_model 写成 Literal 两个 id、默认 None（routers/chat.py:47）。实测传真实模型名 doubao-seedream-5-0-flash-260915 返回 422，余额不变（422 发生在预扣之前）
- ChatContext.image_model 放在最后一个默认字段之后，默认 None（chat_service.py:365）。非测试代码里只有 build_context 这一处构造它（用关键字参数），build_context 用 getattr(req,'image_model',None) 填入
- 默认路径调用形状：ctx.image_model 为 None 或默认 id 时，generate_image(prompt, ratio) / edit_image(prompt, refs, ratio) 不多传任何参数。实测自然语言生图选 qwen-image-3.0 时调用参数是 (("帮我画一只橘猫","1:1"), {})；选 Seedream 时才多传 model_id
- 覆盖面：mode=image、mode=image_edit、chat 自然语言生图（explicit_image_intent→recognize_intent→stream_intent）、待补参数（stream_pending）四条路径实测都带到了 model_id=seedream-5.0-flash
- 选了不可用的模型：抛出规格规定文案「Seedream 生图暂不可用，请改选 Qwen Image 3.0。」，没有回退到其他模型，也没有出网（AsyncClient 已替换成一调用就报错的桩）
- 计费：DEV_MODE=0、真实 JWT 下做了正控，成功一次余额 -10；没配密钥、方舟 404、image_edit 失败时余额变化都是 0。STRAWBERRY_COST_PER_REPLY 和预扣/退款代码一行没改
- trace：stream_generated_image 一开始就写入 image_model（None 会映射成默认 id），成功、失败、并发忙三种情况都会带上；成功时 model 仍记真实模型名。直接查 events 表确认 payload 里不含提示词原文
- GET /image-models：全局中间件生效，生产态匿名 401，带 JWT 200；只返回 default、id、label、available，不含真实模型名和 ARK_API_KEY/DASHSCOPE_API_KEY 字样
- 危机 possible 轮：实测「画一张猫，活着没意思」并选 Seedream 时，没有调用生图，trace 记 crisis=possible，也没有写 image_model；high 轮在进入图片分支之前就返回了
- 修图的检查顺序：参考图归属先在 build_context 校验（越权返回 404 并退款，没有调用生图），之后 edit_image 才检查模型是否可用，再读参考图字节，与基线 Qwen 的顺序一致
- 方舟请求体字段与 §2.1 完全一致（model/prompt/size/response_format/output_format/watermark=false，生图时没有 image 字段）；只发一次 POST、不重试；follow_redirects=False；40MB 有界读取；b64 用 validate=True 严格解码；校验 PNG 和 20MB/2048² 上限后才落盘
- _ark_error 错误映射与 §4.3 一致，返回给用户的文案不含原始 code、message、request_id
- _ark_size 用 15953 组尺寸做了离线压力测试：凡是缩放的结果都是 8 的倍数，像素在 [921600, 4194304] 内，单边不超过 2048，比例在 [1/16, 16] 内，最大比例误差 0.19%；只有超出 4.55:1 的极端比例会报错，而上传图本身限制在 4:1 以内
- Qwen 路径：密钥报错文案、QWEN_IMAGE_MODEL 读取方式、_fetch_generated_bytes、结果域名白名单、1MB 上限都没变
- 没有其他模块调用 generate_image/edit_image；改动和新文件里都没有本机绝对路径（做过正控）；没有读 .env*，worktree 的 backend 下只有 .env.example，且未读取
- 在本会话临时目录写驱动脚本，用 TestClient 在进程内运行，PYTHON_DOTENV_DISABLED=1，危机模型关闭，用占位密钥并打桩所有出网入口；没有跑 pytest，没有启动服务，没有调用真实接口

