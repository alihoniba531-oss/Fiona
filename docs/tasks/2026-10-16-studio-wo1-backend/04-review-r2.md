# WO1 复核记录（第 2 轮，只核 R1-1～R1-8）

- 返修执行模型：GPT-6.1-Sol（ultra 推理、priority 服务档）。用户指定从 R1 起改用这个模型；首轮由 GPT-6-Astra 完成。
- 机械验证（主控在沙箱外执行）：全量 **5866 passed、17 skipped、0 failed**，没有排除任何用例。17 个跳过都是因为 worktree 缺前端 `node_modules`。
- 复核代理在本机（非沙箱）跑了 byok、exchange、safe_http 三组测试加上全部工作室测试：776 passed、0 failed。

## 结论：通过

| 项 | 结论 | 证据 |
|---|---|---|
| R1-1 断网钩子只作用于工作室测试，放行回环 | 通过 | `tests/conftest.py:49-60`；三个受保护的测试文件 `git diff --exit-code` 无改动；不实陈述已删；`test_studio_offline.py` 覆盖 |
| R1-2 浮点或字符串形式的 token 数 | 通过 | `pricing.py:104-112`；无效值不结算，保留预留并计入当日占用（`test_studio_store.py:184-209`） |
| R1-3 tick 日志带异常类型 | 通过 | `scheduler.py:74`，`test_studio_scheduler.py:543` |
| R1-4 成功但没有结果地址时超时暂停 | 通过 | `scheduler.py:200-207,227-233`，`test_studio_scheduler.py:563` |
| R1-5 金额统一两位小数 | 通过 | `store.py:304`、`spend.py:65` |
| R1-6 删号入队用 `studio:` 前缀 | 通过 | `database.py:909-916`、`utils/media.py:380-416`；复核构造了 19 个 `studio:` 变体和 11 个旧格式绝对路径做实测，根目录之外的一律拒绝 |
| R1-7 删除放到线程里执行 | 通过 | `routers/me.py:62,73,100`，`test_studio_integration.py:266-323` |
| R1-8 工作室包失败不阻塞主库快照 | 通过 | `fiona-backup.sh:70-127`，退出码 1 表示部分失败，已写入 `DEPLOYMENT.md:568`；复核用 `chmod 000` 制造了一次真实的打包失败做验证 |

## 新发现
无。重复扣费、额度被绕过、删到根目录之外、访问或密钥泄露这四类风险都没有发现新缺陷。

## 遗留（不阻塞本期）
- `/studio/*` 的 OPTIONS 预检请求会返回 404。WO2 前端走同源，不受影响。
