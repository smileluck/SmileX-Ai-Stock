import { $t } from '@/locales';

/** 熔断状态对应的标签颜色 */
export const circuitStateTagMap: Record<Api.DataSource.CircuitState, NaiveUI.ThemeColor> = {
  closed: 'success',
  half_open: 'warning',
  open: 'error'
};

/** 熔断状态文案（half_open 附带剩余恢复秒数） */
export function circuitStateLabel(source: Api.DataSource.SourceInfo): string {
  if (source.circuit_state === 'half_open' && source.circuit_recover_in_s > 0) {
    return `${$t('page.manage.datasource.circuitStates.halfOpen')} (${source.circuit_recover_in_s}s)`;
  }
  const labelMap: Record<Api.DataSource.CircuitState, string> = {
    closed: $t('page.manage.datasource.circuitStates.closed'),
    half_open: $t('page.manage.datasource.circuitStates.halfOpen'),
    open: $t('page.manage.datasource.circuitStates.open')
  };
  return labelMap[source.circuit_state];
}

/** 计算成功率百分比（保留一位小数） */
export function successRate(success: number, total: number): string {
  if (!total) return '-';
  return `${((success / total) * 100).toFixed(1)}%`;
}

/** 熔断模式选项 */
export function circuitModeOptions() {
  return [
    { label: $t('page.manage.datasource.configForm.circuitModes.auto'), value: 'auto' as const },
    { label: $t('page.manage.datasource.configForm.circuitModes.forceOpen'), value: 'force_open' as const },
    { label: $t('page.manage.datasource.configForm.circuitModes.forceClosed'), value: 'force_closed' as const }
  ];
}

/** FQGate 测试步骤文案 */
export function fqgateTestStepLabel(step: Api.DataSource.FqgateTestStep['step']): string {
  const labelMap: Record<Api.DataSource.FqgateTestStep['step'], string> = {
    health: $t('page.manage.datasource.fqgate.steps.health'),
    daily_klines: $t('page.manage.datasource.fqgate.steps.dailyKlines'),
    realtime_quote: $t('page.manage.datasource.fqgate.steps.realtimeQuote')
  };
  return labelMap[step];
}

/** 失败事件结果文案 */
export function eventOutcomeLabel(outcome: Api.DataSource.EventRecord['outcome']): string {
  return outcome === 'timeout'
    ? $t('page.manage.datasource.outcomes.timeout')
    : $t('page.manage.datasource.outcomes.fail');
}
