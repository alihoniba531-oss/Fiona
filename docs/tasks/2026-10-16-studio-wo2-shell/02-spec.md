# WO2 短片工作室：前端外壳 + 单镜试拍 + 聊天里的完成提醒

> 所属项目：Fiona「短片工作室」，12 期中的第 2 期。WO1 后端已经合入 main（bca81cd）。
> 分支和 worktree：`short-film-studio` @ `/Users/yangjing/Desktop/ai-workspace/.worktrees/fiona-studio`。前端依赖已经装好。
> **改前端之前，必须先读 `frontend/AGENTS.md`，以及 `frontend/node_modules/next/dist/docs/01-app/` 下面这几篇：**
> - `01-getting-started/05-server-and-client-components.md`
> - `03-api-reference/01-directives/use-client.md`
> - `03-api-reference/03-file-conventions/dynamic-routes.md`、`page.md`
> - `03-api-reference/04-functions/use-params.md`、`use-search-params.md`、`use-router.md`
> - `01-getting-started/16-proxy.md`

## 1. 产品目标与使用场景

作者（且只有作者）能在 Fiona 里打开「短片工作室」，完成下面几件事：
- 建项目；
- 在「镜头」页签里**试拍单镜**：上传首帧，写提示词，选模型、分辨率、时长和音频，看报价，确认后由后台生成；
- 在镜头墙上看每个任务的状态和花费，直接播放成片；
- 处理结果不确定的任务：关联控制台里的任务号，或者确认没扣费后释放额度；
- 生成结束后，聊天里收到一条提醒。

其他用户看不到入口，也访问不到任何东西。

工作室的五个阶段页签依次为：①拆解、②定妆、③分镜、④镜头、⑤成片。本期只有 **④镜头** 真正可用，其余页签显示诚实的空状态「这一阶段将在后续版本开放」，不放假按钮。

## 2. 技术与视觉约束（红线）

- **不加任何依赖**，不改 `package.json` 和 lockfile；后端也不加依赖。
- **视觉沿用现有的「宋式清雅 × 液态玻璃」**：
  - 不改 `app/globals.css` 里的令牌，不新增颜色和字体，不引入组件库。
  - `components/ui/*`（shadcn）不要用。
  - 只用这些现成原语：`<Glaze>`（`components/Glaze.tsx`）、`.ceramic-card`、`.mount-frame`、`.btn` / `.btn-primary` / `.btn-quiet` / `.btn-danger`、`.chip` / `.chip-on`、`.tag` / `.tag-rec`、`.readout`（数字用）。
  - 状态组件用 `components/novel/NovelStates.tsx` 里的 `ErrorNotice`、`EmptyState`、`LoadingState`。可以原样 import，也可以抽成通用组件，但抽的时候小说页面的行为不能变。
  - 输入框用小说工坊的写法（`components/novel/NovelModelFields.tsx:5` 的 `novelFieldClass`）。
- **对话框一律用原生 `<dialog>` + `showModal()`**，背景写 `backdrop:bg-[color:var(--scrim)]`（参照 `components/novel/NovelSettingsDialog.tsx:27,42`）。
- **状态一律用文字 `.tag` / `.chip`**；朱印只用于分身身份，状态里不用。
- **无障碍和尺寸**：可点区域不小于 40px，输入框字号不小于 16px；用 `@container` 按容器宽度排版；标题用 `tracking-[.24em]`；1440 / 1024 / 768 / 390 / 360 五个宽度下都不能出现横向滚动。
- **前端只用解析后的字段**：`items`、`params`、`usage`、`meta`，不读 `*_json` 字符串字段。
- **不改动无关模块**；已有测试一条都不能改，尤其是 `backend/tests/test_novel_p2_frontend.py`。

## 3. 前端任务

### 3.1 请求层 `frontend/lib/studio.ts`
- 照 `lib/novels.ts` 的写法封装全部工作室接口，以及第 4 节新增的接口。请求用 `apiFetch` / `apiJson`。
- 类型定义要覆盖 13 个任务状态，并给出中文标签：

