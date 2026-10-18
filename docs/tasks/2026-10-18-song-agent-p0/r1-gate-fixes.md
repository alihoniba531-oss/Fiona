# R1 门禁返修单（写歌 P0）

你上一轮的实现整体通过了门禁：白名单、基线测试零改动、全量 7510 passed / 0 skipped、前端 lint/tsc/build、长命库升级、浅克隆、实机走查都过了。下面 5 项必须修，其中 1、2 是规格作者自己写错/漏写的（`02-spec.md` 已同步修订，见 §15「修订记录」和 §8.1、§8.2 标「R1 修订」的条目，**先读这三处**）。

工作方式不变（见 `02-spec.md` §0）：用工作流 `parallel()` 按文件不重叠并发；不得改任何既有测试（含 `4b45346` 时已存在的测试文件）；新增测试只能加在你上一轮新建的 `backend/tests/test_song_*.py` 里；不提交、不 stash、不切分支；**不要修改 `02-spec.md`、`01-brief.md`、本文件**。

## 必须修复

1. **安全规则必须仍在末尾**（`backend/services/claude_agent.py`）
   - 现状：写歌开启时 `state.sys_prompt_final += "\n\n" + SONG_MODE_PROMPT`，把基础安全规则挤到了中间。Fiona 既有不变量：所有 system 消息合计恰好包含一次基础安全规则，放在最后一条 system 消息末尾（见 `backend/tests/test_beta_safety.py:219–226` 的断言写法）。
   - 改法：写歌开启时把 `SONG_MODE_PROMPT` 拼进 `_final_system_prompt` 的**入参**：`chat._final_system_prompt(chat.apply_mode_prompt(chat._without_safety(ctx.system_prompt), mode) + "\n\n" + SONG_MODE_PROMPT, trailing_system=chat._has_trailing_system(ctx))`；写歌关闭时这一行与现在逐字一致。删掉原来的末尾追加。
   - 新测试（加在 `test_song_agent_tools.py`）：开关开启用假流跑一轮，取发给模型的全部 system 文本，断言 `SONG_MODE_PROMPT` 恰好出现 1 次、`BASE_SAFETY_RULES.strip()` 恰好出现 1 次、最后一条 system 消息 `rstrip()` 以 `BASE_SAFETY_RULES.strip()` 结尾、且 `SONG_MODE_PROMPT` 的位置在安全规则之前；`ctx.messages` 末尾带 trailing system 的情形也测一次（此时安全规则在 trailing system 末尾，写歌提示仍只出现 1 次）。正控：先在测试里构造「末尾追加」的错误拼法，确认断言会失败，再断言真实实现通过。

2. **更新简报时对已有歌词重检**（`backend/song/tools.py`，如需可改 `backend/song/store.py`）
   - 现状：`song_save_brief` 带 `project_id` 更新结构或语言后，最新一稿歌词的 `check_json` 仍是按旧结构算的，`ok=true` 时可以拿着与新结构不符的歌词去生成。
   - 改法：更新已有歌词的项目（`lyrics_revision > 0`）时，在同一次工具调用里，用最新一稿的 `sections`（按 id 取行）对新结构与新语言重跑 `check_lyrics`，另存为新的一稿（稿号 +1、`changed_section_ids=[]`），工具返回文本附上「已按新结构重检第 N 稿」与自检摘要。结构 id 对不上就会有 `structure_mismatch` 错误，`can_generate` 因此为 false。项目还没有歌词时行为不变。
   - 新测试：先存简报+歌词（自检 ok）→ 用 `song_save_brief` 把某段 `lines` 从 4 改成 2（或删掉一段）→ 断言稿号 +1、新稿自检 `ok=false` 且含对应错误、`POST generate` 返回 409、快照 `can_generate=false`；再测「只改了语言为 English 且歌词超过 English 规则」之类的语言变更也会重检（或任选一个能证明语言参与重检的例子）。

3. **「只改这一段」必须有证明力的测试**（`test_song_agent_tools.py`）
   - 门禁变异：在 `_revise_section` 里加一句 `sections[0]["lines"] = list(lines)`（顺带改第一段），全部 280 个写歌测试仍然通过。
   - 补测试：结构至少 4 段（含器乐段），分别对**中间一段**和**最后一个唱段**调用 `song_revise_section`，断言新稿里除目标段外的每一段 `lines` 与基础稿**逐项相等**（比较完整列表，不只比较长度或某一行），目标段等于新行，`changed_section_ids == [目标段 id]`，稿号 +1；基础稿本身在库里不被改动（再读一次第 N 稿仍是原文）。

4. **回读标识核对必须有证明力的测试**（`test_song_media.py`）
   - 门禁变异：把 `_probe_output` 里的 `or aigc.get("ProduceID") != version_id` 删掉，测试仍然全过。
   - 补测试：用 ffmpeg 生成两段 6 秒 mp3：一段 `AIGC` 标签里 `ProduceID` 是另一个 id，一段完全没有 `AIGC` 标签；分别对它们调用 `_probe_output(path, 期望id)`，断言都抛 `MediaError` 且 `code == "invalid_audio"`；正确 id 的文件返回时长 > 5。

5. **`rejected` 文案**（`frontend/components/SongProjectCard.tsx`）
   - `rejected` 显示「提交被拒，已退回草莓」，不再与 `failed` 共用「失败」+ 失败原因；`failed` 行为不变。`test_song_frontend.py` 加一条源码检查。

## 完成后

- 在 `backend/` 跑：`.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_song_*.py` 与全量 `.venv/bin/python -m pytest -q -p no:cacheprovider -rs`，都要 0 failed、0 skipped；前端 `npm run lint && npx tsc --noEmit && npm run build`。
- 在 `03-report.md` 末尾追加「R1 返修」一节：逐条说明 1–5 改了什么、新增了哪些测试（测试名）、各自的正控/反例，以及上面命令的末尾计数行原文。
- 文档里如果写了「写歌提示追加在系统提示末尾」之类的说法，按新做法改正（CLAUDE.md、docs/ARCHITECTURE.md 中与写歌提示词位置有关的句子）。
