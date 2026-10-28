#!/bin/bash
# 空态与文案（2026-10-28）门禁：规格 v1.2 §6 第 1–6 条，外加只增不删、授权测试行等硬核对。v2 = 返修 R1 后的判据；v3 加 page.tsx 文件头 BOM 与 hunk 数。
# 用法：bash gate.sh <仓库根（工作树）>；逐条打印实际值与期望值，退出码 = FAIL 数。
set -u
ROOT="${1:?repo root}"
cd "$ROOT" || exit 99
FAIL=0; N=0
chk() { N=$((N+1)); if [ "$2" = "$3" ]; then printf 'PASS %-64s %s\n' "$1" "$2"; else printf 'FAIL %-64s got=%s want=%s\n' "$1" "$2" "$3"; FAIL=$((FAIL+1)); fi; }
chk_ge() { N=$((N+1)); if [ "$2" -ge "$3" ]; then printf 'PASS %-64s %s>=%s\n' "$1" "$2" "$3"; else printf 'FAIL %-64s got=%s min=%s\n' "$1" "$2" "$3"; FAIL=$((FAIL+1)); fi; }
chk_le() { N=$((N+1)); if [ "$2" -le "$3" ]; then printf 'PASS %-64s %s<=%s\n' "$1" "$2" "$3"; else printf 'FAIL %-64s got=%s max=%s\n' "$1" "$2" "$3"; FAIL=$((FAIL+1)); fi; }
cnt() { grep -cF -- "$1" "$2" 2>/dev/null || true; }
F=frontend; P=$F/app/page.tsx
SITES="$F/components/novel/NovelWizard.tsx $F/components/novel/NovelShelf.tsx $F/components/novel/NovelWorkbench.tsx $F/components/studio/StudioShelf.tsx $F/components/studio/StudioWorkbench.tsx $F/components/studio/kb/KbWorkbench.tsx $F/components/MyAgentWorkspace.tsx $F/components/AgentExchangeWorkspace.tsx $F/components/AgentMemoryPanel.tsx $F/app/agents/[id]/page.tsx"

echo "== 前置：扫描面不为空"
chk "10 sites exist" "$(for f in $SITES; do [ -f "$f" ] && echo x; done | wc -l | tr -d ' ')" 10

echo "== T1 身份确认中"
chk "lib exports useAccountIdentityPending" "$(cnt 'export function useAccountIdentityPending(): boolean {' $F/lib/useAccountIdentity.ts)" 1
chk "lib diff has no removed lines" "$(git diff HEAD -- $F/lib/useAccountIdentity.ts | grep -c '^-[^-]')" 0
chk "lib keeps original snapshot call" "$(cnt 'return useSyncExternalStore(subscribeAccount, getUsername, serverIdentity);' $F/lib/useAccountIdentity.ts)" 1
chk "lib auth import unchanged" "$(cnt 'import { ensureAccountIdentity, getUsername } from "@/lib/auth";' $F/lib/useAccountIdentity.ts)" 1
chk "lib new code avoids useId/dispatchEvent/location/document" "$(git diff HEAD -- $F/lib/useAccountIdentity.ts | grep '^+' | grep -cE 'useId|dispatchEvent|location|document')" 0
chk "lib comment line 1 (v1.2)" "$(cnt '// 身份是否还没确认：服务端渲染与水合首帧为 true；本地没有用户名、且本页第一次身份检查（ensureAccountIdentity）还没结束时也为 true。' $F/lib/useAccountIdentity.ts)" 1
chk "lib comment line 2 (v1.2)" "$(cnt '// 第一次检查结束后不再回到确认中：另一个标签清掉本地用户名、而 Cookie 仍有效时，会先显示登录提示，等 auth.ts 用 Cookie 找回后再恢复。' $F/lib/useAccountIdentity.ts)" 1
chk "lib old comment gone (v1.2)" "$(cnt '还没完成过一次身份找回' $F/lib/useAccountIdentity.ts)" 0
chk "lib/auth.ts untouched" "$(git diff --name-only HEAD -- $F/lib/auth.ts | wc -l | tr -d ' ')" 0
for f in $SITES; do
  b=$(basename "$(dirname "$f")")/$(basename "$f")
  chk "pending hook called: $b" "$(cnt 'useAccountIdentityPending()' "$f")" 1
  chk "pending prop passed: $b" "$(cnt 'identityPending={identityPending}' "$f")" 1
  chk "inner default false: $b" "$(cnt 'identityPending = false' "$f")" 1
  chk "pending text once: $b" "$(cnt '正在加载身份…' "$f")" 1
