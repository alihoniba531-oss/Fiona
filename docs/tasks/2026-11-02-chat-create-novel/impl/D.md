# 实现记录 D：前端向导预填（T6）

- 代理：D（workflow `parallel()` 派发）
- 负责文件：`frontend/components/novel/NovelWizard.tsx`、`frontend/lib/novels.ts`
- 未触碰聊天卡片、页面、既有测试；未运行 git 写操作。

## 实现

1. `lib/novels.ts`：`NovelDraft` 类型、`NovelCreateInput.draft_id?: string`、`getNovelDraft(id, signal)`（`GET /novels/drafts/{id}`）。
2. `NovelWizard.tsx`：
   - 顶层 `useSearchParams().get("draft")`，`/^[0-9a-f-]{36}$/` 合法才传给内部 Wizard；
   - `load` 用 `Promise.allSettled` 同时取目录、余额、草稿；草稿 404/403 只显示「草稿不存在」，不影响向导；
   - 未消费草稿：预填 seed、min/max/chapter_words（有值才覆盖），记 `draftId`；
   - 已消费草稿：顶部「这份草稿已建成《…》」+ 链接，不预填、不记 `draftId`；
   - `submit` 用 `createNovel({...input, draft_id: draftId ?? undefined})`，估算请求不含 `draft_id`；422 沿用 `novelErrorMessage`。
   - 未改既有默认值、校验规则、文案行，未加装饰标签。

## 自检

- `npx tsc --noEmit` 退出码 0。
- `tests/test_novel_p21_frontend.py` → 21 passed；另外三组前端相关回归 39 passed。
- 临时行为探针覆盖预填、已消费提示、404 不阻塞、非法形状不发请求、estimate 无 `draft_id`。

## 决定与风险

- 403 与 404 同样显示「草稿不存在」。
- 非 404/403 草稿错误静默忽略，目录/余额照常可用。
- 同一 Wizard 实例内切换 `?draft=` 不清旧提示；抽屉导航会整页重载，不触发该路径。
