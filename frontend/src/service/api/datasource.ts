import { request } from '../request';

/** ==================== 数据源管理 API ==================== */

/** 获取数据源列表（含 FQGate 网关配置） */
export function fetchGetDataSourceList() {
  return request<Api.DataSource.SourceListData>({
    url: '/admin/datasource/list',
    method: 'get'
  });
}

/** 更新数据源限流/熔断配置 */
export function fetchUpdateDataSourceConfig(data: Api.DataSource.ConfigUpdatePayload) {
  return request<Api.DataSource.SourceConfig>({
    url: '/admin/datasource/config/update',
    method: 'post',
    data
  });
}

/** 更新 FQGate 网关地址 */
export function fetchUpdateFqgateConfig(baseUrl: string) {
  return request<Api.DataSource.FqgateGateway>({
    url: '/admin/datasource/fqgate/config',
    method: 'post',
    data: { base_url: baseUrl }
  });
}

/** 获取近 N 天按小时聚合的用量统计 */
export function fetchGetDataSourceStats(days = 7) {
  return request<Api.DataSource.StatRecord[]>({
    url: '/admin/datasource/stats',
    method: 'get',
    params: { days }
  });
}

/** 获取数据源失败事件，source 为空时返回全部源 */
export function fetchGetDataSourceEvents(source?: string) {
  return request<Api.DataSource.EventRecord[]>({
    url: '/admin/datasource/events',
    method: 'get',
    params: { source: source || undefined }
  });
}

/** FQGate 网关连通性测试 */
export function fetchTestFqgateGateway() {
  return request<Api.DataSource.FqgateTestResult>({
    url: '/admin/datasource/fqgate/test',
    method: 'post'
  });
}
