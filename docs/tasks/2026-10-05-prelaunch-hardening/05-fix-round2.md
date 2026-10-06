# 返修单 第 2 轮：GIF 透明判定只看像素（2026-10-06）

- **依据**：`04-review-round2.md` 媒体视角可优化第 1 条（复核员标「建议优先」），主会话已决定修复。
- **问题**：`backend/utils/media.py:99` 写的是 `gif_transparency = ext == "gif" and "transparency" in image.info`。GIF 只要在首帧图形控制扩展里声明了透明索引，即使所有帧都没有任何透明像素，也会整段设 `disposal=2`，帧间差分全部丢失。
  - 复核员实测：自造的 400×400 噪点 GIF 从 220,943 B 涨到 16,739,099 B（75.8 倍）。
  - 本机真实 GIF 7 个中有 6 个属于「声明了透明但没有透明像素」，例如 `remote_control.gif` 放大 2.80 倍。
- **改法**：删掉按元数据判定透明的条件，`gif_transparency` 初值为 `False`，只保留第 128 行按重建后 RGBA 帧实际 alpha 的判定。其余代码不动。
- **测试**：在 `backend/tests/test_upload_metadata.py` 新增回归测试：
  - 构造一个首帧声明透明索引、但所有帧像素都不透明的多帧 GIF（复杂静态背景加小块运动）；
  - 两条路径的输出体积都不超过输入的 2 倍；
  - 逐帧解码 RGBA 与输入一致。
  - 现有透明 GIF 逐帧一致测试必须继续通过。
- **白名单**：`backend/utils/media.py`、`backend/tests/test_upload_metadata.py`、本目录 `03-report.md`（末尾追加「第 2 轮返修」，贴 diff 与测试结果）。
- **硬规则**：同 `02-spec.md` 第 0 节。
