#!/bin/bash
# 每天跑一次：对话超过 TRIGGER 条，就压成一篇摘要笔记再裁到 KEEP 条。
# 压缩要写 SQLite，所以执行期间会短暂停掉机器人（几秒）。
#
# 必填环境变量：
#   UMO      会话 UMO，例如 wechat:FriendMessage:xxxx@im.wechat
#   DB       data_v4.db 的宿主机路径
#   NOTE_DIR 摘要笔记落盘的目录
# 可选：
#   TRIGGER  超过多少条才压（默认 90）
#   KEEP     压完保留多少条（默认 50）
#   CONTAINER 容器名（默认 astrbot，设为空字符串则不重启容器）

set -e
: "${UMO:?需要设置 UMO}"
: "${DB:?需要设置 DB}"
: "${NOTE_DIR:?需要设置 NOTE_DIR}"
TRIGGER=${TRIGGER:-90}
KEEP=${KEEP:-50}
CONTAINER=${CONTAINER-astrbot}
HERE=$(cd "$(dirname "$0")" && pwd)

CNT=$(python3 - "$DB" "$UMO" <<'PY'
import json, sqlite3, sys
db, umo = sys.argv[1], sys.argv[2]
con = sqlite3.connect(db)
row = con.execute(
    "SELECT content FROM conversations WHERE user_id=? ORDER BY updated_at DESC LIMIT 1",
    (umo,),
).fetchone()
print(len(json.loads(row[0])) if row and row[0] else 0)
PY
)

echo "$(date '+%F %T') 当前 $CNT 条"
if [ "$CNT" -lt "$TRIGGER" ]; then
  echo "不到 $TRIGGER 条，跳过"
  exit 0
fi

if [ -n "$CONTAINER" ]; then
  docker stop "$CONTAINER" >/dev/null
fi
python3 "$HERE/compact_history.py" --db "$DB" --umo "$UMO" --note-dir "$NOTE_DIR" \
  --keep "$KEEP" --trigger "$TRIGGER" --apply
if [ -n "$CONTAINER" ]; then
  docker start "$CONTAINER" >/dev/null
fi
echo "$(date '+%F %T') 完成"
