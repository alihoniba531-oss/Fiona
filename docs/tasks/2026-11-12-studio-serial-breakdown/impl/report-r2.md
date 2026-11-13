# 短片工作室「边写边拆」R2 文档返修报告

- 依据：`docs/tasks/2026-11-12-studio-serial-breakdown/02-spec.md` §4.9 R2 返修
- R2 只改文档；R1 交回时的 `docs/ARCHITECTURE.md` / `CLAUDE.md` 已先快照到 `/tmp/studio-serial-r1` 作为对比基线。
- 结论：R2-D1–D3 完成；相对 R1 交回时只有 R2 白名单文件变化；未重跑后端全量（§4.9 不要求）。

## 1. 改动位置

### R2-D1 `docs/ARCHITECTURE.md:507`

在续拆段落（「续拆走 `continue_quote`/`continue_start`」那一段）末尾补四条事实，未新增重复段落：

1. 「续拆的每集时长沿用原拆解且不能改，续拆报价不带时长与「大约几集」。」
2. 「续拆进行中新章人物就会进入总表并出现在定妆页，G1 回到未通过。」
3. 「本轮批次无论首次执行还是单批重跑，都按批 `source_json.snapshot_no` 读本轮绑定的快照，书斋里再改原文对重跑无效。」
4. 「仍失败只能整本重新拆解，会生成新的总表，已定的妆要重新定。」

### R2-D2 `docs/ARCHITECTURE.md:509`

同一行内把：

```
（`continuing` 时只取 `seq ≤ _published_max_seq` 的单元）
```

改为：

```
（已发布拆解的 `_continuations` 非空时只取 `seq ≤ _published_max_seq` 的单元）
```

与 R1-P3 的过滤条件一致。

### R2-D3 `CLAUDE.md:196`

把聊天读小说段落里的：

```
还要求 `gate.allow_studio(user, auth_method)`，缺失拒绝。
```

改为：

```
还要求 `gate.allow_studio(user, auth_method)`，`auth_method` 缺失拒绝。
```

恢复主语；未改其它文字。

### 新文件 `docs/tasks/2026-11-12-studio-serial-breakdown/impl/report-r2.md`

即本报告。

## 2. 自检

### `wc -c CLAUDE.md`

```
   67364 CLAUDE.md
```

67,364 ≤ 67,400。

### 相对 R1 交回时的变化

`diff -qr`（排除 `.git`、`.venv`、`node_modules`、`.next`、`__pycache__`）只显示：

```
Files /tmp/studio-serial-r1/CLAUDE.md and ./CLAUDE.md differ
Files /tmp/studio-serial-r1/docs/ARCHITECTURE.md and ./docs/ARCHITECTURE.md differ
Only in ./docs/tasks/2026-11-12-studio-serial-breakdown/impl: report-r2.md
```

`git diff --no-index --stat` 对 R1 快照与当前源码副本（因 R1 改动未提交，直接 `git diff` 会把 r0→R1 的全部改动算进来，故以 R1 快照为基线）：

```text
 .../CLAUDE.md                                      |   2 +-
 .../docs/ARCHITECTURE.md                           |   4 +-
 .../impl/report-r2.md}                             | 100 +++++++++++++++++++++
 3 files changed, 103 insertions(+), 3 deletions(-)
```

（报告自身随后补入了上面的命令输出，行数略有增加；文件集合仍是这三个 R2 白名单文件。）

### `docs/ARCHITECTURE.md` 关键词自检

```
== 不能改
507:...续拆的每集时长沿用原拆解且不能改...

== G1 回到未通过
507:...定妆页，G1 回到未通过...

== 绑定的快照
507:...按批 `source_json.snapshot_no` 读本轮绑定的快照...

== 已定的妆要重新定
507:...会生成新的总表，已定的妆要重新定。
```

四个关键词都位于续拆段落 `docs/ARCHITECTURE.md:507`。

## 3. 未完成或需人工确认

- R2 只改文档，没有重跑后端全量、`tsc`、`lint`、`build`；§4.9 明确不要求，派单方合并前会再跑全量门禁。
- 未改代码、测试、其它文档、`docs/tasks/...` 下 01–07，也未执行 commit/stash/checkout/reset。
- 未发现规格与源码事实矛盾，无 §6 阻塞。
