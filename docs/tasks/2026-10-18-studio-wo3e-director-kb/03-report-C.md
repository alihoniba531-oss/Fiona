# WO3e 阶段二 C 块报告：知识库前端

## 1. 修改了哪些文件

新增：

- `frontend/lib/studio-kb.ts`
- `frontend/app/studio/kb/page.tsx`
- `frontend/components/studio/kb/KbWorkbench.tsx`
- `frontend/components/studio/kb/KbCardBrowser.tsx`
- `frontend/components/studio/kb/KbCardDetail.tsx`
- `frontend/components/studio/kb/KbExemplars.tsx`
- `frontend/components/studio/kb/KbStatsPanel.tsx`
- `frontend/components/studio/kb/KbTrialPanel.tsx`
- `frontend/components/studio/kb/KbQuoteDialog.tsx`
- `frontend/components/studio/kb/ReviewProviderPicker.tsx`
- `backend/tests/test_studio_kb_frontend.py`

修改（只改白名单允许的两处）：

- `frontend/app/studio/page.tsx`：页头加「导演知识库」链接。因为首页实际页头在 `StudioShelf`（不在本块白名单）里，本文件用一条与页面同高的顶部条承载链接，并用 `[&>div]:h-full` 让工作室主体继续占满剩余视口。
- `frontend/components/studio/StudioWorkbench.tsx`：在「全部项目」旁加「导演知识库」链接；在 `BrainProviderPicker` 紧后面放 `ReviewProviderPicker`。没有改其他行为。

没有改 `globals.css`，没有加依赖，没有改两张样卡或白名单外文件。

## 2. 实现了哪些功能

- 请求层 `lib/studio-kb.ts` 沿用 `lib/studio.ts` 的 `apiJson` / `API_BASE` / `studioErrorMessage` 风格，封装：
  - 卡片列表与详情、案例列表与 PATCH、节奏统计；
  - 试拆报价、确认、查询；
  - review-provider 读取与 PATCH。
- `/studio/kb` 页面与 7 个页签：语法、场景模板、模型能力、反例、案例库、节奏统计、试拆对比。页签用 roving tabs，窄屏自动换行。
- 四个卡片页签共用左右布局：左侧列表支持按标签筛选和搜索，右侧按 `grammar` / `scene` / `model` / `negative` 分别渲染专属字段；卡片详情显示来源、版本、标签。
- 案例库：按场景类型/好例反例筛选；行内标好例/反例、改原因、保存、归档；显示镜头摘要。
- 节奏统计：未就绪时显示「累计满 5 集后显示你的节奏统计」和当前集数；就绪时显示累计集数、镜头数、分场景的景别/运镜分布。
- 试拆对比：四步表单（选项目、粘贴 3000 字以内的戏、填 `SceneTags`、报价并开始），默认两种模式都拆；报价框沿用 `CastingQuoteDialog` 的 `BreakdownDialog`、`ceramic-card`、`readout`、倒计时和一次确认样式；结果左右两栏（窄屏堆叠），每栏有镜头表/窄屏镜头卡、模板 id、注入字数、lint 标签、审核 verdict/summary/issues，`must` 用 `tag-rec` 警示色且不加粗。
- 试拆在途每 3 秒轮询，页面隐藏或操作中暂停；账号切换沿用 `useAccountRequest` 取消。
- `ReviewProviderPicker`：原生下拉，选项 Claude、千问 3.8 Max、DeepSeek、关闭；与导演模型相同且不是关闭时提示「同一模型自审，效果有限」；始终写明「审核会把原文发给所选厂商」。
- 所有新文件没有 `font-semibold` / `font-bold` / `font-weight ≥ 600` / `<b>` / `<strong>`；空、加载、错误、成功四态齐全；390px 关键容器均从单列 + 可换行开始，无 `overflow-x-auto` 或固定最小宽度。

### 与并行 B 块落盘后的对齐

实现期间 B 块落盘，已按实际响应校准：

- 试拆 GET 的 `modes` 是模式名列表，两个模式的实际结果在顶层 `with_kb` / `without_kb`；helper 同时兼容对象形式和列表形式，并按顶层 `review` 合并。
- 统计就绪响应是 `scene_types`；同时保留 `stats` / `rows` / `by_scene_type` 兼容。
- 案例接口返回解析后的 `shot` / `tags`；行组件优先使用解析值，并保留 `shot_json` 兼容。
- 报价条目带 `item_id`、`versions`、`unit`、`est`，总价与币种按 `CastingQuote` 同形展示。

