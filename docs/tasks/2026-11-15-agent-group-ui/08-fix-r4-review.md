# 复核返修单 第 1 轮：讨论群第二期（界面）

依据独立复核 `04-review.md`、规格 `02-spec.md` 开头的「v1.3 修订」，以及规格作者在复核之后做的浏览器补测。这是复核返修的第 1 轮（最多 3 轮）。

## 一、现状与范围

三轮门禁返修之后的状态已经过了机械门禁：全量 8608 条通过、0 失败、0 跳过；规格作者的 87 处变异全部被断言发现；v1.1、v1.2 的各条在真实浏览器里全部合格。这些不要回退。

独立复核的结论是不通过，有 4 条必须修复；规格作者按复核方点名的疑点到浏览器里补测，又确认了 3 条。本轮做下面 A–G 七件事，外加第三节的文档与用例。

1. 允许改的文件：
   - `frontend/components/discuss/` 下的文件；
   - `frontend/lib/discussLogic.ts`、`frontend/lib/discuss.ts`；
   - 你自己的三份测试 `backend/tests/test_discuss_frontend_logic.py`、`test_discuss_frontend_guards.py`、`test_discuss_frontend_navigation.py`；
   - `README.md`（只改第三节写明的那一句）；
   - `docs/tasks/2026-11-15-agent-group-ui/impl/report.md`（只在开头加第三节写明的那一行说明）与新报告 `impl/report-fix-r4.md`。
2. 其余一律不动：`frontend/app/` 下的文件、`frontend/components/Sidebar.tsx`、`frontend/app/globals.css`、两份既有测试、后端代码、规格、各张返修单、`04-review.md`、依赖。
3. `04-review.md` 第 4 节的 12 条可优化项本轮**不要做**，也不要顺手改（下面写进来的除外）。
4. 不提交 git，不用 `git stash`、`git checkout` 还原文件。界面文字不加粗。除本单写明的以外，不改既有中文文案。
5. 何时停下来问：只有「做不到下面的要求」或「要求之间互相矛盾」才停下来说明；怎么实现、怎么验证，自己定并写明理由。你实测到的事实优先于本单的断言，不符就停下来说明。任何情况下不回滚已完成的工作。

## 二、七件事

### A. 插话之后，轮询会永久漏掉一段引擎消息（复核必须修复 1）

规格作者在浏览器里复现了：一个进行中的群，轮询停在 `after=303`；这时库里写入一条引擎消息（`id` 304），紧接着从界面发一条插话（返回 `id` 305）。之后的轮询全是 `?after=305`，304 那条再也没出现，直到整页重新加载。

原因：`frontend/components/discuss/DiscussRoom.tsx` 里 `poll` 与 `refreshDetail` 都用 `maxMessageId(当前消息)` 当 `after`，而 `sendNote` 把插话并进了当前消息。规格 4.9 原来的写法就是这样，是规格的错，已在 v1.3 第 1 条改正。

要求：见规格 v1.3 第 1 条。所有带 `after` 的读取（轮询、操作之后的补读、重新读方案等）都用这个游标；第一次读取与分页续读照旧。插话会在下一次读取时再回来一次，`mergeDiscussMessages` 去重并以服务器版本为准，界面上不能出现两条。

### B. 新建页自定义成员的模型：显示的和实际用的不一样（复核必须修复 2）

现象：「我来组队」加一位自定义成员，「更多设置」里它的模型下拉显示「千问 3.8 Max」；不动它建群，这位成员实际用的是 DeepSeek Flash；想选千问也选不出来（下拉本来就停在千问，请求里不带）。

原因：`frontend/components/discuss/DiscussCreateForm.tsx` 读 `catalog.defaults.general`，目录里没有这个键（`backend/discuss/service.py` 的 `catalog()` 只给固定席位、角色池成员和分身的默认值），于是回落成目录里的第一个模型；`buildDiscussCreateBody` 又只在「与默认不同」时才带上。

