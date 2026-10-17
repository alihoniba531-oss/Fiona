# WO3d 块 D 报告：前端「②定妆」

> 分支 / worktree：`short-film-studio` @ `/Users/yangjing/Desktop/ai-workspace/.worktrees/fiona-studio`
> 范围：§7 全部（②定妆页签的挂载、门禁、开工确认、风格提案、定妆区、声线区、加载/空/错误/成功状态、390px 自适应）
> 全部实现与测试离线：无网络、无新增依赖、未 `git commit`；块 A/B/C 的文件一律未触碰。

## 1. 改了哪些文件

| 文件 | 动作 | 内容 |
|---|---|---|
| `frontend/lib/studio-casting.ts` | 新建 | §8.3 全部 TS 类型 + 请求封装（沿用 `apiJson` / `json()` 写法）+ 标签/单价/状态/轮询等纯函数 |
| `frontend/components/studio/CastingStage.tsx` | 新建 | ②定妆容器：门禁、五区块编排、5 秒轮询、G1 进度、CastingQuoteDialog 托管 |
| `frontend/components/studio/SetupCard.tsx` | 新建 | 开工确认卡（画幅只读、分辨率 `.chip`、视频模型、语言、尺寸只读、确认/修改摘要） |
| `frontend/components/studio/StyleCard.tsx` | 新建 | 风格卡（提案报价→进行中轮询→提案卡→选定；写实度单选 + 可编辑字段 + 保存） |
| `frontend/components/studio/CastingItems.tsx` | 新建 | 定妆区：`useRovingTabs` 三页签、G1 进度条、批量栏（版本数/派生/补充提示词/参考图上传/报价出图） |
| `frontend/components/studio/CastingItemCard.tsx` | 新建 | 条目卡：外形摘要/待补外形入口、状态 tag、锁定特征、版本网格、选取/归档/确认/跳过/重开、在途占位卡 |
| `frontend/components/studio/VoicePanel.tsx` | 新建 | 声线区：试听台词、≤3 方案行、生成试听（中文显示估价/英文免费）、试听列表、选定这条/已定档 |
| `frontend/components/studio/StudioAssetAudio.tsx` | 新建 | 按 asset id 取 blob → objectURL → `<audio controls>`，仅接受 `audio/*`，卸载释放 objectURL |
| `frontend/components/studio/CastingQuoteDialog.tsx` | 新建 | 原生 `<dialog>` 报价对话框：逐项、合计、模型、过期倒计时、确认 |
| `frontend/components/studio/StudioWorkbench.tsx` | 只改 index 1 | 新增 `import CastingStage`；把 `stages.map` 的 `index === 0 ? … : index === 3 ? …` 之间插入 `index === 1 ? <>{stage === 1 && <CastingStage project owner busy onBusyChange onChanged />}</>`；**其他分支零改动** |
| `backend/tests/test_studio_casting_frontend.py` | 新建 | 22 例离线 SSR / 交互 / 请求契约探针（含缺依赖 skip 守卫自测） |

未触碰任何块 A/B/C 文件；`globals.css`、`package.json`、lockfile 均未改；`BreakdownStage/Dialog/QuoteDialog、BibleTable、StudioAssetImage、studio-breakdown.ts、useRovingTabs.ts` 只读参考。

## 2. 实现了什么（与 §7 逐项对应）

`CastingStage` 是唯一顶层容器，挂载在 `StudioWorkbench` index 1；其余组件是它的纯展示/交互子件。数据来自 `getStudioCasting(id)`（§8.3 `GET /projects/{pid}/casting`），写操作通过各自的 `apiJson` 封装。

