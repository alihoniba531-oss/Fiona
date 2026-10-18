# WO3e 复核返修 R1（接着你前面的工作改）

独立复核没有通过。报告在同目录 `04-review.md`，只读。
- 第 3 节：M1–M7，每项有位置、失败场景和建议改法。
- 第 5 节：复核方给的修改指令。

**本单 = 复核第 5 节第 1–9 条全部照做，另加下面「主控追加」的 6 条。** 两处冲突时，以本单为准。

`02-spec.md` 已更新两处，请先读：
- §3.1：tags 一律用 kebab-case。
- §5：grammar 先按优先级截取前 5 张，再按 id 排序。

## 主控追加（作者规格的澄清，不是新功能）

| 编号 | 内容 |
|---|---|
| X1（复核 P1） | 按更新后的 §5 改 `retrieval.py` 的 grammar 选取：按 template → position → 命中卡的优先级去重，截取前 5 张，再按 id 排序输出。补测试：dialogue + body + `face_closeup` 时，结果必须含 `grammar-over-shoulder`、`grammar-shot-reverse-shot`、`grammar-shot-size`。 |
| X2（复核 P2） | 全库卡片 tags 统一为 kebab-case。`schema.py` 的 tag 正则只允许 `^[a-z0-9]+(?:-[a-z0-9]+)*$`。`retrieval` 匹配前把 `SceneTags.sensitive` 和输入 tags 里的 `_` 换成 `-`。卡片里两种写法重复的，去重后只留连字符写法。**两张样卡 `scene-dialogue.yaml`、`scene-fight.yaml` 本来就是 kebab-case，一字不许改**。补测试：`sensitive=["face_closeup"]` 能命中 `grammar-insert-closeup`；schema 拒收带 `_` 的 tag。 |
| X3（复核 P3） | 写实度为 3d、取不到模型卡时，试拆详情的每个模式加 `model_card_missing: true`；前端在该栏顶部显示「该写实度没有对应的模型卡，未注入模型能力与其检查规则」。补后端测试和前端测试各 1 条。 |
| X4（复核 P4） | 两张位置卡 `scene-opening-hook.yaml`、`scene-cliffhanger.yaml` 删掉与位置无关的通用条目：camera 第 4–6 条（不看镜头、至少 4 秒、写实不脏），以及 opening-hook 的 IP 拦截风险项。只留「在这个位置要额外做什么」。改完后重跑你的 schema 自查和 20 字重合自查。 |
| X5（复核 P6 的一部分） | `lint.py` 改两处。规则 4：camera 含「非固定」时视为非固定机位。`seedance-prompt-too-long`、`seedream-prompt-too-long`：只拿 `video_prompt`（Seedance）或 `first_frame_prompt`（Seedream）的长度去比，不再拿 5 个字段拼起来的长度。每处补正反用例各 1 条。 |
| X6（复核 2c 小瑕疵） | `scene-confrontation.yaml` 的 camera 里「压力升级用固定机位加轻微推轨」自相矛盾。改成：人脸镜头用固定机位；非人脸的双人中景可以轻推轨。 |

**本轮不做**，留给后续：复核的 P6 其余部分、P7、P8、P10、P11、P12、P14、P15。

## 并行方式（必须照做）

用**工作流（workflow 工具）**并行：在脚本里用 `parallel()` 同时运行 4 个 agent，按文件不重叠分工。

- 每个 agent 的任务说明必须自包含：写明工作目录、Python 路径、`04-review.md` 和本单的绝对路径、它负责的条目、白名单、下面的「接口约定」，以及「不得调用 subagent / subagent_fork / workflow」。
- 白名单外的文件一律不许改。
- 既有测试一字不许改，这里的「既有」指 `4b45346` 里已有的测试；本期新增的测试文件可以追加用例。

| agent | 负责条目 | 白名单 |
|---|---|---|
| K 试拆与计费 | M1 后端、M2、M3、M4、M5、M6-B（报价额度测试）、P9（去掉 300 秒超时）、X3 后端、`get_trial` 的 lint 改用 `asyncio.to_thread` | `backend/studio/kb_trial.py`、`backend/studio/cross_review.py`、`backend/studio/spend.py`、`backend/studio/recovery.py`、`backend/tests/test_studio_kb_api.py`、`backend/tests/test_studio_cross_review.py` |
| L 取材料与 lint | M7、P5（一次 lint 只加载一次卡片）、M6-D、M6-E、X1、X2 的 schema 与 retrieval 部分、X5 | `backend/studio/director_kb/{lint,retrieval,schema,loader}.py`、`backend/tests/test_studio_kb_core.py` |
| N 卡片内容 | X2 的卡片 tags 改写、X4、X6 | `backend/studio/director_kb/cards/**/*.yaml`，两张样卡除外 |
| F 前端 | M1 前端、X3 前端、P13 | `frontend/lib/studio-kb.ts`、`frontend/components/studio/kb/*.tsx`、`frontend/app/studio/page.tsx`、`backend/tests/test_studio_kb_frontend.py` |

## 接口约定（K、F 共用；L、N 共用）

**报价**（`kb_trial._public_quote`）
- `items[*]` 每行加 `currency: "CNY" | "USD"`。
- `totals: {"CNY": number, "USD": number}` 保留。
- 全部行同币种时，`total` 为数字、`currency` 为该币种；混合币种时 `total: null`、`currency: "mixed"`。

**试拆详情**
- `with_kb` / `without_kb` 各加 `model_card_missing: bool`。

**tags**
- 卡片里的 tags 只用 kebab-case。
- schema 正则为 `^[a-z0-9]+(?:-[a-z0-9]+)*$`。
- retrieval 匹配前把 `_` 统一换成 `-`。

## 并行之后，主代理自己做

1. **白名单检查**：用 `git status --porcelain -uall`，对比本轮开始前的快照，本轮新增或修改的文件只能落在四个白名单的并集里，外加报告。两张样卡的 sha256 仍为：
   - dialogue：`d99982df83b7bb573c54f59e9a7ac085d871e96296f6731494c2e46e7c13673d`
   - fight：`72e48fd09638d90c3a4469d18b04c920979c828e1ec5e08414976ed1cbeb5129`
2. **门禁**：
   - `cd backend && <Python> -m pytest -q tests/ -k studio`：0 failed、0 skipped。
   - `cd frontend && npx tsc --noEmit && npm run lint`：0 error。
   - 新文件里不得出现粗体写法。
3. **变异自测**：复核第 5 节第 7 条的 3 个变异，加上 X1、X2 各 1 个自选变异，逐一打入，确认变红后还原，并核对 sha256。
4. **集成修正**：有失败时，再用一次工作流做集成修正，同样一块一个 agent、自包含，最多 2 轮。

## 报告

写到 `docs/tasks/2026-10-18-studio-wo3e-director-kb/05-report-r1.md`，内容包括：
- 拆分表：如实列出全部 agent。
- 逐条（M1–M7、P5、P9、P13、X1–X6）列出改动文件与行号、新增测试名。
- 变异自测结果。
- 门禁数字。
- 未完成或需要人工确认的地方。

禁止联网、读 `.env`、读或打印 Key、提交。

如果本机 `NO_PROXY` 含 `[::1]`，跑 pytest 前加 `env -u NO_PROXY -u no_proxy`。