要求：见规格 v1.3 第 2 条。`frontend/lib/discuss.ts` 里那段说「通常取 `catalog.defaults.general`」的注释同步改正。初始值怎么取写成 `discussLogic.ts` 的纯函数。

### C. 方案只读视图不显示自定义调研成员的分工（复核必须修复 3）

`frontend/components/discuss/DiscussPlanPanel.tsx` 的只读视图里，条件是 `member.kind === "lens" && !!member.focus`；后端对自定义调研成员返回 `kind: "custom"` 且带 `focus`。

要求：见规格 v1.3 第 3 条。

### D. 字重守卫有洞（复核必须修复 4）

`backend/tests/test_discuss_frontend_guards.py` 的字重守卫按字面匹配 `<b>`、`<strong>`。复核方实测：在部件里写 `<strong className="…">` 或加 `[font-weight:600]`，全部用例照样通过。

要求：见规格 v1.3 第 4 条。用例里先拿一段样例文本（含 `<strong className="x">`、`<b className="x">`、`[font-weight:600]`、`style={{ fontWeight: 600 }}`）证明正则都能命中，再扫描真实文件。`font-normal` 照旧允许。

### E. 列多的表格被挤到断词（规格作者补测）

实测（抽屉 1280×900，一条消息里有一张 10 列的表）：表格 737px 等于容器宽，不出现横向滚动；每列只有 74px，中文一行三四个字，`Facebook`、`Instagram` 被从中间断开。

要求：见规格 v1.3 第 5 条。做法你定（例如按列数给表格一个最小宽度）。两三列的表格表现不变。

### F. 发送插话之后焦点丢了（规格作者补测）

实测：在插话框里打字、按 Enter 发送，成功后 `document.activeElement` 是 `BODY`，要再点一下输入框才能接着打字。原因多半是发送中把输入框设成了 `disabled`，浏览器会把焦点移走。

要求：见规格 v1.3 第 6 条。发送中仍然不能重复提交。

### G. 停在别的标签时到达的新消息，回来既不跟随也不提示（规格作者补测）

实测（抽屉 1280×900，窄布局）：停在群聊最底，切到成果标签，这期间到达两条新消息，再切回群聊：位置停在原处（离最新一条还有 164px），也没有「有新消息」按钮。

原因：`frontend/components/discuss/DiscussTimeline.tsx` 在面板不可见时只更新了「最后一条消息的 `id`」，回来时认为没有新消息。

要求：见规格 v1.3 第 7 条。v1.1 第 4 条的其余表现不变：第一次看到群聊时停在最新一条；期间没有新消息时，来回切换保持离开时的位置。返修 3 的用例钉住了 `DiscussTimeline.tsx` 里几处标签的类名（`aria-label="群聊"` 的 `section`、`ref={viewportRef}` 的消息区及其外层），这些类名不要动。

## 三、文档与用例

文档：

1. `README.md`「讨论群界面（第二期）」一节里的这句不准确：「访问检查通过才会出现书签，否则显示「暂未开放」。」检查不通过时书签根本不出现；直接打开独立页看到的是「讨论群尚未开放」或「你的账号暂未开通讨论群」。按实际改正这一句。
2. `docs/tasks/2026-11-15-agent-group-ui/impl/report.md` 里关于 `"drawer" + "-panel"` 拼接和 `role="dialog"` 手写弹层的陈述已被返修 1 取代。在这份报告的开头加一行说明，指向 `report-fix-r1.md`，正文不用改。

用例（放进你自己的三份测试文件）：

