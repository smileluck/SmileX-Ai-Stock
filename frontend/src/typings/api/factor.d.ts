declare namespace Api {
  namespace Factor {
    /** 因子来源：preset-预置开源，imported-导入，custom-自定义 */
    export type FactorSource = 'preset' | 'imported' | 'custom';

    /** 因子记录（status 为 bool，无需 1/2 桥接） */
    export interface FactorItem {
      id: number;
      name: string;
      code: string;
      category: string;
      formula: string;
      description: string | null;
      source: FactorSource;
      source_url: string | null;
      params: Record<string, any> | null;
      status: boolean;
      created_at: string | null;
      updated_at: string | null;
    }

    /** 创建因子参数（source 由后端固定为 custom） */
    export interface FactorCreateParams {
      name: string;
      code: string;
      category: string;
      formula: string;
      description?: string | null;
      source_url?: string | null;
      params?: Record<string, any> | null;
      status: boolean;
    }

    /** 更新因子参数（code 不可改；全字段可选） */
    export type FactorUpdateParams = Partial<Omit<FactorCreateParams, 'code'>>;

    /** 导入因子参数：url 与 content 二选一 */
    export interface FactorImportParams {
      url?: string;
      content?: string;
    }

    /** 导入结果 */
    export interface FactorImportResult {
      imported: number;
      skipped: number;
      errors: string[];
    }

    /** 因子计算参数 */
    export interface FactorCalcParams {
      factor_id: number;
      codes: string[];
      /** YYYY-MM-DD，缺省取今天之前最后一个交易日 */
      end_date?: string;
      lookback?: number;
    }

    /** 单只股票因子值 */
    export interface FactorValueItem {
      code: string;
      value: number;
    }

    /** 因子计算结果 */
    export interface FactorCalcResult {
      factor_id: number;
      factor_code: string;
      /** 实际目标交易日 */
      end_date: string;
      values: FactorValueItem[];
      warnings: string[];
    }

    /** 选股操作符：top_n=按因子值降序前 N 名 */
    export type ScreenOp = 'gt' | 'gte' | 'lt' | 'lte' | 'top_n';

    /** 选股条件 */
    export interface ScreenCondition {
      factor_id: number;
      op: ScreenOp;
      value: number;
    }

    /** 选股参数：codes 与 strategy_id 二选一（不支持全市场选股） */
    export interface FactorScreenParams {
      codes?: string[];
      strategy_id?: number;
      conditions: ScreenCondition[];
      end_date?: string;
      lookback?: number;
    }

    /** 选股命中项（factor_values 键为因子 code，无法计算时为 null） */
    export interface ScreenMatchItem {
      code: string;
      name: string;
      factor_values: Record<string, number | null>;
    }

    /** 选股结果 */
    export interface FactorScreenResult {
      total: number;
      end_date: string;
      matched: ScreenMatchItem[];
      warnings: string[];
    }

    /** 保存股票池参数（覆盖 strategy.stock_pool） */
    export interface SavePoolParams {
      strategy_id: number;
      codes: string[];
    }

    /** 保存股票池结果 */
    export interface SavePoolResult {
      strategy_id: number;
      total: number;
    }
  }
}
