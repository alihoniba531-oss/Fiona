# 案头第一期 · 独立复核报告

复核对象：基线 `9adf34c` 之上的待审改动（R1 之后的工作区）。依据：规格 v1.1（`02-spec.md`）、设计参考稿、返修单 R1；实施方报告与验收方门禁记录只当线索，下文结论都是复核方自己运行命令、读代码和做实验得到的。复核方没有启动浏览器或 dev server，三个宽度的真实界面走查沿用 `gate-notes.md`，本报告不替它背书。

## 1. 结论

**不通过。** 有 2 条必须修复：

1. **读请求作用域共用，两处加载状态会卡死**（`DeskDock.tsx`）：
   - 章回页：写操作（继续写、留言等）进行中切换作品，写完后的刷新会取消新作品的详情请求，案头一直停在「正在取回作品…」；
   - 分集页：分集被重新拆解阻塞、5 秒轮询进行中时点「刷新」，轮询会取消候选请求，分集页一直停在加载中。

   两种情况都已用真实源码驱动复现，并做了修复对照。
2. **「已批准」朱色用例没有绑定到标签本身**（`test_desk_views_frontend.py`）。把朱色从「已批准」标签挪到汇总行，72 条新用例照样全过。v1.1 专门要求盯住的这一处因此失去证明力。

规格第 7 节的 10 条机械验收全部符合。花钱与权限方面没有发现新的付费途径或越权途径；锁定项全部保留。另有若干不阻塞的问题列在第 4 节，其中第 1、2 条需要规格作者裁定。

## 2. 验收标准逐条核验

| # | 命令 | 关键输出 | 是否符合 |
|---|---|---|---|
| 1 | `cd backend && NO_PROXY=localhost,127.0.0.1 no_proxy=localhost,127.0.0.1 .venv/bin/python -m pytest -q -p no:cacheprovider`（本机 `NO_PROXY` 含 `[::1]`，按说明覆盖） | `7983 passed, 35 warnings in 303.08s (0:05:03)`，无 failed、无 skipped；7983 = 7911 + 72 | 符合 |
| 2 | `.venv/bin/python -m pytest -q tests/test_desk_*.py -rsf` | `72 passed in 4.72s`，没有 skip 或 fail 摘要；按文件数：contract 40、logic 11、views 21 | 符合 |
| 3 | `cd frontend && npx tsc --noEmit` | 无输出，`exit 0` | 符合 |
| 4 | `cd frontend && npm run lint` | `✖ 25 problems (0 errors, 25 warnings)`；单独 `npx eslint components/desk lib/desk.ts` 无任何输出 | 符合 |
| 5 | `cd frontend && npm run build` | 路由表正常输出（含 `/novels`、`/studio/[id]` 等），`build exit 0`；构建后 `git status` 与构建前一致 | 符合 |
| 6 | `git status --porcelain --untracked-files=all`（排除 `.cache/`） | 修改：`CLAUDE.md`、`PLAN.md`、`README.md`、`docs/ARCHITECTURE.md`、`frontend/app/page.tsx`、`backend/tests/test_ui_closeout_dialog_scrim.py`；新增：三个 `backend/tests/test_desk_*.py`、`frontend/lib/desk.ts`、六个 `frontend/components/desk/*.tsx`、`impl/主代理.md`，以及规格作者的 `01`–`04` 与 `design/` | 符合（全部落在第 6 节白名单或作者文件内；`globals.css`、`package*.json` 未动） |
| 7 | `git diff --stat main -- backend ':!backend/tests'`；`git diff --numstat main -- backend/tests` | 前者为空；后者只有 `1	1	backend/tests/test_ui_closeout_dialog_scrim.py`，第 117 行为 `def assert_dialogs_have_scrim(sources, *, expected_count=14):` | 符合 |
| 8 | `git diff main -- frontend/package.json frontend/package-lock.json` | 空 | 符合 |
| 9 | 七条字面量逐条 `grep -cF`；`head -c 3 frontend/app/page.tsx \| xxd -p` | 依次 `1 2 1 1 1 2 1`（基线 `1 1 1 1 1 2 1`；`onOpenNovel={openNovelAt}` 多出的一处是新增 DeskDock 的 prop，第一处仍在第 2703 行的 ChatBubble 上）；BOM 为 `efbbbf` | 符合 |
| 10 | `grep -rc 'createElement("dialog"' frontend/components/desk/`（另查单引号写法）；`grep -c '<dialog' frontend/components/desk/DeskDialogs.tsx` | 六个文件两种写法都是 0；`<dialog` 为 1 | 符合 |

补充核对：

- `page.tsx` 相对基线新增 53 行，只替换了 lucide import 那一行，改动正好落在 T3 的七处；`<DeskDock` 挂在 `data-chat-panel` 那个 div 闭合之后，是 `div.flex.flex-1.min-w-0.min-h-0` 的最后一个子元素。
- 流式定位块写成 `const streamedCard = data.card; if (streamedCard) {…}`，没有照抄规格的 `if (data.card) {`。原因是既有的 `test_claude_agent_frontend.py` 用 `source.index("          if (data.card")` 截取卡片分支。两种写法行为等价，也不是在躲设计门禁。
- 既有设计门禁确实扫描到案头文件（第 5 节 G1–G3）：在案头文件里写 `text-[13px]`、把 `--ink3` 当文字色、去掉对话框类名，都让对应既有门禁变红。

