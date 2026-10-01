import { enableStatusToBoolean } from '@/utils/status';
import { request } from '../request';

/** ==================== MCP 服务管理 API ==================== */

/** 获取 MCP 服务分页列表 */
export function fetchGetMcpServerList(params?: Api.McpServer.QueryParams) {
  const { enabled, ...rest } = params ?? {};
  return request<Api.McpServer.ServerList>({
    url: '/admin/mcp-server/list',
    method: 'get',
    params: {
      ...rest,
      enabled: enabled === null || enabled === undefined ? undefined : enableStatusToBoolean(enabled)
    }
  });
}

/** 新增 MCP 服务 */
export function fetchCreateMcpServer(data: Api.McpServer.CreatePayload) {
  return request<Api.McpServer.Server>({
    url: '/admin/mcp-server/add',
    method: 'post',
    data
  });
}

/** 更新 MCP 服务（部分字段，code 不可改） */
export function fetchUpdateMcpServer(id: number, data: Api.McpServer.UpdatePayload) {
  return request<Api.McpServer.Server>({
    url: `/admin/mcp-server/${id}`,
    method: 'put',
    data
  });
}

/** 启用/停用 MCP 服务 */
export function fetchUpdateMcpServerStatus(id: number, enabled: boolean) {
  return request<Api.McpServer.Server>({
    url: `/admin/mcp-server/${id}/status`,
    method: 'put',
    data: { enabled }
  });
}

/** 删除 MCP 服务 */
export function fetchDeleteMcpServer(id: number) {
  return request<null>({
    url: `/admin/mcp-server/${id}`,
    method: 'delete'
  });
}

/** MCP 服务连通性测试 */
export function fetchTestMcpServer(id: number) {
  return request<Api.McpServer.TestResult>({
    url: `/admin/mcp-server/${id}/test`,
    method: 'post'
  });
}

/** 获取 MCP 服务工具列表 */
export function fetchGetMcpServerTools(id: number) {
  return request<Api.McpServer.ToolItem[]>({
    url: `/admin/mcp-server/${id}/tools`,
    method: 'get'
  });
}
