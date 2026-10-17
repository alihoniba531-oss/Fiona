# WO3d P1 复核（独立）

结论：**不通过**（3 项必须修复，10 条可优化）。基线 6de7873 未提交改动；复跑 casting 五个测试文件 113 passed。
实测脚本在 `$TMPDIR/review_wo3d_p1/`（test_repro.py、test_e2e.py、test_fe.py），未改动仓库任何文件。

## 必须修复

**M1 造型报价币种写死 CNY**（`casting.py:496`；测试把错误固化在 `test_studio_casting_api.py:1087`）
- 场景：项目导演默认 claude，计价是 USD。实测：`quote.currency=CNY`，同项目的 job.currency=USD，风格报价为 USD。
- 后果：报价框用 ¥ 显示美元金额，与风格提案口径不一致。预留金额 0.1028 实为美元。
- 修复：`currency` 取 `quote_items[0]["currency"]`（对照 `_style_quote_public`），并改测试。

**M2 编辑草稿基线过期，保存时抹掉刚写回的导演造型**（`CastingItemCard.tsx:46-56,78`）
- 场景：导演任务在途时点「编辑」，只改 hair；导演结果落地；点保存。
- 实测（node 探针）：PATCH 发出 `{hair:'作者发型', makeup:'', top:'', …}` 共 7 个空串。原因是 `saveLook` 拿草稿和当前 props 比，不和编辑起点比。
- 后果：导演的付费结果被清空，`look_source` 变为 author，之后该条目报价 409「已由作者修改」，无法再让导演补全。
- 修复：编辑开始时快照 base，只提交草稿≠base 的字段；在途（lookInflight）时禁用「编辑」。

**M3 一批 10 条 × `max_tokens=4096` 很可能截断**（`casting.py:39`、`brain_tasks.py:166`）
- 估算，未用真实模型实测：10 个人物、每字段仅约 31 字（远低于 60 字上限），JSON 约 4.5k 字符。
- 按仓库自己的 1.5 token/字口径（`pricing.estimate_brain`）约 6.7k token；即使按 1 token/字也超过 4096。默认 claude 大概率 `max_tokens` 截断，任务记 invalid_output 失败，已产生的输出仍计费，用户得再付一次。
- 数值来自规格，请主控裁定：批大小改 5，或 `max_tokens` 改 8192（同步调整报价预留）。

## 可优化

1. **回放按完成时间排序，旧请求后完成会覆盖新请求**（`casting.py:264,285-297`）
   - 实测：新任务先完成显示 NEW，旧任务后完成翻成 OLD。`look_job_ids` 截断到 20 条：第 21 次起每次 GET 都重放最老任务并写库（最终结果仍是最新）。
   - 建议改记单一水位（已应用任务的 created_at），只应用更新的任务。
2. **回放是惰性的**（`casting.py:312`，`casting_jobs.py:441`）
   - 任务成功到下一次 GET 之间，`_run_image` 和 `quote_sheets` 读到旧 look。实测：回放前作者 PATCH 一个字段，导演整份结果被丢弃。UI 总是先 GET 再点击，窗口极小，但脚本和直调 API 能踩中。
   - 建议 `start_sheets` 事务内和 `patch_item` 的 look 分支先调 `_apply_look_results`。
3. **PATCH `look={}` 或全清空**（`casting.py:771-791`）：实测 `{}` 返回 200，`look_source` 变 author，look 为 None，再报价 409。建议 `{}` 返回 422；合并后全空时清除 source。
4. **失败或 uncertain 的造型任务在 UI 无出口**
   - 只有 `StyleCard.tsx:46` 有「释放预留」。实测超时后 uncertain 保留 0.1028 美元预留，持续占额度，用户看不到。failed 时「正在补全」悄悄消失，无错误提示。
   - 建议批量栏展示最近一次失败或 uncertain 的 casting_look，并复用释放按钮。