## 3. 必须修复

### 必须修复 1：读请求作用域共用，导致两处加载状态卡死

**文件与行**：`frontend/components/desk/DeskDock.tsx`

- 详情加载：`loadBookDetail` 第 224–244 行。`finally` 只在「本请求仍有效且所选书仍是它」时清 `bookLoading`（第 242 行）。
- 写后刷新：`runNovelAction` 第 408–409 行、`addNote` 第 449–450 行。写完后只判 `request.isCurrent()`，不判所选书是否已变；对比 `planAct` 第 429 行有这道判断。
- 候选与分集共用一个作用域：`loadCandidate` 第 342–378 行用 `beginEpisodeRead`；5 秒轮询（第 779–803 行）调用的 `loadPlan` 第 318–340 行也用 `beginEpisodeRead`。`setCandidateLoading(false)` 只在候选请求自己成功或失败时执行。

**现象**

A. **章回页**：写操作的请求还没返回时，作者在「作品」下拉里切到另一本书（聊天里来了指向另一本书的卡片也一样），流程如下：

1. 新书 B 的详情请求开始；
2. 写操作返回后，`loadBookDetail(旧书)` 调用 `beginRead()`，取消了 B 的请求；
3. 旧书的刷新回来时，因为所选书已经变了被丢弃，`bookLoading` 再也没有人清掉。

结果：内容区一直显示「正在取回作品…」，没有错误提示，也没有重试入口，要手动点「刷新」才会恢复。会触发这个问题的写操作有：GateBanner 的继续、恢复、完结确认，以及留言。

B. **分集页**：方案被重新拆解阻塞（这时会提示作者「去工作室看进度」）、5 秒轮询正在运行时，作者点「刷新」，流程如下：

1. `refreshAll` 调用 `loadCandidate`，`candidateLoading` 变为 true，请求 `listStudioNovelSources`。这个后端接口会对每本书各取一次详情和圣经，比较慢；
2. 下一次轮询的 `loadPlan` 调用 `beginEpisodeRead()`，取消了候选请求；
3. `candidateLoading` 永远停在 true。

`DeskEpisodesView` 第 71 行优先判断 `candidateLoading`，所以分集页一直是「正在取回作品…」，后台轮询却还在继续。拆解完成后轮询会停，但页面仍然卡住。每次刷新撞上轮询的概率约等于「候选请求耗时 ÷ 5 秒」，并不罕见。

**为什么是问题**

规格 T2 第 5 条要求不同用途的请求不能互相取消、不能把状态写乱。实施记录第 4.2 条也说读请求按用途拆作用域，正是为了避免轮询取消其他读请求。但「写后刷新」与「新选中的书」共用详情作用域，「候选」与「分集轮询」共用分集作用域，而加载标志只由发起它的那个请求清除。这会造成界面卡死，属于错误行为。

**证明**

用附录脚本加载真实的 `DeskDock.tsx`、`useAccountIdentity.ts` 和 `desk.ts` 源码，配一个极简 hooks 运行时（支持 useEffect、rAF 和链式 setTimeout），后端用带延迟的桩代替。

- `node desk-race.js write`：

  ```text
  0.48s POST continue 完成
  0.48s GET 详情 乙 被取消
  0.51s GET 详情 甲 完成
  2.01s 结果：{"loading":true,"book":null,"error":null}
  ```

  留言路径（`onAddNote`）的结果相同。
- `node desk-race.js episodes`：

  ```text
  5.96s 点「刷新」
  6.03s GET 工作室来源(候选) 被取消
  6.13s GET 分集方案 完成
  11.23s GET 分集方案 完成
  16.33s GET 分集方案 完成
  17.96s 等待 12 秒后：{"candidateLoading":true,"hasPlan":true}
  ```

- 修复对照（临时改动，跑完已按原字节还原）：
  - 给 `runNovelAction` 的写后检查加上 `selectedBookRef.current !== targetBookId` 后，write 场景得到 `{"loading":false,"book":"乙"}`；
  - 给 `loadCandidate` 单独开一个 `useAccountRequest` 作用域后，episodes 场景得到 `{"candidateLoading":false,…}`。

**真实界面复现**：浏览器开发者工具把网络节流到 Slow 3G。

- A：在一本 `awaiting_review` 的书上点「继续写下 N 章」，请求返回前在「作品」下拉里切到另一本书。
- B：准备一个重新拆解进行中的项目，停在分集页，在一次轮询到来前一秒内点「刷新」。

**建议改法**