done
for pair in "$F/components/novel/NovelWizard.tsx|请登录后新建小说。" "$F/components/novel/NovelShelf.tsx|请登录后查看你的书架。" "$F/components/novel/NovelWorkbench.tsx|请登录后打开你的书斋。" "$F/components/studio/StudioShelf.tsx|请登录后打开工作室。" "$F/components/studio/StudioWorkbench.tsx|请登录后打开工作室。" "$F/components/studio/kb/KbWorkbench.tsx|请登录后打开导演知识库。" "$F/components/MyAgentWorkspace.tsx|请登录后管理自己的分身。" "$F/components/AgentExchangeWorkspace.tsx|请登录后查看分身和自己的交流记录。" "$F/components/AgentMemoryPanel.tsx|请登录后查看私有记忆。" "$F/app/agents/[id]/page.tsx|请登录后查看分身名片。"; do
  f=${pair%%|*}; s=${pair#*|}
  chk "login copy kept once: $(basename "$f")" "$(cnt "$s" "$f")" 1
done
for f in $F/components/novel/NovelShelf.tsx $F/components/novel/NovelWorkbench.tsx $F/components/studio/StudioShelf.tsx; do
  chk "login link targets top when embedded: $(basename $f)" "$(cnt 'href="/login" target={embedded ? "_top" : undefined}' "$f")" 1
done

echo "== T2 书架"
chk "studio h1 sr-only when embedded" "$(cnt '<h1 className={`text-[28px] tracking-[.24em]${embedded ? " sr-only" : ""}`}>短片工作室</h1>' $F/components/studio/StudioShelf.tsx)" 1
chk "studio button ml-auto when embedded" "$(cnt 'className={`btn btn-primary min-h-10${embedded ? " ml-auto" : ""}`}' $F/components/studio/StudioShelf.tsx)" 1
chk "novel header link hidden only with empty card" "$(cnt '{!(owner && !error && !loading && books.length === 0) && <Link href={newBookHref}' $F/components/novel/NovelShelf.tsx)" 1
chk "novel refresh label/icon need owner" "$(( $(cnt 'loading && owner ? "刷新中…"' $F/components/novel/NovelShelf.tsx) + $(cnt 'loading && owner ? "animate-spin"' $F/components/novel/NovelShelf.tsx) ))" 2
chk "novel refresh disabled without owner" "$(cnt 'disabled={loading || !owner}' $F/components/novel/NovelShelf.tsx)" 1
chk "novel header row min-h-10 (v1.2)" "$(cnt '<div className="flex min-h-10 flex-wrap items-center justify-between gap-3">' $F/components/novel/NovelShelf.tsx)" 1
chk "studio header row min-h-10 (v1.2)" "$(cnt '<div className="flex min-h-10 flex-wrap items-center justify-between gap-3">' $F/components/studio/StudioShelf.tsx)" 1
chk "novels/page.tsx untouched" "$(git diff --name-only HEAD -- $F/app/novels/page.tsx | wc -l | tr -d ' ')" 0

echo "== T3 新对话开场"
chk "openers block" "$(cnt 'data-chat-openers' $P)" 1
for s in '>聊聊今天<' '>帮我画一张…<' '>看看我拍的这张图<' 'onClick={startChatOpener}' 'onClick={startDrawOpener}' 'onClick={startPhotoOpener}'; do chk "page has $s" "$(cnt "$s" $P)" 1; done
OPENERS=$(awk '/const startChatOpener = \(\) => \{/{p=1} p{print} /const startPhotoOpener/{q=1} q&&/^  \};/{exit}' $P)
chk_ge "opener bodies extracted (lines)" "$(printf '%s\n' "$OPENERS" | wc -l | tr -d ' ')" 9
chk "opener bodies never send" "$(printf '%s\n' "$OPENERS" | grep -cE 'handleSend|apiFetch|fetch\(')" 0
chk "no inline setImageMode click" "$(cnt 'onClick={() => setImageMode(true)}' $P)" 0
chk "file inputs still 2" "$(cnt 'type="file"' $P)" 2
chk "old 新对话 wording gone (page)" "$(cnt '点击上方“新对话”' $P)" 0
chk "new 新建 wording (page)" "$(cnt '在对话列表里点「新建」，开始和自己的分身交流。' $P)" 1
chk "new retry wording (page)" "$(cnt '对话加载失败，请在对话列表里重试。' $P)" 1
chk "old 上方重试 wording gone" "$(cnt '请在上方重试' $P)" 0
chk "page.tsx keeps HEAD UTF-8 BOM (v3)" "$(head -c3 $P | xxd -p)" "$(git show HEAD:$P | head -c3 | xxd -p)"
chk "page.tsx diff is exactly 4 hunks (v3)" "$(git diff HEAD -- $P | grep -c '^@@')" 4
chk "keydown block is exactly the v1.2 8 lines" "$(python3 -I - "$P" <<'PY'
import sys
s = open(sys.argv[1], encoding="utf-8").read()
m = "const handleKeyDown = (e: React.KeyboardEvent) => {"
i = s.index(m); lines = s[i:].splitlines()
block = []
for ln in lines:
    block.append(ln.strip())
    if ln.strip() == "};": break
want = ["const handleKeyDown = (e: React.KeyboardEvent) => {", 'if (e.key !== "Enter" || e.shiftKey) return;',
        "// Use ref for IME composing state — more reliable than e.nativeEvent.isComposing", "if (isComposingRef.current) return;",
        "e.preventDefault();", "if (e.repeat) return;", "handleSend();", "};"]
print(1 if block == want and s.count(m) == 1 else 0)
PY
)" 1
chk_ge "chat opener respects draft" "$(cnt '!!input.trim()' $P)" 2
chk "old 新对话 wording gone (picker)" "$(cnt '点「新对话」' $F/components/ConversationPicker.tsx)" 0
chk "new 新建 wording (picker)" "$(cnt '点「新建」，开始和自己的分身交流。' $F/components/ConversationPicker.tsx)" 1
chk "stale voice comment gone" "$(cnt 'puts text in input for review' $P)" 0