- **§7.1 门禁**：`state.g0_approved === false` 时只渲染提示「请先在①拆解批准分集方案」，其余区块一律不渲染（`test_casting_gate_hides_sections_and_shows_ssr_loading`）。
- **§7.2 开工确认卡**（`SetupCard`）：画幅只读（`sheet_size` 与 `aspect` 来自 `state.setup`/项目）；分辨率 `.chip` 单选 480P/720P/1080P，默认 480P，旁注「万相 ¥0.3 / ¥0.6 / ¥1.2 每秒」（`castingResolutionPriceNote`）；默认视频模型万相/Seedance；语言中文/英文；定妆图尺寸只读 2560×1440。「确认开工设置」→ `PUT …/casting/setup`；已确认显示摘要 + 「修改」回到编辑态。
- **§7.3 风格卡**（`StyleCard`）：「生成风格提案」→ 报价对话框（金额/模型/过期倒计时）→ 确认 `POST …/casting/style/quote` 后 `POST …/casting/style/start` → 进行中每 5 秒轮询（完成即停）→ 2–3 张提案卡，每张「选这个」→ `PUT …/casting/style {proposal_index, realism}`；选定后显示可编辑字段 + 写实度单选（写实/动漫/3D）+「保存风格」。
- **§7.4 定妆区**（`CastingItems` + `CastingItemCard`）：「人物/场景/道具」页签用 `useRovingTabs`。条目卡显示名字、外形摘要（人物 `needs_author` 时醒目提示「先补外形」并给就地编辑入口 → `PATCH /studio/bible/{id}`）、状态 tag、可编辑锁定特征、版本缩略图网格（`StudioAssetImage`，点开大图 `<dialog>`）。版本可选定（`POST /casting/items/{id}/approve`）与归档（`POST /casting/assets/{asset_id}/archive`）；条目可确认/`skip`/`reopen`。勾选多条目后出现批量栏：每项版本数（1–4）、「以选定版为参考派生」（`derive_from_approved`）、补充提示词、参考图上传（复用 `POST /projects/{pid}/assets` 拿 asset id）→「报价出图」→ `CastingQuoteDialog`（逐项：条目 × 版本数 × 单价，合计，过期倒计时）→ 确认 `POST …/casting/sheets/start`。在途出图任务以占位卡显示在对应条目版本网格里；`uncertain` 显示「可能已扣费」+「释放」（`POST /jobs/{jid}/release`），`rejected` 显示原因。G1 进度条「已确认 x / 共 y（跳过 z）」，通过显示「G1 定妆通过」。
- **§7.5 声线区**（`VoicePanel`，只列人物）：试听台词默认取该人物外形摘要首句（>40 字截断），否则「我是{名字}。」（`castingDefaultAuditionText`）。≤3 方案行，每行引擎/音色（下拉数据来自 `GET /casting/voice-catalog`）/语速/音高/特效（无 + 机器人 A–E 等）/角色类型（对白/旁白）。「生成试听」中文显示「约 ¥0.0x」（`castingAuditionCostLabel`，按 `prices.cosyvoice_cny_per_10k_chars` × 字数）、英文显示「免费」→ `POST …/casting/voices/audition`。试听列表每条一个 `StudioAssetAudio`，显示方案摘要与实测响度，「选定这条」→ `POST /casting/items/{id}/voice/approve`；已定档显示「已定档」与方案摘要。
- **§7.6 状态与视觉**：所有异步区块有加载/空/错误/成功四态，按钮忙碌禁用；`CastingStage` 在 `castingInflight(state)` 为真时每 5 秒轮询、无在途立即停（`test_casting_stage_polling_ticks_pauses_and_stops`）；沿用 `Glaze`、`ceramic-card`、`.btn`、`.chip`、`.tag`、`.readout`、原生 `<dialog>`；容器均带 `min-w-0`，390px 无横向页面滚动；未改 `globals.css`、未加依赖。

### 2.1 请求封面对照（§8.3）

`frontend/lib/studio-casting.ts` 逐条实现（路径、方法、请求体字段名逐字一致，`test_casting_request_wrappers_use_contract_paths` 断言）：

`getStudioCasting`、`putCastingSetup`(resolution/video_model/language)、`quoteCastingStyle`(`{}`)、`startCastingStyle`(quote_id)、`putCastingStyle`(proposal_index 或 custom+realism)、`patchCastingItem`(locked_features?/extra_prompt?/reference_asset_ids?)、`approveCastingItem`(asset_id)、`skipCastingItem`(`{}`)、`reopenCastingItem`(`{}`)、`archiveCastingAsset`(`{}`)、`quoteCastingSheets`、`startCastingSheets`(quote_id)、`auditionCastingVoice`、`approveCastingVoice`(asset_id)、`getCastingVoiceCatalog`。释放沿用已有 `POST /jobs/{jid}/release`。

