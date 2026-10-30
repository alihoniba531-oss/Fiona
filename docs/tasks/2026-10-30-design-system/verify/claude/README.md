# verify/claude/：Claude 的门禁与实测

执行者交付后由 Claude 在沙箱外跑，结果在 `results/`。

| 文件 | 用途 |
|---|---|
| `gate_b4.py` | 结构门禁。`python3 -I gate_b4.py manifest <工作树>` 记下派单时附件的 sha256；`python3 -I gate_b4.py check <工作树> 647a486` 依次核对改动集合、附件未被改动、与「标准答案」逐字节一致（HEAD + 总表 + `t2_edits.json` + 29 行测试字面量）、既有测试 numstat、粗体与「·」不增加、三个参考实现、新测试与 README 存在 |
| `apply_map.py` | `gate_b4.py` 用来重建「标准答案」的总表套用脚本 |
| `measure_b4.py` / `compare_b4.py` | 真实浏览器实测：同一脚本量 HEAD 与候选（13 个画面 × 4 套主题 × 2 种视口），比对 §6 第 7 条的 11 条判据；世界抽屉的热榜接口首次录制、之后回放 |
| `mut_run.py` | §7 的 19 项变异，逐项检查指定的测试函数变红，并按字节还原 |
| `results/gate.txt` | 门禁结果：`== FAIL 0` |
| `results/browser-compare.txt` | 浏览器实测结果：`== FAIL 0` |
