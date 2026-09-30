# 复核报告（v3 第 2 轮，Opus）

- **结论：通过。** M1 已修好。指令 2–6 都按要求完成，没有引入回归。范围与基线一致，测试数符合预期（本文件 23 passed，全量 1533 passed）。
- **说明：** 本轮 Fable 额度已用完，经用户同意改用 Opus 复核。仓库文件和 git 都没有改动：复核开始和结束时对 7 个目标文件算的 sha1 完全一致，`git status` 也与开始时相同，工作区里没有新产生的文件。

## 前置：确认审的是当前代码

- 用暂存区版本加上 `pre-v3fix.diff` 还原出上一轮的状态，再打上 `v3fix-incremental.diff`。得到的测试文件、page.tsx、02-spec.md 与工作区逐字节相同（`cmp` 输出 SAME）。
- 03-report.md 的旧内容（66535 字节）是当前文件的字节前缀，说明只追加了内容（没有读正文）。
- 复核时没有 codex exec 进程在跑，`done-v3fix` 已存在。

## 逐项核验

| # | 核验项 | 结果 | 证据 |
|---|---|---|---|
| 1 | **M1**：只追加 `((9.0, 2.0), 9)`，id 为 larger-reset-first，旧三行和断言都没改 | 通过 | 测试文件 :258-260 原三行不变，:261 为新行，:264-267 的 ids 前三个不变、后面追加两个。断言 :297-299 在 diff 里只作为上下文出现，没有改动 |
| 1a | 变异：取最后一个不通过项的 reset（照常查询全部不通过项） | 通过 | 本文件 **1 failed, 22 passed**，只有 `[larger-reset-first]` 失败，:297 报 `assert 2 == 9`。全量 **1 failed, 1532 passed**，失败的也只有这一条。同一变异在修复前的测试文件副本上 18 passed，完全存活，所以杀死它的正是新行 |
| 1b | 正确实现下全部通过 | 通过 | 不加插件跑本文件：23 passed。用插件换上与原实现逐行等价的负对照 `MUT=orig`：23 passed，mutant_calls=145 |
| 2 | 追加 `((-10.0, -2.5), 1)`，能杀死 `ceil(x) or 1` 和取绝对值两种写法 | 通过 | `ceil_or_1`：只有 `[past-reset-minimum-one-2]` 失败，报 `assert -2 == 1`，全量 1 failed / 1532 passed。`max(1, ceil(abs(x)))`：只有它失败，报 `3 == 1`。`abs(ceil(x)) or 1`：只有它失败，报 `2 == 1`。这三个变异在修复前的副本上都存活（18 passed） |
| 3 | 新增的 on_reject 测试能杀死「日志取最后一个不通过项」 | 通过 | 新测试位于 :302-320，只追加，没改已有用例。两道闸都是 `1/minute`，先打满，:309-312 再确认两道都不通过。`log_last` 变异下只有该测试失败，:320 报 `[(...'second'), 60)] == [(...'first'), 60)]`，全量 1 failed / 1532 passed，修复前副本上存活。另外加测了「每个不通过项各回调一次」的变异 `log_each`，也只有它失败，说明「恰好一次」这个断言确实起作用 |
| 4a | 补丁打在 `type(limiter.limiter)` 上，签名带 self | 通过 | :289 `fake_window_stats(self, ...)`，:293-295 三处都是 `monkeypatch.setattr(type(limiter.limiter), ...)`，lambda 都带 self |
| 4b | 撤销后实例上不残留方法 | 通过 | 新测试 :323-336 断言撤销后 `"test" not in vars(strategy)`，三个方法都不在实例上，类属性恢复原值。**这个测试本身有效：** 在仓库外副本里把 F2b 改回对实例打补丁，它就失败，单独跑时 :333 报 `'test' not in {..., 'test': <bound method ...>}`，与 F2b 同跑时前置断言失败 |
| 4c | 类级补丁在撤销前后都不影响其他测试 | 通过 | 自写的 r2order 插件在每条用例全部 teardown 结束后检查两件事：实例上没有这三个方法，类上的三个属性与会话开始时是同一个对象。它自身有正控：对实例打补丁的小用例会被报 `instance residue ['test']`，退出码 3。检查结果：全量默认顺序 residue_checked=1533、violations=0、1533 passed；把本文件挪到全量最前面也是 1533 passed、violations=0；本文件用种子 1–10 各打乱一次，每次 23 passed、violations=0；用 `--keep-duplicates` 把本文件重复 3 份混在一起打乱（种子 11–13），每次 69 passed、violations=0 |
| 5 | page.tsx 只改注释，常量和逻辑都没动 | 通过 | 这一轮 page.tsx 只有一个 hunk，删 1 行、加 2 行，全部以 `//` 开头。:93 仍是 `TTS_PRELOAD_MAX_TICKET_AGE_MS = 45_000`，:955 的判断没动。注释 :90-92 包含指令要求的全部要点：60 秒过期、一般不会触发、250 字约 39 秒、「帮我读」300 字约 47 秒、越界只多换一张票和一个小空档、不会丢句。核对数值：voice.py:32 为 `TTS_TICKET_TTL_SECONDS = 60`，page.tsx:1419 为 `MAX_CHUNK = 250`，:863 为 `text.slice(0, 300)` |
| 5a | tsc / eslint | 通过 | 在仓库外副本 `scratchpad/fe-r2` 里跑，page.tsx 的 sha 与工作区一致（190ed398…）。`npx tsc --noEmit` 退出码 0。tsc 有正控：在副本里把常量标成 string 类型，报 TS2322 和 TS2365，退出码 2，之后已还原。`npx eslint`：0 errors、26 warnings，其中 page.tsx 25 条、plaza/page.tsx 1 条。把 page.tsx 换回修复前的版本也是 25 条，说明本轮没有新增警告 |
| 6 | 勘误段只补了半句，表述与代码一致 | 通过 | 用脚本比对：新行删掉「；WebKit 换票时的预热合成不计入使用次数，另算一次合成」这一句后，与旧行完全相同，只插入一次（02-spec.md:79）。对照代码：预热在 voice.py:305-323 签票时直接 `create_task(_build_tts_audio(...))`，不经过 `_use_tts_ticket`。`uses` 只在 :140 加一，由 :406、:428 两处调用；:138 用 `TTS_MAX_TICKET_USES` 做检查。所以「不计入使用次数，另算一次合成」是准确的 |
| 7 | 范围：rate_limit.py、voice.py、frontend/lib、ARCHITECTURE.md 与基线一致 | 通过 | 基线 `refs/fiona-baselines/tts-ratelimit-v1` = 67a569e2。`git diff <ref> -- ...` 输出 0 行，`--cached` 也是 0 行，这些路径下没有未跟踪文件。工作区相对暂存区有改动的只有测试文件、02-spec.md、03-report.md、page.tsx 这 4 个 |
| 8 | 测试数 | 通过 | 全量 `1533 passed, 11 warnings in 45.58s`，退出码 0。本文件 `23 passed`，即 19 + 参数表 2 行 + on_reject 测试 1 条 + 残留检查测试 1 条 |

