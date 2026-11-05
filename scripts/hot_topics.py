#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""热点选题器：采集 → 去重 → 核实真实性 → 排序 → 取 top1

链路：
  1. 采集   web-search MCP 多路搜索（freshness=day），拿候选新闻
  2. 去重   标题字符 bigram 相似度聚类（同一件事的多家报道合成一簇）
  3. 核实   源数量 + 权威源命中 + 新鲜度 - 可疑词惩罚（传闻/据传/爆料）
  4. 排序   真实性 45% + 可写性 35% + 热度 20%
            ★ 可写性 = 过 football-copy-check 的题材闸（v59 维度1/4 的禁用落点）：
              比赛进程/进球量化/逆转/伤停名单/位置/奖项/身价 等直接归零 → 踢进「不可写」附录
  5. 取 top1 首选一条，另附备选与不可写清单

用法：
  python3 scripts/hot_topics.py                 # 默认，取 top1
  python3 scripts/hot_topics.py --top 5         # 看前 5
  python3 scripts/hot_topics.py --freshness week
  python3 scripts/hot_topics.py --json          # 只输出 JSON（给下游用）
"""
import argparse
import json
import re
import subprocess
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TMP = ROOT / "tmp"
# mcporter 默认从 ./config/mcporter.json 读配置，需显式指定（脚本可能在任意 cwd 跑）
MCP_CONFIG = Path.home() / ".openclaw" / "workspace" / "config" / "mcporter.json"

QUERIES = [
    "足球 今日热点",
    "足球 转会 最新消息",
    "足球 花边 球星 动态",
    "足球 争议 言论 回应",
    "足球 教练 管理层 新闻",
]

# 权威源（命中加权）
TRUSTED = {
    "hupu.com": 2, "dongqiudi.com": 2, "zhibo8.com": 2, "sina.com.cn": 2,
    "ppsport.com": 1, "163.com": 1, "qq.com": 1, "sohu.com": 1, "toutiao.com": 1,
}

# 记者/官媒署名（出现即视为可信线索）
RELIABLE_MARKERS = ["罗马诺", "here we go", "泰晤士", "天空体育", "回声报", "阿斯报",
                    "米兰体育报", "官方", "俱乐部宣布", "奥莱报", "ESPN"]

# 可疑词（传闻类，扣真实性分）
SUSPICIOUS = ["据传", "传闻", "疑似", "爆料", "网友", "小道消息", "网传", "据说"]

# 热度词
HOT_WORDS = ["热议", "热搜", "炸了", "内讧", "争执", "冲突", "怒", "炮轰", "回怼",
             "回应", "翻脸", "不满", "嘲讽", "球迷炸锅", "批评", "道歉"]

# 题材闸：硬禁（比赛进程/结果类）→ 可写性 0
# 注：比赛进程/比分只看【标题】（绝大多数新闻正文都会提到比分，拿正文判会全军覆没）
HARD_BAN_TITLE = {
    "赛报/比分": [r"\d+[-比]\d+", r"\d+比\d+", r"战报", r"不敌", r"击败",
                   r"战胜", r"逼平", r"惨案", r"血洗", r"大胜", r"完败", r"小胜"],
    "进球量化/制胜球": [r"帽子戏法", r"戴帽", r"梅开二度", r"绝杀", r"绝平", r"双响",
                        r"零封", r"制胜球", r"进球", r"破门", r"扳回一球", r"单场\d+球"],
    "逆转/进程": [r"逆转", r"翻盘", r"绝地", r"让\d+追\d+"],
}
# 题材闸：正文里出现也算硬禁的词（比分类，正文也不安全）——改为扣分而非一票毙，避免误杀
BODY_PENALTY = {
    "正文含进球量化词": [r"帽子戏法", r"戴帽", r"梅开二度", r"绝杀", r"绝平",
                       r"\d+射\d+传", r"单场\d+球"],
}
# 题材闸：软禁（可写但高风险，扣可写性）
SOFT_BAN = {
    "出场/伤停名单": [r"伤停", r"伤病", r"退出名单", r"征召", r"入选", r"首发",
                      r"替补", r"轮换", r"退出大名单"],
    "位置争议": [r"位置", r"右后卫", r"左后卫", r"中卫", r"改踢"],
    "奖项归属": [r"金球", r"最佳球员", r"MVP", r"颁奖", r"候选人"],
    "状态定性": [r"状态火", r"越踢越有", r"找回状态", r"表现神勇"],
    "强弱评判": [r"太弱", r"太强", r"不是一个档次", r"一边倒", r"换谁来"],
    "汇总/简讯类": [r"简讯", r"汇总", r"盘点", r"一览", r"速览", r"早知道", r"热点汇总"],
    "前瞻/看点罗列": [r"前瞻", r"看点", r"焦点战", r"赛前分析", r"赛事预览"],
}


def sh(cmd, timeout=90):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def search(query, freshness, count):
    """调 mcporter 走 web-search MCP，返回解析后的条目列表。"""
    r = sh(["mcporter", "call", "web-search.web_search",
            f"query={query}", f"freshness={freshness}", f"count={count}",
            "--output", "json", "--config", str(MCP_CONFIG)])
    if r.returncode != 0:
        print(f"  ⚠️ 搜索失败 [{query}]: {r.stderr.strip()[:120]}", file=sys.stderr)
        return []
    try:
        payload = json.loads(r.stdout)
        text = payload["content"][0]["text"]
    except Exception as e:
        print(f"  ⚠️ 解析失败 [{query}]: {e}", file=sys.stderr)
        return []
    return parse_markdown(text)


def parse_markdown(text, fallback_site=""):
    items, cur = [], None
    for line in text.splitlines():
        m = re.match(r"^### \[(\d+)\]\s*(.+)$", line.strip())
        if m:
            if cur:
                items.append(cur)
            cur = {"title": m.group(2).strip(), "site": fallback_site,
                   "url": "", "date": "", "body": []}
            continue
        if cur is None:
            continue
        s = line.strip()
        if s.startswith("**来源站点**"):
            cur["site"] = s.split(":", 1)[1].strip() if ":" in s else cur["site"]
        elif s.startswith("**来源URL**"):
            cur["url"] = s.split(":", 1)[1].strip() if ":" in s else ""
        elif s.startswith("**发布时间**"):
            cur["date"] = s.split(":", 1)[1].strip() if ":" in s else ""
        elif s.startswith("**内容详情**"):
            continue
        elif s and not s.startswith("---") and not s.startswith("**来源"):
            cur["body"].append(s)
    if cur:
        items.append(cur)
    for it in items:
        it["body"] = " ".join(it["body"])[:600]
    return items


def domain(url):
    m = re.search(r"https?://([^/]+)", url or "")
    if not m:
        return ""
    d = m.group(1).lower()
    return ".".join(d.split(".")[-2:]) if d.count(".") >= 1 else d


def ngrams(s, n=2):
    s = re.sub(r"[^\w\u4e00-\u9fff]", "", s)
    return {s[i:i + n] for i in range(max(len(s) - n + 1, 1))}


def sim(a, b):
    A, B = ngrams(a), ngrams(b)
    return len(A & B) / len(A | B) if (A or B) else 0.0


SITE_TAIL = re.compile(
    r"(\s*[-|｜_]\s*(虎扑社区|懂球帝|直播吧|新浪|腾讯|网易|搜狐|手机网易网|PP视频体育频道|"
    r"今日头条|国际足球|中国足球|足球话题区|体育|足球|百家号|网易号))+\s*$")


def clean_title(t):
    """只去末尾的「-站点/板块」尾巴（不能按连字符全切，否则会切坏中文人名里的「-」）。"""
    t = SITE_TAIL.sub("", t or "").strip()
    return t


def cluster(items):
    """同一件事的多家报道合成一簇：标题相似、正文相似，或共享一个「有辨识度」的四字串
    （如「德布劳内」「加布里埃尔」）。"""
    def four(s):
        s = re.sub(r"[^\w\u4e00-\u9fff]", "", s or "")
        return {s[i:i + 4] for i in range(max(len(s) - 3, 0))}

    toks = [four(clean_title(it["title"]) + " " + it.get("body", "")[:120]) for it in items]
    n = len(items)
    cnt = defaultdict(int)
    for t in toks:
        for g in t:
            cnt[g] += 1
    # 有辨识度 = 出现过（≥2）但不算烂大街（≤n 的 30%，至少 4）
    cap = max(3, int(0.15 * n))
    distinctive = {g: c for g, c in cnt.items() if 2 <= c <= cap}

    clusters = []
    for it, tk in zip(items, toks):
        t = clean_title(it["title"])
        sig_body = it.get("body", "")[:200]
        dt = {g for g in tk if g in distinctive}
        placed = False
        for c in clusters:
            if (sim(t, c["key"]) >= 0.35
                    or sim(sig_body, c["sig_body"]) >= 0.45
                    or len(dt & c["dtok"]) >= 2
                    or (len(dt & c["dtok"]) >= 1 and sim(t, c["key"]) >= 0.12)):
                c["items"].append(it)
                c["dtok"] |= dt
                placed = True
                break
        if not placed:
            clusters.append({"key": t, "title": it["title"], "sig_body": sig_body,
                             "dtok": dt, "items": [it]})
    return clusters


def days_old(datestr):
    m = re.search(r"(\d{4})[年\-/](\d{1,2})[月\-/](\d{1,2})", datestr or "")
    if not m:
        return 99
    try:
        d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        return (date.today() - d).days
    except ValueError:
        return 99


def writability(title, body):
    """返回 (可写性分, 硬禁原因[], 软禁原因[])。标题判进程，正文判细粒度进球词。"""
    reasons_hard, reasons_soft = [], []
    for name, pats in HARD_BAN_TITLE.items():
        if any(re.search(p, title) for p in pats):
            reasons_hard.append(name)
    for name, pats in BODY_PENALTY.items():
        if any(re.search(p, body) for p in pats):
            reasons_soft.append(name)
    for name, pats in SOFT_BAN.items():
        if any(re.search(p, title) for p in pats):
            reasons_soft.append(name)
    if reasons_hard:
        score = 0
    else:
        score = max(0, 100 - 30 * len(reasons_soft))
    return score, reasons_hard, reasons_soft


def score_cluster(c):
    items = c["items"]
    domains = {domain(i["url"]) for i in items if i["url"]}
    auth = sum(1 for d in domains if d in TRUSTED)
    fresh = min(days_old(i["date"]) for i in items)
    text = " ".join(clean_title(i["title"]) + " " + i["body"] for i in items)

    # 真实性
    real = 40 * min(len(domains), 4) / 4 + 40 * min(auth, 3) / 3
    real += 20 if fresh == 0 else (10 if fresh == 1 else 0)
    markers = [mk for mk in RELIABLE_MARKERS if mk in text]
    if markers:
        real += 15  # 记者署名/官媒线索
    pen = sum(10 for w in SUSPICIOUS if w in text)
    real = min(100, max(0, real - pen))

    # 热度
    heat = min(100, 20 * len({w for w in HOT_WORDS if w in text}))

    # 可写性
    writ, hard, soft = writability(clean_title(c["title"]), text)

    total = 0.45 * real + 0.35 * writ + 0.20 * heat
    c.update({
        "n_sources": len(domains), "auth_sources": auth, "fresh_days": fresh,
        "real": round(real), "heat": round(heat), "writ": writ,
        "hard_ban": hard, "soft_ban": soft, "total": round(total, 1),
        "domains": sorted(domains), "url": items[0]["url"], "body": items[0]["body"][:200],
        "markers": markers,
    })
    c.pop("dtok", None)
    c.pop("sig_body", None)
    return c


def main():
    ap = argparse.ArgumentParser(description="足球热点选题器（核实+排序+top1）")
    ap.add_argument("--freshness", default="day", help="day/week/month 或 YYYY-MM-DD..YYYY-MM-DD")
    ap.add_argument("--count", type=int, default=8, help="每路搜索条数")
    ap.add_argument("--top", type=int, default=1, help="首选几条")
    ap.add_argument("--json", action="store_true", help="只输出 JSON")
    args = ap.parse_args()

    raw = []
    for q in QUERIES:
        got = search(q, args.freshness, args.count)
        if not args.json:
            print(f"  采集 [{q}] → {len(got)} 条", file=sys.stderr)
        raw.extend(got)

    seen, uniq = set(), []
    for it in raw:
        k = clean_title(it["title"])
        if k and k not in seen:
            seen.add(k)
            uniq.append(it)

    clusters = [score_cluster(c) for c in cluster(uniq)]
    clusters.sort(key=lambda c: -c["total"])

    writable = [c for c in clusters if c["writ"] > 0]
    banned = [c for c in clusters if c["writ"] == 0]

    result = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "freshness": args.freshness,
        "collected": len(raw), "clusters": len(clusters),
        "top": writable[:max(args.top, 1)], "backup": writable[max(args.top, 1):max(args.top, 1) + 3],
        "banned": [{"title": c["title"], "why": c["hard_ban"], "sources": c["n_sources"]}
                   for c in banned],
    }

    TMP.mkdir(exist_ok=True)
    (TMP / f"hot_topics_{date.today()}.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    def card(c, idx):
        soft = f" ⚠️软禁:{'/'.join(c['soft_ban'])}" if c["soft_ban"] else ""
        mk = f"｜署名线索:{'/'.join(c['markers'])}" if c.get("markers") else ""
        print(f"\n{'='*66}\n【#{idx}】{c['title']}")
        print(f"  总分 {c['total']} = 真实性 {c['real']}（{c['n_sources']} 源/权威 {c['auth_sources']}）"
              f" + 可写性 {c['writ']}{soft} + 热度 {c['heat']}   [{c['fresh_days']} 天前]")
        print(f"  源: {', '.join(c['domains'][:6])}{mk}")
        print(f"  链接: {c['url']}")
        print(f"  摘要: {c['body'][:160]}...")

    print(f"\n采集 {result['collected']} 条 → 聚成 {result['clusters']} 个选题"
          f"（可写 {len(writable)} / 硬禁 {len(banned)}）")
    print("\n" + "★" * 33 + " TOP1 " + "★" * 33)
    if writable:
        card(writable[0], 1)
    else:
        print("  ⚠️ 今日候选中没有可写的（全被题材闸毙掉），建议换 freshness=week 再放宽一档")
    if result["backup"]:
        print("\n--- 备选 ---")
        for i, c in enumerate(result["backup"], 2):
            card(c, i)
    if banned:
        print("\n--- 不可写（题材闸毙掉，附原因）---")
        for c in banned[:6]:
            print(f"  ✗ {c['title'][:40]}  ← {'/'.join(c['hard_ban'])}（{c['n_sources']} 源）")
    print(f"\n完整 JSON: tmp/hot_topics_{date.today()}.json")


if __name__ == "__main__":
    main()