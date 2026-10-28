#!/bin/bash
# 手机对话页修缮（2026-10-28）门禁：规格 §6 第 1–7 条的命令类判据。
# 用法：bash gate.sh <仓库根（工作树）>   —— 逐条打印实际值与期望值，末尾汇总 FAIL 数；退出码 = FAIL 数。
set -u
ROOT="${1:?repo root}"
cd "$ROOT" || exit 99
P=frontend/app/page.tsx; S=frontend/components/ChatScrollArea.tsx; G=frontend/app/globals.css
FAIL=0; N=0
chk() { # chk <名称> <实际> <期望>（字符串相等）
  N=$((N+1)); if [ "$2" = "$3" ]; then printf 'PASS %-58s %s\n' "$1" "$2"; else printf 'FAIL %-58s got=%s want=%s\n' "$1" "$2" "$3"; FAIL=$((FAIL+1)); fi; }
chk_le() { N=$((N+1)); if [ "$2" -le "$3" ]; then printf 'PASS %-58s %s<=%s\n' "$1" "$2" "$3"; else printf 'FAIL %-58s got=%s max=%s\n' "$1" "$2" "$3"; FAIL=$((FAIL+1)); fi; }
chk_ge() { N=$((N+1)); if [ "$2" -ge "$3" ]; then printf 'PASS %-58s %s>=%s\n' "$1" "$2" "$3"; else printf 'FAIL %-58s got=%s min=%s\n' "$1" "$2" "$3"; FAIL=$((FAIL+1)); fi; }
cnt() { grep -c -- "$1" "$2"; }
cntF() { grep -cF -- "$1" "$2"; }

echo "== §6-5 结构判据"
chk "chat-shell overflow-clip" "$(cnt 'chat-shell relative flex flex-col h-dvh overflow-clip' $P)" 1
chk "no h-dvh overflow-hidden in page" "$(cnt 'h-dvh overflow-hidden' $P)" 0
chk "drawer-panel x6" "$(cnt 'drawer-panel' $P)" 6
chk "chat-latest in page" "$(cnt 'chat-latest' $P)" 1
chk "renderLatestButton={false}" "$(cnt 'renderLatestButton={false}' $P)" 1
chk "onLatestVisibilityChange={setShowLatestPill}" "$(cnt 'onLatestVisibilityChange={setShowLatestPill}' $P)" 1
chk "onLatestVisibilityChange= once" "$(cnt 'onLatestVisibilityChange=' $P)" 1
chk "CSA calls onLatestVisibilityChange?.(showLatest)" "$(cntF 'onLatestVisibilityChange?.(showLatest)' $S)" 1
chk "回到最新 in page" "$(cnt '回到最新' $P)" 1
chk "回到最新 in CSA" "$(cnt '回到最新' $S)" 1
chk "</ChatScrollArea> once" "$(cnt '</ChatScrollArea>' $P)" 1
awk '/<\/ChatScrollArea>/{a=NR} a&&!d&&/<\/div>/{d=NR} /chat-latest/{b=NR} /<Glaze as="footer"/{c=NR} END{exit !(d && b && c && d<b && b<c)}' $P; chk "pill between layer-close and footer (awk)" "$?" 0
chk "pill line has no old tokens" "$(grep 'chat-latest' $P | grep -cE 'border-border|bg-background|text-muted-foreground|shadow-sm|outline-primary')" 0
DIFF21=$(diff <(git show HEAD:$S | sed -n 21,113p) <(awk '/^  const viewportRef = /{p=1} p{print} p&&/^  const onScroll = /{q=1} q&&/^  };$/{exit}' $S) | wc -l | tr -d ' ')
chk "CSA 21-113 unchanged (diff lines)" "$DIFF21" 0
HUNKS=$(git diff -U0 HEAD -- $S | grep -E '^@@ -' | sed -E 's/^@@ -([0-9]+)(,([0-9]+))?.*/\1 \3/')
BAD=0; while read -r a b; do [ -z "$a" ] && continue; b=${b:-1}; if [ "$b" -gt 0 ]; then end=$((a+b)); if [ "$a" -lt 114 ] && [ "$end" -gt 21 ]; then BAD=$((BAD+1)); fi; else if [ "$a" -ge 21 ] && [ "$a" -le 112 ]; then BAD=$((BAD+1)); fi; fi; done <<< "$HUNKS"
chk "CSA hunks avoid [21,114)" "$BAD" 0
chk "css modal lens rule" "$(cnt 'chat-conversation-modal > .glaze > .glaze-lens' $G)" 1
chk "css drawer finish rule" "$(cnt 'drawer-panel > .glaze-finish' $G)" 1
chk "css modal finish rule" "$(cnt 'chat-conversation-modal > .glaze > .glaze-finish' $G)" 1
chk "no desktop modal rule" "$(cnt 'data-shell=desktop\] .chat-conversation-modal' $G)" 0
chk "first .drawer-panel line" "$(grep -n '\.drawer-panel' $G | head -1 | cut -d: -f1)" 565
chk "last mobile media line" "$(grep -n '@media (width < 48rem)' $G | tail -1 | cut -d: -f1)" 564
chk "footer no max-md:pb-2" "$(grep 'as="footer"' $P | grep -cE 'max-md:pb-2([^.0-9]|$)')" 0
chk "footer max-md:pb-1.5" "$(grep 'as="footer"' $P | grep -c 'max-md:pb-1.5')" 1
chk "footer max-md:pt-2" "$(grep 'as="footer"' $P | grep -c 'max-md:pt-2')" 1
chk "composer-inner max-md:py-1.5" "$(grep 'composer-inner' $P | grep -c 'max-md:py-1.5')" 1
chk "footer desktop classes intact" "$(grep 'as="footer"' $P | grep -c 'px-\[18px\] pb-3 pt-3')" 1
chk "fee note span" "$(cntF '每条消息消耗 <span className="readout font-normal">10</span> 颗草莓' $P)" 1
chk "平台模型 · 每条 10 颗草莓 x2" "$(cntF '平台模型 · 每条 10 颗草莓' $P)" 2
chk "title 平台模型每条消息消耗" "$(cntF '平台模型每条消息消耗 10 颗；自带模型聊天不扣' $P)" 1
chk "Enter 发送 copy" "$(cntF 'Enter 发送，Shift + Enter 换行' $P)" 1
chk_le "font-semibold in page" "$(cnt 'font-semibold' $P)" 3
chk "no bold in CSA" "$(grep -cE 'font-(semibold|bold)' $S)" 0

