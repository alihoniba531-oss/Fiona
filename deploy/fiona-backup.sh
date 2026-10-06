#!/bin/sh
# 与后端使用同一个账号运行，避免在在线 WAL 库旁生成不同属主的侧文件。
set -eu
umask 077

db_path=${FIONA_DB_PATH:-/var/lib/fiona/fiona.db}
uploads_dir=${FIONA_UPLOADS_DIR:-/var/lib/fiona/uploads}
backup_dir=${FIONA_BACKUP_DIR:-/var/backups/fiona}
retention_days=${FIONA_BACKUP_RETENTION_DAYS:-14}

case "$retention_days" in
    ''|*[!0-9]*) echo '备份保留天数必须是正整数' >&2; exit 2 ;;
esac
if [ "$retention_days" -lt 1 ]; then
    echo '备份保留天数必须是正整数' >&2
    exit 2
fi
retention_days=$(expr "$retention_days" + 0)
if [ ! -f "$db_path" ] || [ ! -d "$uploads_dir" ]; then
    echo '数据库或上传目录不存在，备份未执行' >&2
    exit 2
fi
# GNU 和 BSD stat 的格式不同；只读属主检查，不能用 root 绕过服务账号。
db_owner=$(stat -c '%u' "$db_path" 2>/dev/null) || db_owner=$(stat -f '%u' "$db_path")
if [ "$db_owner" != "$(id -u)" ]; then
    echo '请使用数据库属主账号运行备份，避免生成异属主 WAL 侧文件' >&2
    exit 2
fi

mkdir -p "$backup_dir"
backup_dir=$(cd "$backup_dir" && pwd -P)
uploads_dir=$(cd "$uploads_dir" && pwd -P)
db_name=$(basename "$db_path")
db_parent=$(dirname "$db_path")
db_path=$(cd "$db_parent" && pwd -P)/$db_name
stamp=$(date -u '+%Y%m%dT%H%M%SZ')-$$
db_backup=$backup_dir/fiona-db-$stamp.sqlite3
uploads_backup=$backup_dir/fiona-uploads-$stamp.tar.gz
db_temp=$backup_dir/.fiona-db-$stamp.tmp
uploads_temp=$backup_dir/.fiona-uploads-$stamp.tmp
published=0
cleanup() {
    rm -f "$db_temp" "$db_temp-wal" "$db_temp-shm" "$uploads_temp"
    if [ "$published" -eq 0 ]; then
        rm -f "$db_backup" "$uploads_backup"
    fi
}
trap cleanup EXIT
trap 'exit 1' HUP INT TERM

# .backup 目标只用生成的安全文件名；路径中的空格/引号由 shell 的 cd 处理。
(cd "$backup_dir" && sqlite3 "$db_path" ".backup '.fiona-db-$stamp.tmp'")
# 快照转为独立的非 WAL 文件，避免移动主文件后遗漏快照自己的侧文件。
sqlite3 "$db_temp" 'PRAGMA journal_mode=DELETE;' >/dev/null
if [ "$(sqlite3 "$db_temp" 'PRAGMA integrity_check;')" != 'ok' ]; then
    echo '备份数据库完整性检查失败' >&2
    exit 1
fi
# 固定 uploads/ 前缀；源目录可重命名，恢复时仍能明确 strip-components=1。
mkdir "$backup_dir/.fiona-media-$stamp"
media_stage=$backup_dir/.fiona-media-$stamp
trap 'cleanup; rm -rf "$media_stage"' EXIT
ln -s "$uploads_dir" "$media_stage/uploads"
tar_status=0
# macOS tar 否则会自动生成 ._* AppleDouble 条目，绕过源文件排除规则。
COPYFILE_DISABLE=1 tar -czhf "$uploads_temp" --exclude='.*' -C "$media_stage" uploads || tar_status=$?
case "$tar_status" in
    0)
        chmod 600 "$db_temp" "$uploads_temp"
        mv "$db_temp" "$db_backup"
        mv "$uploads_temp" "$uploads_backup"
        published=1
        ;;
    1)
        # 在线上传可能在遍历时变化，完整的数据库快照仍是可用的恢复点。
        chmod 600 "$db_temp"
        mv "$db_temp" "$db_backup"
        published=1
        echo '警告：媒体打包期间文件被修改或删除；数据库快照已保存，媒体备份可能不完整，请重新备份媒体' >&2
        if [ -f "$uploads_temp" ]; then
            chmod 600 "$uploads_temp"
            mv "$uploads_temp" "$uploads_backup"
        fi
        ;;
    *)
        echo '媒体打包失败，本次备份未发布' >&2
        exit "$tar_status"
        ;;
esac

# -mtime 使用完整的 24 小时；+N-1 删除达到 N 天的历史备份。
older_than=$((retention_days - 1))
find "$backup_dir" -maxdepth 1 -type f \( -name 'fiona-db-*.sqlite3' -o -name 'fiona-uploads-*.tar.gz' \) \
    -mtime +"$older_than" -exec rm -f {} +
if [ "$tar_status" -eq 1 ]; then
    echo '备份以失败状态结束：请核对媒体备份并重新执行' >&2
    exit 1
fi
printf '备份完成：%s\n' "$stamp"
