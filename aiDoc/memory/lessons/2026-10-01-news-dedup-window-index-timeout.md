<!-- last-updated: 2026-10-01 -->
<!-- lesson-meta: status=pending count=1 post=0 target= -->
# 窗口函数去重缺配套索引导致列表接口超时

## 情境

用户反馈「资讯聚合无法加载数据」。后端 `NewsService.build_news_query`（`backend/modules/admin/services/sys/news_service.py`）用 `row_number() OVER (PARTITION BY title ...)` 对全表去重，表已 27.9 万行 / 293MB。

## 坑 / 模式

- 表象是「前端加载失败」，真因在后端慢查询：窗口函数按 `title` 全表排序，分页数据查询 ~9.6s + 分页 count ~9s，接口总耗时 ~20s，超出前端请求超时。后端日志里请求其实是 200，只是 `elapsed` 极大——查「前端加载失败」先看后端日志 elapsed，别只盯 status。
- 窗口函数 / DISTINCT ON 去重必须配与 partition/order 键一致的部分复合索引：`(title, published_at DESC NULLS LAST, id DESC) WHERE deleted_at IS NULL`，建索引后 9.6s → 0.44s（迁移 0047）。
- 新增任何「全表窗口/排序 + 分页」查询时，数据量上到十万级就会炸；写完即用真实数据量 EXPLAIN/计时验证。

## 出现次数

1

## 状态

pending

## 晋升去向

（待晋升）

## 晋升后复发

0

## 记录日期

2026-10-01
