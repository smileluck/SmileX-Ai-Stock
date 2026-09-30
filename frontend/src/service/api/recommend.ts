import { request } from '../request';

/** ==================== AI 推荐板块 API ==================== */

/** manually trigger a recommend run (async, returns immediately) */
export function fetchRunRecommend() {
  return request<Api.Recommend.RecommendRunSubmitResult>({
    url: '/admin/recommend/run',
    method: 'post'
  });
}

/** get the latest recommend run detail (with stocks and report, data is null when none) */
export function fetchRecommendLatest() {
  return request<Api.Recommend.RecommendRunDetail | null>({
    url: '/admin/recommend/latest',
    method: 'get'
  });
}

/** get recommend run history (paginated, records without stocks) */
export function fetchRecommendRuns(params: { page: number; page_size: number }) {
  return request<Api.Common.PaginatingQueryRecord<Api.Recommend.RecommendRunItem>>({
    url: '/admin/recommend/runs',
    method: 'get',
    params
  });
}

/** get a single recommend run detail (with stocks and report) */
export function fetchRecommendDetail(runId: number) {
  return request<Api.Recommend.RecommendRunDetail>({
    url: `/admin/recommend/runs/${runId}`,
    method: 'get'
  });
}
