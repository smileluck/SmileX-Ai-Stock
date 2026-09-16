declare namespace Api {
  namespace Strategy {
    /** 执行时段 */
    export type ExecutePeriod = 'pre_market' | 'morning' | 'noon' | 'tail' | 'post_close';

    /** 策略分类 */
    export type StrategyCategory = 'pre_market_auction' | 'noon' | 'tail' | 'blue_chip' | 'general';

    /** 持仓状态 */
    export type PositionStatus = 'holding' | 'closed' | 'cancelled';

    /** 策略配置 */
    export interface StrategyItem {
      id: number;
      name: string;
      description: string | null;
      category: StrategyCategory | string;
      is_preset: boolean;
      is_template: boolean;
      /** 克隆/导入来源策略 ID */
      source_id: number | null;
      tags: string[] | null;
      prompt_template: string | null;
      stock_pool: { codes?: string[] } | null;
      execute_periods: ExecutePeriod[] | null;
      max_positions: number;
      stop_loss_pct: number | null;
      take_profit_pct: number | null;
      trailing_drawdown_pct: number | null;
      status: boolean;
      last_executed_at: string | null;
      created_at: string | null;
      updated_at: string | null;
    }

    /** 最近一次 success 回测的绩效摘要（模板市场列表附带，无则 null） */
    export interface TemplateBacktestSummary {
      start_date: string;
      end_date: string;
      total_return_pct: number | null;
      max_drawdown_pct: number | null;
      win_rate: number | null;
      trade_count: number | null;
    }

    /** 模板市场列表项 */
    export interface TemplateItem extends StrategyItem {
      clone_count: number;
      last_backtest: TemplateBacktestSummary | null;
    }

    /** 发布/下架模板参数（tags 传入时覆盖更新） */
    export interface TemplatePublishParams {
      tags?: string[];
    }

    /** 策略导出 JSON（schema_version 固定 1，不含 id/状态/时间戳） */
    export interface StrategyExportData {
      schema_version: number;
      name: string;
      description: string | null;
      category: StrategyCategory | string;
      prompt_template: string | null;
      stock_pool: { codes?: string[] } | null;
      execute_periods: ExecutePeriod[] | null;
      max_positions: number;
      stop_loss_pct: number | null;
      take_profit_pct: number | null;
      trailing_drawdown_pct: number | null;
      tags: string[] | null;
    }

    /** 策略导入参数（导出 JSON + schema_version；新件默认停用） */
    export interface StrategyImportParams extends Omit<StrategyExportData, 'schema_version'> {
      schema_version: number;
    }

    /** 策略创建/更新参数 */
    export interface StrategySaveParams {
      name: string;
      description?: string | null;
      category?: StrategyCategory | string;
      prompt_template?: string | null;
      stock_pool?: { codes: string[] } | null;
      execute_periods: ExecutePeriod[];
      max_positions: number;
      stop_loss_pct?: number | null;
      take_profit_pct?: number | null;
      trailing_drawdown_pct?: number | null;
      status: boolean;
    }

    /** 单条 AI 信号 */
    export interface SignalItem {
      stock_code: string;
      stock_name: string;
      action: 'buy' | 'sell' | 'adjust' | 'hold';
      buy_price: number | null;
      target_sell_price: number | null;
      stop_loss_price: number | null;
      reason: string | null;
    }

    /** 策略执行记录 */
    export interface StrategyRunItem {
      id: number;
      strategy_id: number;
      strategy_name: string;
      run_period: string;
      run_date: string;
      trigger_type: 'schedule' | 'manual';
      status: 'running' | 'success' | 'failed';
      parsed_signals: SignalItem[] | null;
      opened_count: number;
      closed_count: number;
      error_msg: string | null;
      created_at: string | null;
    }

    /** 策略执行提交结果（异步执行：接口立即返回，结果见执行记录） */
    export interface StrategyRunResult {
      run_id: number;
      status: string;
    }

    /** 持仓 */
    export interface PositionItem {
      id: number;
      strategy_id: number;
      strategy_name: string;
      stock_code: string;
      stock_name: string;
      buy_price: number;
      buy_time: string;
      buy_reason: string | null;
      quantity: number;
      target_sell_price: number | null;
      stop_loss_price: number | null;
      trailing_drawdown_pct: number | null;
      peak_price: number | null;
      status: PositionStatus;
      latest_price: number | null;
      floating_pnl_pct: number | null;
      tracked_at: string | null;
      sell_price: number | null;
      sell_time: string | null;
      sell_reason: string | null;
      return_rate: number | null;
    }

    /** 持仓跟踪日志 */
    export interface TrackLogItem {
      id: number;
      position_id: number;
      track_time: string;
      latest_price: number | null;
      pnl_pct: number | null;
      ai_adjusted_target: number | null;
      adjust_reason: string | null;
    }

    /** 策略回报率统计 */
    export interface StrategyStatsItem {
      strategy_id: number;
      strategy_name: string;
      holding_count: number;
      closed_count: number;
      win_count: number;
      loss_count: number;
      win_rate: number | null;
      total_return_rate: number | null;
      avg_return_rate: number | null;
      best_return_rate: number | null;
      worst_return_rate: number | null;
    }
  }
}
