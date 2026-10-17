# R2-C 前端返修报告

- 工作区：`/Users/yangjing/Desktop/ai-workspace/.worktrees/fiona-studio`
- 依据：`08-fix-r2-common.md`、`08-fix-r2-C.md`
- 解释器：`/Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python`
- 基线：改前 `pytest -q tests/test_studio_casting_frontend.py tests/test_studio_frontend_shell.py` = 39 passed；改后 40 passed
- 未提交、未联网、未读 `.env`、未改 `globals.css`、未加依赖

## 改动文件

R2-C 清单内：`frontend/lib/studio-casting.ts`、`frontend/components/studio/SetupCard.tsx`、`StyleCard.tsx`、`CastingItems.tsx`、`CastingItemCard.tsx`、`VoicePanel.tsx`（`CastingStage.tsx`、`StudioAssetAudio.tsx`、`CastingQuoteDialog.tsx` 无需改动）、测试 `backend/tests/test_studio_casting_frontend.py`。

清单外 1 个：`frontend/components/studio/StudioAssetImage.tsx`（第 3 项必需，见「越界说明」）。

## 逐项

### 1. ISO 时间本地化

- `frontend/lib/studio-casting.ts:101-107` 新增纯函数 `formatCastingTime(value)`：用 `/[zZ]$|[+-]\d\d:\d\d$/` 判断是否已带时区，否则补 `T` / 末尾补 `Z`；`new Date()` 解析失败原样返回；成功返回本地时区 `YYYY-MM-DD HH:mm`（手写补零，不用 `toLocaleString`，避免平台差异）。
  未复用 `frontend/lib/studio.ts:130` 的 `formatStudioDate`：它是 `toLocaleString("zh-CN",{hour12:false})`，输出 `2026/10/17 04:14:52`，与 R2-C 要求的 `2026-10-17 04:14` 样式不符，故按 R2-C 许可「没有就在 `lib/studio-casting.ts` 写一个纯函数」实现。
- `frontend/components/studio/SetupCard.tsx:34`：`开工已确认：<time dateTime={setup.confirmed_at}>{formatCastingTime(setup.confirmed_at)}</time>`。
- `frontend/components/studio/VoicePanel.tsx:203`：试听行新增 `<time dateTime={audition.created_at}>创建于 {formatCastingTime(audition.created_at)}</time>`。
- 全量复查：`CastingQuoteDialog` 只显示倒计时（`quoteRemainingSeconds(quote.expires_at)`），不渲染 ISO 文本；`CastingStage / CastingItems / StyleCard / CastingItemCard / StudioAssetAudio` 无其它 ISO 文本展示。
- 测试：`test_casting_lib_labels_costs_and_guards:326`（形状正则 `^\d{4}-\d\d-\d\d \d\d:\d\d$`、`Z` 结尾、`+00:00` 结尾、空格分隔、无效输入原样、结果不含 `T`）；`test_setup_card_defaults_confirm_and_reedit:132`（断言 `开工已确认：${localStamp(...)}`，且全文不含原始 ISO）；`test_voice_panel_ssr_defaults_cost_and_approved_summary:301`（`dateTime` 属性保留 ISO，可见文本为 `创建于 ${localStamp(...)}`，原始 ISO 全页只出现 1 次）。

### 2. uncertain 提示去重

- `frontend/components/studio/CastingItemCard.tsx:90`：只保留一句「可能已扣费，请勿直接重试，去控制台核对」；`:92` 保留「释放」按钮。上游 `error_message` 与「可能已扣费」不同时（如「上游超时」）作为第二行补充显示，不再重复扣费提示。
- 测试：`test_item_card_inflight_placeholder_and_uncertain_release:238`（`body.split('可能已扣费').length-1 === 1`、含完整句、不含「可能已扣费，请勿直接重试。」；另加 `error_message='上游超时'` 用例仍只出现 1 次提示且保留原因；「释放」可点并上报 `jimg`）。

### 3. 版本图 / 参考图懒加载

- `frontend/components/studio/CastingItemCard.tsx:69,78,105`：参考图、版本缩略图、大图预览的 `StudioAssetImage` 均传 `loading="lazy" decoding="async"`。
- 越界说明：`<img>` 实际在共享组件 `frontend/components/studio/StudioAssetImage.tsx` 内（不在 R2-C 清单）。改法是加两个可选 props（`loading?` / `decoding?`，默认 `undefined` → 不输出该属性），转发到 `<img>`（`:8-16,43`）。`ShotCard` / `ClipComposer` 未传参，DOM 与改前逐字节一致，行为不变；只有定妆版本图与参考图变成懒加载。
- 测试：`test_item_card_appearance_locked_actions_and_preview:218`（从 `CastingItemCard` 取出 2 个 `StudioAssetImage`，再挂载其返回的 `AccountAssetImage`，断言 `img.props.loading === 'lazy'`、`img.props.decoding === 'async'`）。

### 4. 补充提示词文案

- `CastingItemCard.tsx:62`：条目卡 →「补充提示词（之后每次出图都会带上）」。
- `CastingItems.tsx:86`：批量栏 →「补充提示词（只对本批生效，追加在条目自己的补充提示词之后）」。
- 测试：`test_item_card_appearance_locked_actions_and_preview:218`、`test_casting_items_tabs_progress_batch_and_quote:168`（并断言旧文案「只对下一次出图生效」不再出现）。