1. A：游标怎么前进的纯函数，至少覆盖：游标 1、并入 `id` 3 的插话之后，下一次 `after` 仍是 1；服务器读回 2、3 之后游标是 3；读回空列表时游标不变；读回的最大 `id` 比游标小时游标不变。再加一条守卫，钉住 `DiscussRoom.tsx` 里带 `after` 的读取用的是这个游标，而不是本地最大 `id`。
2. B：初始值的纯函数，用 `backend/discuss/service.py` 里 `catalog()` 的真实形状断言返回 `deepseek:deepseek-flash`；`buildDiscussCreateBody` 对自定义成员总是带上 `models.customN`（不改模型时也带）。你原有的相关用例按 v1.3 第 2 条更新。
3. C：只读视图是否显示分工的判断写成纯函数并测：`lens` 与 `custom` 且 `focus` 非空为真；`focus` 为空、固定席位、分身为假。
4. D：见上。
5. E、F、G：各至少一条守卫，钉住你选的机制，断言落在具体的标签或函数上，不按整份文件查子串。
6. 复核方的变异 M16（`DiscussDocument.tsx` 里编号链接直接用 `source.url`，不经过 `safeExternalUrl`）现在没有用例拦得住。加一条守卫，让这种改坏变红；`DiscussSourcesPanel.tsx` 里的来源链接同理。
7. 自检表：A–G 与 M16 各自的改坏方式（把实现改回本轮之前的写法，或上面写明的改法），由哪条用例靠断言失败发现（必须是 `failed`，不是 `error`）。自检用的临时脚本放在仓库外，用完删掉。

## 四、判据（规格作者会在真实浏览器里逐条量）

1. A：进行中的群，在一次轮询被拦住时往库里写一条引擎消息，再从界面发一条插话；放开之后，下一次轮询的 `after` 小于插话的 `id`，那条引擎消息出现在插话之前，插话只有一条。
2. B：`/discuss/new`「我来组队」加一位自定义成员，下拉初始显示「DeepSeek Flash」；不改直接建群，请求体里有 `models.custom1`，值是 DeepSeek Flash；选千问建群，方案标签里这位成员显示千问。
3. C：有自定义成员、且主持人给了分工的群，方案标签只读视图里这位成员显示「分工：…」。
4. E：抽屉 1280×900，10 列的表：每列不小于 100px，表格在自己的容器里横向滚动，页面不出现横向滚动；两三列的表仍是 720 / 720，不滚动。
5. F：按 Enter 发送成功后，`document.activeElement` 是插话框，紧接着打字能输入；发送失败后同样。
6. G：停在群聊最底，切到成果，到达两条新消息，切回群聊：离最新一条的距离为 0。先往上滚 300px 再重复一遍：位置不变（±2px），出现「有新消息」按钮，点它滚到最新。期间没有新消息时来回切换，位置不变。
7. 不回退：v1.1、v1.2 的各条判据（群聊高度、底部留白、消息区最小高度、对话框只在点遮罩时关闭等）。

## 五、验收

命令前加 `NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=localhost,127.0.0.1,::1,.local`。

1. 在 `frontend/`：`npm run lint -- --max-warnings=25`、`npx tsc --noEmit`、`npm run build` 都是退出码 0。
2. 在 `backend/`：`.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_discuss_frontend_*.py tests/test_discuss_ui_api.py tests/test_ui_polish_page_contracts.py tests/test_ui_closeout_dialog_scrim.py tests/test_studio_frontend_*.py` 全部通过、0 跳过。
3. 在 `backend/`：全量 `.venv/bin/python -m pytest -q -p no:cacheprovider`，0 失败、0 跳过，通过数 = 8608 + 本轮净增的用例数（写明净增几条）。唯一的失败如果是 `tests/test_novel_workflow.py::test_failed_parallel_phase_cancels_and_drains_siblings_before_return`，单独重跑并贴出两次输出，不要为它改文件。
4. `git diff --stat -- backend/tests/test_ui_polish_page_contracts.py backend/tests/test_ui_closeout_dialog_scrim.py`：与本单派出时相同。
5. `git status --porcelain --untracked-files=all`：相对本单派出时，变动只在第一节第 1 条允许的文件里。

报告写进 `docs/tasks/2026-11-15-agent-group-ui/impl/report-fix-r4.md`，不写本机绝对路径：A–G 逐条做了什么、改了哪些文件、选的做法与理由；文档两处的改动；新用例与自检表；验收五条的命令与输出摘要；没做完或需要人工确认的地方。
