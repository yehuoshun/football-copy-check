#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抖音足球文案查重工具

功能:
  1. 查重:输入新文案,与本地文案库比对,输出相似度与命中条目
  2. 入库:查重通过后把文案写入文案库

用法:
  python3 check.py "要查重的文案"
  python3 check.py --add "新文案" --match "英超 阿森纳vs曼城" [--source 豆包]
  python3 check.py --list            # 列出库里所有文案
  python3 check.py --stats           # 统计条数/覆盖赛事

阈值参考:
  >= 0.80  高风险,建议重写
  0.60~0.79 中风险,建议修改措辞
  <  0.60  安全
"""
import argparse
import json
import re
import sys
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

DATA_FILE = Path(__file__).parent / "data" / "copywriting.jsonl"

HIGH = 0.80
MED = 0.60


def normalize(text: str) -> str:
    """去掉标点/空白/大小写影响,只留中英文+数字"""
    text = re.sub(r"[\s\u3000]+", "", text)
    text = re.sub(r"[^\w\u4e00-\u9fff]", "", text)
    return text.lower()


def char_ngrams(text: str, n: int = 3) -> set:
    if len(text) <= n:
        return {text}
    return {text[i:i + n] for i in range(len(text) - n + 1)}


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def similarity(a: str, b: str) -> float:
    """取 n-gram Jaccard 与编辑相似度的最大值"""
    na, nb = normalize(a), normalize(b)
    if not na or not nb:
        return 0.0
    j = jaccard(char_ngrams(na), char_ngrams(nb))
    r = SequenceMatcher(None, na, nb).ratio()
    return max(j, r)


def load_records():
    if not DATA_FILE.exists():
        return []
    with DATA_FILE.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def save_record(rec):
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with DATA_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def do_check(text: str, records, detail: bool = False):
    hits = []
    for rec in records:
        s = similarity(text, rec["text"])
        if s >= MED:
            hits.append((s, rec))
    hits.sort(key=lambda x: x[0], reverse=True)
    if not hits:
        print(f"相似度: 全部 < {MED:.0%},安全 ✅")
        return 0
    worst = hits[0][0]
    level = "高风险 🔴" if worst >= HIGH else "中风险 🟡"
    print(f"最高相似度: {worst:.0%} ({level})")
    for s, rec in hits[:5]:
        print(f"  {s:.0%} | {rec.get('match','?')} | {rec.get('date','?')}")
        if detail:
            print(f"    -> {rec['text']}")
    return 1


def main():
    ap = argparse.ArgumentParser(description="抖音足球文案查重")
    ap.add_argument("text", nargs="?", help="要查重的文案")
    ap.add_argument("--add", action="store_true", help="查重通过后入库")
    ap.add_argument("--match", default="", help="赛事/主题标签,如:英超 阿森纳vs曼城")
    ap.add_argument("--source", default="", help="文案来源:豆包/懂球帝/自写")
    ap.add_argument("--detail", action="store_true", help="显示命中文案全文")
    ap.add_argument("--force", action="store_true", help="中风险也强制入库")
    ap.add_argument("--list", action="store_true", help="列出全部文案")
    ap.add_argument("--stats", action="store_true", help="统计概览")
    args = ap.parse_args()

    records = load_records()

    if args.list:
        for i, rec in enumerate(records, 1):
            print(f"{i}. [{rec.get('date','')}] {rec.get('match','')} | {rec['text']}")
        print(f"共 {len(records)} 条")
        return
    if args.stats:
        matches = {}
        for rec in records:
            m = rec.get("match", "未标注")
            matches[m] = matches.get(m, 0) + 1
        print(f"文案总数: {len(records)}")
        for m, c in sorted(matches.items(), key=lambda x: -x[1]):
            print(f"  {m}: {c} 条")
        return
    if not args.text:
        ap.print_help()
        return

    do_check(args.text, records, args.detail)

    if args.add:
        worst = max((similarity(args.text, r["text"]) for r in records), default=0.0)
        if worst >= HIGH:
            print(f"❌ 未入库:最高相似度 {worst:.0%} 超过高风险阈值 {HIGH:.0%}")
            sys.exit(1)
        if worst >= MED and not args.force:
            print(f"⚠️ 相似度 {worst:.0%} 达中风险,仍要入库请加 --force")
            sys.exit(1)
        rec = {
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "match": args.match,
            "source": args.source,
            "text": args.text,
        }
        save_record(rec)
        print(f"✅ 已入库 #{len(records) + 1}")


if __name__ == "__main__":
    main()