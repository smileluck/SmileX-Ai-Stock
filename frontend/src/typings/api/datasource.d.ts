declare namespace Api {
  /** 数据源管理 */
  namespace DataSource {
    /** 熔断模式：auto 自动 / force_open 手动熔断 / force_closed 强制可用 */
    type CircuitMode = 'auto' | 'force_open' | 'force_closed';

    /** 熔断状态：closed 正常 / open 手动熔断 / half_open 熔断冷却中 */
    type CircuitState = 'closed' | 'open' | 'half_open';

    /** 数据源限流/熔断配置 */
    interface SourceConfig {
      enabled: boolean;
      max_concurrency: number;
      min_interval_ms: number;
      timeout_s: number;
      failure_threshold: number;
      cooldown_s: number;
      circuit_mode: CircuitMode;
    }

    /** 配置更新请求体（config 支持部分字段合并） */
    interface ConfigUpdatePayload {
      source: string;
      config: Partial<SourceConfig>;
    }

    /** 今日用量统计 */
    interface TodayStats {
      total: number;
      success: number;
      fail: number;
      timeout: number;
      rejected: number;
      avg_latency_ms: number;
      max_latency_ms: number;
    }

    /** 数据源能力项 */
    interface Capability {
      key: string;
      label: string;
    }

    /** 数据源运行状态 */
    interface SourceInfo {
      key: string;
      name: string;
      category: string;
      /** 数据源支持的能力清单 */
      capabilities: Capability[];
      call_sites: string[];
      config: SourceConfig;
      circuit_state: CircuitState;
      consecutive_failures: number;
      /** 熔断剩余恢复秒数 */
      circuit_recover_in_s: number;
      last_success_at: string | null;
      last_error_at: string | null;
      last_error_msg: string | null;
      today: TodayStats | null;
    }

    /** FQGate 网关配置 */
    interface FqgateGateway {
      base_url: string;
    }

    /** 数据源列表响应 */
    interface SourceListData {
      sources: SourceInfo[];
      fqgate_gateway: FqgateGateway;
    }

    /** 按小时聚合的历史用量统计记录 */
    interface StatRecord {
      source_key: string;
      /** ISO 格式统计小时 */
      stat_hour: string;
      total_calls: number;
      success_calls: number;
      fail_calls: number;
      timeout_calls: number;
      rejected_calls: number;
      avg_latency_ms: number;
      max_latency_ms: number;
    }

    /** 失败事件记录 */
    interface EventRecord {
      source: string;
      /** ISO 格式时间 */
      time: string;
      outcome: 'fail' | 'timeout';
      error: string;
      latency_ms: number;
    }

    /** FQGate 连通性测试步骤 */
    interface FqgateTestStep {
      step: 'health' | 'daily_klines' | 'realtime_quote';
      ok: boolean;
      error?: string;
      latency_ms: number;
    }

    /** FQGate 连通性测试结果 */
    interface FqgateTestResult {
      ok: boolean;
      steps: FqgateTestStep[];
      health?: unknown;
      klines_sample?: unknown;
      quote_sample?: unknown;
    }
  }
}
