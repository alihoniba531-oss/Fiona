#!/bin/bash
# 第三批隔离后端：临时库、DEV_MODE=1、不读 backend/.env（FIONA_ENV_FILE 指向空文件）、
# 启动前清掉会让自带模型不可用的 11 个变量；测试用密钥每次启动随机生成，厂商 Key 只用占位串。
# 用法：bash backend-iso.sh <仓库根> <数据目录> [端口，默认 8097] [小说工坊 1/0，默认 1]
set -u
ROOT="${1:?repo root}"; DATA="${2:?data dir}"; PORT="${3:-8097}"; NOVEL="${4:-1}"
mkdir -p "$DATA/uploads" "$DATA/studio" "$DATA/songs" && : > "$DATA/empty.env"
cd "$ROOT/backend" || exit 1
export FIONA_ENV_FILE="$DATA/empty.env" DEV_MODE=1
export DASHSCOPE_API_KEY=sk-placeholder-verify-only DEEPSEEK_API_KEY=sk-placeholder-verify-only
export JWT_SECRET="verify-only-$(python3 -c 'import secrets; print(secrets.token_hex(24))')"
export FIONA_BYOK_SECRET="$(python3 -c 'import base64, secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())')"
export FIONA_DB_PATH="$DATA/fiona.db" FIONA_UPLOADS_DIR="$DATA/uploads" FIONA_STUDIO_DIR="$DATA/studio" FIONA_SONG_DIR="$DATA/songs"
export FIONA_STUDIO_OWNERS=tester FIONA_STUDIO_REQUIRE_JWT=0
if [ "$NOVEL" = "1" ]; then export FIONA_NOVEL=1 FIONA_NOVEL_USERS=tester; fi
export NO_PROXY="${NO_PROXY//[\[\]]/}" no_proxy="${no_proxy//[\[\]]/}"
exec env -u OPENAI_ORG_ID -u OPENAI_PROJECT_ID -u OPENAI_CUSTOM_HEADERS -u OPENAI_BASE_URL \
  -u ANTHROPIC_BASE_URL -u ANTHROPIC_AUTH_TOKEN -u ANTHROPIC_PROFILE -u ANTHROPIC_FEDERATION_RULE_ID \
  -u ANTHROPIC_IDENTITY_TOKEN -u ANTHROPIC_IDENTITY_TOKEN_FILE -u ANTHROPIC_CUSTOM_HEADERS \
  .venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port "$PORT"
