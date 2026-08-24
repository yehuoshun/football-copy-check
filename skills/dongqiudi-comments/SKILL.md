---
name: dongqiudi-comments
version: 1.0.0
description: |
  懂球帝文章评论区抓取工具。给定文章链接或 ID，全量获取评论区
  （用户名、点赞数、回复数、发布时间、评论文本），支持按赞/时间
  排序、点赞过滤、批量抓取。触发词：抓懂球帝评论、懂球帝评论区、
  球迷评论、看看这场的球迷反应。
category: content-media
tags:
  - 懂球帝
  - 足球
  - 评论
  - 抓取
author: agent
---

# 懂球帝评论区抓取

## 触发场景

- "抓懂球帝评论 + 文章链接"
- "看看这篇下面的球迷都怎么说"
- "批量拉某几场比赛的文章评论"

## 用法

```bash
# 单篇（裸 ID 或完整 URL 均可）
python3 scripts/fetch_comments.py 6225262

# 按点赞排序 + 过滤水评
python3 scripts/fetch_comments.py 6225049 --sort up --min-up 5

# 批量 + JSON 输出（适合下游分析）
python3 scripts/fetch_comments.py 6225262 6225049 --json
```

## 核心逻辑

1. **接口**：`api.dongqiudi.com/v2/article/{id}/comment?sort=down&version=600`，
   返回 `errCode=0` 时解析 `data.comment_list`（评论）与 `data.user_list`（用户名映射）
2. **游标翻页**：响应带 `data.next` 游标链接，循环请求直到翻尽，默认抓取约 40-50 条热门子集
3. **全量对账**：以第一页 `data.comment_total` 为官方总数，输出 `实抓/总数`，漏多少透明可见
4. **反爬规避**：内置浏览器 UA 轮换 + 请求间隔 0.5s + 失败重试 2 次（间隔 2s）

## 已知边界

- **接口只暴露热门/活跃评论子集**（实测 205 条总数只给 44 条），翻页到底也无法拿全量；
  对“球迷观点提炼/舆情”场景足够，对“全量导出”不足
- 被删除的评论用户名显示为“已删除评论”（user_id 99999999）
- 接口字段若变动，优先检查 `comment_list` / `comment_total` / `user_list` / `next` 四个 key
- 高频批量请加 `--json` 并人工控频，高频会触发 IP 限流