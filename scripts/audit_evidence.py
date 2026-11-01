#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""记忆审计：把最近几天的原文重放一遍，看哪些事实没进记忆库。只报告，不改数据。

回答的是这个问题：用户说「我明明讲过，你怎么忘了」——
到底是「原话本身没被规则命中」，还是「命中了却没存进去」。

用法：
  python audit_evidence.py --hot hot/ --db simple_memory.db --days 7
"""

import argparse
import difflib
import json
import os
import re
import sys
import time
import urllib.request


def norm(text: str) -> str:
    return re.sub(r"[^一-鿿A-Za-z0-9]", "", text or "")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hot", required=True, help="memory_rawlog 的 hot 目录")
    ap.add_argument("--db", required=True, help="记忆库 simple_memory.db")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--out-dir", default=".")
    ap.add_argument("--api-base", default=os.environ.get("MEMORY_KIT_API_BASE", "https://api.deepseek.com/v1"))
    ap.add_argument("--api-key", default=os.environ.get("MEMORY_KIT_API_KEY", ""))
    ap.add_argument("--model", default=os.environ.get("MEMORY_KIT_MODEL", "deepseek-chat"))
    ap.add_argument("--threshold", type=float, default=0.6, help="相似度低于它算漏记")
    args = ap.parse_args()

    if not args.api_key:
        print("缺少 API key：用 --api-key 或环境变量 MEMORY_KIT_API_KEY")
        return 2

    texts = []
    cutoff = time.time() - args.days * 86400
    if os.path.isdir(args.hot):
        for name in sorted(os.listdir(args.hot)):
            if not name.endswith(".jsonl"):
                continue
            with open(os.path.join(args.hot, name), encoding="utf-8") as fh:
                for line in fh:
                    try:
                        rec = json.loads(line)
                    except Exception:
                        continue
                    if float(rec.get("ts", 0)) < cutoff:
                        continue
                    t = str(rec.get("text", "")).strip()
                    if t:
                        texts.append(t)

    print("原文条数", len(texts))
    if not texts:
        print("没有原文，先攒几天")
        return 0

    material = "\n".join("- " + t[:200] for t in texts[-200:])[-9000:]
    system = (
        "你在做记忆审计。下面是一个人这几天说过的话。"
        "请只挑出「以后可能用得上、应该被记住」的明确事实：身份、属性、偏好、讨厌的东西、重要日期、正在做的事、约定。"
        "不要挑一次性的状态，不要猜。"
        '输出 JSON：{"facts":["事实一","事实二"]}，每条不超过二十字，最多十五条，没有就给空数组。'
    )
    payload = {
        "model": args.model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": "他这几天说过的话：\n" + material},
        ],
        "temperature": 0.2,
        "max_tokens": 600,
    }
    try:
        req = urllib.request.Request(
            args.api_base.rstrip("/") + "/chat/completions",
            data=json.dumps(payload).encode(),
            headers={"Authorization": "Bearer " + args.api_key, "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.load(resp)
        raw = str(data["choices"][0]["message"]["content"])
        match = re.search(r"\{.*\}", raw, re.S)
        facts = []
        if match:
            facts = [str(x).strip() for x in json.loads(match.group(0)).get("facts", []) if str(x).strip()]
    except Exception as exc:
        print("抽取失败：", exc)
        return 1

    import sqlite3

    con = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    known = [norm(r[0]) for r in con.execute("SELECT judgment FROM memory_records")]
    con.close()

    missing = []
    for fact in facts:
        nf = norm(fact)
        best = 0.0
        for nb in known:
            if not nb:
                continue
            if nf and nf in nb:
                best = 1.0
                break
            best = max(best, difflib.SequenceMatcher(None, nf, nb).ratio())
        if best < args.threshold:
            missing.append((fact, best))

    print(f"抽到事实 {len(facts)} 条，疑似漏记 {len(missing)} 条")
    for fact, score in missing:
        print(f"  · {fact}  (最高相似 {score:.2f})")

    day = time.strftime("%Y-%m-%d")
    os.makedirs(args.out_dir, exist_ok=True)
    path = os.path.join(args.out_dir, f"audit-{day}.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(f"# 记忆审计 {day}\n\n原文 {len(texts)} 条，抽出事实 {len(facts)} 条，疑似漏记 {len(missing)} 条。\n\n")
        if missing:
            fh.write("## 疑似漏记\n")
            for fact, score in missing:
                fh.write(f"- {fact}（最高相似 {score:.2f}）\n")
        else:
            fh.write("没有漏记。\n")
    print("报告写到", path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