echo "== T4 匹配页 / T5 画像改名"
M=$F/app/match/page.tsx
chk "match empty block" "$(cnt 'data-match-empty' $M)" 1
chk "match CTA" "$(cnt '查看公开名片设置' $M)" 1
chk "match CTA top target" "$(cnt 'href="/agents/me" target={embedded ? "_top" : undefined}' $M)" 1
python3 -I - "$M" <<'PY' || FAIL=$((FAIL+1))
import re, sys
s = open(sys.argv[1], encoding="utf-8").read()
a = s.find("<section data-match-empty"); b = s.find("</section>", a)
sec = s[a:b] if a >= 0 and b > a else ""
need = ["匹配是什么", "发送打招呼", "查看公开名片设置", "不会建立真人聊天"]
ok = bool(sec) and all(x in sec for x in need) and not re.search("匿名|不知道你是谁|Skill|自动交流|左侧", sec)
print(("PASS" if ok else "FAIL") + " match empty section copy (required phrases present, forbidden words absent in section)")
sys.exit(0 if ok else 1)
PY
N=$((N+1))
chk "match section padding not margin (v1.2)" "$(cnt '<section data-match-empty className="relative z-[1] mx-auto max-h-full max-w-[520px] overflow-y-auto px-6 pb-6 pt-10 text-[13px] leading-[1.85] text-[color:var(--ink2)] mobile:px-1 mobile:pt-2">' $M)" 1
chk "match :74 comment kept" "$(cnt '{/* 匿名头像 */}' $M)" 1
chk "match no max-md" "$(cnt 'max-md:' $M)" 0
chk "match old left copy gone" "$(cnt '接受匹配后会出现在这里' $M)" 0
chk "旧社交画像 gone (frontend+docs)" "$(grep -rnF '旧社交画像' $F/app $F/components README.md PLAN.md docs/ARCHITECTURE.md | wc -l | tr -d ' ')" 0
chk_ge "社交画像（旧版） in profile" "$(grep -o '社交画像（旧版）' $F/app/profile/page.tsx | wc -l | tr -d ' ')" 3
chk "positive control: new name in profile+docs" "$(( $(grep -o '社交画像（旧版）' $F/app/profile/page.tsx README.md PLAN.md docs/ARCHITECTURE.md | wc -l) >= 6 ? 1 : 0 ))" 1
chk "profile footer sentence" "$(cnt '那里的「清空记忆与个人画像」会一并清空这份社交画像（旧版），聊天记录会保留。' $F/app/profile/page.tsx)" 1
chk "profile join 、 kept" "$(cnt '.join("、")' $F/app/profile/page.tsx)" 1
chk "existing tests touched: only one file" "$(git diff --name-only HEAD -- backend/tests | tr '\n' ' ')" "backend/tests/test_ui_polish_settings_drawers.py "
chk "authorised test diff is 1/1" "$(git diff --numstat HEAD -- backend/tests/test_ui_polish_settings_drawers.py | awk '{print $1"/"$2}')" "1/1"
chk "authorised test line new" "$(git diff HEAD -- backend/tests/test_ui_polish_settings_drawers.py | grep -cF '+    assert_heading_hides_when_embedded(PROFILE, "社交画像（旧版）")')" 1

