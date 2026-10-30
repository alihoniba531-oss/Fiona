# verify/：第四批的附件与参考实现

本目录由 Claude 维护，执行者只读、不得改动（门禁会比对 sha256）。

| 文件 | 用途 |
|---|---|
| `replacements.tsv` | T1 总表：1158 行、76 个文件，行列号对应 HEAD `647a486` |
| `t2_edits.json` | T2 令牌层：28 条逐字改动，字段 `n` / `file` / `count` / `old` / `new`，以它为准 |
| `r1_edits.json` | 返修 R1：`globals.css` 两条对话框遮罩加兜底色，格式同 `t2_edits.json` |
| `test_literals.tsv` | T4：既有测试里授权修改的 29 行 |
| `ref/gate_rules.py` | T3-1 源码规则的参考实现。`python3 -I ref/gate_rules.py <仓库根>`，HEAD 上 `== FAIL 21`（R1 加了 T8），改完应为 `== FAIL 0` |
| `ref/contrast_check.py` | T3-2 对比度算法的参考实现。`python3 -I ref/contrast_check.py frontend/app/globals.css`，退出码 = 不达标条数；HEAD 上 43，改完应为 0 |
| `ref/gate_twcss.mjs` | T3-4 生成 CSS 检查的参考实现。`node ref/gate_twcss.mjs frontend`，退出码 = 违规条数 + 令牌编译不符条数；HEAD 上 49 + 12，改完应为 0 |

新测试要把规则写进测试文件本身，不得 import、执行或读取本目录下的任何文件。