echo "== §6-6 改动集合"
STATUS=$(git status --porcelain | awk '{print $2}' | grep -vE '^docs/tasks/2026-10-28-mobile-chat-fix/' | sort | tr '\n' ' ')
chk "changed paths (whitelist only)" "$STATUS" "backend/tests/test_mobile_chat_fix.py frontend/app/globals.css frontend/app/page.tsx frontend/components/ChatScrollArea.tsx "
chk "no forbidden files in diff" "$(git diff --stat HEAD | grep -cE 'package.json|package-lock.json|next.config.ts|components/ui/')" 0

echo "== §6-1..4 工具链（耗时）"
export npm_config_cache=/tmp/fiona-npm-cache
( cd frontend && npx tsc --noEmit > /tmp/b1-tsc.txt 2>&1 ); chk "tsc exit" "$?" 0
( cd frontend && npm run lint > /tmp/b1-lint.txt 2>&1 ); LE=$?; WARN=$(grep -oE '[0-9]+ warnings?' /tmp/b1-lint.txt | tail -1 | grep -oE '[0-9]+'); ERR=$(grep -oE '[0-9]+ errors?' /tmp/b1-lint.txt | tail -1 | grep -oE '[0-9]+')
chk "lint exit" "$LE" 0; chk "lint errors" "${ERR:-0}" 0; chk_le "lint warnings" "${WARN:-0}" 25
( cd frontend && npm run build > /tmp/b1-build.txt 2>&1 ); chk "build exit" "$?" 0
( cd backend && .venv/bin/python -m pytest -q tests/test_ui_polish_*.py tests/test_*frontend*.py tests/test_mobile_chat_fix.py -p no:cacheprovider > /tmp/b1-pytest.txt 2>&1 ); PE=$?
PASSED=$(grep -oE '[0-9]+ passed' /tmp/b1-pytest.txt | tail -1 | grep -oE '[0-9]+'); NEWT=$(cd backend && .venv/bin/python -m pytest -q tests/test_mobile_chat_fix.py -p no:cacheprovider 2>/dev/null | grep -oE '[0-9]+ passed' | grep -oE '[0-9]+')
chk "pytest subset exit" "$PE" 0; chk_ge "pytest subset passed" "${PASSED:-0}" 499; chk_ge "new test count" "${NEWT:-0}" 7
grep -q 'test_globals_css_smooths_drawer_materials_on_mobile_only' /tmp/b1-pytest.txt && echo "note: drawer css test name appears in output (likely failure)";

echo "== 汇总: $N 项，FAIL=$FAIL"
exit $FAIL
