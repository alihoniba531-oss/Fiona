# 复核报告（v1.2 测试补强，Opus 5.5）

- **结论：通过。**
- 上一轮复核的可优化项 1、2 已按规格「v1.2 追加」补好。
- 规格点名的三种错误实现，都至少有一条新测试会失败，其中两种只有新测试能拦住。
- 未改动的副本和工作树都是全量 1545 passed。

## 逐项核验

| 核验项 | 结果 | 证据 |
|---|---|---|
| 1a. 只动了白名单内的文件 | 通过 | `git diff --name-only` 只有两个文件：`backend/tests/test_tts_ticket_ttl.py`、`docs/tasks/2026-09-30-tts-ticket-ttl-150/03-report.md`。<br>没有未跟踪文件。<br>`git diff -- backend/routers frontend docs/ARCHITECTURE.md` 输出 0 字节。<br>排除这两个文件后的 diff 也是 0 字节。<br>工作树里的 voice.py 与暂存区一致，sha1 为 969473f9…。 |
| 1b. 已有用例一字未改 | 通过 | `--numstat` 是 43 行新增、0 行删除，只有一个 hunk：`@@ -201,0 +202,43 @@`，接在原文件最后一条用例之后。<br>`^-[^-]` 删除行计数为 0。<br>03-report.md 也是纯追加（328/0，hunk 从 541 行之后开始），正文按要求没有读。 |
| 2a. 新测试 1 对应 v1.2-1：每用户淘汰前先清过期票 | 通过，非退化 | 用例 `test_expired_newest_ticket_is_cleaned_before_user_cap_evicts_oldest`（:204-214）。<br>场景与规格一致：每用户上限 2；签 a1、a2，把 a2 设为过期（它是最新的，不是最早的）；再签 a3。<br>断言整张表 `== [a1, a3]`，这比「A 的票」更严格，因为表里只有 A 的票；a1、a3 都能播放（200）。<br>限流已关：autouse 夹具把 `voice.limiter.enabled` 设为 False；`voice.limiter` 与 `rate_limit.limiter` 是同一个对象，`check_and_hit` 在 :43 处直接返回。 |
| 2b. 新测试 2 对应 v1.2-2：全局淘汰前先清过期票 | 通过，非退化 | 用例 `test_expired_newest_ticket_is_cleaned_before_global_cap_evicts_oldest`（:217-230）。<br>场景与规格一致：全局上限 3、每用户上限 20；依次签 b1、a1、c1，把 c1 设为过期；A 再签 a2。<br>断言 `== [b1, a1, a2]`，b1、a1、a2 都返回 200。 |
| 2c. 新测试 3 对应 v1.2-3：全局淘汰只看全局最早，不偏向调用者 | 通过，非退化 | 用例 `test_global_cap_evicts_oldest_other_user_ticket_without_caller_preference`（:233-244）。<br>场景与规格一致：全局上限 3、每用户上限 20；依次签 a1、b1、b2，B 再签 b3。<br>断言 `== [b1, b2, b3]`，a1 返回 404，b1、b2、b3 返回 200。 |
| 3a. 副本搭建 | 完成 | rsync 到 `/private/tmp/tts-ttl-v12-mut/base`，排除了 .venv、.env*、*.db、`__pycache__`。`diff -rq` 确认与 worktree 的 backend 一致。<br>变异体用脚本做精确字符串替换，原代码块断言只命中 1 次，每个变异体的 diff 都逐一看过。<br>另外：`test_tts_ticket_rate_limit.py:165` 会读 `../docs/tasks/2026-09-29-tts-ticket-ratelimit/rate_model.py`，所以把这一个文件复制到副本的同级位置。补上之前，副本全量是 1544 passed + 1 个 FileNotFoundError，属于副本目录布局问题，与本单无关。 |
| 3b. 未改动的副本 | 全部通过 | TTL 文件 12 passed；全量 **1545 passed**。 |
| 3c. M1：每用户淘汰挪到过期清理之前 | 被拦住 | 顺序改成 USER→CLEAN→GLOBAL。全量 1 failed / 1544 passed，失败的只有**新测试 1**，旧用例全部照过，说明这个缺口只由新测试补上。 |
| 3d. M2：全局淘汰挪到过期清理之前 | 被拦住 | 顺序改成 GLOBAL→CLEAN→USER。全量 3 failed，其中有**新测试 2**；另外两条旧用例失败，是因为全局淘汰被挪到了每用户淘汰之前。<br>下面几个变体用来把「全局淘汰先于清过期票」这一点单独测出来：<br>• M2b（USER→GLOBAL→CLEAN）：只有新测试 1、2 失败。<br>• M2c（先只清调用者自己的过期票→USER→GLOBAL→再清其余过期票）：全量里只有**新测试 2** 失败。 |
| 3e. M3：全局淘汰优先淘汰调用者自己的票 | 被拦住 | 全量 1 failed / 1544 passed，失败的只有**新测试 3**。 |
| 3f. 自行加的变异 | 见右 | X1（过期清理只清调用者自己的票）：只有新测试 2 失败，被拦住。<br>X3（全局淘汰改成淘汰最新的票）：新测试 3 和旧的全局 FIFO 用例都失败，被拦住。<br>P（CLEAN→GLOBAL→USER）：旧用例失败，被拦住。<br>X2（全局淘汰跳过调用者、优先淘汰别人的票）：**全量 1545 passed，存活**，见「可优化」。 |
| 3g. 变异检测有效性 | 已证实 | 每个变异体都至少有一条测试失败，未变异副本全部通过，说明测试确实测到了变异。<br>乱序脚本本身也做了正控：拿到 M3 副本上跑，能报出失败（SOMETHING_FAILED）。 |
| 4a. worktree 全量 | 通过 | 按指定命令跑，结果 **1545 passed**，11 warnings，45.6 秒，退出码 0。1545 = 1542 + 3。 |
| 4b. 顺序依赖 | 未发现 | 用 `-v` 确认 pytest 按命令行给出的节点顺序执行（每轮都核对了顺序）。<br>测过的顺序：6 个随机种子（1/2/3/7/42/2026）、整体倒序、三条新测试各自单独跑、新测试倒序放最前。每轮都是 12/12 或 1/1 passed。 |
| 约束遵守 | 遵守 | 没有改仓库，没有做 git 写操作，跑完测试后 `git status` 与开始时一致。<br>没有读 .env*，没有碰 *.db，没有读 03-report.md 和 03-verification.md，没有用浏览器。<br>夹具已经把 `tts.synthesize` 和 `synthesize_stream` 换成假实现，变异只调整字典的淘汰顺序，不会连外网。 |