5. **在途提示与重复付费**
   - casting_look 任务的 `item_id` 恒为 null，`castingLookInflight`（`studio-casting.ts:110`）使每张人物和道具卡都显示「正在补全」，符合规格字面但会误导；`task==null && item_id` 分支是死代码。
   - 在途时「补全造型说明」仍可点（`CastingItems.tsx:98`），同条目可再次付费并触发第 1 条的乱序覆盖；勾选超过 30 个时按钮不禁用，点后才收到 422。
6. **start 不复核**（`casting.py:557-590`）：报价后 15 分钟内条目变孤儿、作者改过造型、锁定特征改动，仍照付费生成（写回会跳过，但钱已花，锁定特征用报价时旧值）。建议仿 `_revalidate_sheet_item`。
7. **造型行位置**（`casting_prompts.py:277`）：现为 标题→造型→版式→外形，字面符合规格，可接受。但最长造型行约 1700 字，会把「一图两区」的版式推到 1000 字之后；建议 标题→版式→造型→外形（仍在外形之前，版式不被裁）。字段名也建议加冒号（现为「发型齐耳短发」）。
8. **`casting_look.md` 措辞**
   - ① schema 要求每字段 minLength=1，模板没写「无此项写『无』」，空串会触发 invalid_output 和付费修正。② 只写「依据外形、描述、锁定特征、风格」，但输入还有 synopsis，没说明用途。
   - ③ 全局系统提示（`brain.py:97-99`）写「不得编造人物外形」，与本模板「合理设计」冲突，建议声明本任务例外。④ 未禁止写品牌、真人名，也未禁止服装或道具上的文字字样，与出图提示词「不模仿品牌、画面无文字」冲突。
9. **校验信息不具体**：`schema_errors` 对 anyOf 只报「不符合 anyOf」（实测），付费修正轮拿不到具体字段。
10. **其他**：报价明细行显示「1 项 × …」但名称是 10 条一批（`CastingQuoteDialog.tsx:23`）；`style_proposals.md:6`、`CastingQuoteDialog.tsx:26`、`SetupCard.tsx:57` 仍写旧版式；`_apply_look_results` 无异常保护，异常会让整个 GET /casting 返回 500 并回滚 `_sync_items`；前端 `CASTING_LOOK_FIELDS` 与后端 `LOOK_FIELDS` 目前一致但无对拍测试。

## 已核实无问题

- **写回机制**
  - `state()` 本来就用 BEGIN IMMEDIATE（同事务先同步条目再回放），WAL + 5s busy timeout。实测 8 并发 GET + 4 并发 PATCH 无报错；30 任务×10 条时 GET 约 76ms。
  - 作者在进行中或回放后改 look 永不被覆盖（`look_source=author` 跳过）；孤儿跳过；请求外 id（含 foreign）忽略；同一任务只应用一次。完整链路（报价→确认→假 brain→写回）实测通过。
- **付费**：与风格提案同口径（`check_brain_budget` 单次、日、月 USD；`_insert_job` 预留 `first_max`）。同一报价确认两次 200/409；过期 409；报价类型串用（造型↔风格/出图）均 409；超时进入 uncertain 并保留预留（实测）。币种见 M1。
- **归属与前置**：跨项目 item_id、他人项目、他人报价、跨项目报价均 404；G0、开工、风格、孤儿、场景 kind 均 409。
- **出图提示词**
  - 版式文字与 §2.4 一致；`_FRAME` 已按 kind 拆分，无重复或矛盾。
  - 实测裁剪顺序 extra→description→风格→appearance→造型；最坏情形（600 字锁定特征 + 8×200 造型 + 长风格 + 4 条参考说明）长度恰为 1800；名称、版式、锁定特征、负向、原创声明从不被裁；造型文本压成单行，无法注入伪造行。
- **前端**：字段与标签逐项一致；保存只提交与 props 不同的字段（但见 M2）；轮询由 `castingInflight`（queued、submitting、submitted、running）驱动，在途提示不参与，任务完成或 uncertain 后轮询停止。
