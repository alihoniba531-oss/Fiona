# WO3d 返修 R2-B 报告：错误分类只看结构化状态码、Seedream 总超时、CosyVoice 取消标志、提示词总长 ≤1800

- 工作目录：`/Users/yangjing/Desktop/ai-workspace/.worktrees/fiona-studio`
- Python：`/Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python`
- 依据：`docs/tasks/2026-10-16-studio-wo3d-casting/08-fix-r2-common.md`、`08-fix-r2-B.md`；复核报告 `04-review.md`「必须修复 3」「可优化 g 前半 / h / m 后半」
- 性质：只改本块允许清单内的 7 个文件；未提交、未联网、未读 `.env`、未动 `frontend/node_modules`、未碰其他块的文件。
- 改动文件：
  - `backend/studio/providers/tts_cosy.py`（必修 3、可优化 h）
  - `backend/studio/providers/tts_edge.py`（必修 3）
  - `backend/studio/providers/image_seedream.py`（可优化 g 前半）
  - `backend/studio/casting_prompts.py`（可优化 m 后半）
  - `backend/tests/test_studio_media_tts.py`、`tests/test_studio_media_seedream.py`、`tests/test_studio_casting_prompts.py`（新增 8 个用例）

## 0. 结论

四项全部改完，改动自带回归测试。「测试先在旧代码上失败、在新代码上通过」已逐项反证（见 §5）。

## 1. 必须修复 3：错误分类只看结构化状态码

### 1.1 改法

- `backend/studio/providers/tts_cosy.py:88-111` `_status_code`：**删掉** `re.search(r"\b(4\d{2})\b", str(value))`。改为只读结构化数值字段：
  - 对象（异常）走属性：`status_code` / `status` / `http_status` / `httpStatus`；
  - 映射（上游 `task-failed` 的 `header` / `payload` / `output`）走同名键。
  两者都只接受 `int`（`bool` 跳过）或纯数字字符串；都取不到就返回 `None`，交给 `_classify` 判 `uncertain`。
- `tts_cosy.py:3-12` 模块文档补一条：断连文本里的 `:443` 不是 4xx。
- `tts_cosy.py:88-99` 函数文档写明「不从 `str(value)` 里正则找 4xx」的理由（`Cannot connect to host x:443`、`429ms 后重试` 都会被误判成「上游拒绝」→ 错误释放预留）。
- `import re` 已从两个模块移除（模块内再无其它 `re` 用法）。
- `_failure_from_message`（`tts_cosy.py:123-145`）保留「按结构取 `error_code` / `error_message` / 状态字段」的写法，但**不再对整段 dict 做 `str()` 扫描**：`_status_code(item)` 现在只查键。`code` / `message` 的取值与 `_classify` 的审核语义码判定（`_MODERATION_MARKERS`）保持原样，审核拦截仍判 `failed`。
- `backend/studio/providers/tts_edge.py:31-44` `_status_code`：同样删掉文本正则（aiohttp 的 `ClientConnectorError` 文本固定含 `host:port`，edge-tts 断连必中），只认 `status_code` / `status` / `http_status` 属性；`import re` 一并移除。

### 1.2 对应测试（`tests/test_studio_media_tts.py`）

| 用例 | 行 | 覆盖 |
|---|---|---|
| `test_cosyvoice_transport_text_with_port_is_uncertain` | `:296` | `ConnectionError("Cannot connect to host dashscope.aliyuncs.com:443 …")`、`OSError("… wss://dashscope.aliyuncs.com:443/…")`、`task-failed` 说明文本里带 `:443` 与 `429ms` 的 dict、以及整段失败信息为非 JSON 纯文本 —— 全部 `uncertain` |
| `test_edge_tts_transport_text_with_port_is_uncertain` | `:443` | aiohttp 风格 `ConnectionError("Cannot connect to host speech.platform.bing.com:443 ssl:default [None]")` 与 edge-tts 风格 `OSError("… wss://speech.platform.bing.com:443/…")` —— `uncertain` |
| 既有 `test_cosyvoice_http_4xx_is_rejected_and_message_is_sanitized` | `:318` | `status_code=429` 异常、`header.status_code=400` 的 `task-failed` —— 仍 `rejected`（回归保护） |
| `test_cosyvoice_structured_numeric_status_is_still_rejected` | `:325` | 新增：`status=429`、`status_code=400` 两个异常与 `header.status_code=429` 的 `task-failed` —— 仍 `rejected` |
| `test_edge_tts_structured_numeric_status_is_still_rejected` | `:460` | 新增：`status=429` / `status_code=400` 的异常 —— 仍 `rejected` |
| 既有 `test_cosyvoice_moderation_is_failed` | `:349` | 审核语义码（`DataInspectionFailed`，同时带 400）维持 `failed` |

### 1.3 复核脚本口径对照

复核者的复现脚本 `test_status_regex` 现在输出：

```
COSY ConnectionError(:443) -> uncertain ConnectionError
EDGE ConnectionError(:443) -> uncertain ConnectionError
synthesize_cosy -> uncertain OSError
COSY task-failed with 5xx-ish code and '429' in text -> uncertain InternalError
```

