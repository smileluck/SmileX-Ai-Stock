declare namespace Api {
  namespace Analysis {
    /** 分析类型 */
    export type AnalysisType = 'market' | 'sector' | 'news' | 'rotation';

    /** 分析时段：close-收盘分析（16:05），morning-早盘分析（9:20），weekly-周度复盘（周日晚，仅资讯分析） */
    export type SessionType = 'close' | 'morning' | 'weekly';

    /** 明日研判（parsed_result.tomorrow_outlook） */
    export interface TomorrowOutlook {
      direction?: string;
      summary?: string;
    }

    /** 大盘分析结构化摘要（parsed_result） */
    export interface MarketParsedResult {
      sentiment?: string;
      score?: number;
      summary?: string;
      key_points?: string[];
      tomorrow_outlook?: TomorrowOutlook;
    }

    /** 板块分析热门板块项 */
    export interface HotBoardItem {
      board_name?: string;
      board_type?: string;
      change_pct?: number | null;
      viewpoint?: string;
    }

    /** 板块分析结构化摘要（parsed_result） */
    export interface SectorParsedResult {
      rotation_summary?: string;
      hot_boards?: HotBoardItem[];
      key_points?: string[];
      tomorrow_outlook?: TomorrowOutlook;
    }

    /** 资讯分析分类资讯项（macro_industry_news / stock_news 数组元素） */
    export interface NewsAnalysisItem {
      title?: string;
      category?: string;
      stock_name?: string;
      viewpoint?: string;
      impact?: string;
      source?: string;
    }

    /** 每日资讯分析结构化摘要（parsed_result） */
    export interface NewsParsedResult {
      macro_industry_news?: NewsAnalysisItem[];
      stock_news?: NewsAnalysisItem[];
      summary?: string;
      key_points?: string[];
    }

    /** 轮动分析近期板块项（parsed_result.recent_boards） */
    export interface RotationBoardItem {
      board_name?: string;
      board_type?: string;
      stage?: string;
      change_pct?: number | null;
      viewpoint?: string;
    }

    /** 轮动分析明日候选板块项（parsed_result.tomorrow_boards） */
    export interface RotationTomorrowBoardItem {
      board_name?: string;
      board_type?: string;
      action?: string;
      confidence?: string;
      viewpoint?: string;
    }

    /** 轮动分析切换信号项（parsed_result.switch_signals） */
    export interface RotationSwitchSignalItem {
      board_name?: string;
      summary?: string;
    }

    /** 轮动策略分析结构化摘要（parsed_result） */
    export interface RotationParsedResult {
      rotation_summary?: string;
      recent_boards?: RotationBoardItem[];
      tomorrow_boards?: RotationTomorrowBoardItem[];
      switch_signals?: RotationSwitchSignalItem[];
      key_points?: string[];
      tomorrow_outlook?: TomorrowOutlook;
    }

    /** 分析策略配置（无记录时后端返回默认值，data 始终非空） */
    export interface AnalysisConfig {
      analysis_type: AnalysisType | string;
      session: SessionType | string;
      prompt_template: string | null;
      include_tomorrow: boolean;
      tomorrow_prompt_template: string | null;
      updated_at: string | null;
    }

    /** 分析策略配置保存参数 */
    export interface AnalysisConfigSaveParams {
      prompt_template?: string | null;
      include_tomorrow: boolean;
      tomorrow_prompt_template?: string | null;
    }

    /** 分析执行记录（列表项） */
    export interface AnalysisRunItem {
      id: number;
      analysis_type: AnalysisType | string;
      session: SessionType | string;
      run_date: string;
      trigger_type: 'schedule' | 'manual';
      status: 'running' | 'success' | 'failed';
      parsed_result:
        | MarketParsedResult
        | SectorParsedResult
        | NewsParsedResult
        | RotationParsedResult
        | Record<string, unknown>
        | null;
      error_msg: string | null;
      created_at: string | null;
    }

    /** 分析执行记录详情（含报告原文） */
    export interface AnalysisRunDetail extends AnalysisRunItem {
      ai_raw_response: string | null;
    }

    /** 分析提交结果（异步执行：接口立即返回，结果见执行记录） */
    export interface AnalysisRunSubmitResult {
      run_id: number;
      status: string;
    }
  }
}
