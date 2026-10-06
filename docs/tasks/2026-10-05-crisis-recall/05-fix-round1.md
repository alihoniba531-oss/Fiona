# 返修单 第 1 轮：收窄为「路由保护 + 繁体計畫」（2026-10-05）

- **依据**：
  - `04-review.md`（Opus 5.5 第 1 次复核，不通过）。路由改动通过；新增的判级规则误伤大量日常话，剥离规则还删掉了真实危机信号。
  - 用户 2026-10-05 拍板：**保留路由保护，改用模型判级**。本单只保留复核通过的部分，判级扩充交给下一单（模型判级）。
- **当前状态**：工作区就是第 0 轮实现的结果，基线仍是 `9061a52`。
- **硬规则**：沿用 `02-spec.md` 第 0 节，另加两条：
  - 本轮**不得新增任何判级词或规则**，只做下面列出的收窄。
  - 「不得修改已有测试」中的「已有」仍指 `9061a52` 时的测试；第 0 轮新建的 `test_crisis_recall_2026_10.py` 按下文处理。

## 1. 改动

### F1 `backend/safety.py`：回到基线，只保留三处

以 `git show 9061a52:backend/safety.py` 为底稿重写这个文件，**只**在基线基础上保留以下三处：

1. **计划词**：基线里有两处意图动词表写着 `计划`：
   - `_HIGH_PATTERNS` 第 3 条：`(?:想|要|打算|准备|计划|考虑).{0,4}(?:自杀|…)`；
   - 第 7 条：`(?:想|要|准备|打算|计划|考虑).{0,8}(?:割腕|…)`。

   这两处的 `计划` 都换成 `(?<![设统])计(?:划|画|畫)`，**直接写汉字**，不要用 `\u` 转义。其余字符一个不改。
2. **辅助函数** `_normalize_crisis_text`：与第 0 轮相同，`assess_crisis` 改为调用它。
3. **`is_informational_crisis_context(text)`**：与第 0 轮相同。

除此之外的第 0 轮改动全部撤回，包括：
- 四条日常剥离；
- 他人语境扩词；
- 致死询问新分支；
- 生命分支改写；
- 新增的 high / possible 规则；
- `contextual_death` 逻辑；
- 英文扩充。

### F2 `backend/utils/traditional_chinese.py`：完全恢复为 `9061a52` 版本

### F3 `backend/tests/test_traditional_crisis.py`

- 保留第 0 轮授权的那处修改：`("計畫下週跳樓", "high")`。
- `RULE_CHARACTER_VARIANTS`、`NO_VARIANT_RULE_CHARACTERS` 恢复为基线内容，然后只追加 F1 新引入的规则字：`画`、`畫` 两个字追加到 `NO_VARIANT_RULE_CHARACTERS` 末尾，并在该行上方加一行注释：

  ```python
  # 画/畫 appear literally in the plan-word pattern; 畫 is deliberately not mapped
  # (see test_plan_word_does_not_cross_word_boundaries).
  ```

  如果 F1 之后还有别的字导致这个覆盖测试失败，说明 F1 没有完全回到基线，要修 F1，不要改清单。
- 其余内容与基线逐字相同。

### F4 `backend/tests/test_crisis_resource_paths.py`

保持第 0 轮的授权修改（possible 的 tool / pending 分支）。不再改动。

### F5 `backend/tests/test_crisis_recall_2026_10.py`

- **保留**以下用例：
  - 路由测试 R1–R4、R6；
  - 镜子 / 看图测试；
  - 固定修图引导；
  - `is_informational_crisis_context` 接口测试；
  - 计划词与词边界测试。
- **删除**四组规格语料（`SPEC_MUST_HIGH` 等），以及依赖第 0 轮新规则的各个护栏参数组。这些句子转为下一单（模型判级）的验收语料，本单不再测。
- **新增一组繁体「計畫」用例**，句子逐字取自 `02-spec.md` 第 5 节：
  - 判 `high`：「計畫明天跳海」「計畫吞藥」「計畫下週跳河」「計畫今晚跳江」「計畫割腕」「計畫上吊」「計畫自殺」「計畫下週跳樓」「我計畫明天跳海」；
  - 判 `None`：「計畫下週去日本旅行」「计划下周去海边玩」。

  如果其中有句子在 F1 之后达不到期望，**不要加规则**，在报告里列出。

### F6 文档

`CLAUDE.md`、`README.md`、`docs/ARCHITECTURE.md`：
- 保留「可能相关的轮次除信息或求助语境外，跳过自然语言生图候选、意图识别、工具及待补参数，保留 pending」这类路由描述；
- 删掉任何描述第 0 轮新增判级词的句子（如果有的话）；
- 补一句「繁体『計畫』与『計劃』判级一致」。

`PLAN.md`：把第 0 轮插在 2026-09-29 小节里的那行移出来，在该小节之后新建一个小节「### 2026-10-05：危机路由保护」，写两条：
- 可能相关轮不进工具 / 待补参数；
- 繁体計畫。

再加一条待办：「危机判级改为规则加模型复核（下一单）」。

### F7 报告

在 `03-report.md` 末尾追加「第 1 轮返修」：
- `git diff 9061a52 -- backend/safety.py` 的原样输出（应只有 F1 三处）；
- `git diff 9061a52 -- backend/utils/traditional_chinese.py` 的输出（应为空）；
- 测试数；
- 第 2 节的验收输出。

## 2. 验收（Claude 主会话会独立重跑）

| # | 命令 | 期望 |
|---|---|---|
| R1 | `backend/` 下 `python -m pytest -q -p no:cacheprovider` | 全部通过 |
| R2 | `git diff 9061a52 --stat -- backend/utils/traditional_chinese.py` | 无输出 |
| R3 | `git diff 9061a52 -- backend/safety.py` | 只有：计划词两处替换、`_PLAN` 定义（如果采用）、`_normalize_crisis_text`、`is_informational_crisis_context` |
| R4 | 用 `9061a52` 的 `backend/tests/test_beta_safety.py`、`test_traditional_crisis.py`、`test_crisis_resource_paths.py` 中的全部字符串字面量，分别跑新旧两版 `assess_crisis` | 判级不同的只有「計畫下週跳樓」一句 |

## 勘误（2026-10-05，主会话）

F2「`traditional_chinese.py` 完全恢复为 9061a52」写错了。原因：计划词规则的前置排除 `(?<![设统])` 要求繁体的「設」「統」先被归一成「设」「统」，否则「遊戲設計畫面」「統計畫面」会被误判（实施方在报告「未决问题」第 2 条已指出，处理正确）。

改为采用实施方提出的最小例外：
- **F2**：在 `9061a52` 版本基础上，只追加两组映射 `"设": "設"`、`"统": "統"`，写法与文件现有条目一致，其他不动。
- **F3**：`RULE_CHARACTER_VARIANTS` 在基线内容末尾只追加 `"设": "設"`、`"统": "統"` 两项；`NO_VARIANT_RULE_CHARACTERS` 维持本轮只追加「画畫」的状态。
- **验收**：
  - R2 改为「diff 只有这两行映射」；
  - R4 仍要求：现有测试字面量中判级变化的只有「計畫下週跳樓」一句。
