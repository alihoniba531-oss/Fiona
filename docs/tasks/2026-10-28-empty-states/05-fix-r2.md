# 返修单 R2：补回 page.tsx 的 BOM

第二轮复核核实，返修 R1 的 1–8 号改动都已做到。只有一处偏差：R1 改 `frontend/app/page.tsx` 时，文件开头的 UTF-8 BOM（字节 `EF BB BF`）被去掉了。

- HEAD 的前三字节是 `efbbbf`，现在是 `227573`；相对 HEAD 因此多出一个第 1 行的 hunk，一共 5 个，本该是 4 个。
- 这违反了返修单 R1 第 1 条「page.tsx 其余一字不动」。
- 运行时没有影响，但要补回。

## 只做这两件事

1. 在 `frontend/app/page.tsx` 开头补回三个字节 `EF BB BF`，文件其余字节一律不动。用这一条命令：
   ```
   python3 -c "p='frontend/app/page.tsx';b=open(p,'rb').read();assert not b.startswith(b'\xef\xbb\xbf');open(p,'wb').write(b'\xef\xbb\xbf'+b)"
   ```
   做完自检三项，全部前台跑：
   - `head -c3 frontend/app/page.tsx | xxd -p` 输出 `efbbbf`；
   - `git diff HEAD -- frontend/app/page.tsx | grep -c '^@@'` 输出 `4`；
   - 52 条新测试 `cd backend && .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_empty_states_*.py` 全部通过（跑前清代理变量）。
2. `docs/tasks/2026-10-28-empty-states/03-report.md`：
   - 把 §8.1 表格第 1 行里的「page.tsx 其余未动」改成「page.tsx 其余未动（R1 时曾误删文件开头的 UTF-8 BOM，R2 已补回）」；
   - 在文件末尾追加一节「## 9. 返修 R2」，写清：补回了什么、上面三项自检的实际输出、补回后的快照哈希。快照哈希按 `(git diff HEAD; cat backend/tests/test_empty_states_*.py) | shasum -a 256 | cut -c1-16` 计算。

## 规矩

- 只改上面两个文件。不做 git 写操作。不跑 build、不起服务器、不用浏览器、不调用 subagent / subagent_fork / workflow。
- 所有命令前台跑完再继续，不要后台跑，也不要 sleep。
- 自检任何一项不符，就停下来说明，不要自行扩大改动。

回复给出变更总结五项：修改了哪些文件、实现了哪些功能、与任务清单的逐项对应、测试结果、未完成或需人工确认的地方。
