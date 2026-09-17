declare namespace Api {
  namespace Backtest {
    /** 回测状态（字符串三态，无需 1/2 桥接） */
    export type BacktestStatus = 'running' | 'success' | 'failed';

    /** 滑点模型：fixed-固定百分比，amp-振幅比例（slippage_pct 改作振幅系数） */
    export type SlippageModel = 'fixed' | 'amp';

    /** 绩效汇总（result JSON） */
    export interface BacktestResult {
      /** 总收益率(%) */
      total_return_pct: number | null;
      /** 年化收益率(%)，按 252 交易日 */
      annual_return_pct: number | null;
      /** 最大回撤(%) */
      max_drawdown_pct: number | null;
      /** 夏普比率（日收益率年化，样本不足为 null） */
      sharpe: number | null;
      /** 盈利笔数 */
      win_count: number;
      /** 亏损笔数 */
      loss_count: number;
      /** 胜率(%)，无卖出记录为 null */
      win_rate: number | null;
      /** 盈亏比（总盈利/总亏损），无亏损为 null */
      profit_factor: number | null;
      /** 买入笔数 */
      trade_count: number;
      /** 期末权益 */
      final_equity: number;
      /** 告警列表（北交所跳过、缺行情等） */
      warnings: string[];
    }

    /** 每日净值点 */
    export interface EquityPoint {
      date: string;
      equity: number;
      cash: number;
      market_value: number;
    }

    /** 回测任务记录 */
    export interface BacktestItem {
      id: number;
      strategy_id: number;
      strategy_name: string;
      start_date: string;
      end_date: string;
      initial_capital: number;
      slippage_pct: number;
      slippage_model: SlippageModel;
      commission_pct: number;
      stamp_tax_pct: number;
      status: BacktestStatus;
      error_msg: string | null;
      result: BacktestResult | null;
      started_at: string | null;
      finished_at: string | null;
      created_at: string | null;
    }

    /** 回测详情（额外含净值曲线） */
    export interface BacktestDetail extends BacktestItem {
      equity_curve: EquityPoint[] | null;
    }

    /** 发起回测参数 */
    export interface BacktestRunParams {
      strategy_id: number;
      start_date: string;
      end_date: string;
      initial_capital: number;
      slippage_pct: number;
      /** 不传默认为 fixed */
      slippage_model?: SlippageModel;
      commission_pct: number;
      stamp_tax_pct: number;
    }

    /** 回测成交明细 */
    export interface BacktestTradeItem {
      id: number;
      backtest_id: number;
      stock_code: string;
      stock_name: string;
      action: 'buy' | 'sell';
      trade_date: string;
      price: number;
      quantity: number;
      amount: number;
      fee: number;
      /** 买入理由或卖出原因：stop_loss/target_reached/trailing_stop/ai_signal/backtest_end */
      reason: string | null;
      return_rate: number | null;
      created_at: string | null;
    }

    /** 参数寻优网格（缺省/空=该参数沿用策略当前值不参与扫描） */
    export interface SweepGrid {
      stop_loss_pct?: number[] | null;
      take_profit_pct?: number[] | null;
      trailing_drawdown_pct?: number[] | null;
    }

    /** rule 型买入条件单条阈值扫描 */
    export interface BuyConditionScan {
      condition_index: number;
      values: number[];
    }

    /** 参数寻优请求（同步接口，笛卡尔积 ≤27，不落库） */
    export interface BacktestSweepParams {
      strategy_id: number;
      start_date: string;
      end_date: string;
      initial_capital?: number;
      slippage_pct?: number;
      slippage_model?: SlippageModel;
      commission_pct?: number;
      stamp_tax_pct?: number;
      grid?: SweepGrid;
      buy_condition_scan?: BuyConditionScan | null;
    }

    /** 单组生效参数（未参与扫描的为策略当前值） */
    export interface SweepParams {
      stop_loss_pct: number | null;
      take_profit_pct: number | null;
      trailing_drawdown_pct: number | null;
      buy_condition: { index: number; factor_id: number; value: number } | null;
    }

    /** 单组参数的回放绩效 */
    export interface SweepResultItem {
      params: SweepParams;
      total_return_pct: number | null;
      annual_return_pct: number | null;
      max_drawdown_pct: number | null;
      sharpe: number | null;
      win_rate: number | null;
      profit_factor: number | null;
      trade_count: number;
      final_equity: number | null;
      is_baseline: boolean;
    }

    /** 参数寻优响应（results 按 total_return_pct 降序） */
    export interface BacktestSweepResult {
      strategy_id: number;
      strategy_name: string;
      /** recorded_replay-回放已记录信号 / rule_daily_eval-规则逐日评估 */
      mode: string;
      total_runs: number;
      results: SweepResultItem[];
    }
  }
}
