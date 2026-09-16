<!-- last-updated: 2026-09-15 -->
# aiDoc

`aiDoc/` 是本仓库的结构化 AI 文档层，用于把长期有效的项目上下文从工具目录中抽离出来，并按主题拆分成可维护的约束文档。

## 使用方式

1. `AGENTS.MD` 已随根 `CLAUDE.md @AGENTS.md` 自动加载（L0），始终生效
2. 接到任务先查本文件的「任务→必读文档」路由表，确定必读（L1）
3. 不清楚某个文档讲什么时，再翻「常用入口」字典（L1）
4. 按路由表打开 `aiDoc/` 下具体子文档深读（L2）

不再把项目级规则复制到工具私有目录；Claude Code 走 `@import`，Trae 等走薄适配指针（见 `AGENTS.MD` 的「各工具加载方式」）。

> 路由表 = 按任务导航；常用入口 = 按文档查字典。两者分工，避免维护漂移。

## 目录说明

- `relations/`: 仓库结构、技术栈、依赖关系、开发流程；`code-index.md` 为机器产物
- `modules/`: 跨组件架构规则、后端分层规则、模块/插件/MCP/i18n 专题
- `contracts/`: 前后端契约与字段类型约束
- `frontend/`: 前端规范、工具函数复用规则
- `examples/`: 讲解型示例，告诉 AI 每一层应该按什么标准组织和书写
- `memory/`: AI 记忆层，拆分为长期记忆、业务记忆与经验记忆（lessons）
- `notes/`: 决策记录（非平凡决策的动机、结论与后果）
- `plans/`: 变更计划与交接文档（active/completed）

## 常用入口

- `relations/repo-profile.md`: 项目定位、技术栈、核心特性
- `relations/development-workflow.md`: 开发流程、分支与提交规范
- `relations/system-map.md`: 系统架构与组件关系
- `relations/code-index.md`: 机器生成的代码索引（组件清单、语言构成、命令索引，勿手改）
- `modules/architecture-rules.md`: 跨组件架构规则与各组件范式归属
- `modules/backend-layer-rules.md`: 后端分层、统一响应、错误码约束
- `modules/module-development.md`: 后端/前端模块开发流程
- `modules/mcp-guide.md`: MCP 工具平台使用指南（独立服务、工具开发、管理接口）
- `modules/plugin-development.md`: 插件开发与管理指南（生命周期、CLI、多租户集成）
- `modules/i18n.md`: 后端文案国际化规范
- `contracts/boundary.md`: 前后端契约与字段类型约束
- `frontend/frontend-rules.md`: 前端代码、状态、路由、样式规范
- `frontend/frontend-utils.md`: 工具函数的强制复用规则
- `examples/README.md`: 示例层总入口
- `memory/README.md`: 记忆层规则
- `memory/project-memory.md`: 记忆层总索引
- `memory/long-term/README.md`: 长期记忆规则
- `memory/business/README.md`: 业务需求记忆规则与需求索引
- `memory/lessons/README.md`: 经验记忆（踩坑/模式）采集与晋升纪律
- `notes/README.md`: 决策记录的写作时机、目录结构与维护纪律
- `plans/README.md`: 变更计划的建立时机、生命周期与交接规范

## 任务→必读文档 路由表

接到任务先按本表确定必读，再按需扩展（路径相对 `aiDoc/`）：

| 任务类型 | 必读文档 |
|---|---|
| 新建后端模块 / 新增后端接口 | `modules/module-development.md`、`modules/backend-layer-rules.md`、`examples/backend/*` |
| 新建前端页面 / 前端功能 | `modules/module-development.md`（前端部分）、`frontend/frontend-rules.md`、`frontend/frontend-utils.md`、`examples/frontend/*` |
| 前后端契约变更 / 字段对接 | `contracts/boundary.md`、`modules/backend-layer-rules.md`（响应/分页结构） |
| 跨组件架构判断 / 模块归属 | `modules/architecture-rules.md`、`relations/system-map.md` |
| MCP 工具开发 / 调用 | `modules/mcp-guide.md`、`modules/architecture-rules.md`（mcp-platform 边界） |
| 插件开发 / 多租户 | `modules/plugin-development.md`、`relations/system-map.md` |
| 项目结构 / 技术栈 / 依赖答疑 | `relations/repo-profile.md`、`relations/system-map.md`、`relations/code-index.md` |
| 开发流程 / 提交规范 / 分支 | `relations/development-workflow.md` |
| 数据库迁移 / 模型变更 | `modules/backend-layer-rules.md`（Model 层）、`relations/development-workflow.md`（迁移命令） |
| 后端文案国际化 | `modules/i18n.md` |
| 工具函数复用 / 不重复造轮子 | `frontend/frontend-utils.md`、`examples/frontend/utils-usage-example.md` |
| 看示例 / 不确定如何组织某层代码 | `examples/README.md` + 对应 `examples/backend/*` 或 `examples/frontend/*` |
| 用户提出新业务需求（任意） | `memory/business/TEMPLATE.md`、`memory/business/README.md`、`memory/project-memory.md`（必更新索引） |
| 跨任务长期偏好沉淀 | `memory/long-term/README.md` |
| 踩坑 / 可复用模式记录 | `memory/lessons/README.md`、`memory/lessons/TEMPLATE.md` |
| 非平凡决策的动机与结论 | `notes/README.md`、`notes/TEMPLATE.md` |
| 多步骤 / 跨组件变更的计划与交接 | `plans/README.md`、`plans/change-plan.TEMPLATE.md`、`plans/handoff.TEMPLATE.md` |
| 权限 / 数据范围 / 多租户相关 | `modules/plugin-development.md`、`contracts/boundary.md`（status 桥接）、`memory/business/` 中相关历史记录 |

## 维护原则

- 稳定规则放这里，不放到工具私有目录里
- 临时会话草稿不要入库，只有变成长期知识时才记录
- 适用于所有 AI 的项目级规则，先写进 `AGENTS.MD`
- 细节说明再拆到 `aiDoc/` 对应子目录
- 新增/删除 `aiDoc/` 子文档时，必须同步更新本文件「常用入口」与路由表，否则等于未入库
- 只要用户提出业务需求，就要同步更新 `memory/business/`