## 仍未达标项

无。

## 可优化（不阻塞，超出 v1.2 范围）

1. **「全局淘汰跳过调用者、优先淘汰别人的票」这种变异，全量都拦不住。**
   - 变异写法：`_others = [k for k, e in _tts_tickets.items() if e.user != user]`，然后淘汰 `_others[0]`。
   - 它和正确实现确实不等价。在副本里临时加了一条探针：先签 a1、b1、b2，再由 A 签 a2。
     - 原实现得到 `[b1, b2, a2]`，探针通过。
     - 该变异淘汰 b1，得到 `[a1, b2, a2]`，探针失败。
   - 所有 1545 条测试都拦不住它，原因是：
     - 新测试 3 里全局最早的票不属于调用者；
     - 旧的轮转用例最终表面结果恰好一样。
   - 这种错误会让高频用户把别人的票挤掉，正是跨用户公平要防的方向。
   - 建议：以后顺手追加上面那条探针场景，断言 `[b1, b2, a2]`，并断言 a1 返回 404。
   - 这一条不在 v1.2 的三项要求里，只作为建议。

变异副本留在 `/private/tmp/tts-ttl-v12-mut/`，可以复查。变异脚本和乱序脚本在本会话 scratchpad：
- `mutate.py`
- `run_mut.sh`
- `shuffle.py`