| 状态 | 中文 |
|---|---|
| queued | 排队中 |
| submitting | 提交中 |
| submitted | 已提交 |
| running | 生成中 |
| succeeded | 下载中 |
| downloaded | 已完成 |
| rejected | 被拒绝（未扣费） |
| uncertain | 结果不确定 |
| failed | 失败 |
| filtered | 被内容审核拦截（未扣费） |
| expired | 结果已过期 |
| cancelled | 已取消 |
| released | 已释放（确认未扣费） |

- 已知错误码给出中文说明：`restart_during_submission`、`submission_interrupted`、`submission_error`、`poll_timeout`、`short_output`、`not_charged`。未知错误码原样显示。
- `studioHref(path, embedded)`：嵌入模式下保留 `?embed=1`，照抄 `lib/novels.ts:161` 的 `novelHref`。

### 3.2 页面
- **`frontend/app/studio/page.tsx`**：项目列表。客户端组件，用 `Suspense` 包住，写法参照 `app/novels/page.tsx`。
  - 顶部显示「今日额度」：已占用 / 日上限，以及剩余金额，用 `.readout` 显示数字。
  - 列表每项显示标题、画幅（16:9 / 9:16 用 chip）和更新时间。
  - 「新建项目」打开原生 dialog，填标题和画幅。
  - 空态、加载态、错误态都要有。
  - 访问 `/studio/access` 返回 404 时，显示「暂未开放」的空状态，不报错。
- **`frontend/app/studio/[id]/page.tsx`**：单个项目。用 `useParams` 取 id。
  - 页头显示项目名、画幅和今日额度。
  - 下面是五个阶段页签，写法参照 `NovelWorkbench.tsx:274,287`：`role=tablist`，选中项用下边框标示，**默认选中「④镜头」**。
- **嵌入模式**（`?embed=1`）：
  - 非嵌入时渲染 `<InkLandscape variant="page"/><Sidebar/>`；嵌入时不渲染这两样。
  - 提供「在新页面打开」（`target=_blank`）。
  - 按 Esc 时 `postMessage({type:"fiona-studio-close"})`，与 `NovelShell` 相同。

### 3.3 「镜头」页签：试拍面板 + 镜头墙
- **试拍面板** `components/studio/ClipComposer.tsx`：
  - 首帧：隐藏的 `input type=file`，接受 PNG、JPEG、WebP，不超过 20MB。上传前在本地校验类型和大小。上传成功后显示预览：用 `apiFetch` 取 blob 再生成 objectURL，写法可以参照 `components/GeneratedImage.tsx`。页面卸载时释放 objectURL。
  - 提示词：textarea，1–2000 字，带字数计数。
  - 模型：chip 单选「万相 3.0」（默认）/「Seedance 2.5」。
  - 分辨率：chip 单选 480P（默认）/ 720P / 1080P。
  - 时长：数字输入，默认 5 秒。合法范围用报价接口返回的 `params.duration_min_s` / `duration_max_s` 提示用户；报价接口返回 422 时，把后端给的中文 detail 原样显示出来。
  - 音频：开关，默认开。
  - 「报价」按钮：提交中禁用，防止连点。
- **报价对话框** `components/studio/QuoteDialog.tsx`，用原生 dialog：
  - 显示模型、分辨率、时长、音频，以及预估区间 `¥min–¥max`（两位小数，`.readout`）。
  - 显示今日剩余额度，以及报价剩余有效时间（倒计时到 `expires_at`；过期后确认按钮禁用，改显示「报价已过期，请重新报价」）。
  - 确认按钮文案是 **「确认生成（最多 ¥x.xx）」**；确认中禁用，并防止连点。
  - 确认返回 409 时，显示后端给的 detail，例如「超出今日上限」「报价已确认」。
  - 取消即关闭对话框，不发任何请求。
