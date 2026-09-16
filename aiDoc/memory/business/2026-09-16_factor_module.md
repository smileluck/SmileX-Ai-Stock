# 因子管理模块

## 需求描述

新建因子管理后端模块（`/admin/factor`）：公式因子 CRUD + 在线导入（URL/粘贴 JSON）+ 因子计算（日线 OHLCV）+ 多条件 AND 选股器（结果可存为策略股票池）。因子来源三类：预置开源公式因子（迁移种子 source=preset，不可删只可停用）、在线导入（imported）、手工自建（custom）。公式 DSL 用 Python ast 白名单安全求值，严禁 eval/exec。

## 状态

已完成（后端 + 前端页面）

## 涉及范围

### 后端

- 新模块 `backend/modules/factor/`（endpoints/services/schemas + router）
- DSL 求值器 `services/formula.py`：`validate_formula` 白名单校验 + `calc_factor_values` 两段式求值（每股 pandas rolling 时序 → RANK 截面归一化 pos/total ∈(0,1]，NaN 不参与）
- CRUD+导入 `services/factor_service.py`；计算/选股/存池 `services/factor_calc.py`
- 新表 `business_factor`（迁移 0034，17 条预置因子种子，固定 ID 段 2942406616009201-217，按 code 幂等）
- 行情复用 backtest `fetch_market_data`（`_BAR_FIELDS` 扩展 volume/amount，向后兼容）
- 错误码新段 11801-11805；权限复用 `strategy:manage`；i18n 双 yaml + error_codes.md 同步

### 前端

- `frontend/src/views/ai/factor/`：三 Tab（因子库 / 因子试算 / 选股器），路由 `ai_factor` → `/ai/factor`（elegant-router 自动生成）
- 因子库：分类/来源/关键字筛选分页、新建编辑抽屉（编辑禁改 code）、预置因子只可停用不可删、导入弹窗（URL/粘贴 JSON，展示 imported/skipped/errors 明细）
- 试算：因子+多代码（或从策略股票池带入）+目标日+回看天数 → /calc 结果表 + warnings
- 选股器：股票池（手动 codes / 策略股票池）+ 动态条件行（因子+运算符含前N名+数值）→ /screen，结果可一键「存为策略股票池」（/screen/save-pool 覆盖更新）
- typings `api/factor.d.ts`、api 函数 `service/api/factor.ts`、i18n `page.aiFactor.*` 双语 + app.d.ts 类型已同步
- status 用 boolean 直传（同 strategy 模块，无 "1"/"2" 桥接）；菜单项需后台手工新增指向 /ai/factor

## 约束与备注

- 选股不支持全市场：codes 与 strategy_id 必须且只能给一个（RequestError 400）
- top_n = 按因子值降序取前 N（value 须正整数）；多条件 AND
- 目标日 = ≤end_date 的最后一个交易日；每股截取末 lookback（默认 120，5..750）条 bar
- 北交所等 `is_supported_stock=False` 的代码跳过进 warnings
- 股票简称 best-effort 取自该代码最近一条 AI 信号的 stock_name，无则空串
- `POST /` 实际路径 `/admin/factor/`：FastAPI 拒绝「子路由空前缀+空路径」，用 `/` 兜底（`/admin/factor` 会 307 重定向，语义一致）
- 坑：Base 是 MappedAsDataclass，**无默认值列必须全部排在有默认值列之前**（formula 曾排在 default 的 category 后导致启动即 TypeError）
- 坑：当前 head 实为 17203a828aab（drift sync 迁移，0033 之后已 upgrade），0034 的 down_revision 指向它而非 0033

## 相关文件

- `backend/modules/factor/services/formula.py`（DSL 求值器）
- `backend/modules/factor/services/factor_service.py`、`factor_calc.py`
- `backend/modules/factor/endpoints/factor.py`、`router.py`、`schemas/factor.py`
- `backend/database/models/business/factor.py`
- `backend/alembic/versions/0034_add_factor_module.py`
- `backend/modules/backtest/services/market_data.py`（_BAR_FIELDS 扩展）
- `backend/core/response/response_code.py`、`backend/core/i18n/locales/{zh-CN,en-US}.yaml`、`error_codes.md`
- `aiDoc/contracts/boundary.md`（因子管理模块契约小节）

## 记录日期

2026-09-16