四项与复核报告里「误判 rejected」的实测结果逐一相反。

## 2. 可优化 g（前半）：Seedream 整体超时

### 2.1 改法

- `backend/studio/providers/image_seedream.py:37-39`：新增模块常量 `TOTAL_TIMEOUT_S = 240.0`（单次 POST 的 `_TIMEOUT_SECONDS = 150` 不变，它仍是 httpx 的单次读取超时）。
- `image_seedream.py:179-182`：原 `generate_sheet` 主体改名为 `_generate_sheet`（单次 POST 的实现体，逻辑一字未动）。
- `image_seedream.py:241-256`：新 `generate_sheet` 用 `asyncio.wait_for(_generate_sheet(...), timeout=TOTAL_TIMEOUT_S)` 套整体超时，`TimeoutError` → `MediaCallError("uncertain", "timeout", …)`；**不重试**，只发一次 POST。工厂内非 `Exception` 的取消信号（`CancelledError`）不被吞。
- 常量在调用点读取（`timeout=TOTAL_TIMEOUT_S`），测试可用 `monkeypatch.setattr(image_seedream, "TOTAL_TIMEOUT_S", …)` 改小。
- 覆盖范围含建连、上传参考图、读满响应与解码；`image_seedream.py:10-11` 模块文档写明。

说明：复核 `可优化 g` 的后半（`casting_jobs.py:342` 的 `get_job` 移入 `try`）属于 R2-A 的文件，本块未动。

### 2.2 对应测试

`tests/test_studio_media_seedream.py:265` `test_total_timeout_is_uncertain_and_sends_single_post`：`TOTAL_TIMEOUT_S=0.05` + 一个 `await asyncio.sleep(5)` 的 MockTransport handler（带 1 张参考图）→ 断言 `uncertain/timeout`、**只发出 1 次请求**（不重试）、错误文本不含 Key。

## 3. 可优化 h：CosyVoice 超时后不再发付费请求

### 3.1 改法

- `backend/studio/providers/tts_cosy.py:223`：`synthesize_cosy` 每次调用新建 `cancelled = threading.Event()`，作为 `cancelled=` 关键字参数传给工作线程（`:229-231`）。
- `tts_cosy.py:232-235`：`except (TimeoutError, asyncio.TimeoutError)` 分支先 `cancelled.set()` 再抛 `uncertain/timeout`，即「调用方已放弃结果」这一事实被显式传递给后台线程。
- `tts_cosy.py:170-171, 186-188`：`_synthesize_blocking` 增加 `cancelled` 形参，并在**拿到 `_API_KEY_LOCK` 之后、设置全局 key 与调用 SDK 之前**检查标志；已取消就直接返回，不构造 `SpeechSynthesizer`、不发付费请求（返回值随超时被丢弃，`wait_for` 已经取消等待）。

### 3.2 对应测试

`tests/test_studio_media_tts.py:221` `test_cosyvoice_timeout_while_waiting_for_lock_never_calls_sdk`：假 factory + 一个**预先占住** `_API_KEY_LOCK` 的线程；`SYNTHESIS_TIMEOUT_S=0.05` 触发超时后放开锁，断言 `factory.params is None and factory.texts == []`（SDK 调用次数 0），且全局 `dashscope.api_key` 未被改写（线程在设置 key 之前就返回了）。

## 4. 可优化 m（后半）：提示词总长永远不超过 1800

### 4.1 改法

`backend/studio/casting_prompts.py:177-240` `build_sheet_prompt`：把「只裁 extra_prompt / description，其余 `break`」的旧循环换成按优先级逐级裁尾部的循环：

1. `extra_prompt`（整段 `补充要求：` 可为空）→ 2. `description` 尾部 → 3. 风格段尾部 → 4. `appearance` 尾部 → 5. 参考图说明尾部（只作兜底，永不先于 appearance 被裁）。

- 每轮按 `len(text) - PROMPT_LIMIT` 精确裁掉对应字段尾部（`short()`，`:205-207`），超出量不小于整段长度时整段去掉，因此**只要还能裁就一定收敛到 1800**，不再出现旧的「裁不动就超长返回」。
- 版式、主体名称、`locked_features`、写实度负向、原创声明从不参与裁剪（不在阶段列表内）；`locked_features` 因此依赖 PATCH 处 ≤600 字的校验（由 R2-A 负责），函数文档 `:181-185` 写明这条前置条件。
- 顺带修掉「`locked_features` 2000 字时 `break` 返回超长提示词」的旧行为：现在先吃掉全部可裁字段。

### 4.2 对应测试

