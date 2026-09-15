declare namespace Api {
  /**
   * namespace StockLimitUp
   *
   * backend api module: "limit-up" (涨停股池 / 热门个股)
   */
  namespace StockLimitUp {
    /** 市场板块 */
    type MarketBoard = 'all' | 'main' | 'chinext' | 'star' | 'bse';

    /** 池类型: limit_up=收盘封板 / broken=涨停后炸板未封住 */
    type PoolType = 'all' | 'limit_up' | 'broken';

    /** 连板概率评分因子 */
    interface ContinuationFactor {
      /** 因子类型: consecutive/seal_ratio/break_count/first_seal/turnover_rate */
      type: string;
      /** 因子原始值，缺失为 null */
      value: number | string | null;
    }

    /** 涨停/炸板股单项 */
    interface LimitUpStockItem {
      /** 记录 ID */
      id: number;
      /** 快照日期 */
      record_date: string;
      /** 股票代码 */
      stock_code: string;
      /** 股票名称 */
      stock_name: string;
      /** 池类型: limit_up=收盘封板 / broken=涨停后炸板未封住 */
      pool_type: string;
      /** 市场板块: main/chinext/star/bse */
      market_board: string;
      /** 最新价 */
      latest_price: number | null;
      /** 涨跌幅(%) */
      change_pct: number | null;
      /** 换手率(%) */
      turnover_rate: number | null;
      /** 成交额(元) */
      turnover: number | null;
      /** 振幅(%) */
      amplitude: number | null;
      /** 封板资金(元) */
      seal_amount: number | null;
      /** 首次封板时间 */
      first_limit_up_time: string | null;
      /** 最后封板时间 */
      last_limit_up_time: string | null;
      /** 炸板次数 */
      break_count: number | null;
      /** 连板数 */
      consecutive_limit_up: number | null;
      /** 所属行业 */
      industry: string | null;
      /** 涨停原因 */
      limit_up_reason: string | null;
      /** 连板概率评分(0-100)，读时按封板质量启发式计算 */
      continuation_probability: number | null;
      /** 连板概率评分因子明细 */
      continuation_factors: ContinuationFactor[] | null;
    }

    /** 涨停统计 */
    interface LimitUpStats {
      /** 快照日期 */
      record_date: string | null;
      /** 涨停总数（仅封板股） */
      total_count: number;
      /** 炸板家数（涨停后破板未封住） */
      broken_count: number;
      /** 沪深主板数量 */
      main_count: number;
      /** 创业板数量 */
      chinext_count: number;
      /** 科创板数量 */
      star_count: number;
      /** 北交所数量 */
      bse_count: number;
      /** 最高连板数 */
      max_consecutive: number;
      /** 行业分布统计 */
      board_distribution: Record<string, number>;
    }

    /** 涨停列表查询参数 */
    type LimitUpListParams = CommonType.RecordNullable<{
      date?: string | null;
      market_board?: MarketBoard;
      pool_type?: PoolType;
    }> &
      Common.CommonSearchParams;
  }
}