## 3. 约束核对（§2 红线 + 用户硬性要求）

- 只改 / 新建 §9 块 D 列出的文件；`StudioWorkbench.tsx` 仅 index 1 渲染改动（`git diff` 证实为 2 行有效变更）。块 A/B/C 文件零触碰。
- 后端接口路径、字段名、类型严格按 §8.3，类型集中在 `frontend/lib/studio-casting.ts`；请求封装沿用 `lib/studio.ts` / `studio-breakdown.ts` 的 `apiJson`、`json()` 写法。
- 不联网、不新增依赖、不改 `globals.css`、不提交 git。
- 测试仿 `backend/tests/test_studio_breakdown_frontend.py`：复用 `test_studio_frontend_components.py` 的 `DRIVER`（补 `next/link` 与 `@/components/Glaze` mock），`probe()` 缺依赖即 `pytest.skip`，并有独立守卫自测 `test_dependency_guard_skips_before_starting_node`（参数化覆盖每个依赖，断言 Node 不启动）。数据用假的 `apiJson`（`env.resolve`）返回 §8.3 形状。

## 4. 自测结果

命令与结果（在 `frontend/node_modules` 完整、不隐藏的情况下执行）：

- `cd backend && /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python -m pytest -q tests/test_studio_casting_frontend.py tests/test_studio_frontend_shell.py tests/test_studio_brain_frontend.py`
  → **53 passed in 11.13s**（其中 `test_studio_casting_frontend.py` 22 例全过；`shell`/`brain` 未受影响）。
- `cd frontend && npm run lint`
  → **exit 0，0 errors / 25 warnings**；25 条警告全部为既有文件（`app/plaza/page.tsx`、`app/chat/page.tsx` 等），`grep -iE "Casting|SetupCard|StyleCard|VoicePanel|StudioAssetAudio|StudioWorkbench"` 无任何命中，即块 D 文件贡献 0 警告。
- `cd frontend && npx tsc --noEmit`
  → **exit 0**。

22 例覆盖：门禁隐藏+SSR 加载、读取错误→重试、stage 空/未选风格/就绪三态接线、开工确认默认值/确认/再编辑、风格报价→开始→轮询、StyleCard 选定/写实度/请求体（含进行中/不确定/空）、CastingItems 页签/进度/批量/报价（版本数/派生/补充/参考图上传/60 张上限）、`needs_author` 门禁拦截报价、条目卡外形/锁定/操作/预览/orphan/跳过/重开、条目卡在途占位/不确定释放、stage 轮询节拍/暂停/停止、报价对话框 SSR 逐项/合计/过期、`StudioAssetAudio` 控件+拒绝非 `audio/*`+objectURL 释放、VoicePanel 卡片默认/校验/生成/选定/英文免费/错误/加载/空、VoicePanel SSR 默认值/费用/已定档防误点、请求封装路径+请求体契约、lib 标签/费用/守卫函数。

## 5. 未完成 / 需确认

- 无未完成项，§7 全部落地。
- 需主控在集成时确认（不属块 D 范围，未自行处理）：
  1. 真实的「5 秒轮询 / 无在途即停」依赖块 A 的 `CastingState.jobs` 是否把在途任务全部包含；块 D 只按 `castingInflightStatuses = [queued, submitting, submitted, running]` 判定。
  2. `GET /casting/voice-catalog` 返回的 `fx` 键名（`robot`/`beast`/`inner`）与块 B 的 `VOICE_CATALOG`/`FX_PRESETS` 对齐情况由主控在集成测试核对；块 D 仅按 §8.3 形状渲染下拉。
  3. 参考图上传复用 `POST /projects/{pid}/assets` 返回的 asset id 语义（块 A 侧）需在集成时确认。
- 测试侧备注：`StudioAssetAudio` 用例经外层 `useAccountIdentity` 包裹后挂载其内层组件（`outer.tree.type`），因此仍直接覆盖音频组件本身；`CastingItems`「报价出图」按钮仅在至少勾选 1 个条目后出现（测试据此断言勾选前不可见）；条目名字位于子 `CastingItemCard` 的 props（扁平文本中不出现），测试用 `cardsOf(page).map(card => card.props.item.name)` 读取。