1. 在 `loadBookDetail` 开头、调用 `beginRead()` 之前加 `if (selectedBookRef.current !== id) return;`，让不是当前所选书的刷新根本不发起，也就取消不了所选书的请求。同时在 `runNovelAction`、`addNote` 的写后检查里补上与 `planAct` 相同的所选书判断。
2. `loadCandidate` 改用独立的读作用域，例如 `const { beginRequest: beginCandidateRead } = useAccountRequest(owner);`；分集方案的加载与轮询继续用 `beginEpisodeRead`。
3. 顺带排查：凡是由某个请求置 true、并且只由它自己清除的加载标志，都要确认同作用域里其他用途的请求不能把它取消。导出建议也从 `beginRead` 挪出去，见第 4 节第 5 条。

### 必须修复 2：「已批准」朱色用例没有绑定标签，变异不变红

**文件与行**：`backend/tests/test_desk_views_frontend.py` 第 566–576 行，`test_episodes_approved_tag_has_seal_classes_and_pending_does_not`。

**现象**：用例只断言整页 HTML 里出现 `text-[color:var(--seal)]` 和 `border-[color:var(--seal)]`，没有断言这两个类在「已批准」那个 `tag` 元素上。

**为什么是问题**：规格 T8（v1.1）原文是「分集页：『已批准』标签带两个朱色类，『待批准』标签不带」，规格 4.1 也只允许这两种标签用朱色；T8 总则还要求「每条断言都要能区分对错实现」。这条是 v1.1 专为测试盲区补的用例，题目说要验的东西它实际没有验，属于「只匹配到别处同名文字」的断言。同文件里章回页的朱色用例（第 207–225 行，用 `TAG_SPAN` 定位标签再查类）是对的写法。

**证明**：变异 M2B 把 `DeskEpisodesView.tsx` 里「已批准」标签改成纯 `tag`，再把两个朱色类加到汇总行 `<p>` 上（仅在已批准时）。结果 `72 passed`，没有任何用例变红。

**建议改法**：用与章回页相同的方式定位标签：

- 找出类名含 `tag`、文字是「已批准」的 `<span>`，断言两个朱色类都在它的类里；
- 断言已批准渲染里两个朱色类在整页各只出现 1 次；
- 待批准渲染里找到文字是「待批准」的 `tag`，断言它不带朱色，并且整页没有朱色类；
- 再配一条自检：把朱色挪到别的元素，检查器必须报错。

改完用 M2B 与「去掉已批准朱色」两个变异各验一次，确认会变红。

## 4. 可优化

### 需要规格作者裁定

1. **所有 409 都按版本冲突处理**（`DeskDock.tsx` 第 569–575、599–605 行，照规格 T6 实现）。后端分集操作与批准会因 5 种原因返回 409（`backend/studio/breakdown_plan.py` 第 325–331、345–353 行）：
   - 「分集方案已更新，请刷新」（真正的版本冲突）；
   - 「拆解尚未完成，完成后才能修改分集方案」；
   - 「请先完成拆解」；
   - 「拆解尚未全部完成，不能批准分集方案」；
   - 「至少需要一集才能批准」。

   案头不轮询未阻塞的方案。作者在工作室发起重新拆解后回到案头，看到的还是旧状态；这时保存修改会得到后面几种 409，案头却显示「分集方案已在别处改动……请再试一次」，同时关掉对话框、丢掉作者刚填的内容。建议：刷新后只在 `plan_revision` 真的变了时才当冲突处理；其余 409 刷新后照原样抛出，由对话框显示真实原因。
2. **自动打开会抢走输入框焦点**（`DeskDock.tsx` 第 805–821 行）。规格写的是「打开后把焦点移到面板」。page.tsx 第 2115 行在工具事件后会 `setTimeout(focusChatInput, 100)`，明确是想在回复进行中把焦点留在输入框；而 ≥768 宽度下卡片一到，案头就把焦点拉到面板，作者正在打的字会落空。刷新页面时恢复为打开状态，也会抢走初始焦点。建议只在作者亲手打开时移动焦点。
3. **布局**：768–1439 宽度下抽屉会盖住头部的「案头 / 朗读 / 免提」开关和发送按钮；手机半屏未展开时，列表只露出一行左右（`gate-notes.md` 也记录了这两点）。

### 实现

4. **关闭后的残留**：
   - `resize` 监听在组件挂载时就挂上（第 170–178 行）。没打开过案头的账号也一直挂着，关闭后也不摘。
   - 关闭时不取消在途的读请求。写操作返回后的刷新、409 后的刷新、定位解析之后的 `selectBook`，都会在关闭后再发 GET。
   - 规格 T2 第 1 条要求「open 为假……不发请求」。建议关闭时让读作用域失效（例如用 `openRef` 拦住链式请求），`resize` 只在打开时监听。
5. **导出与详情共用 `beginRead`**（第 457–485 行）。导出进行中点「刷新」、页面重新可见（第 760–769 行）或切换作品，都会静默取消导出，没有任何提示。建议给导出单独一个作用域。
6. **聊天定位的两个副作用**：
   - 定位到同一本书的另一个项目时，不清 `planNotice`（第 700–710 行），与 T6「切换项目时清空」不一致，旧项目的冲突提示会挂到新项目上；
   - 定位会调用 `dismissDialogs`（第 701 行，以及 `selectBook` 第 250 行）。作者正在细纲对话框里改稿时来一张指向同一本书的项目卡，对话框会被直接关掉、改动丢失。建议有对话框打开时推迟定位。
