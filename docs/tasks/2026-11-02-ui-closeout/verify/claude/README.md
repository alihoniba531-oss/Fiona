# verify/claude/：Claude 的门禁与实测（第五批）

执行者交付后由 Claude 在沙箱外跑，结果在 `results/`。

| 文件 | 用途 |
|---|---|
| `gate_b5.py` | 机械门禁：`python3 -I gate_b5.py <工作树> <HEAD 副本> [--skip-build]`，核对改动集合与白名单、既有字面量锁、tsc / lint / build、全量 pytest、新测试在 HEAD 副本上的对照。`results/gate.txt` 是 R1 后 `--skip-build` 的一次：`== FAIL 0 / 34`，7855 = 7836 + 19（build 单独跑，见 `results/build.txt`，退出码 0）；`results/gate-r2.txt` 是 R2（只补强三个新测试，已跟踪 diff 逐字节不变）后的一次：`== FAIL 0 / 34`，7863 = 7836 + 27。 |
| `mut_b5.py` | 11 项变异：逐项改坏实现，对应测试必须变红，按字节还原。`results/mutations.txt`：`== FAIL 0 / 11`。 |
| `mut_b5_r2.py` | R2 变异 7 项：第一轮独立复核证明在 R1 新测试下「全绿」的六处写坏（原生框去 `aria-hidden`、`tabIndex` 挪到按钮、`rawChip` 键对调、扫描目录不存在、首次恒为 false、去 ref 守卫、余额不看 `lowBalance`），R2 之后必须有非 selfcheck 的真实用例变红。`results/mutations-r2.txt`：`== FAIL 0 / 7`。 |
| `measure_b5.py` | 真实浏览器实测（Playwright 1.63 无头 Chromium，隔离实例：HEAD 副本后端 + HEAD / 候选两个 dev 前端）：费用提示三态与自带模型两态的输入区高度、文字、颜色；历史页 Tab 顺序、Enter/Space 打开选择器、退回路径、指针路径；遮罩在变量失效时的兜底色。`--tag head` 是正控（旧行为必须被量到），`--tag cand` 是本批判据。`results/browser-head.txt`：`== FAIL 0 / 27`；`results/browser-cand.txt`：`== FAIL 0 / 58`。 |

实测关键数字（390×844）：平台模型非首次输入区 108.81px（HEAD 133.81），首次 133.81，自带模型 157.81（与 HEAD 相同）；低余额文字「每条消息消耗 10 颗草莓，还剩 20 颗」昼 `rgb(168,50,42)`、夜 `rgb(229,111,93)`。