echo "== T6 设置页隐私"
C=$F/components/ChatModelSection.tsx
chk "details once" "$(cnt '<details className=' $C)" 1
chk "summary copy" "$(cnt '>更多隐私与计费说明</summary>' $C)" 1
chk "enable note says first save enables" "$(cnt '首次保存后会直接启用；之后可以用这个开关停用或重新启用。' $C)" 1
chk "old misleading note gone" "$(cnt '先保存配置，才能启用。' $C)" 0
chk "claude-only disclosure line (v1.2 copy)" "$(cnt '{provider.id === "anthropic" && <p className={noteClass}>已选 Claude：你在聊天里发的图片和工具结果也会发送给 Anthropic，详见下方「更多隐私与计费说明」。</p>}' $C)" 1
chk "old 本轮图片 copy gone (v1.2)" "$(cnt '本轮图片和工具结果' $C)" 0
for s in '启用后，聊天回复会把分身设定' '危机复核、平台工具执行' '<p>生图：' '<p>选 Claude 时，' '自带模型文字聊天不扣草莓' 'Key 加密保存，删除 Key' '<p>开启『聊天读小说』后' '<p>Claude 的接口不对中国大陆提供服务。</p>'; do chk "privacy paragraph once: ${s:0:12}" "$(cnt "$s" $C)" 1; done
python3 -I - "$C" <<'PY' || FAIL=$((FAIL+1))
import sys
s = open(sys.argv[1], encoding="utf-8").read()
d0, d1 = s.index("<details"), s.index("</details>")
first, save = s.index("启用后，聊天回复会把分身设定"), s.index('"保存"}</button>')
toggle = s.index("启用我的聊天模型")
inside = all(d0 < s.index(x) < d1 for x in ("<p>生图：", "<p>选 Claude 时，", "<p>开启『聊天读小说』后"))
ok = first < toggle < save and not (d0 < first < d1) and inside and s.index("<p>生图：") < s.index("<p>选 Claude 时，") and d0 > s.rindex("</fieldset>", 0, d0 + 1)
print(("PASS" if ok else "FAIL") + " privacy order: first paragraph before toggle & 保存, outside details; locked three inside details")
sys.exit(0 if ok else 1)
PY
N=$((N+1))

echo "== T7 历史页 / T8 语音"
H=$F/app/history/page.tsx
chk "history showPicker( exactly once (v1.2)" "$(grep -oF 'showPicker(' $H | wc -l | tr -d ' ')" 1
chk "history openDatePicker(e.currentTarget) x4 (v1.2)" "$(grep -oF 'openDatePicker(e.currentTarget)' $H | wc -l | tr -d ' ')" 4
chk "history aria 从（开始日期） (v1.2)" "$(cnt 'aria-label="从（开始日期）"' $H)" 1
chk "history aria 到（结束日期） (v1.2)" "$(cnt 'aria-label="到（结束日期）"' $H)" 1
chk "history old bare aria labels gone (v1.2)" "$(( $(cnt 'aria-label="开始日期"' $H) + $(cnt 'aria-label="结束日期"' $H) ))" 0
chk "history from max bound (v1.2)" "$(cnt 'max={dateTo || "9999-12-31"}' $H)" 1
chk "history to min kept (v1.2)" "$(cnt 'min={dateFrom || undefined}' $H)" 1
chk "history to max bound (v1.2)" "$(cnt 'max="9999-12-31"' $H)" 1
chk "history dayFace raw fallback (v1.2)" "$(cnt 'const dayFace = (key: string) => (key ? formatBeijingDateLong(beijingDayStart(key)) || key : "不限");' $H)" 1
chk "history 至 divider gone" "$(cnt 'text-muted-foreground">至</div>' $H)" 0
chk "history 全部 highlight fixed" "$(cnt '(key !== "all" || (!dateFrom && !dateTo))' $H)" 1
chk_ge "history chip focus ring" "$(cnt 'has-[:focus-visible]:outline' $H)" 2
chk "history beijing helpers kept" "$( (cnt '@/lib/beijingTime' $H; cnt 'formatBeijingTime(' $H) | awk '$1>0' | wc -l | tr -d ' ')" 2
V2=$F/components/VoiceButton.tsx
chk "voice status bubble" "$(cnt 'data-voice-status' $V2)" 1
chk "voice diff has no removed lines" "$(git diff HEAD -- $V2 | grep -c '^-[^-]')" 0
chk "voice try once" "$(cnt 'try {' $V2)" 1