7. **细纲操作的错误信息没有转成中文**（第 419–437 行）。`planAct` 把原始错误抛给 `PlanEditor`，而 PlanEditor 直接显示 `cause.message`，非中文的后端 detail 或中断错误会原样显示。书斋工作台的 `mutate` 会先经 `novelErrorMessage` 转换。建议 `throw new Error(novelErrorMessage(cause))`。
8. **无障碍**：
   - 竖排标签没有 `aria-orientation="vertical"`，也不响应上下方向键；
   - `useRovingTabs` 会尝试把焦点移到置灰的标签上而失败：在「分集」上按右键、在「立意」上按左键、按 End，焦点都不动；
   - 没有 `tabpanel` 与 `aria-controls`；
   - 章号、集号是 `aria-hidden`，而章名经 `displayNovelChapterTitle` 去掉了「第 n 章」，读屏用户听不到章号（`DeskChaptersView.tsx` 第 104 行、`DeskEpisodesView.tsx` 第 170 行）；
   - 没有章节时，`role="list"` 里直接放了 EmptyState（`DeskChaptersView.tsx` 第 89–90 行）；
   - 批准细纲成功后，触发按钮随关卡变化被卸载，焦点退回到头部开关（第 180–190 行），在抽屉方式下随后按 Esc 也收不起案头。建议退回到面板；
   - `DeskDialog` 在 busy 时按 Esc 也能关闭（`DeskDialogs.tsx` 第 44–47 行），而 `BreakdownDialog` 在 busy 时拦住了 Esc。
9. **文案**：
   - `DeskEpisodesView.tsx` 第 89 行在 `reason` 为空时自拟了「暂时还不能建短片项目。」；
   - 取数期间书名位置显示「未命名」（`DeskFrame.tsx` 第 70–71 行）。
10. **`localStorage` 访问没有包 try/catch**：`DeskDock.tsx` 第 249、315、624、635、702 行直接访问 `window.localStorage`。实施记录第 4.5 条说「都包了 try/catch」，与事实不符。由于 `auth.ts` 本身也直接读 localStorage，实际风险低。

### 测试

11. **`DeskDock` 与 page.tsx 接线零自动化覆盖**。以下变异全部不变红：

    | 变异 | 内容 |
    |---|---|
    | M7 | 手机宽度也自动打开 |
    | M8 | 409 不再按冲突处理 |
    | M9 | 轮询间隔从 3000ms 改成 300ms |
    | M10 | 详情回包不判 isCurrent 与所选书 |
    | M13B | 去掉两道 studioAllowed 守卫 |
    | M14 | 并排方式下 Esc 也收起 |
    | M17 | 写操作成功后不再刷新详情 |

    建议把可以写成纯函数的判定挪进 `lib/desk.ts` 测（例如「这个宽度下是否自动打开」「这个 409 是否算版本冲突」），或者参照附录写一个带虚拟时钟的 node 用例。
12. **断言没有绑定元素，或只验了一部分**：
    - 面板骨架用例对 `bg-[color:var(--paper)]` 查的是整页 HTML，没有绑定 `<aside>` 的类；dock 的否定断言没有正向锚点；
    - 只查 `45dvh` 子串，证明不了「不超过可用高度」这层上限（M4 不变红）；
    - 手机横排标签的 `disabled` 与 `title` 没有用例（M5 不变红）；
    - `editsBlocked` 时「修改」「与下一集合并」的禁用没有用例（M3 不变红）；
    - 冲突提示用例没有把 `role="alert"` 和提示文字绑定在同一个元素上。

### 文档

13. **四份文档里与实现不一致的描述**：
    - `CLAUDE.md` 第 237 行与 `docs/ARCHITECTURE.md` 第 149 行都写「页面隐藏或操作中暂停」。实际上详情轮询只在细纲或正文对话框打开时暂停，写操作进行中不暂停；分集轮询也一样。
    - `ARCHITECTURE.md` 写「读请求按书目/详情、聊天定位、章节对话框、分集各用一个作用域」。实际是 5 个：书目与详情各一个，导出用的是详情作用域。
    - 四份文档都没有本机绝对路径、账号名或密钥；其余描述与实现一致。
14. **实施记录**（不属于四份文档）：第 4.1 条（用 createElement 写对话框）与第 2 节「未改任何既有测试」是首轮的旧说法，R1 之后已经不成立，但没有标注作废；第 4.5 条的说法见第 10 条。

### 核对过、没有问题的点

- **花钱**：付费动作只有两个入口，都是原有组件和原有提示：
  - GateBanner 的继续、恢复、再写几章、完结确认，案头经 `runNovelAction` 原样转给 `novelApi.action`；
  - PlanEditor 的批准细纲、改完批准、附一句话重做，以及它自带的「重新定稿会再次扣除草莓」提示。

  书斋工作台对这些动作本来就没有额外的确认框。案头没有提供拆解、报价或「做成片」（没有传 `onMakeFilm`）。连续点击被 `busyRef` 同步拦住。
