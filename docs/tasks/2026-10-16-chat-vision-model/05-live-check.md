# 05 真实验证（2026-10-16，作者同意后执行一次）

- 免费核对：`GET https://dashscope.aliyuncs.com/compatible-mode/v1/models` 共 176 个模型；`qwen3.8-omni-flash` 在列，`qwen-vl-max` 不在。
- 付费调用一次，未重试（`DASHSCOPE_MAX_RETRIES=0`）。走 worktree 代码：`_chat_vision_model()`（未设环境变量，取默认值）、`CHAT_VISION_EXTRA_BODY`、`QWEN_CLIENT`，参数与 `stream_image()` 相同：`max_tokens=400`、`temperature=0.9`、`stream=True`。另加 `stream_options.include_usage` 读取用量。
- 输入：480×320 本地合成 PNG，内容为红圆、蓝方块和文字「FIONA 42」，配一句短 system 提示，user 文本为「这是啥」。
- 结果：`model=qwen3.8-omni-flash`，耗时 1.5 秒；prompt 198 token（其中图片 152），completion 31 token，没有 reasoning token，说明关闭思考生效。
- 回复：「哈，这不就是一个红圆和一个蓝方块嘛，下面还写着“FIONA 42”，你朋友名字是菲奥娜？」形状、颜色和文字都识别正确。
- Key 从 `~/.zshrc` 注入子进程，未打印，也未写入磁盘。
