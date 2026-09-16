import { request } from '../request';

/** ==================== AI 因子管理 API ==================== */

/** get factor list (paginated, category/source/keyword filters) */
export function fetchGetFactorList(params: {
  category?: string;
  source?: Api.Factor.FactorSource;
  keyword?: string;
  page: number;
  page_size: number;
}) {
  return request<Api.Common.PaginatingQueryRecord<Api.Factor.FactorItem>>({
    url: '/admin/factor/list',
    method: 'get',
    params
  });
}

/** create a custom factor (source fixed to custom by the backend; note the trailing slash) */
export function fetchCreateFactor(data: Api.Factor.FactorCreateParams) {
  return request<Api.Factor.FactorItem>({
    url: '/admin/factor/',
    method: 'post',
    data
  });
}

/** update a factor (code/source immutable; preset factors can be disabled via status=false) */
export function fetchUpdateFactor(factorId: number, data: Api.Factor.FactorUpdateParams) {
  return request<Api.Factor.FactorItem>({
    url: `/admin/factor/${factorId}`,
    method: 'put',
    data
  });
}

/** delete a factor (soft; preset factors are rejected by the backend, disable them instead) */
export function fetchDeleteFactor(factorId: number) {
  return request<null>({
    url: `/admin/factor/${factorId}`,
    method: 'delete'
  });
}

/** import factors from a URL or pasted JSON (per-item validation; conflicts skipped) */
export function fetchImportFactors(data: Api.Factor.FactorImportParams) {
  return request<Api.Factor.FactorImportResult>({
    url: '/admin/factor/import',
    method: 'post',
    data
  });
}

/** calc factor values for a stock universe at the target trading day */
export function fetchCalcFactor(data: Api.Factor.FactorCalcParams) {
  return request<Api.Factor.FactorCalcResult>({
    url: '/admin/factor/calc',
    method: 'post',
    data
  });
}

/** screen stocks by factor conditions (AND; codes or strategy_id, no whole-market screen) */
export function fetchScreenStocks(data: Api.Factor.FactorScreenParams) {
  return request<Api.Factor.FactorScreenResult>({
    url: '/admin/factor/screen',
    method: 'post',
    data
  });
}

/** save screened codes as a strategy stock pool (overwrite strategy.stock_pool) */
export function fetchSaveScreenPool(data: Api.Factor.SavePoolParams) {
  return request<Api.Factor.SavePoolResult>({
    url: '/admin/factor/screen/save-pool',
    method: 'post',
    data
  });
}