echo "== 通用"
chk_ge "aria-label= total" "$(grep -rho 'aria-label=' $F/app $F/components --include='*.tsx' | wc -l | tr -d ' ')" 118
BOLD_NOW=$(git diff HEAD -- $F | grep '^+' | grep -cE 'font-semibold|font-bold|fontWeight|<strong')
chk "no new bold in diff" "$BOLD_NOW" 0
chk "no new middle dot in added lines" "$(git diff HEAD -- $F | grep '^+' | grep -v '^+++' | grep -c '·')" 0

echo "== §6-6 改动集合"
ALLOW='^(frontend/lib/useAccountIdentity\.ts|frontend/components/novel/(NovelWizard|NovelShelf|NovelWorkbench)\.tsx|frontend/components/studio/(StudioShelf|StudioWorkbench)\.tsx|frontend/components/studio/kb/KbWorkbench\.tsx|frontend/components/(MyAgentWorkspace|AgentExchangeWorkspace|AgentMemoryPanel|ConversationPicker|ChatModelSection|VoiceButton)\.tsx|frontend/app/agents/\[id\]/page\.tsx|frontend/app/(page|match/page|profile/page|history/page)\.tsx|README\.md|PLAN\.md|docs/ARCHITECTURE\.md|backend/tests/test_ui_polish_settings_drawers\.py|backend/tests/test_empty_states_(identity|novel|studio|agents|chat_openers|match_profile|settings_privacy|history_dates|voice_hint)\.py|docs/tasks/2026-10-28-empty-states/.*)$'
OUTSIDE=$(git status --porcelain --untracked-files=all | awk '{print $2}' | grep -vE "$ALLOW" | tr '\n' ' ')
chk "changes outside whitelist" "${OUTSIDE:-none}" none
chk "new test files present" "$(ls backend/tests/test_empty_states_*.py 2>/dev/null | wc -l | tr -d ' ')" 9
chk "docs lines changed only (README/PLAN/ARCH 1/1 each)" "$(git diff --numstat HEAD -- README.md PLAN.md docs/ARCHITECTURE.md | awk '{print $1"/"$2}' | tr '\n' ' ')" "1/1 1/1 1/1 "

if [ "${SKIP_TOOLCHAIN:-0}" != "1" ]; then
echo "== §6-1..4 工具链"
export npm_config_cache=/tmp/fiona-npm-cache NEXT_TELEMETRY_DISABLED=1
NV=$(cd $F && node -e "console.log(require('next/package.json').version)"); chk "next version" "$NV" 16.4.3
( cd $F && npx tsc --noEmit > /tmp/b3-tsc.txt 2>&1 ); chk "tsc exit" "$?" 0
( cd $F && npm run lint > /tmp/b3-lint.txt 2>&1 ); LE=$?; WARN=$(grep -oE '[0-9]+ warnings?' /tmp/b3-lint.txt | tail -1 | grep -oE '[0-9]+'); ERR=$(grep -oE '[0-9]+ errors?' /tmp/b3-lint.txt | tail -1 | grep -oE '[0-9]+')
chk "lint exit" "$LE" 0; chk "lint errors" "${ERR:-0}" 0; chk_le "lint warnings" "${WARN:-0}" 25
( cd $F && rm -rf .next && npm run build > /tmp/b3-build.txt 2>&1 ); chk "build exit" "$?" 0
( cd backend && PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider -rs > /tmp/b3-pytest.txt 2>&1 ); PE=$?
PASSED=$(grep -oE '[0-9]+ passed' /tmp/b3-pytest.txt | tail -1 | grep -oE '[0-9]+'); SKIPPED=$(grep -oE '[0-9]+ skipped' /tmp/b3-pytest.txt | tail -1 | grep -oE '[0-9]+'); FAILED=$(grep -oE '[0-9]+ failed' /tmp/b3-pytest.txt | tail -1 | grep -oE '[0-9]+')
NEWT=$(cd backend && .venv/bin/python -m pytest -q --collect-only tests/test_empty_states_*.py -p no:cacheprovider 2>/dev/null | grep -oE '^[0-9]+ tests? collected|[0-9]+ tests collected' | grep -oE '[0-9]+' | head -1)
chk "pytest full exit" "$PE" 0; chk "pytest failed" "${FAILED:-0}" 0; chk "pytest skipped" "${SKIPPED:-0}" 0
chk_ge "new tests collected" "${NEWT:-0}" 16
chk_ge "pytest passed >= 7774 + new" "${PASSED:-0}" "$((7774 + ${NEWT:-0}))"

fi
echo "== 汇总: $N 项，FAIL=$FAIL"
exit $FAIL
