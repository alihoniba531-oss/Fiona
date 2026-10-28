#!/bin/bash
# 组件语言统一（2026-10-28）门禁：规格 §6 第 1–7 条。
# 用法：bash gate.sh <仓库根（工作树）>；逐条打印实际值与期望值，退出码 = FAIL 数。
set -u
ROOT="${1:?repo root}"
cd "$ROOT" || exit 99
FAIL=0; N=0
chk() { N=$((N+1)); if [ "$2" = "$3" ]; then printf 'PASS %-60s %s\n' "$1" "$2"; else printf 'FAIL %-60s got=%s want=%s\n' "$1" "$2" "$3"; FAIL=$((FAIL+1)); fi; }
chk_le() { N=$((N+1)); if [ "$2" -le "$3" ]; then printf 'PASS %-60s %s<=%s\n' "$1" "$2" "$3"; else printf 'FAIL %-60s got=%s max=%s\n' "$1" "$2" "$3"; FAIL=$((FAIL+1)); fi; }
chk_ge() { N=$((N+1)); if [ "$2" -ge "$3" ]; then printf 'PASS %-60s %s>=%s\n' "$1" "$2" "$3"; else printf 'FAIL %-60s got=%s min=%s\n' "$1" "$2" "$3"; FAIL=$((FAIL+1)); fi; }
P=frontend/app/page.tsx; B=frontend/components/ChatBubble.tsx

