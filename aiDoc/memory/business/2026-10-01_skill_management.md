# Skills 管理（AI 助手技能包）

## 需求描述

新增 AI 技能包（Skill）管理：技能 = 名称 + 编码 + 描述 + 指令内容（提示词片段），
启用（status=启用）的技能按 sort 排序自动注入 Agent 对话的系统提示词，指导 LLM 按技能指令行事。
全栈交付：后端新模块 + 前端管理页 + 菜单/权限种子。

## 状态

已完成

## 涉及范围

### 后端

- 新表 `sys_skill`（name/code 唯一/content/description/status/sort），模型 `SysSkill` 放 `database/models/sys/`
- 新模块 `modules/skill/`（前缀 `/admin/skill`）：list（分页）/add/update/status/delete 五接口
- 权限码两段式：`skill:list`、`skill:manage`；错误处理沿用 mcpserver 模式（NotFoundError/ConflictError + i18n，未新增 CustomErrorCode 号段）
- `agent_service.py`：对话时在 MCP 动态工具注册后加载启用技能，以「已启用技能」段落拼入 system prompt（`## {name}（{description}）\n{content}`，sort 升序），加载失败不阻塞对话
- 迁移 `0052_add_skill.py`：建表 + 「环境配置」目录下菜单种子（菜单 8049，按钮 8050/8051，仅插菜单不分配角色）
- 顺带修复：0051 的 `SysMcpServer` 漏注册进 `alembic/env.py`（本次一并补 import，否则 autogenerate 会把 sys_mcp_server 当漂移表 drop）

### 前端

- 页面 `views/env-config/skill/`（index.vue + modules/skill-operate-drawer.vue，照搬同目录 mcp-server 页模式：内联搜索 + NDrawer 编辑 + NSwitch 行内启停）
- `typings/api/skill.d.ts`（Api.Skill）、`service/api/skill.ts`（fetch 前缀五函数，index.ts 导出）
- locales 双语：`route['env-config_skill']` + `page.manage.skill.*`；`typings/app.d.ts` I18n Schema 同步
- 路由由 elegant-router vite 插件自动重生成（dev server 监听，imports/routes/transform 三文件自动含 env-config_skill）

## 约束与备注

- status 走标准桥接：后端 bool → BaseRespEntity 自动序列化 "1"/"2"；前端搜索直接传 '1'/'2'（BoolField 解析），行内 NSwitch 提交布尔
- code 创建后不可改；正则 `^[a-z][a-z0-9_]{0,49}$` 前后端双校验
- 技能注入只作用于 Agent 聊天（agent_service），strategy/analysis 独立 prompt 不在范围
- FastAPI 拒绝空前缀+空路径，创建接口用 `/add`（沿用 0051 教训）

## 相关文件

- `backend/database/models/sys/skill.py`、`backend/alembic/versions/0052_add_skill.py`、`backend/alembic/env.py`
- `backend/modules/skill/{router.py,endpoints/skill.py,services/skill_service.py,schemas/skill.py}`、`backend/main.py`
- `backend/core/i18n/locales/{zh-CN,en-US}.yaml`（skill 段）
- `backend/modules/agent/services/agent_service.py`（技能注入）
- `frontend/src/views/env-config/skill/`、`frontend/src/service/api/skill.ts`、`frontend/src/typings/api/skill.d.ts`
- `frontend/src/locales/langs/{zh-cn,en-us}.ts`、`frontend/src/typings/app.d.ts`

## 记录日期

2026-10-01
