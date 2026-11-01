#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""记忆遗忘体检：按「强度 × 半衰期」算哪些记忆该淡出，把它们搬进归档表（不删除）。

配合 angel_memory 使用（读取它的 simple_memory.db）。如果你的记忆插件表结构不同，
改 --table / --archive-table 两个参数即可。

用法：
  python audit_forget.py --db simple_memory.db            # 只看
  python audit_forget.py --db simple_memory.db --apply    # 搬进归档
"""

import argparse
import shutil
import sqlite3
import sys
import time

HARD_KEYWORDS = (
    "生日", "名字", "叫", "称呼", "住在", "家乡", "老家", "工作", "学校",
    "专业", "大学", "过敏", "忌口", "不吃", "家人", "妈妈", "爸爸",
)
DAY = 86400.0

COLUMNS = [
    "id", "memory_type", "judgment", "reasoning", "strength", "is_active",
    "useful_count", "useful_score", "last_recalled_at", "last_decay_at",
    "memory_scope", "created_at", "updated_at",
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True, help="angel_memory 的 simple_memory.db")
    ap.add_argument("--table", default="memory_records")
    ap.add_argument("--archive-table", default="memory_archive")
    ap.add_argument("--min-score", type=float, default=2.0, help="折算分低于它才考虑归档")
    ap.add_argument("--min-idle-days", type=float, default=30.0, help="至少多少天没被提起")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    con = sqlite3.connect(args.db)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute(f"SELECT * FROM {args.table}")]
    now = time.time()

    plan = []
    for r in rows:
        text = str(r.get("judgment") or "")
        idle = (now - float(r.get("last_recalled_at") or r.get("created_at") or now)) / DAY
        if any(k in text for k in HARD_KEYWORDS):
            continue  # 硬事实永不归档
        half = 7 if r.get("memory_type") == "事件记忆" else 30
        score = float(r.get("strength") or 0) * (0.5 ** (idle / half))
        if score < args.min_score and idle > args.min_idle_days:
            plan.append((r, idle, score))

    print(f"总数 {len(rows)}，该淡出的 {len(plan)}")
    for r, idle, score in sorted(plan, key=lambda x: x[2])[:10]:
        print(f"  {idle:.0f} 天没提，强度 {r['strength']} 折算 {score:.1f}  {str(r['judgment'])[:40]}")

    if not args.apply:
        print("\n（试运行；加 --apply 才搬进归档）")
        return 0
    if not plan:
        return 0

    backup = args.db + ".bak_" + time.strftime("%Y%m%d_%H%M%S")
    shutil.copyfile(args.db, backup)
    print("已备份", backup)

    insert = (
        f"INSERT OR REPLACE INTO {args.archive_table} ({', '.join(COLUMNS)}, tags_json, closed_at, close_reason)"
        f" VALUES ({', '.join(['?'] * len(COLUMNS))}, ?, ?, ?)"
    )
    for r, idle, score in plan:
        con.execute(insert, [r[c] for c in COLUMNS] + ["[]", now, f"遗忘（{int(idle)} 天未提）"])
        con.execute("DELETE FROM memory_tag_rel WHERE memory_id=?", (r["id"],))
        con.execute(f"DELETE FROM {args.table} WHERE id=?", (r["id"],))
    con.commit()
    print("归档", len(plan), "条")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