| 用例 | 行 | 覆盖 |
|---|---|---|
| `test_prompt_limit_holds_with_max_locked_features_and_oversized_style_and_appearance` | `:98` | `locked_features` 600 字 + 风格 2400 字 + 外形/说明/补充要求各 1200 字 → 总长 ≤1800；`必须保持（锁定特征）：<600 字原文>`、主体名称、版式、负向、原创声明逐条仍完整；`补充要求`/`说明：`/`风格：` 整段被裁掉，外形只剩被裁短的一段 |
| `test_trim_priority_order_extra_then_description_then_style_then_appearance` | `:119` | 四档边界各造「刚好超 60 字」：① 只裁 extra_prompt 尾部（description/风格/外形完整）② extra 清空后接着裁 description 尾部（风格/外形完整）③ 再裁风格段尾部（外形完整）④ 最后才动 appearance，且 `locked_features`、负向、原创声明仍完整 |
| 既有 `test_prompt_length_limit_and_trim_priority` | `:83` | 旧断言不动，仍通过 |

## 5. 反证：修复前确实失败

把四个源文件临时还原成修复前行为（`_status_code` 恢复文本正则、去掉取消标志检查、`generate_sheet` 直接 await、`build_sheet_prompt` 恢复旧循环），用同一批新用例跑：

```
tests/test_studio_media_tts.py -k "transport_text or structured_numeric or never_calls_sdk or http_4xx"
  FAILED test_cosyvoice_timeout_while_waiting_for_lock_never_calls_sdk
  FAILED test_cosyvoice_transport_text_with_port_is_uncertain
  FAILED test_edge_tts_transport_text_with_port_is_uncertain
  3 failed, 3 passed      ← 3 个 passed 是「结构化状态码仍 rejected」的回归保护，故意两边都过
     （含 edge 侧 rejection 断言的旧实现报 'rejected' != 'uncertain'）

tests/test_studio_media_seedream.py -k total_timeout
  FAILED test_total_timeout_is_uncertain_and_sends_single_post
     （旧实现没有总超时，handler 睡满 5 秒后拿到 200 正文 → 'invalid_response' != 'timeout'）

tests/test_studio_casting_prompts.py -k "max_locked or trim_priority"
  FAILED test_prompt_limit_holds_with_max_locked_features_and_oversized_style_and_appearance
     （旧实现返回长度 1860，assert 1860 == 1800）
  FAILED test_trim_priority_order_extra_then_description_then_style_then_appearance
  2 failed, 1 passed
```

还原前的「修复后」结果见 §6。临时还原后已立即从备份恢复成修复版（备份在 `/tmp/r2b_backup/`，工作区文件为最终版）。

## 6. 测试结果（修复版）

```
$ cd backend && <py> -m pytest -q tests/test_studio_media_tts.py tests/test_studio_media_seedream.py tests/test_studio_casting_prompts.py
82 passed in 1.83s
   （tts 22 + seedream 46 + prompts 14；其中本块新增 8 个用例）

$ cd backend && <py> -m pytest -q tests/test_studio_casting_prompts.py tests/test_studio_casting_jobs.py tests/test_studio_casting_recovery.py
43 passed in 1.36s          ← 本块四个源文件的直接调用方

$ cd backend && <py> -m pytest -q tests/ -k studio
1573 passed, 5550 deselected, 32 warnings in 69.92s
```

`-k studio` 全绿（1573 passed / 0 failed），即在 R2-A / R2-C 的改动同时在场的工作区里，本块改动没有破坏任何既有用例。

补充说明（并发噪音）：本块执行期间另两块一直在同一工作区改文件，中途的两次全量跑分别出现过 9 个、4 个失败，逐条核对后全部落在别的块的在途文件上，两类原因：(1) `studio/casting.py` 调用尚未落地的 `casting_jobs.prepare_jobs`（R2-A 在途重构）；(2) R2-A / R2-C 刚写好、实现还没落地的断言（如 `test_patch_locked_features_caps_at_600`、`test_skip_and_reopen_clear_approved_version`、`test_item_card_appearance_locked_actions_and_preview`）。这些用例单独复跑时随后均通过；最终那次全量跑已全绿，本块未改这些文件。

## 7. 未完成 / 说明（不在本块范围或有意留白）

- 复核 `可优化 g` 后半（`get_job` 移出 `try`）与 `可优化 d`、`e`、`f`（`casting.py`）属 R2-A；`a`、`b`、`c`、`i`、`j`、`k`（`casting_jobs.py`）属 R2-A；`可优化 l`（试听条数上限）按公共说明明确不做；缩略图留 WO5。本块一行未动这些文件。
- 与「必须修复 5」相关的提示词合并只在 R2-A（quote/执行期合并）与 R2-C（前端文案）落；本块只保证 `build_sheet_prompt` 的长度与裁剪语义。
- `build_sheet_prompt` 的「任何输入 ≤1800」有一个已知前置条件：`locked_features` 由 PATCH 校验 ≤600 字。若绕过校验塞入超过约 1400 字的 `locked_features`，因为「锁定特征绝不裁」，总长仍可能超过 1800 —— 这是规格里「绝不裁」与「总长 ≤1800」的固有冲突点，函数文档已写明依赖 R2-A 的校验。
- CosyVoice 的取消标志目前只在**超时**分支置位（按 R2-B 规格原文）。若外层任务被 `CancelledError` 取消（请求中断 / 进程关停），排队的线程仍可能发出一次请求；同类缺陷的进一步收紧不在本块清单内，已在此登记。
