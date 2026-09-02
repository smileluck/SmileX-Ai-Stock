import { request } from '../request';

/** ==================== 板块轮动分析 API ==================== */

/** get rotation overview (近期轮动板块总览) */
export function fetchGetRotationOverview(boardType: Api.StockRotation.BoardType = 'industry', days = 10) {
  return request<Api.StockRotation.RotationOverviewResponse>({
    url: '/admin/stock/rotation/overview',
    method: 'get',
    params: { board_type: boardType, days }
  });
}

/** get rotation switch signals (板块内高低切换信号) */
export function fetchGetRotationSwitch(boardType: Api.StockRotation.BoardType = 'industry', topN = 15) {
  return request<Api.StockRotation.RotationSwitchResponse>({
    url: '/admin/stock/rotation/switch',
    method: 'get',
    params: { board_type: boardType, top_n: topN }
  });
}

/** manually trigger board stock snapshot sync */
export function fetchSyncRotationStocks(conceptTop = 30) {
  return request<Api.StockRotation.RotationSyncResult>({
    url: '/admin/stock/rotation/sync_stocks',
    method: 'post',
    params: { concept_top: conceptTop }
  });
}

/** submit board history backfill (background task) */
export function fetchBackfillRotationHistory(boardType: Api.StockRotation.BackfillBoardType = 'all', days = 60) {
  return request<Api.StockRotation.RotationBackfillResult>({
    url: '/admin/stock/rotation/backfill',
    method: 'post',
    params: { board_type: boardType, days }
  });
}
