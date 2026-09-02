declare namespace Api {
  namespace Financial {
    /** 财报关键指标记录 */
    export interface FinancialReportItem {
      id: number;
      stock_code: string;
      stock_name: string | null;
      report_period: string;
      metrics: Record<string, number | string | null> | null;
      fetched_at: string | null;
    }

    /** 财报解读结构化摘要（parsed_result） */
    export interface FinancialParsedResult {
      quality_rating?: string;
      /** 下一报告期预测评级：优秀 / 良好 / 一般 / 较差 */
      next_quality_rating?: string;
      highlights?: string[];
      risks?: string[];
      forecast?: {
        direction?: string;
        summary?: string;
        /** 下期盈利增长预测的来源分析（驱动因素） */
        drivers?: string[];
      };
    }

    /** 每股最新一条券商研报摘要（盈利预测对照） */
    export interface ResearchBrief {
      org_name: string | null;
      rating: string | null;
      published_date: string | null;
      /** {年份: {eps, pe}} */
      forecast: Record<string, { eps?: number | string; pe?: number | string }> | null;
    }

    /** 财报解读记录（列表项） */
    export interface FinancialInterpretItem {
      id: number;
      stock_code: string;
      stock_name: string | null;
      industry: string | null;
      report_period: string | null;
      run_date: string;
      trigger_type: 'schedule' | 'manual';
      status: 'running' | 'success' | 'failed';
      parsed_result: FinancialParsedResult | null;
      research_brief: ResearchBrief | null;
      error_msg: string | null;
      created_at: string | null;
    }

    /** 财报解读详情（含报告原文） */
    export interface FinancialInterpretDetail extends FinancialInterpretItem {
      ai_raw_response: string | null;
    }

    /** 解读提交结果（异步执行：接口立即返回，结果轮询解读记录） */
    export interface FinancialInterpretSubmitResult {
      interpretation_id: number;
      status: string;
    }

    /** 财报解读分析策略配置（prompt 为空则使用内置默认策略） */
    export interface FinancialConfigItem {
      prompt_template: string | null;
      updated_at: string | null;
    }
  }
}
