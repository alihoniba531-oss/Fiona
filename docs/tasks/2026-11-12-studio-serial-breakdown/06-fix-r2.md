# 返修单 R2：只改文档

R1 的代码与测试经第 2 轮独立复核全部通过（`07-review-r2.md`）。唯一必须修复项是文档：R1 压缩 `CLAUDE.md` 时删掉的续拆细节，没有迁到 `docs/ARCHITECTURE.md`。依据是同目录 `02-spec.md` 新增的 **§4.9 R2 返修**，先读它再动手。

规矩：

1. 只改 §4.9 的 R2 白名单：`docs/ARCHITECTURE.md`、`CLAUDE.md`、新文件 `impl/report-r2.md`。代码、测试、其他文档一字不动。
2. 不要 `git commit` / `git stash` / `git checkout` / `git reset`；不要改 `docs/tasks/2026-11-12-studio-serial-breakdown/` 下的 `01-brief.md`、`02-spec.md`、`03-dispatch.md`、`04-review.md`、`05-fix-r1.md`、`06-fix-r2.md`、`07-review-r2.md`。
3. 这一轮很小，**不用工作流、不派子代理**，主代理直接改。
4. 只改文档，不需要重跑后端全量；按 §4.9「R2 报告」自检并写报告。
