#!/bin/zsh
# 用法：WT=<工作树根目录> NONODE_DIR=<仓库外的临时目录> gate.sh <输出目录>
# 在 $WT 上跑规格 §5 的确定性门禁，退出码逐项记录到 <输出目录>/exits.txt
: ${WT:?请设置 WT=工作树根目录} ${NONODE_DIR:?请设置 NONODE_DIR=仓库外的临时目录}
export NO_PROXY=localhost,127.0.0.1,::1,.local no_proxy=localhost,127.0.0.1,::1,.local
O=$1; mkdir -p "$O"; : > "$O/exits.txt"
cd "$WT/backend" || exit 2
.venv/bin/python -m pytest -q -p no:cacheprovider -rsf tests/test_novel_chat_feedback.py tests/test_novel_chat_feedback_frontend.py tests/test_desk_polish_frontend.py > "$O/new.txt" 2>&1; echo "new_exit=$?" >> "$O/exits.txt"
.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_novel_chat.py tests/test_novel_chat_create.py tests/test_novel_chat_create_frontend.py tests/test_song_agent_tools.py tests/test_song_frontend.py tests/test_claude_agent_runtime.py tests/test_claude_agent_docs.py tests/test_claude_agent_frontend.py tests/test_claude_agent_r1_frontend.py tests/test_novel_p1_api.py tests/test_novel_p1_runner.py tests/test_novel_r2_required_responses.py tests/test_novel_v2_api.py tests/test_novel_v2_compat.py tests/test_novel_p21_service.py tests/test_novel_p2_frontend.py tests/test_ui_closeout_dialog_scrim.py tests/test_design_system_gate.py tests/test_component_language.py tests/test_desk_logic_frontend.py tests/test_desk_views_frontend.py tests/test_desk_contract_frontend.py tests/test_desk_dock_races_frontend.py tests/test_studio_sources_readonly_integration.py tests/test_studio_sources.py > "$O/listed.txt" 2>&1; echo "listed_exit=$?" >> "$O/exits.txt"
.venv/bin/python -m pytest -q -p no:cacheprovider -rs > "$O/full.txt" 2>&1; echo "full_exit=$?" >> "$O/exits.txt"
cd "$WT/frontend" || exit 2
npx tsc --noEmit > "$O/tsc.txt" 2>&1; echo "tsc_exit=$?" >> "$O/exits.txt"
npm run lint > "$O/lint.txt" 2>&1; echo "lint_exit=$?" >> "$O/exits.txt"
npm run build > "$O/build.txt" 2>&1; echo "build_exit=$?" >> "$O/exits.txt"
# 无 node_modules 副本：起 node 的用例必须按约定 skip
C=$NONODE_DIR
rm -rf "$C"; mkdir -p "$C"
rsync -a --exclude 'frontend/node_modules' --exclude 'frontend/.next' "$WT/" "$C/"
cd "$C/backend" && .venv/bin/python -m pytest -q -p no:cacheprovider -rsf tests/test_novel_chat_feedback.py tests/test_novel_chat_feedback_frontend.py tests/test_desk_polish_frontend.py > "$O/nonode.txt" 2>&1; echo "nonode_exit=$?" >> "$O/exits.txt"
echo done >> "$O/exits.txt"