### 5. 派生勾选禁用

- `CastingItems.tsx:35-36`：`deriveBlocked = selectedItems.some(item => !item.approved_asset_id)`、`useDerive = derive && !deriveBlocked`；`:57` 请求体改用 `useDerive`；`:85` checkbox `disabled={busy || deriveBlocked}` 且 `title` 说明原因；`:88` 渲染「所选条目里有条目还没有已选定版本，要先给这些条目「选定」一个版本才能派生。」。
- 测试：`test_casting_items_derive_gate_and_orphan_exclusion:188`（无选定版时 checkbox disabled + 提示；此时报价 payload 不含 `derive_from_approved`；换到有选定版的条目后恢复可勾选，payload 带 `derive_from_approved:true`）。

### 6. 孤儿条目

- `CastingItemCard.tsx:26`（`blocked = busy || saving || item.orphaned`）、`:44`（标签「已不在当前总表」）：勾选框、出图/试听相关操作、选定、归档、保存、跳过全部禁用。
- `CastingItems.tsx:34`：`selectedItems` 过滤掉 `orphaned`，孤儿不进批量栏、不参与报价；G1 展示直接用后端 `g1`（`:72` 文案、`:75` progressbar 的 `aria-valuemax/valuenow`），前端不自行计算。
- `VoicePanel.tsx:78`（`blocked` 含 `orphaned`）、`:138`（标签）：孤儿的生成试听 / 选定这条 / 归档 / 各输入框全部禁用。
- 测试：`test_casting_items_derive_gate_and_orphan_exclusion:188`（页面 3 个条目但后端 `g1.total=2` → `aria-valuemax=2`；勾选孤儿不计入「已勾选 N 个条目」、不改 payload）、`test_item_card_appearance_locked_actions_and_preview:218`（孤儿卡：标签存在、checkbox disabled、选定/标为不需要/归档 disabled）、`test_voice_panel_card_defaults_validation_generate_and_approve:282`（孤儿卡：标签存在、生成试听与台词输入 disabled）。

### 7. 自定义风格空值

- `StyleCard.tsx:21`（`incomplete = !!active && (!name.trim() || !visual_style.trim())`）、`:24`（`save()` 早退）、`:59`（`role="status"` 文案）、`:60`（「保存风格」`disabled={blocked || incomplete}`）。
- 测试：`test_style_card_selection_realism_and_payloads:152`（清空 name → 按钮 disabled + 提示 + 点击不触发 `onSave`；恢复之后清空 visual_style → 同样 disabled；都填好 → 恢复可点）。

### 8. 已定档试听 / 已选定版本不可归档

- `CastingItemCard.tsx:82`：版本「归档」`disabled={blocked || item.approved_asset_id === version.asset_id}`，已选定时 `title="先换选定"`。
- `VoicePanel.tsx:124-131`（新增 `archive()`，走 `archiveCastingAsset` + `onChanged`）、`:206`（每条试听「归档」按钮，`disabled={blocked || approved}`，已定档时 `title="先换选定"`）。
- 不做乐观假设：选定 / 归档 / skip / reopen 一律经 `mutate`，成功后 `refresh(true)` 用后端返回值重建 state（`CastingStage.tsx:64-77`，409 也会强制 `refresh`），前端不本地改 `approved_asset_id`。
- 测试：`test_item_card_appearance_locked_actions_and_preview:218`（已选定版本的归档 disabled + title；另一版本可归档；孤儿归档 disabled）、`test_voice_panel_card_defaults_validation_generate_and_approve:282`（未定档试听归档可点 → POST `/casting/assets/aud-0/archive`、body `{}`；定档后该按钮 disabled + `title='先换选定'`，「选定这条」也 disabled）、`test_voice_panel_ssr_defaults_cost_and_approved_summary:301`（SSR 含「归档」按钮）。

## 与 R2-A 后端口径的依赖

- G1 只读后端 `state.g1`（R2-A 让孤儿不计入 G1）；前端不复算。
- skip / reopen 由 R2-A 清空 `approved_asset_id`；前端 mutation 后 `refresh(true)`，界面以后端为准，「归档/选定」随之解锁。
- 前端已禁掉孤儿的出图/试听/勾选，对应 R2-A 的 409 兜底。

## 测试结果

```
cd backend && <py> -m pytest -q tests/test_studio_casting_frontend.py tests/test_studio_frontend_shell.py
→ 40 passed in 8.33s
cd frontend && npx tsc --noEmit      → exit 0（0 error）
cd frontend && npm run lint          → 0 error（25 warning，全部在 app/page.tsx、app/plaza/page.tsx，与本次改动无关）
```

先失败验证（红-绿）：把 8 项修复逐一回退后重跑对应测试，全部按预期失败——懒加载属性、风格空值 disabled、试听归档 title、孤儿 disabled、uncertain 去重、SetupCard 本地化、孤儿剔除批量栏、派生禁用。脚本：`/tmp/verify_fail.py`。

## 未完成 / 其它

- 可优化 l（试听条数上限）按公共说明不做；缩略图生成留 WO5，本期仅懒加载。
- 唯一越界改动：`StudioAssetImage.tsx`（两个可选 props，向后兼容），原因见第 3 项；如主控要求绝对不碰清单外文件，可改为在 `CastingItemCard` 内自带取 blob 的图片组件（会重复鉴权/blob 逻辑，不推荐）。
- 未提交（按约定）。
