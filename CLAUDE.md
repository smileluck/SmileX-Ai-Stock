# CLAUDE.md

@AGENTS.md


<!-- smilex-memory-guide -->
## 长期记忆(SmileX Memory MCP)

本项目已接入 SmileX 记忆服务,工具前缀 `mcp__smilex-memory__`:

- **回答涉及项目事实、历史决策、个人偏好的问题前**,先调 `memory_recall(query)` 获取上下文
- **任务完成或得到新结论后**,调 `memory_write(content, entities?, relations?)` 沉淀
- 首次接触本项目时调 `memory_init_project(name)` 完成冷启动
- 同一对话内保持相同 session_id(默认 "default")
