# 实现记录 C：前端聊天卡片与抽屉（T4 / T5）

- 代理：C（workflow `parallel()` 派发）
- 负责文件：`frontend/components/NovelDraftCard.tsx`（新）、`frontend/components/ChatBubble.tsx`、`frontend/lib/useConversations.ts`、`frontend/app/page.tsx`
- 未触碰 `lib/novels.ts`、`NovelWizard.tsx`、既有测试；未运行 git 写操作。

## 实现

1. `NovelDraftCard.tsx`：挂载/`draftId` 变化时用 `AbortController` 拉取 `getNovelDraft`；loading「正在读取草稿…」、ready「书斋草稿 · 《title》」+ 思路前 80 字 +「去书斋建书」、已建书「已建书《title》」+「打开」、404/403「草稿已不存在」、其他失败「草稿暂时读不到」；`ceramic-card w-[340px] max-w-full`、`btn btn-primary min-h-10`、仅 `font-medium`。
2. `ChatBubble.tsx`：`CardData.draft_id`、`ChatCardProps/ChatBubbleProps.onOpenNovel`、`novel_draft` 分支、两处 `ChatCard` 都透传。
3. `useConversations.ts`：`StoredMessage.novel_draft_id`；`toMessages` 逐条构造 cards，写歌卡与草稿卡可同时存在。
4. `page.tsx`（Python bytes 读写保留 BOM）：
   - `novelFrameSrc` 状态，iframe `src={novelFrameSrc}`；保留注释字面量以兼容既有 `test_novel_p2_frontend`。
   - `openNovelAt` 只接受 `/novels/new?embed=1&draft=<36>` 与 `/novels/<36>?embed=1`，通过才 set state + `setDrawer("novel")`。
   - 两处 SSE `const card: CardData` 都补 `draft_id`；`ChatBubble` 渲染处补 `onOpenNovel={openNovelAt}`。

## 自检

- `npx tsc --noEmit` 退出码 0；`npm run build` 退出码 0；ESLint 0 errors（page.tsx 仅既有 24 warnings）。
- 既有前端契约测试 108 passed。
- BOM 每次编辑后 `head -c 3 | xxd` 均为 `efbb bf`。
- 已提醒主代理：共享 `render_card` 不注入 `NovelDraftCard`，新渲染测试需注入桩；主代理最终测试已处理。

## 决定与风险

- 按钮路径用字符串拼接，便于源码契约匹配。
- 多张卡各自拉取；P0 不做「只最后一张完整显示」。
- 抽屉导航只改 iframe `src`；同路径不强制重载，符合规格。