### 变异方法与正控

- 插件：`scratchpad/plug/r2mut.py`。它在 autouse fixture 里用 `monkeypatch.setattr(request.module, "check_and_hit", 变异)` 替换测试模块里的函数，同时替换 `routers.voice.check_and_hit`。变异体在调用时读取 `rate_limit.time.time()` 和 `rate_limit.limiter`，所以 F2b 伪造的时间和类级补丁对它同样生效。
- **正控 `const42`（恒返回 42）：** 本文件 18 failed / 5 passed，mutant_calls=22。全量 48 failed / 1485 passed。插件确实生效。
- **负对照 `orig`（与原实现等价）：** 23 passed，mutant_calls=145。
- **修复前对照：** 从基线还原出上一轮的测试文件，放到仓库外副本里跑，排除一条依赖文件路径的用例。last_failed、ceil_or_1、abs_ceil、log_last 这几个变异在它上面全都 18 passed，也就是全部存活。
- 运行方式：`PYTHONPATH=<plug> MUT=<名> PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider -p r2mut ...`，在 backend/ 下执行。

## 仍未修好的必须修复项

无。

## 可优化（不影响结论）

1. F2b 的函数名 `test_retry_after_uses_latest_failed_reset_...` 和旧 id `latest-failed-reset` 里的 latest 容易被读成「最后一个不通过项」。实际要求的是取所有不通过项里最大的 reset，这正是 M1 暴露的那个歧义。本轮指令禁止改旧的 id 和用例，所以只记下来，以后整理时可以改成 max/largest 一类的说法。
2. eslint 的 26 条警告是 page.tsx 25 条加 plaza/page.tsx 1 条。上一轮报告写的「25 warnings」应该只算了 page.tsx，口径不同，不是新增的警告。以后记录基线时最好写明统计范围。