echo "== §6-5 结构判据"
chk "native confirm/alert = 0" "$(grep -rnE '(^|[^.A-Za-z_])(window\.)?(confirm|alert)\((`|")' frontend/app frontend/components frontend/lib --include='*.tsx' --include='*.ts' | wc -l | tr -d ' ')" 0
SCANNED=$(find frontend/app frontend/components frontend/lib -name '*.ts' -o -name '*.tsx' | wc -l | tr -d ' '); chk_ge "scanned ts/tsx files" "$SCANNED" 100
for f in frontend/app/settings/page.tsx frontend/app/page.tsx frontend/components/LocalWatchSection.tsx frontend/components/AgentMemoryPanel.tsx frontend/components/ChatModelSection.tsx frontend/components/novel/NovelWorkbench.tsx; do chk_ge "useConfirm() in $(basename $(dirname $f))/$(basename $f)" "$(grep -c 'useConfirm()' $f)" 1; done
for f in frontend/app/settings/page.tsx frontend/app/page.tsx; do chk_ge "useNotice() in $f" "$(grep -c 'useNotice()' $f)" 1; done
chk "NovelWorkbench still has confirm(" "$(grep -c 'confirm(' frontend/components/novel/NovelWorkbench.tsx | awk '{print ($1>0)?1:0}')" 1
chk "<ConfirmProvider> in layout" "$(grep -c '<ConfirmProvider>' frontend/app/layout.tsx)" 1
chk "font-semibold in page" "$(grep -c 'font-semibold' $P)" 0
chk "ChatBubble dead state/icons gone" "$(grep -cE 'setMuted|setHovered|onMouseEnter|VolumeX|Trash2' $B)" 0
chk "setVoiceOn count unchanged (5)" "$(grep -c 'setVoiceOn' $P)" 5
chk_ge "aria-label= total" "$(grep -rho 'aria-label=' frontend/app frontend/components --include='*.tsx' | wc -l | tr -d ' ')" 118
chk "平台官方 AI · 无真人用户 kept" "$(grep -c '平台官方 AI · 无真人用户' frontend/components/AgentExchangeWorkspace.tsx)" 1
for pair in 'frontend/app/settings/page.tsx|的所有聊天记录？此操作不可恢复。' 'frontend/app/settings/page.tsx|自带模型配置与 Key。确定继续？' 'frontend/app/settings/page.tsx|账号数据已删除，但有媒体文件需要管理员继续清理。' 'frontend/app/page.tsx|清空当前聊天界面？（历史记录仍保留）' 'frontend/app/page.tsx|删除这段对话及其中的消息？其他对话和分身设定会保留。此操作不可恢复。' 'frontend/app/page.tsx|只能上传图片' 'frontend/app/page.tsx|图片不能超过 5MB' 'frontend/components/LocalWatchSection.tsx|的令牌？监控程序将停止。' 'frontend/components/LocalWatchSection.tsx|删除规则「' 'frontend/components/AgentMemoryPanel.tsx|清空分身记忆和已有个人画像？聊天记录与分身设定会保留，后续交流可形成新的记忆。' 'frontend/components/ChatModelSection.tsx|确定删除自带模型配置与 Key？之后聊天将使用平台模型。' 'frontend/components/novel/NovelWorkbench.tsx|章节、推演和留言都会删除，无法恢复。' 'frontend/app/page.tsx|删除这条消息？此操作不可恢复。'; do f=${pair%%|*}; s=${pair#*|}; chk "copy once: ${s:0:18}" "$(grep -cF -- "$s" $f)" 1; done
echo "== 中点替换"
chk "ChatBubble title （AI 分身）" "$(grep -cF '（AI 分身）' $B)" 1
chk "ChatBubble no ' · AI 分身' / ' · 由你的模型回复'" "$(grep -cE ' · AI 分身| · 由你的模型回复' $B)" 0
chk "settings Chloe AI 助理（内测版）" "$(grep -cF 'Chloe AI 助理（内测版）' frontend/app/settings/page.tsx)" 1
chk "plaza 更新中，" "$(grep -cF '"更新中，"' frontend/app/plaza/page.tsx)" 1
chk "plaza 标签（最多 5 个）" "$(grep -cF '标签（最多 5 个）' frontend/app/plaza/page.tsx)" 1
chk "profile join 、" "$(grep -cF 'join("、")' frontend/app/profile/page.tsx)" 1
chk "localwatch （type，state）" "$(grep -cF '（{typeLabels[rule.kind]}，' frontend/components/LocalWatchSection.tsx)" 1
chk "exchange 发起方/受邀方 (2 lines)" "$(grep -cE '我的 AI 分身（发起方）|对方 AI 分身（受邀方）' frontend/components/AgentExchangeWorkspace.tsx)" 2
chk "exchange <b className=\"readout\"> gone" "$(grep -cF '<b className="readout">' frontend/components/AgentExchangeWorkspace.tsx)" 0

echo "== §6-6 改动集合"
ALLOW='^(frontend/app/layout\.tsx|frontend/app/globals\.css|frontend/app/page\.tsx|frontend/components/ChatBubble\.tsx|frontend/app/settings/page\.tsx|frontend/app/plaza/page\.tsx|frontend/app/profile/page\.tsx|frontend/components/LocalWatchSection\.tsx|frontend/components/AgentMemoryPanel\.tsx|frontend/components/ChatModelSection\.tsx|frontend/components/AgentExchangeWorkspace\.tsx|frontend/components/novel/NovelWorkbench\.tsx|frontend/components/ConfirmDialog\.tsx|frontend/lib/ttsChunks\.ts|backend/tests/test_component_language\.py|docs/tasks/2026-10-28-component-language/.*)$'
OUTSIDE=$(git status --porcelain --untracked-files=all | awk '{print $2}' | grep -vE "$ALLOW" | tr '\n' ' ')
chk "changes outside whitelist" "${OUTSIDE:-none}" none
chk "no forbidden files in diff" "$(git diff --stat HEAD | grep -cE 'package.json|package-lock.json|next.config.ts|components/ui/|components/studio/|SongProjectCard')" 0
echo "== §6-7 ChatCard 未动"
L=$(awk '/^function weatherDayLabel\(/{p=1} /^export type ImageAspectRatio/{exit} p' $B | wc -l | tr -d ' '); chk_ge "ChatCard block extracted (lines)" "$L" 100
chk "ChatCard block diff vs HEAD" "$(diff <(git show HEAD:$B | awk '/^function weatherDayLabel\(/{p=1} /^export type ImageAspectRatio/{exit} p') <(awk '/^function weatherDayLabel\(/{p=1} /^export type ImageAspectRatio/{exit} p' $B) | wc -l | tr -d ' ')" 0

echo "== §6-1..4 工具链"
export npm_config_cache=/tmp/fiona-npm-cache
NV=$(cd frontend && node -e "console.log(require('next/package.json').version)"); chk "next version" "$NV" 16.4.3
( cd frontend && npx tsc --noEmit > /tmp/b2-tsc.txt 2>&1 ); chk "tsc exit" "$?" 0
( cd frontend && npm run lint > /tmp/b2-lint.txt 2>&1 ); LE=$?; WARN=$(grep -oE '[0-9]+ warnings?' /tmp/b2-lint.txt | tail -1 | grep -oE '[0-9]+'); ERR=$(grep -oE '[0-9]+ errors?' /tmp/b2-lint.txt | tail -1 | grep -oE '[0-9]+')
chk "lint exit" "$LE" 0; chk "lint errors" "${ERR:-0}" 0; chk_le "lint warnings" "${WARN:-0}" 25
( cd frontend && rm -rf .next && npm run build > /tmp/b2-build.txt 2>&1 ); chk "build exit" "$?" 0
( cd backend && .venv/bin/python -m pytest -q tests/test_ui_polish_*.py tests/test_*frontend*.py tests/test_mobile_chat_fix.py tests/test_component_language.py -p no:cacheprovider -rs > /tmp/b2-pytest.txt 2>&1 ); PE=$?
PASSED=$(grep -oE '[0-9]+ passed' /tmp/b2-pytest.txt | tail -1 | grep -oE '[0-9]+'); SKIPPED=$(grep -oE '[0-9]+ skipped' /tmp/b2-pytest.txt | tail -1 | grep -oE '[0-9]+')
NEWT=$(cd backend && .venv/bin/python -m pytest -q tests/test_component_language.py -p no:cacheprovider 2>/dev/null | grep -oE '[0-9]+ passed' | grep -oE '[0-9]+')
chk "pytest subset exit" "$PE" 0; chk_ge "pytest subset passed" "${PASSED:-0}" 507; chk "pytest skipped" "${SKIPPED:-0}" 0; chk_ge "new test count" "${NEWT:-0}" 8
chk "novel confirm( test still green" "$(cd backend && .venv/bin/python -m pytest -q 'tests/test_novel_p2_frontend.py::test_workbench_polls_only_running_books_and_pauses_on_visibility' -p no:cacheprovider 2>&1 | grep -c '1 passed')" 1

echo "== 汇总: $N 项，FAIL=$FAIL"
exit $FAIL
