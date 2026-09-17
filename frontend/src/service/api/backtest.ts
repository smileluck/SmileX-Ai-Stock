import { request } from '../request';

/** ==================== AI 策略回测 API ==================== */

/** submit a backtest (async, returns the running record immediately) */
export function fetchRunBacktest(data: Api.Backtest.BacktestRunParams) {
  return request<Api.Backtest.BacktestItem>({
    url: '/admin/backtest/run',
    method: 'post',
    data
  });
}

/** run parameter sweep (sync, ≤27 combinations, not persisted) */
export function fetchRunBacktestSweep(data: Api.Backtest.BacktestSweepParams) {
  return request<Api.Backtest.BacktestSweepResult>({
    url: '/admin/backtest/sweep',
    method: 'post',
    data
  });
}

/** get backtest list (paginated, created_at desc) */
export function fetchGetBacktestList(params: {
  strategy_id?: number;
  status?: Api.Backtest.BacktestStatus;
  page: number;
  page_size: number;
}) {
  return request<Api.Common.PaginatingQueryRecord<Api.Backtest.BacktestItem>>({
    url: '/admin/backtest/list',
    method: 'get',
    params
  });
}

/** get backtest detail (result + equity curve) */
export function fetchGetBacktestDetail(backtestId: number) {
  return request<Api.Backtest.BacktestDetail>({
    url: `/admin/backtest/${backtestId}`,
    method: 'get'
  });
}

/** get backtest trade records (paginated, trade_date asc) */
export function fetchGetBacktestTrades(backtestId: number, params: { page: number; page_size: number }) {
  return request<Api.Common.PaginatingQueryRecord<Api.Backtest.BacktestTradeItem>>({
    url: `/admin/backtest/${backtestId}/trades`,
    method: 'get',
    params
  });
}

/** delete a backtest (soft; running records are rejected by the backend) */
export function fetchDeleteBacktest(backtestId: number) {
  return request<null>({
    url: `/admin/backtest/${backtestId}`,
    method: 'delete'
  });
}
