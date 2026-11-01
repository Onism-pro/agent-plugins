#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把老对话压成一页摘要笔记，然后只保留最近 N 条。

思路：上下文里的历史越长，每轮回复越慢越贵，而且注意力被稀释。
但直接删又会丢事——所以先让模型把「这段发生过什么、他这次说了自己的什么」
压成一页笔记，落进笔记目录，再从对话历史里裁掉原文。

用法：
  python compact_history.py --db data_v4.db --umo "$UMO" --note-dir notes/
  python compact_history.py ... --apply        # 真正写库（写之前请先停掉机器人）
"""

import argparse
import json
import os
import re
import sqlite3
import sys
import time
import urllib.request


def text_of(msg: dict) -> str:
    content = msg.get("content")
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                t = item.get("text", "")
                t = re.sub(r"<system_reminder>.*?</system_reminder>", "", t, flags=re.S)
                t = re.sub(r"<system_reminder>.*", "", t, flags=re.S)
                if t.strip():
                    parts.append(t.strip())
        return " ".join(parts)
    return str(content or "").strip()


SYSTEM = (
    "你在把一段旧聊天压成一页记忆。只做归纳，不要扮演，不要抒情。"
    "保留这几样：他这次说了自己的什么事、两人的约定或承诺、你的判断、情绪上真正重要的转折。"
    "丢掉寒暄、重复、已经过时的进度。"
    "写成 250 字以内的中文，不用第二人称，不要写日期以外的元信息，不许编。"
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True, help="AstrBot 的 data_v4.db")
    ap.add_argument("--umo", required=True, help="会话 UMO，例如 平台:FriendMessage:xxx")
    ap.add_argument("--note-dir", required=True, help="摘要笔记写到哪个目录")
    ap.add_argument("--keep", type=int, default=50, help="压缩后保留最近多少条")
    ap.add_argument("--trigger", type=int, default=90, help="超过多少条才开始压")
    ap.add_argument("--api-base", default=os.environ.get("MEMORY_KIT_API_BASE", "https://api.deepseek.com/v1"))
    ap.add_argument("--api-key", default=os.environ.get("MEMORY_KIT_API_KEY", ""))
    ap.add_argument("--model", default=os.environ.get("MEMORY_KIT_MODEL", "deepseek-chat"))
    ap.add_argument("--apply", action="store_true", help="真正写入；不加则只试运行")
    args = ap.parse_args()

    if not args.api_key:
        print("缺少 API key：用 --api-key 或环境变量 MEMORY_KIT_API_KEY")
        return 2

    con = sqlite3.connect(args.db)
    row = con.execute(
        "SELECT content FROM conversations WHERE user_id=? ORDER BY updated_at DESC LIMIT 1",
        (args.umo,),
    ).fetchone()
    if not row or not row[0]:
        print("这个会话没有历史")
        return 0

    history = json.loads(row[0])
    print("当前消息数", len(history))
    if len(history) < args.trigger:
        print(f"不到 {args.trigger} 条，不用压")
        return 0

    old, recent = history[: -args.keep], history[-args.keep:]
    lines = []
    for msg in old:
        t = text_of(msg)
        if not t:
            continue
        lines.append(("他：" if msg.get("role") == "user" else "你：") + t[:200])
    material = "\n".join(lines)
    print("要压缩", len(old), "条，文本", len(material), "字")
    if not material.strip():
        print("没有可压缩的正文")
        return 0

    payload = {
        "model": args.model,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": "这段对话（由旧到新）：\n" + material + "\n请压缩。"},
        ],
        "temperature": 0.3,
        "max_tokens": 500,
    }
    try:
        req = urllib.request.Request(
            args.api_base.rstrip("/") + "/chat/completions",
            data=json.dumps(payload).encode(),
            headers={"Authorization": "Bearer " + args.api_key, "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.load(resp)
        summary = str(data["choices"][0]["message"]["content"]).strip()
    except Exception as exc:
        print("摘要失败：", exc)
        return 1

    print("\n摘要：\n" + summary[:800])
    if not args.apply:
        print("\n（试运行；加 --apply 才写入，写入前请先停掉机器人）")
        return 0

    os.makedirs(args.note_dir, exist_ok=True)
    day = time.strftime("%Y-%m-%d")
    path = os.path.join(args.note_dir, f"过往 {day}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# 过往 {day}\n\n{summary}\n")

    con.execute(
        "UPDATE conversations SET content=? WHERE user_id=? AND updated_at="
        "(SELECT MAX(updated_at) FROM conversations WHERE user_id=?)",
        (json.dumps(recent, ensure_ascii=False), args.umo, args.umo),
    )
    con.commit()
    con.close()
    print("已写笔记", path, "；对话剩", len(recent), "条")
    return 0


if __name__ == "__main__":
    sys.exit(main())