- **账号隔离**：
  - 偏好键是 `fiona.desk.v1:` 加账号名；
  - `DeskDock` 用 `key={owner}` 包了一层，换账号时整个容器重建，六个读写作用域全部取消；
  - 所有回包都先判 `isCurrent()`；
  - 卡片里的 id 经正则校验后才使用；`openNovelAt` 与 `openStudioAt` 都会再校验一遍；
  - 后端取草稿 `get_draft` 按 `owner_username` 过滤，`list_candidates` 只列本人的书；
  - 换账号后残留的 `deskFocus` 只会在新账号下得到 404 或找不到，然后被忽略，不会定位到别人的书或项目。

## 5. 变异实验记录

做法：每次只改一处或一组。改之前记下 11 个相关文件的 sha256，改完立即按原字节写回；全部实验结束后逐个 `shasum -c`，结果全部 OK。

- 案头文件的变异跑 72 条新用例；
- page.tsx 的变异跑 16 个读 page.tsx 的测试文件，加设计门禁与对话框门禁；
- G 组只跑两个既有门禁。

| 编号 | 位置 | 变异 | 结果 | 变红的用例 / 结论 |
|---|---|---|---|---|
| M1 | `lib/desk.ts` | `deskMode` 的 `>= 1440` 改成 `> 1440` | 1 failed | `test_desk_stages_default_prefs_and_mode`，有证明力 |
| M2 | `DeskEpisodesView.tsx` | 已批准时汇总行额外加朱色（标签保留） | 72 passed | 多出来的朱色不会被发现（只作说明） |
| M2B | `DeskEpisodesView.tsx` | 朱色从「已批准」标签整体挪到汇总行 | 72 passed | **无，见必须修复 2** |
| M3 | `DeskEpisodesView.tsx` | 「修改」按钮不再受 `editsBlocked` 禁用 | 72 passed | 无（规格未要求此用例，见第 12 条） |
| M4 | `DeskFrame.tsx` | 半屏高度改成纯 `"45dvh"`，去掉可用高度上限 | 72 passed | 无（第 12 条） |
| M5 | `DeskFrame.tsx` | 半屏横排标签去掉 `disabled` 与 `title` | 72 passed | 无（第 12 条） |
| M6 | `DeskChaptersView.tsx` | 留言已满时不再禁用输入框 | 1 failed | `test_chapter_notes_input_respects_pending_limit[5-…]`，有证明力 |
| M7 | `page.tsx` | 去掉非手机宽度的判断，手机也自动打开 | 302 passed | 无（第 11 条） |
| M8 | `DeskDock.tsx` | 两处 `status === 409` 改成 4090（冲突不再处理） | 72 passed | 无（第 11 条） |
| M9 | `DeskDock.tsx` | 详情轮询从 3000ms 改成 300ms | 72 passed | 无（第 11 条） |
| M10 | `DeskDock.tsx` | 详情回包不再判 `isCurrent` 与所选书 | 72 passed | 无（第 11 条） |
| M11 | `lib/desk.ts` | 偏好键不再带账号名 | 3 failed | parse、read、update 三条，有证明力 |
| M12 | `lib/desk.ts` | `parseDeskPrefs` 接受置灰阶段 | 2 failed | parse、update 两条，有证明力 |
| M13 | `DeskDock.tsx` | 只去掉 `episodeBookId` 里的 `studioAllowed` | 72 passed | 被 `loadCandidate` 的第二道守卫兜住，行为没有变，不算缺陷 |
| M13B | `DeskDock.tsx` | 两道 `studioAllowed` 守卫都去掉 | 72 passed | 无（第 11 条；后端仍会对白名单外账号返回 404） |
| M14 | `DeskDock.tsx` | 并排方式下 Esc 也收起 | 72 passed | 无（第 11 条） |
| M15 | `DeskChaptersView.tsx` | 所有章节标签都加朱色 | 2 failed | 章回朱色用例及其自检，有证明力 |
| M16 | `DeskFrame.tsx` | 抽屉方式去掉纸色底 | 1 failed | `test_frame_uses_opaque_drawer_and_sheet_and_correct_width_and_height`，有证明力 |
| M17 | `DeskDock.tsx` | 写操作成功后不再刷新详情 | 72 passed | 无（第 11 条） |
| G1 | `DeskIdeaView.tsx` | 写 `text-[13px]` | 1 failed | 既有 `test_design_system_gate.py::test_font_size_rules`，门禁覆盖到案头 |
| G2 | `DeskEpisodesView.tsx` | 文字色改成 `--ink3` | 1 failed | 既有 `test_design_system_gate.py::test_role_rules` |
| G3 | `DeskDialogs.tsx` | 对话框 `className=""` | 1 failed | 既有 `test_ui_closeout_dialog_scrim.py::test_all_dialogs_use_scrim_dialog` |

