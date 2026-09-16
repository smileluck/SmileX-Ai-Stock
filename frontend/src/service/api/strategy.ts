import { request } from '../request';

/** ==================== AI 分析策略 API ==================== */

/** get strategy list (paginated) */
export function fetchGetStrategyList(params: {
  name?: string;
  status?: boolean;
  category?: string;
  page: number;
  page_size: number;
}) {
  return request<Api.Common.PaginatingQueryRecord<Api.Strategy.StrategyItem>>({
    url: '/admin/strategy/strategies',
    method: 'get',
    params
  });
}

/** create strategy */
export function fetchCreateStrategy(data: Api.Strategy.StrategySaveParams) {
  return request<Api.Strategy.StrategyItem>({
    url: '/admin/strategy/strategies',
    method: 'post',
    data
  });
}

/** update strategy */
export function fetchUpdateStrategy(strategyId: number, data: Api.Strategy.StrategySaveParams) {
  return request<Api.Strategy.StrategyItem>({
    url: `/admin/strategy/strategies/${strategyId}`,
    method: 'put',
    data
  });
}

/** delete strategy (soft) */
export function fetchDeleteStrategy(strategyId: number) {
  return request<null>({
    url: `/admin/strategy/strategies/${strategyId}`,
    method: 'delete'
  });
}

/** manually run a strategy once */
export function fetchRunStrategy(strategyId: number) {
  return request<Api.Strategy.StrategyRunResult>({
    url: `/admin/strategy/strategies/${strategyId}/run`,
    method: 'post'
  });
}

/** get strategy run history (paginated) */
export function fetchGetStrategyRuns(strategyId: number, params: { page: number; page_size: number }) {
  return request<Api.Common.PaginatingQueryRecord<Api.Strategy.StrategyRunItem>>({
    url: `/admin/strategy/strategies/${strategyId}/runs`,
    method: 'get',
    params
  });
}

/** get positions (paginated) */
export function fetchGetStrategyPositions(params: {
  strategy_id?: number;
  status?: Api.Strategy.PositionStatus;
  stock_code?: string;
  /** 建仓时间起，ISO 8601 */
  start_time?: string;
  /** 建仓时间止，ISO 8601 */
  end_time?: string;
  /** 排序列：buy_time/sell_time/pnl/return_rate */
  sort_by?: string;
  sort_desc?: boolean;
  page: number;
  page_size: number;
}) {
  return request<Api.Common.PaginatingQueryRecord<Api.Strategy.PositionItem>>({
    url: '/admin/strategy/positions',
    method: 'get',
    params
  });
}

/** manually trigger position tracking */
export function fetchTrackStrategyPositions() {
  return request<{ tracked: number; closed: number; total: number }>({
    url: '/admin/strategy/positions/track',
    method: 'post'
  });
}

/** close a position manually */
export function fetchCloseStrategyPosition(positionId: number, data: { price?: number; reason?: string }) {
  return request<Api.Strategy.PositionItem>({
    url: `/admin/strategy/positions/${positionId}/close`,
    method: 'post',
    data
  });
}

/** get position track logs */
export function fetchGetPositionTracks(positionId: number, limit = 100) {
  return request<Api.Strategy.TrackLogItem[]>({
    url: `/admin/strategy/positions/${positionId}/tracks`,
    method: 'get',
    params: { limit }
  });
}

/** get strategy return-rate stats */
export function fetchGetStrategyStats(strategyId?: number) {
  return request<Api.Strategy.StrategyStatsItem[]>({
    url: '/admin/strategy/positions/stats',
    method: 'get',
    params: { strategy_id: strategyId || undefined }
  });
}

/** clone a strategy (copy is disabled by default, name gets a （副本） suffix) */
export function fetchCloneStrategy(strategyId: number) {
  return request<Api.Strategy.StrategyItem>({
    url: `/admin/strategy/strategies/${strategyId}/clone`,
    method: 'post'
  });
}

/** publish a strategy as a template (tags overwrite when provided) */
export function fetchPublishStrategy(strategyId: number, data?: Api.Strategy.TemplatePublishParams) {
  return request<Api.Strategy.StrategyItem>({
    url: `/admin/strategy/strategies/${strategyId}/publish`,
    method: 'post',
    data
  });
}

/** unpublish a template */
export function fetchUnpublishStrategy(strategyId: number, data?: Api.Strategy.TemplatePublishParams) {
  return request<Api.Strategy.StrategyItem>({
    url: `/admin/strategy/strategies/${strategyId}/unpublish`,
    method: 'post',
    data
  });
}

/** get template market list (published templates + preset strategies, paginated) */
export function fetchGetStrategyTemplates(params: { page: number; page_size: number }) {
  return request<Api.Common.PaginatingQueryRecord<Api.Strategy.TemplateItem>>({
    url: '/admin/strategy/strategies/templates',
    method: 'get',
    params
  });
}

/** export a strategy as portable JSON (schema_version=1) */
export function fetchExportStrategy(strategyId: number) {
  return request<Api.Strategy.StrategyExportData>({
    url: `/admin/strategy/strategies/${strategyId}/export`,
    method: 'get'
  });
}

/** import a strategy from portable JSON (new strategy is disabled by default) */
export function fetchImportStrategy(data: Api.Strategy.StrategyImportParams) {
  return request<Api.Strategy.StrategyItem>({
    url: '/admin/strategy/strategies/import',
    method: 'post',
    data
  });
}
