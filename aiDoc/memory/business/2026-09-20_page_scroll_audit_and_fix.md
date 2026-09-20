# 2026-09-20 全站页面滚动审计与修复（5 页面滚动失效）

## 需求

用户报告「AI分析-策略管理」等页面滚动没有反应，要求检查每个页面的滚动。

## 根因

本布局（SoybeanAdmin AdminLayout）页面级滚动容器是 `main#__SCROLL_EL_ID`，列表页采用「页面高度钉死视口 + 表格内部滚动」设计：页面根 `overflow-hidden` + 卡片 `sm:flex-1-hidden`。该设计成立的前提是高度链完整传递：

```
main(定高) → 页面根(flex-grow + overflow-hidden) → NCard(sm:flex-1-hidden) → .n-card__content(flex:1 1 0)
  → h-full 包裹层 → NDataTable(flex-1-hidden + :flex-height) → 表体内部滚动
```

断裂方式有两种：

1. **表格没配内部滚动**：表格直接放在卡片内容里、无 `flex-height`/`flex-1-hidden` 包裹 → 表格 min-content 撑破卡片，被 `overflow:hidden` 静默裁掉（无任何滚动条，滚轮无反应）。
2. **`.n-card__content` 的 `min-height:auto`**：flex 子项默认 min-height 为内容最小高度，即使 `flex:1 1 0` 也压不下去 → 内容超出卡片仍被裁。修法：卡片加 `content-style="min-height: 0"`（在 info/news 实测一加即复位）。

## 修复清单（8 文件）

| 页面 | 修法 |
|---|---|
| `ai/analysis` 策略管理 Tab | 表格+分页包进 `h-full flex-col-stretch`，表格加 `flex-1-hidden` + `:flex-height="!appStore.isMobile"`；NCard 加 `content-style="min-height: 0"` |
| `ai/backtest` 回测记录 | 同上 |
| `ai/factor` 因子库 Tab | NCard 加 `sm:h-full`；同上包裹表格；index.vue 深度选择器补 `.n-tab-pane { height: 100% }` 打通 pane 高度链 |
| `ai/factor` 因子试算/选股器 Tab | 模块根改 `h-full ... overflow-y-auto` 面板内整页滚动；结果卡 `sm:flex-1-hidden` → `flex-shrink-0` |
| `info/news` | 只需 NCard 加 `content-style="min-height: 0"`（原本模式就对，栽在 min-height:auto） |
| `a-stock/market-overview` | 网格卡片页不适用钉高模式；根改自然高度让 `main` 滚动（去掉 `h-full overflow-hidden`） |

## 审计方法（可复用）

浏览器逐页加载，几何探针判定：

- `main.scrollHeight - clientHeight > 0` → 页面可滚（正常）；
- 否则查找 `overflowY:hidden && scrollHeight>clientHeight` 的可见元素 → 死裁剪（bug）；
- 存在 `overflowY:auto/scroll && scrollHeight>clientHeight` 的元素 → 内部滚动正常。
- 注意排除表格自身的 `n-data-table-wrapper`/`n-data-table-base-table`（那是表格内部滚动机制，不是 bug）。

结论：除上述 5 页外其余页面（manage/*、log/*、scheduler/*、a-stock 其余、ai 其余、home/monitor/about）均正常；manage/* 是该模式的正确参照（表格 `sm:h-full` + `flex-height` + `remote` + 表内分页）。

## 契约

纯前端布局修复，无接口变更。typecheck 23 个错误均为存量（stash 对照 HEAD 一致）。
