declare namespace Api {
  /**
   * namespace StockRotation
   *
   * backend api module: "rotation" (板块轮动分析)
   */
  namespace StockRotation {
    /** 板块类型 */
    type BoardType = 'industry' | 'concept';

    /** 回填板块类型（all=行业+概念合并为一个后台任务） */
    type BackfillBoardType = BoardType | 'all';

    /** 轮动阶段: start-低位启动 / ferment-发酵 / climax-高潮 / ebb-退潮 / observe-蓄势观察 */
    type RotationStage = 'start' | 'ferment' | 'climax' | 'ebb' | 'observe';

    /** 操作建议: attack-主攻 / ambush-潜伏埋伏 / avoid-回避 / watch-观察 */
    type RotationAction = 'attack' | 'ambush' | 'avoid' | 'watch';

    /** 高低切换信号: switching-高低切换 / split-分歧 / resonance-共振 / unknown-数据不足 */
    type SwitchSignal = 'switching' | 'split' | 'resonance' | 'unknown';

    /** 近期轮动板块指标项（读时计算，不入库） */
    interface RotationOverviewItem {
      /** 板块类型: industry/concept */
      board_type: BoardType;
      /** 板块代码 */
      board_code: string;
      /** 板块名称 */
      board_name: string;
      /** 今日涨跌幅(%) */
      change_pct: number | null;
      /** 近3日累计涨跌幅(%) */
      gain_3d: number | null;
      /** 近5日累计涨跌幅(%) */
      gain_5d: number | null;
      /** 近10日累计涨跌幅(%) */
      gain_10d: number | null;
      /** 今日涨幅排名(1=最强) */
      rank: number | null;
      /** 排名变化 = 5日前排名 - 今日排名，正数=排名上升 */
      rank_change: number | null;
      /** 量比 = 今日成交额 / 前5日成交额均值 */
      volume_ratio: number | null;
      /** 主力净流入连续为正的交易日数 */
      inflow_days: number | null;
      /** 近3日板块内涨停家数（去重） */
      limit_up_count: number | null;
      /** 近3日板块内最高连板数 */
      max_consecutive: number | null;
      /** 轮动阶段 */
      stage: RotationStage;
      /** 明日轮动候选评分 0-100 */
      tomorrow_score: number;
      /** 操作建议 */
      action: RotationAction;
    }

    /** 近期轮动板块总览响应 */
    interface RotationOverviewResponse {
      /** 最新快照日期 */
      snapshot_date: string | null;
      /** 实际可用的历史交易日数 */
      history_days: number;
      /** 按明日候选评分降序 */
      items: RotationOverviewItem[];
    }

    /** 高低切换个股明细项 */
    interface RotationSwitchStockItem {
      /** 股票代码 */
      stock_code: string;
      /** 股票名称 */
      stock_name: string;
      /** 最新价 */
      price: number | null;
      /** 今日涨跌幅(%) */
      change_pct: number | null;
      /** 今日成交额(元) */
      amount: number | null;
      /** 位置涨幅(%)：近10日，缺失时近5日，再缺失当日 */
      position_gain: number | null;
    }

    /** 板块内高低切换信号项 */
    interface RotationSwitchItem {
      /** 板块类型: industry/concept */
      board_type: BoardType;
      /** 板块代码 */
      board_code: string;
      /** 板块名称 */
      board_name: string;
      /** 板块今日涨跌幅(%) */
      change_pct: number | null;
      /** 信号: switching/split/resonance/unknown */
      signal: SwitchSignal;
      /** 高位组（位置前20%）今日平均涨幅(%) */
      high_avg_pct: number | null;
      /** 低位组（位置后20%）今日平均涨幅(%) */
      low_avg_pct: number | null;
      /** 分层使用字段: gain_10d/gain_5d/change_pct */
      position_key: string;
      /** 高位滞涨股前5（高位组中今日表现最差） */
      high_laggards: RotationSwitchStockItem[];
      /** 低位启动股前5（低位组中今日表现最好） */
      low_starters: RotationSwitchStockItem[];
    }

    /** 板块内高低切换总览响应 */
    interface RotationSwitchResponse {
      /** 成分股快照日期 */
      snapshot_date: string | null;
      /** 按板块今日涨幅降序 */
      items: RotationSwitchItem[];
    }

    /** 板块成分股快照同步结果 */
    interface RotationSyncResult {
      /** 计划同步板块数 */
      boards: number;
      /** 成功板块数 */
      saved_boards: number;
      /** 写入成分股记录数 */
      stocks: number;
      /** 失败板块数 */
      failed_boards: number;
      /** 快照日期 */
      snapshot_date: string | null;
    }

    /** 板块历史回填提交结果（后台任务执行） */
    interface RotationBackfillResult {
      board_type: string;
      /** 回填天数 */
      days: number;
      /** 待回填板块数 */
      boards: number;
      /** submitted-已提交后台执行 / no_data-无可回填板块 */
      status: string;
    }
  }
}
