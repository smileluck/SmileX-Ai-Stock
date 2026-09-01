import { request } from '../request';

/** ==================== 企业财报 AI 解读 API ==================== */

/** get stock financial reports (recent periods in db, report_period descending) */
export function fetchGetFinancialReports(stockCode: string, limit = 8) {
  return request<Api.Financial.FinancialReportItem[]>({
    url: `/admin/financial/reports/${stockCode}`,
    method: 'get',
    params: { limit }
  });
}

/** trigger stock financial AI interpretation (async, auto-fetch reports when missing) */
export function fetchRunFinancialInterpretation(stockCode: string) {
  return request<Api.Financial.FinancialInterpretSubmitResult>({
    url: `/admin/financial/interpretations/${stockCode}`,
    method: 'post'
  });
}

/** get financial interpretation records (paginated, filterable by stock code / rating / forecast direction) */
export function fetchGetFinancialInterpretations(params: {
  page: number;
  page_size: number;
  stock_code?: string;
  quality_rating?: string;
  forecast_direction?: string;
}) {
  return request<Api.Common.PaginatingQueryRecord<Api.Financial.FinancialInterpretItem>>({
    url: '/admin/financial/interpretations',
    method: 'get',
    params
  });
}

/** get financial interpretation detail (with AI report content) */
export function fetchGetFinancialInterpretationDetail(interpretationId: number) {
  return request<Api.Financial.FinancialInterpretDetail>({
    url: `/admin/financial/interpretations/detail/${interpretationId}`,
    method: 'get'
  });
}