**缺依赖时的跳过**（第 4 项）：

- 把 `frontend/node_modules` 临时改名后跑新测试：`46 passed, 26 skipped`，0 failed。跳过原因是 `frontend dependencies unavailable: typescript`（9 条）和 `… typescript, react, react-dom/server`（17 条）。跑完已改回原名。
- `PATH` 里去掉 node：同样 `46 passed, 26 skipped`，原因是 `node is unavailable`。
- 正向对照：把两个文件守卫里的 `pytest.skip(` 临时换成 `print(`，并去掉 node_modules：`30 failed, 2 passed`。说明确实是守卫在起 node 之前把用例跳过了，不是用例本身恒真。跑完已还原。

**竞态复现**：附录脚本的两个场景都复现了卡死；两种修复对照都消除了卡死（见必须修复 1）。

## 6. 给实施方的二次修改指令

> 背景：案头第一期 R1 的机械门禁全部通过，独立复核发现 2 条必须修复。只改下列文件，其余规矩照旧：`backend/` 非测试文件不动；`page.tsx` 这一轮不需要改；不新增依赖；不改任何既有测试；不提交、不切分支；任务目录下 `01`–`05` 与 `design/` 不要改。不要调用 subagent / subagent_fork / workflow。
>
> **一、`frontend/components/desk/DeskDock.tsx`：消除两处加载卡死**
>
> 1. 在 `loadBookDetail` 开头、调用 `beginRead()` 之前加 `if (selectedBookRef.current !== id) return;`。在 `runNovelAction` 与 `addNote` 写请求成功后的检查里，补上与 `planAct` 相同的条件 `selectedBookRef.current !== targetBookId`，满足时直接返回、不刷新。目的：写操作进行中切换作品后，旧书的写后刷新不能取消新书的详情请求。
> 2. 新增一个只给候选用的读作用域：`const { beginRequest: beginCandidateRead } = useAccountRequest(owner);`。`loadCandidate` 改用它，并把它加进依赖数组。分集方案的加载、5 秒轮询与 409 后的刷新继续用 `beginEpisodeRead`。目的：轮询不能取消候选请求，避免 `candidateLoading` 永远为 true。
> 3. 自查：凡是由某个请求置 true、只由它自己清除的加载标志（`bookLoading`、`candidateLoading`、`planLoading`），同一作用域里其他用途的请求都不能把它取消掉而又不清除它。
> 4. 验证：把复核报告附录的 `desk-race.js` 放到临时位置（不要加进仓库），在 `frontend/` 下运行 `node <路径> write` 与 `node <路径> episodes`，最后一行应分别是 `"loading":false,"book":"乙"` 和 `"candidateLoading":false`。把两段输出贴进实施记录。
>
> **二、`backend/tests/test_desk_views_frontend.py`：让「已批准」朱色用例绑定到标签**
>
> 1. 改写 `test_episodes_approved_tag_has_seal_classes_and_pending_does_not`：
>    - 用与章回页 `TAG_SPAN` 相同的方式，找出类名含 `tag`、文字为「已批准」的 `<span>`，断言 `text-[color:var(--seal)]` 与 `border-[color:var(--seal)]` 都在它的类里，并且已批准渲染里这两个类在整页各只出现 1 次；
>    - 待批准渲染里找到文字为「待批准」的 `tag`，断言它不带朱色，并且整页没有朱色类。
> 2. 加一条自检：把已批准渲染里的朱色挪到另一个元素上，检查器必须报错。
> 3. 验证：临时把 `DeskEpisodesView.tsx` 里「已批准」标签改成纯 `tag`，再把两个朱色类加到汇总行 `<p>` 上（仅在已批准时），这条用例必须变红；再单独去掉已批准朱色一次，也必须变红。两次都按原字节还原。
>
> **三、可选（不阻塞，有余力再做）**：复核报告第 4 节第 4–8 条与第 13 条。第 1、2 条要等规格作者裁定后再动。
>
> **四、验收**：重跑规格第 7 节的 10 条命令。全量要求 0 failed、0 skipped，通过数等于 7911 加新增用例总数；本机 `NO_PROXY` 含 `[::1]` 时，命令前加 `NO_PROXY=localhost,127.0.0.1 no_proxy=localhost,127.0.0.1`。在 `impl/主代理.md` 末尾追加「## R2」：写明改了哪些文件、两条各自怎么改的、两个复现场景的前后输出、两次变异的结果和第 7 节的实际输出。同时把第 4.5 条（localStorage 都包了 try/catch）的说法改对，并给第 4.1 条、第 2 节「未改任何既有测试」标注「已被 R1 取代」。

## 附录：竞态复现脚本 `desk-race.js`

在 `frontend/` 目录下运行，只读仓库内的源码，不访问网络，也不写任何文件。它用一个极简 hooks 运行时（支持 useState、useRef、useCallback、useMemo、useEffect、rAF 和 setTimeout）加载真实的 `components/desk/DeskDock.tsx`、`lib/useAccountIdentity.ts` 和 `lib/desk.ts`，视图组件和后端接口都用桩代替。