- **镜头墙** `components/studio/ShotWall.tsx` + `ShotCard.tsx`，用 `.ceramic-card` 网格，按容器宽度自适应列数。每张卡片显示：
  - 首帧缩略图，用 `params.first_frame_asset_id` 取图；
  - 模型、分辨率、时长 chip；
  - 金额：已结算显示「实付 ¥x.xx」，否则显示「预估 ¥min–¥max（预留 ¥x.xx）」；
  - 状态 tag（中文）和创建时间；
  - 状态为 `downloaded` 时，内嵌 `<video controls preload="metadata" src={API_BASE + "/studio/assets/" + result_asset_id + "/file"}>`，靠同源 cookie 访问，后端支持 Range。
  - **各状态下的操作**：
    - `queued`：「取消」，调 cancel 接口。
    - `submitted` / `running` / `needs_recheck=1` / 有 task_id 的 `uncertain`：「重新查询」，调 recheck 接口。
    - `uncertain`：醒目显示「可能已扣费，请勿直接重试，去控制台核对」（用 `.tag-rec` 或现有的警示样式，不新增颜色）。
      - 没有 task_id 时，提供「关联任务号」：输入框加按钮，调 link-task。
      - 提供「确认未扣费，释放额度」：先弹原生 dialog 二次确认，再调 release，请求体 `{not_charged:true}`。
    - `failed` / `rejected` / `filtered` / `expired` / `cancelled` / `released`：显示错误说明，并提供「用同样参数重新报价」。这个按钮**只把参数回填到试拍面板，不自动报价，更不自动提交**。
- **轮询**：
  - 只要还有任务处在 queued、submitting、submitted、running、succeeded 中的任意一个，就每 5 秒刷新一次任务列表和今日额度；页面隐藏时暂停，有操作进行中时跳过本轮。参照 `NovelWorkbench.tsx:98-115` 和 `NovelShelf.tsx:40-52`。
  - 没有在途任务就停止轮询。
  - 每次操作完成后立即刷新一次。
  - 切换账号或卸载组件时取消请求，用 `useAccountIdentity` / `useAccountRequest`。

### 3.4 侧栏与主页抽屉
- **侧栏**：`components/Sidebar.tsx` 的 `navItems` 静态数组**不改**。工作室入口在运行时追加：先请求 `GET /studio/access`，只有返回 200 时才显示「工作室」，404 或出错都不显示。图标和样式沿用侧栏已有的写法。
- **手机底栏**：360px 宽度下如果放不下第 7 项，工作室入口就不进底栏，只在桌面侧栏和直接访问 URL 时可用，并在总结里写明。
- **主页抽屉**（`app/page.tsx`）：
  - `DrawerName` 改为 `..."studio" | "novel" | null`，**必须保留 `"novel" | null` 这个子串**，已有测试会检查它。
  - 新增 studio 抽屉，写法照抄 `novel-drawer`（`:2720-2750`）：iframe 指向 `/studio?embed=1`；**只有 access 返回 200 之后才挂载 iframe**；带 `aria-hidden` / `inert`；遮罩、关闭方式、postMessage 的 origin 和 source 校验，都与小说抽屉保持一致。

### 3.5 聊天里的完成提醒（前端部分）
照抄本机监控提醒的完整做法：
- `lib/studio.ts` 里新增 `createStudioNoticePoller`，与 `lib/localWatch.ts:81-126` 一样：第一次只建立基线，不推送历史；遇到 404 就永久停止轮询；出错时保留游标，下次再试。
- `app/page.tsx`：每 10 秒 tick 一次，页面可见时才请求。
  - 提醒属于当前会话，且没有在回复或加载时，按 `localWatch.ts:128-142` 的消息形状插入：`{id:"db-"+message_id, dbId, role:"assistant", content, timestamp}`，按 dbId 去重。可以把插入函数抽成通用函数，但**本机监控的行为不能变**。
  - 提醒属于其他会话时，显示 chip「有新的工作室提醒 · 项目名」，点击后切到那个会话。
  - 可以选择性地弹系统通知，开关与本机提醒共用。

## 4. 后端任务（在 WO1 基础上只新增，不改已有行为）

1. **只读接口**（全部经过 gate，按 owner 隔离，别人的资源返回 404）：
   - `GET /studio/projects/{pid}`：项目详情。
   - `GET /studio/projects/{pid}/assets`：素材列表，不返回 rel_path。
