# 案头第一期 · 隔离验收环境（8061 后端 + 3061 前端 + 临时库）。不要指向正在用的数据库。
# 用法：把 H 改成一个仓库外的空目录、WT 改成工作树根目录，然后 `. env.example.sh`。
H=/path/to/scratch/desk-verify
WT=/path/to/worktree
unset OPENAI_ORG_ID OPENAI_PROJECT_ID OPENAI_CUSTOM_HEADERS OPENAI_BASE_URL ANTHROPIC_BASE_URL ANTHROPIC_AUTH_TOKEN ANTHROPIC_PROFILE ANTHROPIC_FEDERATION_RULE_ID ANTHROPIC_IDENTITY_TOKEN ANTHROPIC_IDENTITY_TOKEN_FILE ANTHROPIC_CUSTOM_HEADERS ANTHROPIC_API_KEY DEEPSEEK_API_KEY ARK_API_KEY
export FIONA_DB_PATH="$H/data/desk.db" FIONA_UPLOADS_DIR="$H/uploads" FIONA_STUDIO_DIR="$H/studio" FIONA_SONG_DIR="$H/songs"
export DEV_MODE=1 DASHSCOPE_API_KEY=placeholder-not-a-key JWT_SECRET=placeholder-not-a-secret-desk-verify-0000000000
export FIONA_NOVEL=1 FIONA_NOVEL_USERS=tester,empty_user FIONA_NOVEL_CHAT=1 FIONA_NOVEL_CHAT_CREATE=1
export FIONA_STUDIO=1 FIONA_STUDIO_OWNERS=tester FIONA_STUDIO_REQUIRE_JWT=0
# 后端：cd "$WT/backend" && .venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8061 --env-file <一个空文件>
# 前端：cd "$WT/frontend" && FIONA_BACKEND_ORIGIN=http://localhost:8061 node_modules/.bin/next dev -H 127.0.0.1 -p 3061
