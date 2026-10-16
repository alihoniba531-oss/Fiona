# 小说工坊 P2 第 2 轮返修单（小）

**来源**：`04-review-r2.md`。F1–F9 全部通过核验，另有一条回归必须修复。

**红线**与第 1 轮相同：
- 只改下面列出的文件；
- 既有测试的输入和断言不改，`test_novel_p2_*.py` 已有断言不得放宽；
- 不加依赖，不联网，不读密钥，不提交 commit。

## R2-1【必须】`backend/tests/test_novel_p2_r1.py` 在 CI 的后端作业中会整文件变红

**原因**：CI 的后端作业（`.github/workflows/quality.yml`）只做 checkout 和 pip 安装，不执行 `npm ci`；而 ubuntu-latest 自带 node。测试里的 `DRIVER` 会 `require(frontend/node_modules/typescript)`，`probe()` 只在没有 node 时才 skip。结果是缺包时 14 条用例全部报 `MODULE_NOT_FOUND`。

**改法**：
- 在 `probe()`（或模块级的 fixture）开头增加判断：`frontend/node_modules/typescript` 不存在时，执行 `pytest.skip("frontend/node_modules/typescript is unavailable")`。
- 写法参照 `backend/tests/test_claude_agent_r1_frontend.py` 中约 147–158 行的先例。
- 不改任何断言。

**验收**：
1. 复制 `backend/tests/test_novel_p2_r1.py`、`frontend/lib`、`frontend/components/novel` 到一个**不含** `node_modules` 的临时目录，保持相对结构，然后运行该测试：应全部 skip，0 failed。
2. 在正常工作树中运行：14 条全部 passed，没有 skip。

## R2-2【建议】切换章节时闪一帧空态（`NovelWorkbench.tsx`）

**现象**：`ChapterReader` 的 `loading` 现在只看 `chapterLoading`。切换章节后的第一帧 `currentChapter` 为 null，会先渲染出空态文案。

**改法**：恢复返修前的条件：

```ts
chapterLoading || (selectedChapter != null && !currentChapter)
```

## R2-3【建议】章名去重的边界情况（`lib/novels.ts` 的 `displayNovelChapterTitle`）

- 剥掉前缀后结果为空时（章名恰好就是「第二章」），回退为原章名。
- 只有当「第…章」后面紧跟空白、标点或字符串结尾时才剥离。例如「第三章节的秘密」不应被剥成「节的秘密」。
- 在 `test_novel_p2_r1.py` 中补充这两种情况的断言。

**完成后**：在 `03-report.md` 末尾追加「第 2 轮返修」一节，并输出变更总结。
