declare namespace Api {
  namespace Recommend {
    /** 推荐运行状态 */
    export type RecommendRunStatus = 'running' | 'success' | 'failed';

    /** 推荐方向：limit_up-涨停候选，bottom_fish-抄底 */
    export type RecommendDirection = 'limit_up' | 'bottom_fish';

    /** 入场方式：market-市价入场，limit-回踩买点入场 */
    export type RecommendEntryType = 'market' | 'limit';

    /** 推荐理由六维度依据（仅返回有依据的维度） */
    export interface RecommendReasons {
      /** 资讯面 */
      news?: string;
      /** 情绪面 */
      sentiment?: string;
      /** 因子面 */
      factor?: string;
      /** 板块资金 */
      sector_fund?: string;
      /** 主力资金 */
      main_force?: string;
      /** 连板梯队 */
      limit_up?: string;
    }

    /** 推荐个股 */
    export interface RecommendStock {
      id: number;
      /** 排名 1-10 */
      rank: number;
      stock_code: string;
      stock_name: string;
      direction: RecommendDirection;
      /** 综合分 0-100 */
      score: number;
      /** 预判买点 */
      buy_price: number;
      target_price: number | null;
      stop_loss_price: number | null;
      entry_type: RecommendEntryType;
      reasons: RecommendReasons | null;
      /** AI 推荐理由 */
      summary: string;
    }

    /** 推荐运行记录摘要（历史列表项，不含 stocks） */
    export interface RecommendRunItem {
      id: number;
      /** 推荐所属交易日 */
      run_date: string;
      status: RecommendRunStatus;
      error_msg: string | null;
      parsed_result: Record<string, unknown> | null;
      /** 专用策略 id（用于跳回测/持仓，可能为空） */
      strategy_id: number | null;
      created_at: string;
    }

    /** 推荐运行详情（latest/详情返回，含推荐个股与 AI 综合研判原文） */
    export interface RecommendRunDetail extends RecommendRunItem {
      /** AI 综合研判（markdown） */
      ai_raw_response: string;
      stocks: RecommendStock[];
    }

    /** 推荐提交结果（异步执行：接口立即返回，结果见执行记录） */
    export interface RecommendRunSubmitResult {
      id: number;
      status: RecommendRunStatus | string;
      run_date: string;
    }
  }
}
