# LLM配置菜单移入「环境配置」目录

## 需求描述

应用户要求把「LLM配置」菜单从「AI助手」目录移动到根级「环境配置」目录下（继数据源管理之后第二个迁入项）。

## 状态

已完成

## 涉及范围

### 后端

- 迁移 `0048_move_ai_model_to_env_config.py`：sys_menu 菜单 2942406616007001 改 parent_id=2942406616008042（env-config CATALOG）、name `ai_model`→`env-config_model`、path `/ai/model`→`/env-config/model`、component `view.ai_model`→`view.env-config_model`、sort 11→80（排在数据源管理 sort=90 之前）
- 按钮行 2942406616007002-005 不动：name 仅展示用途，权限串 `sys:ai_model:*` 不变

### 前端

- 视图 `git mv src/views/ai/model → src/views/env-config/model`（dev server 的 elegant-router 插件自动重新生成 routes.ts/imports.ts/elegant-router.d.ts）
- 语言键 `route.ai_model` → `route.env-config_model`（zh-cn LLM配置 / en-us LLM Config）
- 视图无 defineOptions、无跨文件 import，移动零牵连

## 约束与备注

- 沿用 0046 的约束：挂在某目录下的菜单，其 i18n route 键类型由 elegant-router 从 src/views 目录结构生成，纯 DB 改名不过 typecheck，视图必须同步迁目录
- `pnpm typecheck` 通过（剩 10 个存量错误，均与本次无关）

## 相关文件

- `backend/alembic/versions/0048_move_ai_model_to_env_config.py`
- `frontend/src/views/env-config/model/`（原 `views/ai/model/`）
- `frontend/src/locales/langs/zh-cn.ts`、`en-us.ts`
- `frontend/src/router/elegant/{routes.ts,imports.ts}`、`frontend/src/typings/elegant-router.d.ts`（自动生成）

## 记录日期

2026-10-01