## 3. 与 §10 / §12 的对应

- §10 C 行：白名单内所有文件均已交付；`StudioWorkbench` 只加链接和 picker 两处；`app/studio/page.tsx` 加首页入口链接。
- §8：卡片列表/详情、案例列表/PATCH、统计、报价/确认/查询、review-provider 的 URL、方法和请求体均按接口表编码；测试逐项断言。
- §8.1：试拆结果读取两种模式的 `review`，审核失败只降级该栏审核区，不影响镜头结果；`off` 显示「本次未开启交叉审核」。
- §9：
  - 七页签与卡片左右布局、标签筛选/搜索、按类型渲染字段；
  - 案例标好例/反例、改原因、归档；
  - 统计不足 5 集的原文空态；
  - 试拆四步、CastingQuoteDialog 风格报价、双栏镜头表五列（另加镜号）、lint 标签、模板 id 与注入字数、verdict/summary/issues；
  - 审核模型下拉、同模型提示、隐私说明；
  - 不加粗、不改 globals.css、不加依赖、四态和 390px 约束。
- §12 第 7 项：新页面/组件由离线 SSR + 交互探针覆盖七页签与四态；390px 以静态类约束检查（所有新布局从 `grid-cols-1` / `flex-wrap` / 单列开始，无 `overflow-x-auto`、无 `min-w-[...]`）。

## 4. 测试结果（原始数字）

在 `frontend/`：

```text
$ npx tsc --noEmit
（无输出）
exit 0
```

```text
$ npm run lint
✖ 25 problems (0 errors, 25 warnings)
exit 0
```

25 条 warning 全部来自既有文件 `app/page.tsx` 和 `app/plaza/page.tsx`（未使用变量、exhaustive-deps、`<img>`）；新增 KB 文件 0 warning、0 error。

在 `backend/`：

```text
$ /Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python -m pytest -q tests/test_studio_kb_frontend.py
...............                                                          [100%]
15 passed
```

- passed：15
- failed：0
- skipped：0
- 另有依赖缺失保护参数化 4 例包含在其中；测试不联网、不读仓库外文件。

回归：

```text
$ pytest -q tests/test_studio_brain_frontend.py tests/test_studio_brain_r1_frontend.py \
  tests/test_studio_frontend_components.py tests/test_studio_frontend_dependencies.py \
  tests/test_studio_frontend_navigation.py tests/test_studio_frontend_shell.py \
  tests/test_studio_kb_frontend.py tests/test_studio_sources_frontend.py \
  tests/test_studio_wo3_polish_frontend.py
101 passed in 17.12s
```

`npm run build` 也通过（Next.js 16.3.8，`/studio/kb` 成功生成）。

## 5. 未完成或需要人工确认的地方

- 本机 `pytest -q tests/ -k studio` 中 A/B 的 API 测试在当前终端环境会因为代理变量被解析成 `:1]` 而在 `main` 导入阶段报 `httpx.InvalidURL`；这是环境问题，C 的测试和全部既有工作室前端测试不受影响。主控跑总门禁时需要确认该环境变量。
- 390px 除静态探针外，还用本机 headless Chrome（390×844）对页签、试拆双栏、卡片详情和案例行做了一次静态渲染检查，`document.documentElement.scrollWidth - clientWidth = 0`，标题与 `.tag` 的 computed `font-weight` 均为 `400`；完整交互表单尚未做自动化浏览器截图，建议主控验收时再用开发服务器目测一次。
- 卡片列表的搜索和标签筛选是在已拉取的列表上客户端过滤（58 张卡规模很小）；接口的 `q` 参数已在请求层封装并有契约测试，但页面没有每次输入都打接口。若主控希望搜索也走服务端，可后续把搜索框接到 `listKbCards(type, q)`。
- 首页入口采用页面级顶部条，而不是改 `StudioShelf`（白名单限制）。如果作者希望链接进 `StudioShelf` 的原有标题行，需要把 `StudioShelf.tsx` 加入白名单再改。
- 试拆报价/结果按 B 已落盘的真实形状做了兼容；如果 B 后续再改响应字段，需要同步 `lib/studio-kb.ts` 的 `KbTrial`/`KbStats` 归一化。
