import { request } from '../request';

/** ==================== 涨停股池（热门个股） API ==================== */

/** get limit-up stock list (paginated) */
export function fetchGetLimitUpList(params: Api.StockLimitUp.LimitUpListParams) {
  return request<Api.Common.PaginatingQueryRecord<Api.StockLimitUp.LimitUpStockItem>>({
    url: '/admin/stock/limit-up/list',
    method: 'get',
    params
  });
}

/** get limit-up stats */
export function fetchGetLimitUpStats(date?: string | null) {
  return request<Api.StockLimitUp.LimitUpStats>({
    url: '/admin/stock/limit-up/stats',
    method: 'get',
    params: { date: date || undefined }
  });
}

/** get available limit-up dates */
export function fetchGetLimitUpDates() {
  return request<string[]>({
    url: '/admin/stock/limit-up/dates',
    method: 'get'
  });
}

/** manually trigger limit-up sync */
export function fetchSyncLimitUp() {
  return request<{ fetched: number; saved: number; broken: number }>({
    url: '/admin/stock/limit-up/sync',
    method: 'post'
  });
}
