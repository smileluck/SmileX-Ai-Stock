# 「环境配置」目录新增 FQGate 演示外部页面

## 需求描述

应用户要求在「环境配置」目录下增加 FQGate 的外部页面 https://fqgate.github.io/demo/ 。

## 状态

已完成

## 涉及范围

### 后端

- 迁移 `0049_seed_fqgate_demo_menu.py`：sys_menu 新增 `env-config_fqgate`（id=2942406616008043，parent=env-config 目录 2942406616008042，path=/env-config/fqgate，component=view.env-config_fqgate，sort=85，permission=NULL 纯展示页无按钮行）

### 前端

- 新视图 `frontend/src/views/env-config/fqgate/index.vue`：iframe 内嵌 demo 页（仿 `_builtin/iframe-page/[url].vue` 写法）
- locale 键 `route.env-config_fqgate`（zh FQGate 演示 / en FQGate Demo）

## 约束与备注

- **未采用 meta_href 外链方案**：href 菜单 component 为 NULL，仅靠路由守卫 `window.open` 新标签打开；且 i18n 键 `route.<name>` 不在 elegant-router 生成的 I18nRouteKey 内（纯 DB 菜单无对应 views 目录），补 locale 键过不了 typecheck、不补则菜单显示原始键名。iframe 内嵌则视图目录存在、键合法（同 0046 约束）
- 已验证目标站无 X-Frame-Options / CSP frame-ancestors，可内嵌
- 菜单 ID 编排约定：0043 用至 ...8041、8042 为 env-config 目录，本菜单 8043

## 相关文件

- `backend/alembic/versions/0049_seed_fqgate_demo_menu.py`
- `frontend/src/views/env-config/fqgate/index.vue`
- `frontend/src/locales/langs/zh-cn.ts`、`en-us.ts`

## 记录日期

2026-10-01