2. **新表 `studio_notices`**：字段 id、username、project_id、job_id（**唯一**）、created_at、summary（≤200 字）、message_id、conversation_id。DDL 放进 `studio/store.py`。删号时在同一个事务里删除这张表的数据，与 WO1 的删号流程一致。
3. **何时写提醒**：调度器把任务推进到 `downloaded`、`failed`、`rejected`、`filtered`、`expired`、`uncertain` 中任意一个状态时，写一条提醒。
   - **同一个任务只写一次**（job_id 唯一约束；之后状态再变化不再写）。
   - 写提醒失败**绝不影响**任务状态和结算：只记录错误码，并在下一个 tick 补写。
   - 正文模板如下，不含任何 URL、task_id 或密钥：
     - 成功：`【短片工作室】《{项目名}》镜头已生成：{模型中文名} {分辨率} {时长} 秒，实付 ¥{x.xx}。`
     - 失败或被拒：`【短片工作室】《{项目名}》镜头未生成：{状态中文}{，原因：错误码中文说明}。未扣费的部分已释放。`（仅在确实释放了预留时，才写最后一句）
     - 结果不确定：`【短片工作室】《{项目名}》镜头提交结果不确定，可能已扣费，请到工作室核对。`
   - 写入方式照抄 `database.save_watch_alert`（`backend/database.py:1873-1910`）：写进默认会话（`resolve_chat_conversation`），调普通的 `save_message(username,"assistant",content,conversation_id)`，在 `BEGIN IMMEDIATE` 里精确找回 message_id，并检查用户仍然存在。项目和会话的绑定留到 WO3b 再做，本期统一写默认会话。
4. **`GET /studio/notices?after=<id>`**：经过 gate，响应头带 `private, no-store`，每页最多 50 条，返回 `{id, project_id, project_title, job_id, summary, created_at, conversation_id, message_id, content}`。读取方式照抄 `list_watch_alerts_with_content`（`database.py:1952-1967`）。

## 5. 测试（全部离线，沿用仓库的写法：pytest + node 转译）

前端测试放在 `backend/tests/test_studio_frontend*.py`，可以参照 `test_claude_agent_frontend.py:136-190` 的 SSR 写法和 `test_novel_p2_r1.py:17-140` 的行为探针写法。必须覆盖：

1. **侧栏**：access 返回 200 才出现「工作室」，404 不出现；`navItems` 静态数组仍然只有原来那 6 项（原有测试照样通过）。
2. **ShotCard**：13 个状态分别渲染出正确的中文标签和对应的操作按钮。
   - uncertain 时显示「可能已扣费」，释放额度前有二次确认。
   - 「重新报价」只回填参数，不发任何请求。
   - downloaded 时出现 `<video` 元素，src 指向 `/studio/assets/{id}/file`。
3. **QuoteDialog**：区间显示为两位小数，确认按钮文案正确，过期后确认按钮禁用，点「取消」不发任何请求。
4. **轮询**：有在途任务时每 5 秒请求一次；全部进入终态后停止；页面隐藏时暂停。
5. **提醒轮询器**：第一次只建基线不推送；之后的提醒按 dbId 去重插入；遇到 404 后永久停止。
6. **后端**：
   - 两个只读接口：owner 隔离，非作者返回 404。
   - `studio_notices`：
     - 每个终态写且只写一次；
     - 写入失败不影响任务；
     - 写入的会话正确，消息真实出现在 messages 表里；
     - 删号后被清理；
     - `/studio/notices` 的游标分页正确，非作者返回 404。
7. **回归**：全量测试 0 failed，已有测试一条不改。

## 6. 验收标准

- 在 `backend/` 下，用 `/Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python -m pytest -q` 跑全量，0 failed。沙箱里因为不能绑定端口而失败的项，如实列出，**不得用 deselect 掩盖**。
- 在 `frontend/` 下：`npm run lint`、`npx tsc --noEmit`、`npm run build` 全部通过。
- `git diff --name-only` 加上未跟踪文件，只包含本规格涉及的前端文件、`backend/studio/*`、`backend/routers/studio.py`、`backend/database.py`、新增的测试，以及必要的文档（按事实全库搜索后更新 CLAUDE.md、README、ARCHITECTURE）。`package.json` 和 lockfile 没有改动。
- 截图由主控在浏览器里完成，你不需要做。

## 7. 完成后输出

按以下五项输出：
1. 修改了哪些文件；
2. 实现了哪些功能；
3. 与第 3–5 节的逐条对应；
4. 测试、lint、tsc、build 的结果；
5. 未完成或需要人工确认的地方，尤其是手机底栏放不放得下这一项。
