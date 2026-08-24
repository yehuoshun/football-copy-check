#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""懂球帝文章评论区抓取器。

用法:
  python3 fetch_comments.py 6225262
  python3 fetch_comments.py https://www.dongqiudi.com/articles/6225262.html
  python3 fetch_comments.py 6225262 6225049 --limit 10 --min-up 5 --sort up

依赖: Python 3.8+（仅标准库 urllib）
"""
import argparse
import json
import re
import sys
import time
import urllib.request

UA_LIST = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
]
API_URL = "https://api.dongqiudi.com/v2/article/{}/comment?sort=down&version=600"


def parse_article_id(raw: str) -> str:
    """从完整 URL 或裸 ID 提取文章 ID。非数字且无 articles 路径则报错。"""
    m = re.search(r"articles/(\d+)\.html", raw)
    if m:
        return m.group(1)
    if raw.isdigit():
        return raw
    raise ValueError(f"无法解析文章 ID: {raw}")


def http_get(url: str, ua: str) -> str:
    """带 UA 的 GET，超时 30 秒。"""
    req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def fetch_comments(article_id: str, min_up: int = 0) -> dict:
    """沿 next 游标翻页，抓取接口公开的评论子集。
    返回 {article_id, total, fetched, comments}，fetched 为实抓条数。"""
    ua = UA_LIST[int(time.time()) % len(UA_LIST)]
    url = API_URL.format(article_id)
    comments, seen, users, total = [], set(), {}, None
    while url:
        for attempt in (1, 2):
            try:
                raw = http_get(url, ua)
                break
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(2)
        data = json.loads(raw)
        if data.get("errCode") != 0:
            raise RuntimeError("API 错误: {}".format(data.get("errMesg")))
        d = data["data"]
        if total is None:
            total = int(d.get("comment_total", 0))
        user_list = d.get("user_list")
        if user_list:
            users.update({u["id"]: u.get("username", "匿名") for u in user_list})
        for c in d.get("comment_list", []):
            cid = str(c.get("id"))
            if cid in seen:
                continue
            seen.add(cid)
            up = int(c.get("up", 0))
            if min_up and up < min_up:
                continue
            comments.append({
                "id": c.get("id"),
                "user": users.get(str(c.get("user_id")), "匿名"),
                "up": up,
                "created_at": c.get("created_at", ""),
                "reply_total": int(c.get("reply_total", 0)),
                "content": (c.get("content") or "").strip(),
            })
        nxt = d.get("next") or ""
        url = nxt if (nxt and nxt != url and "next=" in nxt) else None
        time.sleep(0.5)
    return {
        "article_id": article_id,
        "total": total if total is not None else len(comments),
        "fetched": len(comments),
        "comments": comments,
    }


def render(meta: dict, sort_key: str, limit: int) -> str:
    """格式化输出：按 sort_key 降序，最多 limit 条。"""
    lines = ["文章 {} 评论 {}/{} 条(接口公开子集 {})".format(
        meta["article_id"], len(meta["comments"]), meta["total"], meta.get("fetched", len(meta["comments"]))) ]
    cs = sorted(meta["comments"], key=lambda c: c[sort_key], reverse=True)
    for i, c in enumerate(cs[:limit], 1):
        lines.append("{}. [{}] 赞{} 回复{} {}".format(i, c["user"], c["up"], c["reply_total"], c["created_at"]))
        lines.append("   {}".format(c["content"]))
    return "\n".join(lines)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="懂球帝文章评论区抓取")
    ap.add_argument("ids", nargs="+", help="文章 ID 或 URL，可多个")
    ap.add_argument("--sort", choices=["up", "created_at"], default="up", help="排序字段")
    ap.add_argument("--limit", type=int, default=10, help="每篇最多输出条数")
    ap.add_argument("--min-up", type=int, default=0, help="只输出点赞不低于该值的评论")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出（批量推荐）")
    args = ap.parse_args(argv)
    results = []
    for raw in args.ids:
        try:
            aid = parse_article_id(raw)
            r = fetch_comments(aid, args.min_up)
            results.append(r)
            print(render(r, args.sort, args.limit))
        except Exception as e:
            print("[{}] 失败: {}".format(raw, e), file=sys.stderr)
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()