```js
// 迷你 hooks 运行时（含 useEffect、rAF、链式 setTimeout）驱动真实 DeskDock.tsx，复现两处加载卡死：
//   node desk-race.js episodes  分集被拆解阻塞、5 秒轮询中点「刷新」→ 候选请求被轮询取消 → candidateLoading 永远为 true
//   node desk-race.js write     写操作（继续写 / 留言）进行中切换作品 → 新作品详情被写后刷新取消 → loading 永远为 true
// 在 frontend/ 目录下运行；只读源码，不访问网络。
const fs = require('fs');
const path = require('path');
const ts = require(path.join(process.cwd(), 'node_modules/typescript'));
const FRONTEND = process.cwd();

let slots = [], cursor = 0, pendingEffects = [], scheduled = false, Component = null, props = null, lastTree = null;
function schedule() { if (!scheduled) { scheduled = true; setTimeout(flush, 0); } }
function flush() {
  scheduled = false; cursor = 0; pendingEffects = [];
  lastTree = Component(props);
  for (const run of pendingEffects) run();
}
const React = {
  useState(init) {
    const i = cursor++;
    if (!(i in slots)) slots[i] = { v: typeof init === 'function' ? init() : init };
    const slot = slots[i];
    return [slot.v, next => { const v = typeof next === 'function' ? next(slot.v) : next; if (!Object.is(v, slot.v)) { slot.v = v; schedule(); } }];
  },
  useRef(init) { const i = cursor++; if (!(i in slots)) slots[i] = { current: init }; return slots[i]; },
  useCallback(fn, deps) { const i = cursor++; const prev = slots[i]; if (prev && deps && deps.every((d, k) => Object.is(d, prev.deps[k]))) return prev.fn; slots[i] = { fn, deps }; return fn; },
  useMemo(fn, deps) { const i = cursor++; const prev = slots[i]; if (prev && deps && deps.every((d, k) => Object.is(d, prev.deps[k]))) return prev.v; const v = fn(); slots[i] = { v, deps }; return v; },
  useEffect(fn, deps) {
    const i = cursor++; const prev = slots[i];
    if (prev && deps && prev.deps && deps.every((d, k) => Object.is(d, prev.deps[k]))) return;
    if (!prev) slots[i] = { deps: null, cleanup: null };
    pendingEffects.push(() => { const p = slots[i]; if (p.cleanup) p.cleanup(); const c = fn(); slots[i] = { deps, cleanup: typeof c === 'function' ? c : null }; });
  },
  useId() { cursor++; return 'id'; },
  useSyncExternalStore(_s, get) { cursor++; return get(); },
};
const jsx = (type, p, key) => ({ type, props: p || {}, key });

const t0 = Date.now(); const log = [];
const stamp = () => ((Date.now() - t0) / 1000).toFixed(2) + 's';
const delay = (ms, value, signal, label) => new Promise((resolve, reject) => {
  let settled = false;
  const t = setTimeout(() => { settled = true; log.push(`${stamp()} ${label} 完成`); resolve(typeof value === 'function' ? value() : value); }, ms);
  if (signal) signal.addEventListener('abort', () => { if (settled) return; settled = true; clearTimeout(t); log.push(`${stamp()} ${label} 被取消`); reject(Object.assign(new Error('aborted'), { name: 'AbortError' })); });
});
const SCENARIO = process.argv[2] || 'episodes';
const A = '11111111-1111-1111-1111-111111111111', B = '22222222-2222-2222-2222-222222222222';
const book = { id: A, title: '甲', status: SCENARIO === 'write' ? 'awaiting_review' : 'completed', chapters_done: 3, words_done: 9000, updated_at: '2026-11-10', chapters: [], config: { batch_size: 3, adaptation: { max_scenes_per_chapter: 6 } }, pending_notes: 0, bible: null, compass: null };
const plan = { episodes: [{ id: 'e1', no: 1, title: '一', warnings: [] }], units: [], unassigned: [], plan_revision: 2, plan_approved_revision: null, g0_approved: false, total_seconds: 200, status: 'done', active_breakdown_status: 'running', rebreakdown_pending: true };
class ApiError extends Error { constructor(m, s) { super(m); this.status = s; } }
const STUBS = {
  react: React, 'react/jsx-runtime': { jsx, jsxs: jsx, Fragment: 'Fragment' },
  '@/lib/auth': { getUsername: () => 'fixture-user', ensureAccountIdentity: async () => {} },
  '@/lib/agents': { ApiError },
  '@/lib/novels': {
    listNovels: signal => delay(30, SCENARIO === 'write' ? [book, { ...book, id: B, title: '乙' }] : [book], signal, 'GET 书目'),
    getNovel: (id, signal) => delay(id === B ? 300 : 30, id === B ? { ...book, id: B, title: '乙' } : book, signal, `GET 详情 ${id === B ? '乙' : '甲'}`),
    novelApi: { action: (id, action, body, opts) => delay(120, {}, opts && opts.signal, `POST ${action}`) }, getNovelChapter: async () => ({}), getNovelDraft: async () => ({}),
    addNovelNote: async () => ({}), exportNovel: async () => null, novelErrorMessage: e => String(e && e.message),
  },
  '@/lib/studio': {
    listStudioNovelSources: signal => delay(800, { enabled: true, books: [{ id: A, eligible: true, projects: [{ id: 'p1', title: '甲短片', snapshot_no: 1, created_at: '2026-11-10' }] }] }, signal, 'GET 工作室来源(候选)'),
    studioErrorMessage: String,
  },
  '@/lib/studio-breakdown': { getStudioEpisodes: (id, signal) => delay(100, plan, signal, 'GET 分集方案'), operateStudioEpisodes: async () => plan, approveStudioEpisodes: async () => plan },
  '@/components/novel/NovelShell': { canCloseNovelDrawer: () => false },
  './DeskChaptersView': { __esModule: true, default: function DeskChaptersView() {} },
  './DeskDialogs': { DeskPlanDialog() {}, DeskReaderDialog() {} },
  './DeskEpisodesView': { __esModule: true, default: function DeskEpisodesView() {} },
  './DeskFrame': { __esModule: true, default: function DeskFrame() {} },
  './DeskIdeaView': { __esModule: true, default: function DeskIdeaView() {} },
};
const cache = new Map();
function load(file) {
  if (cache.has(file)) return cache.get(file).exports;
  const mod = { exports: {} }; cache.set(file, mod);
  const out = ts.transpileModule(fs.readFileSync(file, 'utf8'), { fileName: file, compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true } }).outputText;
  new Function('exports', 'require', 'module', out)(mod.exports, spec => {
    if (spec in STUBS) return STUBS[spec];
    if (spec.startsWith('@/')) { const base = path.join(FRONTEND, spec.slice(2)); return load(fs.existsSync(base + '.ts') ? base + '.ts' : base + '.tsx'); }
    throw new Error('unexpected import ' + spec);
  }, mod);
  return mod.exports;
}
const store = new Map([['fiona.desk.v1:fixture-user', JSON.stringify({ open: true, novelId: A, stage: SCENARIO === 'write' ? 'chapters' : 'episodes' })]]);
global.window = { localStorage: { getItem: k => store.get(k) ?? null, setItem: (k, v) => store.set(k, v) }, requestAnimationFrame: cb => setTimeout(cb, 0), cancelAnimationFrame: t => clearTimeout(t), addEventListener() {}, removeEventListener() {}, innerWidth: 1440, setTimeout, clearTimeout };
global.document = { activeElement: null, hidden: false, addEventListener() {}, removeEventListener() {}, querySelector: () => null, querySelectorAll: () => [] };

function find(tree, name) {
  if (!tree || typeof tree !== 'object') return null;
  if (Array.isArray(tree)) { for (const t of tree) { const f = find(t, name); if (f) return f; } return null; }
  if (tree.type && tree.type.name === name) return tree;
  return find(tree.props && tree.props.children, name);
}
const { default: DeskDock } = load(path.join(FRONTEND, 'components/desk/DeskDock.tsx'));
props = { owner: 'fixture-user', open: true, onOpenChange() {}, studioAllowed: true, composerHeight: 96, focus: null, onAsk() {}, onOpenNovel() {}, onOpenNovelShelf() {}, onOpenStudio() {}, onOpenSettings() {} };
Component = DeskDock(props).type;
flush();
const sleep = ms => new Promise(r => setTimeout(r, ms));
const view = () => { const v = find(lastTree, 'DeskEpisodesView'); return v ? { candidateLoading: v.props.candidateLoading, hasPlan: !!v.props.plan } : null; };
async function writeScenario() {
  await sleep(300);
  log.push(`${stamp()} 点 GateBanner「继续写下 3 章」，POST 进行中立即在「作品」下拉切到乙`);
  const action = find(lastTree, 'DeskChaptersView').props.onAction('continue').catch(() => {});
  await sleep(10);
  find(lastTree, 'DeskFrame').props.onSelectBook(B);
  await action; await sleep(1500);
  const frame = find(lastTree, 'DeskFrame').props;
  log.push(`${stamp()} 结果：${JSON.stringify({ loading: frame.loading, book: frame.book && frame.book.title, error: frame.error })}`);
  console.log(log.join('\n')); process.exit(0);
}
(async () => {
  if (SCENARIO === 'write') return writeScenario();
  await sleep(1500);
  log.push(`${stamp()} 首次载入后：${JSON.stringify(view())}（此后每 5 秒轮询一次分集方案）`);
  // 第一次轮询在载入完成后约 5 秒；在它到来前 0.3 秒点「刷新」，候选请求需要 0.8 秒。
  await sleep(4400);
  log.push(`${stamp()} 点「刷新」`);
  find(lastTree, 'DeskFrame').props.onRefresh();
  await sleep(12000);
  log.push(`${stamp()} 等待 12 秒后：${JSON.stringify(view())}`);
  console.log(log.join('\n'));
  process.exit(0);
})();
```
