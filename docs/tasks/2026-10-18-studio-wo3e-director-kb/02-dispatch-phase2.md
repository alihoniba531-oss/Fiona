# WO3e 阶段二派单：导演知识库 + 交叉审核（7 块并行）

- **工作目录**：`/Users/yangjing/Desktop/ai-workspace/.worktrees/fiona-studio`
- **Python**：`/Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python`
- **规格**：同目录 `02-spec.md`。先完整读这份，再读以下三份：
  - `00-house-rules.md`：作者规则，优先级最高。
  - `01-scene-list.md`：场景类型定义。
  - `03-cross-review.md`：交叉审核。与 `02-spec.md` §8.1 冲突时，以 §8.1 为准。
- **样卡**：`backend/studio/director_kb/cards/scene/scene-dialogue.yaml` 和 `scene-fight.yaml` 已经作者确认，**一字不许改**。它们是其余场景卡的写法样板。

## 你的角色

你是主代理，只做六件事：拆分、派发、汇总、白名单检查、跑门禁、写报告。实现工作一律交给子代理。

## 并行方式（必须照做）

用**工作流（workflow 工具）**并行：
- 在脚本里用 `parallel()` 同时运行 7 个 agent，对应 `02-spec.md` §10 的 A、B、C、D1、D2、D3、D4 七块。
- 按文件不重叠拆分；同一文件及其测试只归一个 agent。
- agent 不带 schema，直接返回文本。

每个 agent 的任务说明都必须**自包含**，因为 agent 看不到你的对话。说明里要原样写明以下内容：
1. 工作目录、Python 路径，以及上面四份文档的绝对路径；要它先读 `02-spec.md` 全文和 `00-house-rules.md`，并指明它这一块最相关的章节：
   - A：§3、§5、§6、§7、§12，以及 §10 的 A 行。
   - B：§5、§8、§8.1、§12。
   - C：§8、§8.1、§9、§12。
   - D1、D2、D3、D4：§3、§4、§11，并以两张样卡为样板。
2. 本块的**白名单**：照抄 §10 本块那一行的文件，加上本块报告 `docs/tasks/2026-10-18-studio-wo3e-director-kb/03-report-<块>.md`。写明「白名单外的文件一律不许改，也不许新建」。
3. 跨块契约：§13 最后一条。
   - B、C 按 §5–§7 和 §10 A 行的函数签名编码。
   - 场景卡只能引用 §3.6 里的 id。
   - 跑集成测试前，先确认依赖文件已经落盘；没落盘就先做别的，最后再跑。
4. §13 的执行约定，全部照抄：
   - 既有测试一字不许改。
   - 测试不读仓库外文件。
   - 何时停下来问。
   - 实测事实优先于规格。
5. 规格末尾的禁止事项：联网、读 `.env`、读或打印 Key、提交、动 `frontend/node_modules`。
6. **不得调用 subagent / subagent_fork / workflow**，全部工作自己完成。
7. 分块要求：
   - **C 块**：先读 `frontend/AGENTS.md` 和 `frontend/node_modules/next/dist/docs/` 里对应的文档再改前端；遵守 §9「界面文字不加粗」。
   - **D 块（D1–D4）**：
     - 在 `$TMPDIR` 写临时自查脚本，不入库。一个按 §3 做 schema 检查（A 的 `schema.py` 已落盘就直接用它）；另一个把本块卡片和 §11 的来源文件逐一比对，查连续 20 字相同，`sources` 行里的路径字符串不算。
     - 改到两项都 0 问题为止。
     - 数字一律用阿拉伯数字。
     - `example` 一律原创。
8. 报告 `03-report-<块>.md` 写五项：
   - 修改了哪些文件
   - 实现了哪些功能
   - 与 §10 和 §12 的逐项对应
   - 测试结果，带 passed / failed / skipped 数
   - 未完成或需要人工确认的地方

## 并行之后，主代理自己做

1. **白名单检查**：用 `git status --porcelain -uall` 列出改动。派单前已存在的未跟踪文件不算：本目录下以 `00-`、`01-`、`02-`、`03-cross-review` 开头的文档，以及两张样卡。其余改动必须全部落在七块白名单的并集里，`__pycache__/` 除外。两张样卡用 `git diff --no-index` 或 sha256 确认未变：
   - dialogue：`d99982df83b7bb573c54f59e9a7ac085d871e96296f6731494c2e46e7c13673d`
   - fight：`72e48fd09638d90c3a4469d18b04c920979c828e1ec5e08414976ed1cbeb5129`
2. **跑门禁**：
   - 在 `backend` 目录运行 `<Python> -m pytest -q tests/ -k studio`。
   - 在 `frontend` 目录运行 `npx tsc --noEmit` 和 `npm run lint`。
3. **集成修正**：有失败时，再用一次工作流 `parallel()` 做集成修正。
   - 每个 agent 只负责一块的白名单，任务说明里附上失败输出原文，其余要求同上。
   - 集成修正最多 2 轮。
   - 仍不过就停下，在报告里写清原因，不回滚已完成的工作。

## 最终回复

- **开头**：拆分表，如实列出全部派出过的 agent，包括集成修正轮；每行写块名、白名单、结果。
- **变更总结五项**：
  1. 修改了哪些文件
  2. 实现了哪些功能
  3. 与 §12 验收的逐项对应
  4. 门禁结果：pytest、tsc、lint 的原样摘要和数字
  5. 未完成或需要人工确认的地方
