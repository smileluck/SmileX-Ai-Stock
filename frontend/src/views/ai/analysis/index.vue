<script setup lang="tsx">
import { computed, onMounted, reactive, ref, watch } from 'vue';
import {
  NButton,
  NCard,
  NDataTable,
  NDatePicker,
  NDrawer,
  NDrawerContent,
  NDynamicTags,
  NGi,
  NGrid,
  NInput,
  NModal,
  NPagination,
  NPopconfirm,
  NSelect,
  NSpace,
  NSpin,
  NStatistic,
  NTabPane,
  NTabs,
  NTag,
  NText
} from 'naive-ui';
import type { DataTableColumns, DataTableSortState } from 'naive-ui';
import dayjs from 'dayjs';
import {
  fetchCloseStrategyPosition,
  fetchCloneStrategy,
  fetchCreateStrategy,
  fetchDeleteStrategy,
  fetchExportStrategy,
  fetchGetStrategyAttribution,
  fetchGetStrategyEquityCurve,
  fetchGetStrategyList,
  fetchGetStrategyPositions,
  fetchGetStrategyRuns,
  fetchGetStrategyStats,
  fetchPublishStrategy,
  fetchRunStrategy,
  fetchTrackStrategyPositions,
  fetchUnpublishStrategy,
  fetchUpdateStrategy
} from '@/service/api';
import { useAutoRefresh } from '@/hooks/common/auto-refresh';
import { useAppStore } from '@/store/modules/app';
import { $t } from '@/locales';
import EquityChart from '@/components/common/equity-chart.vue';
import IconTooltip from '@/components/common/icon-tooltip.vue';
import StrategyOperateDrawer from './modules/strategy-operate-drawer.vue';
import StrategyTemplate from './modules/strategy-template.vue';

defineOptions({ name: 'AiAnalysis' });

const appStore = useAppStore();

const activeTab = ref<'strategies' | 'positions' | 'stats' | 'templates'>('strategies');

// ================================================================
// 策略管理
// ================================================================
const strategySearch = reactive({ name: '', category: null as string | null });
const strategyList = ref<Api.Strategy.StrategyItem[]>([]);
const strategyTotal = ref(0);
const strategyPage = reactive({ page: 1, pageSize: 20 });
const strategyLoading = ref(false);

const CATEGORY_LABEL: Record<string, string> = {
  pre_market_auction: $t('page.aiStrategy.categoryAuction'),
  noon: $t('page.aiStrategy.categoryNoon'),
  tail: $t('page.aiStrategy.categoryTail'),
  blue_chip: $t('page.aiStrategy.categoryBlueChip'),
  general: $t('page.aiStrategy.categoryGeneral')
};

const CATEGORY_TAG_TYPE: Record<string, 'warning' | 'info' | 'success' | 'primary' | 'default'> = {
  pre_market_auction: 'warning',
  noon: 'info',
  tail: 'success',
  blue_chip: 'primary',
  general: 'default'
};

const CATEGORY_OPTIONS = Object.entries(CATEGORY_LABEL).map(([value, label]) => ({ value, label }));

async function loadStrategies(silent = false) {
  if (!silent) strategyLoading.value = true;
  try {
    const { data, error } = await fetchGetStrategyList({
      name: strategySearch.name || undefined,
      category: strategySearch.category || undefined,
      page: strategyPage.page,
      page_size: strategyPage.pageSize
    });
    if (!error) {
      strategyList.value = data?.records ?? [];
      strategyTotal.value = data?.total ?? 0;
    }
  } finally {
    if (!silent) strategyLoading.value = false;
  }
}

const drawerVisible = ref(false);
const editingStrategy = ref<Api.Strategy.StrategyItem | null>(null);

function searchStrategies() {
  strategyPage.page = 1;
  loadStrategies();
}

function onStrategyPageChange(page: number) {
  strategyPage.page = page;
  loadStrategies();
}

function openCreate() {
  editingStrategy.value = null;
  drawerVisible.value = true;
}

function openEdit(row: Api.Strategy.StrategyItem) {
  editingStrategy.value = row;
  drawerVisible.value = true;
}

async function onDrawerSubmitted(payload: { data: Api.Strategy.StrategySaveParams; isEdit: boolean; id?: number }) {
  const { error } = payload.isEdit
    ? await fetchUpdateStrategy(payload.id!, payload.data)
    : await fetchCreateStrategy(payload.data);
  if (!error) {
    window.$message?.success($t(payload.isEdit ? 'common.updateSuccess' : 'common.addSuccess'));
    await loadStrategies();
  }
}

async function onDeleteStrategy(row: Api.Strategy.StrategyItem) {
  const { error } = await fetchDeleteStrategy(row.id);
  if (!error) {
    window.$message?.success($t('common.deleteSuccess'));
    await loadStrategies();
  }
}

const runningIds = ref<number[]>([]);
async function onRunStrategy(row: Api.Strategy.StrategyItem) {
  runningIds.value.push(row.id);
  try {
    const { error } = await fetchRunStrategy(row.id);
    if (!error) {
      // 执行已异步化：接口提交即返回，LLM 分析在后台进行，
      // 买卖信号由每分钟交易引擎按实时价执行
      window.$message?.success($t('page.aiStrategy.runSubmitted'));
      await loadStrategies(true);
      if (runHistoryStrategy.value?.id === row.id) await loadRunHistory();
    }
  } finally {
    runningIds.value = runningIds.value.filter(id => id !== row.id);
  }
}

// ------------------------------------------------------------------
// 克隆 / 导出 / 发布模板
// ------------------------------------------------------------------
async function onCloneStrategy(row: Api.Strategy.StrategyItem) {
  const { error } = await fetchCloneStrategy(row.id);
  if (!error) {
    // 克隆件默认停用（实盘引擎只跑启用策略），提示用户确认后手动启用
    window.$message?.success($t('page.aiStrategy.cloneSuccess'));
    await loadStrategies();
  }
}

/** 导出策略 JSON 并下载为 <策略名>.strategy.json */
async function onExportStrategy(row: Api.Strategy.StrategyItem) {
  const { data, error } = await fetchExportStrategy(row.id);
  if (error || !data) return;
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `${row.name}.strategy.json`;
  link.click();
  URL.revokeObjectURL(url);
  window.$message?.success($t('page.aiStrategy.exportSuccess'));
}

const publishVisible = ref(false);
const publishingStrategy = ref<Api.Strategy.StrategyItem | null>(null);
const publishTags = ref<string[]>([]);
const publishing = ref(false);

function openPublish(row: Api.Strategy.StrategyItem) {
  publishingStrategy.value = row;
  publishTags.value = row.tags ? [...row.tags] : [];
  publishVisible.value = true;
}

async function onPublishSubmit() {
  if (!publishingStrategy.value) return;
  publishing.value = true;
  try {
    const { error } = await fetchPublishStrategy(publishingStrategy.value.id, { tags: publishTags.value });
    if (!error) {
      window.$message?.success($t('page.aiStrategy.publishSuccess'));
      publishVisible.value = false;
      await loadStrategies();
    }
  } finally {
    publishing.value = false;
  }
}

async function onUnpublish(row: Api.Strategy.StrategyItem) {
  const { error } = await fetchUnpublishStrategy(row.id);
  if (!error) {
    window.$message?.success($t('page.aiStrategy.unpublishSuccess'));
    await loadStrategies();
  }
}

const PERIOD_LABEL: Record<string, string> = {
  pre_market: $t('page.aiStrategy.periodPreMarket'),
  morning: $t('page.aiStrategy.periodMorning'),
  noon: $t('page.aiStrategy.periodNoon'),
  tail: $t('page.aiStrategy.periodTail'),
  post_close: $t('page.aiStrategy.periodPostClose'),
  manual: $t('page.aiStrategy.periodManual')
};

const SELL_REASON_LABEL: Record<string, string> = {
  stop_loss: $t('page.aiStrategy.reasonStopLoss'),
  take_profit: $t('page.aiStrategy.reasonTakeProfit'),
  target_reached: $t('page.aiStrategy.reasonTarget'),
  trailing_stop: $t('page.aiStrategy.reasonTrailingStop'),
  ai_signal: $t('page.aiStrategy.reasonAi'),
  manual: $t('page.aiStrategy.reasonManual')
};

function fmtTime(t: string | null) {
  return t ? dayjs(t).format('YYYY-MM-DD HH:mm') : '-';
}

const strategyColumns = computed<DataTableColumns<Api.Strategy.StrategyItem>>(() => [
  {
    key: 'name',
    title: $t('page.aiStrategy.form.name'),
    width: 150,
    render: row => (
      <div class="flex items-center gap-4px">
        <span class="font-500">{row.name}</span>
        {row.strategy_type === 'rule' ? (
          <NTag size="tiny" bordered={false} type="success">
            {$t('page.aiStrategy.ruleTag')}
          </NTag>
        ) : null}
        {row.is_preset ? (
          <NTag size="tiny" bordered={false} type="primary">
            {$t('page.aiStrategy.presetTag')}
          </NTag>
        ) : null}
        {row.is_template ? (
          <NTag size="tiny" bordered={false} type="warning">
            {$t('page.aiStrategy.templateTag')}
          </NTag>
        ) : null}
      </div>
    )
  },
  {
    key: 'category',
    title: $t('page.aiStrategy.form.category'),
    width: 100,
    render: row => (
      <NTag
        size="small"
        bordered={false}
        type={CATEGORY_TAG_TYPE[row.category] ?? 'default'}
      >
        {CATEGORY_LABEL[row.category] ?? row.category}
      </NTag>
    )
  },
  {
    key: 'execute_periods',
    title: $t('page.aiStrategy.form.periods'),
    width: 200,
    render: row => (
      <NSpace size={4}>
        {(row.execute_periods ?? []).map(p => (
          <NTag size="small" type="info" bordered={false}>
            {PERIOD_LABEL[p] ?? p}
          </NTag>
        ))}
      </NSpace>
    )
  },
  {
    key: 'max_positions',
    title: $t('page.aiStrategy.form.maxPositions'),
    width: 90,
    align: 'right',
    render: row => <span>{row.max_positions}</span>
  },
  {
    key: 'stop_loss_pct',
    title: $t('page.aiStrategy.form.stopLoss'),
    width: 90,
    align: 'right',
    render: row => <span>{row.stop_loss_pct !== null ? `${Number(row.stop_loss_pct).toFixed(1)}%` : '-'}</span>
  },
  {
    key: 'status',
    title: $t('page.aiStrategy.form.status'),
    width: 80,
    align: 'center',
    render: row =>
      row.status ? (
        <NTag type="success" size="small" bordered={false}>
          {$t('page.aiStrategy.enabled')}
        </NTag>
      ) : (
        <NTag type="default" size="small" bordered={false}>
          {$t('page.aiStrategy.disabled')}
        </NTag>
      )
  },
  {
    key: 'last_executed_at',
    title: $t('page.aiStrategy.lastExecuted'),
    width: 140,
    render: row => <span class="text-12px">{fmtTime(row.last_executed_at)}</span>
  },
  {
    key: 'actions',
    title: $t('common.action'),
    width: 380,
    align: 'center',
    render: row => (
      <NSpace size={4} justify="center">
        <NButton
          size="tiny"
          type="primary"
          ghost
          loading={runningIds.value.includes(row.id)}
          onClick={() => onRunStrategy(row)}
        >
          {$t('page.aiStrategy.run')}
        </NButton>
        <NButton size="tiny" tertiary onClick={() => openRunHistory(row)}>
          {$t('page.aiStrategy.runHistory')}
        </NButton>
        <NButton size="tiny" tertiary onClick={() => openEdit(row)}>
          {$t('common.edit')}
        </NButton>
        <NPopconfirm onPositiveClick={() => onCloneStrategy(row)}>
          {{
            trigger: () => (
              <NButton size="tiny" tertiary>
                {$t('page.aiStrategy.clone')}
              </NButton>
            ),
            default: () => $t('page.aiStrategy.cloneConfirm')
          }}
        </NPopconfirm>
        <NButton size="tiny" tertiary onClick={() => onExportStrategy(row)}>
          {$t('page.aiStrategy.export')}
        </NButton>
        {row.is_template ? (
          <NButton size="tiny" type="warning" ghost onClick={() => onUnpublish(row)}>
            {$t('page.aiStrategy.unpublish')}
          </NButton>
        ) : (
          <NButton size="tiny" type="warning" tertiary onClick={() => openPublish(row)}>
            {$t('page.aiStrategy.publish')}
          </NButton>
        )}
        <NPopconfirm onPositiveClick={() => onDeleteStrategy(row)}>
          {{
            trigger: () => (
              <NButton size="tiny" type="error" ghost>
                {$t('common.delete')}
              </NButton>
            ),
            default: () => $t('page.aiStrategy.deleteConfirm')
          }}
        </NPopconfirm>
      </NSpace>
    )
  }
]);

// ================================================================
// 执行记录抽屉
// ================================================================
const runDrawerVisible = ref(false);
const runHistoryStrategy = ref<Api.Strategy.StrategyItem | null>(null);
const runList = ref<Api.Strategy.StrategyRunItem[]>([]);
const runLoading = ref(false);

function openRunHistory(row: Api.Strategy.StrategyItem) {
  runHistoryStrategy.value = row;
  runDrawerVisible.value = true;
  loadRunHistory();
}

async function loadRunHistory() {
  if (!runHistoryStrategy.value) return;
  runLoading.value = true;
  try {
    const { data, error } = await fetchGetStrategyRuns(runHistoryStrategy.value.id, { page: 1, page_size: 50 });
    if (!error) runList.value = data?.records ?? [];
  } finally {
    runLoading.value = false;
  }
}

function sigTagType(action: string) {
  if (action === 'buy') return 'error';
  if (action === 'sell') return 'success';
  return 'default';
}

const runColumns = computed<DataTableColumns<Api.Strategy.StrategyRunItem>>(() => [
  {
    key: 'created_at',
    title: $t('page.aiStrategy.execTime'),
    width: 140,
    render: row => <span class="text-12px">{fmtTime(row.created_at)}</span>
  },
  {
    key: 'run_period',
    title: $t('page.aiStrategy.execPeriod'),
    width: 110,
    render: row => (
      <NTag size="small" bordered={false}>
        {PERIOD_LABEL[row.run_period] ?? row.run_period}
      </NTag>
    )
  },
  {
    key: 'status',
    title: $t('page.aiStrategy.execStatus'),
    width: 80,
    render: row => {
      if (row.status === 'running') {
        return (
          <NTag type="info" size="small" bordered={false}>
            {$t('page.aiStrategy.execRunning')}
          </NTag>
        );
      }
      return row.status === 'success' ? (
        <NTag type="success" size="small" bordered={false}>
          {$t('page.aiStrategy.execOk')}
        </NTag>
      ) : (
        <NTag type="error" size="small" bordered={false}>
          {$t('page.aiStrategy.execFail')}
        </NTag>
      );
    }
  },
  { key: 'opened_count', title: $t('page.aiStrategy.openedCount'), width: 80, align: 'right' },
  { key: 'closed_count', title: $t('page.aiStrategy.closedCount2'), width: 80, align: 'right' },
  {
    key: 'signals',
    title: $t('page.aiStrategy.signalsCol'),
    minWidth: 200,
    render: row => (
      <div>
        {(row.parsed_signals ?? []).map(sig => (
          <div key={sig.stock_code} class="text-12px">
            <NTag size="tiny" bordered={false} type={sigTagType(sig.action)} class="mr-4px">
              {sig.action}
            </NTag>
            {sig.stock_name}({sig.stock_code}){sig.reason ? ` — ${sig.reason}` : ''}
          </div>
        ))}
        {row.error_msg ? (
          <NText type="error" class="text-12px">
            {row.error_msg}
          </NText>
        ) : null}
      </div>
    )
  }
]);

// ================================================================
// 持仓跟踪
// ================================================================
const positionSearch = reactive({
  strategy_id: undefined as number | undefined,
  status: 'holding' as Api.Strategy.PositionStatus | undefined,
  stock_code: ''
});
/** 建仓时间段筛选（时间戳毫秒） */
const positionTimeRange = ref<[number, number] | null>(null);
/** 服务端排序状态（column key -> 后端 sort_by 映射） */
const SORT_KEY_MAP: Record<string, string> = {
  buy_time: 'buy_time',
  sell_time: 'sell_time',
  floating_pnl_pct: 'pnl',
  return_rate: 'return_rate'
};
const positionSort = reactive({ by: undefined as string | undefined, desc: false });
/** 策略筛选下拉选项（独立全量加载，不受策略 Tab 搜索影响） */
const strategyFilterOptions = ref<{ value: number; label: string }[]>([]);

async function loadStrategyFilterOptions() {
  const { data, error } = await fetchGetStrategyList({ page: 1, page_size: 100 });
  if (!error) {
    strategyFilterOptions.value = (data?.records ?? []).map(s => ({ value: s.id, label: s.name }));
  }
}

const positionList = ref<Api.Strategy.PositionItem[]>([]);
const positionTotal = ref(0);
const positionPage = reactive({ page: 1, pageSize: 20 });
const positionLoading = ref(false);
const tracking = ref(false);

async function loadPositions(silent = false) {
  if (!silent) positionLoading.value = true;
  try {
    const range = positionTimeRange.value;
    const { data, error } = await fetchGetStrategyPositions({
      strategy_id: positionSearch.strategy_id,
      status: positionSearch.status,
      stock_code: positionSearch.stock_code || undefined,
      start_time: range ? dayjs(range[0]).format('YYYY-MM-DDTHH:mm:ss') : undefined,
      end_time: range ? dayjs(range[1]).format('YYYY-MM-DDTHH:mm:ss') : undefined,
      sort_by: positionSort.by,
      sort_desc: positionSort.by ? positionSort.desc : undefined,
      page: positionPage.page,
      page_size: positionPage.pageSize
    });
    if (!error) {
      positionList.value = data?.records ?? [];
      positionTotal.value = data?.total ?? 0;
    }
  } finally {
    if (!silent) positionLoading.value = false;
  }
}

function searchPositions() {
  positionPage.page = 1;
  loadPositions();
}

function onPositionPageChange(page: number) {
  positionPage.page = page;
  loadPositions();
}

/** 服务端排序：表格列排序变化 */
function onPositionSorterChange(sorter: DataTableSortState | DataTableSortState[] | null) {
  const state = Array.isArray(sorter) ? sorter[0] : sorter;
  const key = state?.columnKey ? String(state.columnKey) : '';
  positionSort.by = SORT_KEY_MAP[key];
  positionSort.desc = state?.order === 'descend';
  searchPositions();
}

async function onTrack() {
  tracking.value = true;
  try {
    const { data, error } = await fetchTrackStrategyPositions();
    if (!error) {
      window.$message?.success(
        $t('page.aiStrategy.trackDone', { tracked: data?.tracked ?? 0, closed: data?.closed ?? 0 })
      );
      await Promise.all([loadPositions(true), loadStats(true)]);
    }
  } finally {
    tracking.value = false;
  }
}

async function onClosePosition(row: Api.Strategy.PositionItem) {
  const { error } = await fetchCloseStrategyPosition(row.id, {});
  if (!error) {
    window.$message?.success($t('page.aiStrategy.closeSuccess'));
    await Promise.all([loadPositions(true), loadStats(true)]);
  }
}

function pnlColor(val: number | null) {
  if (val === null || val === undefined) return '#8c8c8c';
  if (val > 0) return '#f5222d';
  if (val < 0) return '#52c41a';
  return '#8c8c8c';
}

function renderPct(val: number | null) {
  if (val === null || val === undefined) return <NText depth={3}>-</NText>;
  const sign = val > 0 ? '+' : '';
  return (
    <span style={{ color: pnlColor(val), fontWeight: '500' }}>
      {sign}
      {Number(val).toFixed(2)}%
    </span>
  );
}

const positionColumns = computed<DataTableColumns<Api.Strategy.PositionItem>>(() => [
  {
    key: 'stock_name',
    title: $t('page.aiStrategy.stock'),
    width: 170,
    render: row => (
      <div class="flex items-center gap-8px">
        <span class="font-500">{row.stock_name}</span>
        <NText depth={3} style={{ fontSize: '12px', fontFamily: 'monospace' }}>
          {row.stock_code}
        </NText>
      </div>
    )
  },
  {
    key: 'strategy_name',
    title: $t('page.aiStrategy.strategyCol'),
    width: 120,
    render: row => (
      <NTag size="small" bordered={false}>
        {row.strategy_name}
      </NTag>
    )
  },
  {
    key: 'buy_price',
    title: $t('page.aiStrategy.buyPrice'),
    width: 90,
    align: 'right',
    render: row => <span>{Number(row.buy_price).toFixed(2)}</span>
  },
  {
    key: 'buy_time',
    title: $t('page.aiStrategy.buyTime'),
    width: 140,
    sorter: true,
    render: row => <span class="text-12px">{fmtTime(row.buy_time)}</span>
  },
  {
    key: 'target_sell_price',
    title: $t('page.aiStrategy.targetSell'),
    width: 100,
    align: 'right',
    render: row => (
      <span style={{ color: '#faad14' }}>{row.target_sell_price ? Number(row.target_sell_price).toFixed(2) : '-'}</span>
    )
  },
  {
    key: 'stop_loss_price',
    title: $t('page.aiStrategy.stopLossPrice'),
    width: 90,
    align: 'right',
    render: row => (
      <span style={{ color: '#52c41a' }}>{row.stop_loss_price ? Number(row.stop_loss_price).toFixed(2) : '-'}</span>
    )
  },
  {
    key: 'latest_price',
    title: $t('page.aiStrategy.latestPrice'),
    width: 90,
    align: 'right',
    render: row => (
      <span style={{ fontWeight: '500' }}>{row.latest_price ? Number(row.latest_price).toFixed(2) : '-'}</span>
    )
  },
  {
    key: 'floating_pnl_pct',
    title: $t('page.aiStrategy.floatingPnl'),
    width: 100,
    align: 'right',
    sorter: true,
    render: row => renderPct(row.floating_pnl_pct)
  },
  {
    key: 'status',
    title: $t('page.aiStrategy.positionStatus'),
    width: 120,
    render: row => {
      if (row.status === 'holding') {
        return (
          <NTag type="info" size="small" bordered={false}>
            {$t('page.aiStrategy.statusHolding')}
          </NTag>
        );
      }
      const label = SELL_REASON_LABEL[row.sell_reason ?? ''] ?? row.sell_reason ?? '-';
      return (
        <NSpace size={4} align="center">
          <NTag type="default" size="small" bordered={false}>
            {$t('page.aiStrategy.statusClosed')}
          </NTag>
          <NText depth={3} style={{ fontSize: '11px' }}>
            {label}
          </NText>
        </NSpace>
      );
    }
  },
  {
    key: 'return_rate',
    title: $t('page.aiStrategy.returnRate'),
    width: 100,
    align: 'right',
    sorter: true,
    render: row => renderPct(row.return_rate)
  },
  {
    key: 'sell_price',
    title: $t('page.aiStrategy.sellPrice'),
    width: 90,
    align: 'right',
    render: row =>
      row.sell_price ? (
        <span style={{ fontWeight: '500' }}>{Number(row.sell_price).toFixed(2)}</span>
      ) : (
        <NText depth={3}>-</NText>
      )
  },
  {
    key: 'sell_time',
    title: $t('page.aiStrategy.sellTime'),
    width: 140,
    sorter: true,
    render: row => <span class="text-12px">{row.sell_time ? fmtTime(row.sell_time) : '-'}</span>
  },
  {
    key: 'actions',
    title: $t('common.action'),
    width: 90,
    align: 'center',
    render: row =>
      row.status === 'holding' ? (
        <NPopconfirm onPositiveClick={() => onClosePosition(row)}>
          {{
            trigger: () => (
              <NButton size="tiny" type="warning" ghost>
                {$t('page.aiStrategy.close')}
              </NButton>
            ),
            default: () => $t('page.aiStrategy.closeConfirm')
          }}
        </NPopconfirm>
      ) : null
  }
]);

// ================================================================
// 回报率统计
// ================================================================
const statsList = ref<Api.Strategy.StrategyStatsItem[]>([]);
const statsLoading = ref(false);

/** 净值曲线 / 归因的策略选择（必填，独立于表格筛选） */
const statsStrategyId = ref<number | null>(null);
const equityCurve = ref<Api.Strategy.EquityCurvePoint[]>([]);
const curveLoading = ref(false);
const attribution = ref<Api.Strategy.AttributionResult | null>(null);
const attributionLoading = ref(false);

async function loadStats(silent = false) {
  if (!silent) statsLoading.value = true;
  try {
    const { data, error } = await fetchGetStrategyStats();
    if (!error) statsList.value = data ?? [];
  } finally {
    if (!silent) statsLoading.value = false;
  }
}

async function loadEquityCurve() {
  if (!statsStrategyId.value) {
    equityCurve.value = [];
    return;
  }
  curveLoading.value = true;
  try {
    const { data, error } = await fetchGetStrategyEquityCurve(statsStrategyId.value);
    if (!error) equityCurve.value = data ?? [];
  } finally {
    curveLoading.value = false;
  }
}

async function loadAttribution() {
  if (!statsStrategyId.value) {
    attribution.value = null;
    return;
  }
  attributionLoading.value = true;
  try {
    const { data, error } = await fetchGetStrategyAttribution(statsStrategyId.value);
    if (!error) attribution.value = data ?? null;
  } finally {
    attributionLoading.value = false;
  }
}

// 策略选择变化时联动刷新净值曲线与归因
watch(statsStrategyId, () => {
  loadEquityCurve();
  loadAttribution();
});

// 选项晚于 Tab 加载完成时补默认值
watch(strategyFilterOptions, opts => {
  if (activeTab.value === 'stats' && !statsStrategyId.value && opts.length) {
    statsStrategyId.value = opts[0].value;
  }
});

/** 归因-卖出原因中文化（缺组时回退原始值） */
const SELL_REASON_LABEL: Record<string, string> = {
  stop_loss: $t('page.aiStrategy.reasonStopLoss'),
  target_reached: $t('page.aiStrategy.reasonTarget'),
  trailing_stop: $t('page.aiStrategy.reasonTrailingStop'),
  ai_signal: $t('page.aiStrategy.reasonAi'),
  manual: $t('page.aiStrategy.reasonManual')
};

/** 归因-执行时段中文化（unknown = 存量 run_id 为 NULL 的历史持仓） */
const RUN_PERIOD_LABEL: Record<string, string> = {
  pre_market: $t('page.aiStrategy.periodPreMarket'),
  morning: $t('page.aiStrategy.periodMorning'),
  noon: $t('page.aiStrategy.periodNoon'),
  tail: $t('page.aiStrategy.periodTail'),
  post_close: $t('page.aiStrategy.periodPostClose'),
  manual: $t('page.aiStrategy.periodManual'),
  review: $t('page.aiStrategy.periodReview'),
  unknown: $t('page.aiStrategy.periodUnknown')
};

function attributionColumns<T extends Api.Strategy.AttributionMetrics>(labelOf: (row: T) => string) {
  return computed<DataTableColumns<T>>(() => [
    {
      key: 'name',
      title: $t('page.aiStrategy.attrName'),
      minWidth: 90,
      render: row => <span class="font-500">{labelOf(row)}</span>
    },
    { key: 'count', title: $t('page.aiStrategy.attrCount'), width: 70, align: 'right' },
    {
      key: 'win_rate',
      title: $t('page.aiStrategy.winRate'),
      width: 80,
      align: 'right',
      render: row => (row.win_rate === null ? <NText depth={3}>-</NText> : <span>{`${Number(row.win_rate).toFixed(1)}%`}</span>)
    },
    {
      key: 'avg_return',
      title: $t('page.aiStrategy.avgReturn'),
      width: 90,
      align: 'right',
      render: row => renderPct(row.avg_return)
    },
    {
      key: 'total_return',
      title: $t('page.aiStrategy.attrTotalReturn'),
      width: 100,
      align: 'right',
      render: row => renderPct(row.total_return)
    }
  ]);
}

const sellReasonColumns = attributionColumns<Api.Strategy.SellReasonAttributionItem>(
  row => SELL_REASON_LABEL[row.reason] ?? row.reason
);
const runPeriodColumns = attributionColumns<Api.Strategy.RunPeriodAttributionItem>(
  row => RUN_PERIOD_LABEL[row.period] ?? row.period
);

const statsColumns = computed<DataTableColumns<Api.Strategy.StrategyStatsItem>>(() => [
  {
    key: 'strategy_name',
    title: $t('page.aiStrategy.strategyCol'),
    width: 140,
    render: row => <span class="font-500">{row.strategy_name}</span>
  },
  { key: 'holding_count', title: $t('page.aiStrategy.holdingCount'), width: 90, align: 'right' },
  { key: 'closed_count', title: $t('page.aiStrategy.closedCount'), width: 90, align: 'right' },
  {
    key: 'win_count',
    title: $t('page.aiStrategy.winCount'),
    width: 90,
    align: 'right',
    render: row => <span style={{ color: '#f5222d' }}>{row.win_count}</span>
  },
  {
    key: 'loss_count',
    title: $t('page.aiStrategy.lossCount'),
    width: 90,
    align: 'right',
    render: row => <span style={{ color: '#52c41a' }}>{row.loss_count}</span>
  },
  {
    key: 'win_rate',
    title: $t('page.aiStrategy.winRate'),
    width: 90,
    align: 'right',
    render: row => renderPct(row.win_rate)
  },
  {
    key: 'total_return_rate',
    title: $t('page.aiStrategy.totalReturn'),
    width: 110,
    align: 'right',
    render: row => renderPct(row.total_return_rate)
  },
  {
    key: 'compound_return_rate',
    title: () => (
      <span class="inline-flex items-center gap-2px">
        {$t('page.aiStrategy.compoundReturn')}
        <IconTooltip desc={$t('page.aiStrategy.compoundTip')} />
      </span>
    ),
    width: 110,
    align: 'right',
    render: row => renderPct(row.compound_return_rate)
  },
  {
    key: 'avg_return_rate',
    title: $t('page.aiStrategy.avgReturn'),
    width: 100,
    align: 'right',
    render: row => renderPct(row.avg_return_rate)
  },
  {
    key: 'best_return_rate',
    title: $t('page.aiStrategy.bestReturn'),
    width: 100,
    align: 'right',
    render: row => renderPct(row.best_return_rate)
  },
  {
    key: 'worst_return_rate',
    title: $t('page.aiStrategy.worstReturn'),
    width: 100,
    align: 'right',
    render: row => renderPct(row.worst_return_rate)
  }
]);

const totalReturn = computed(() => statsList.value.reduce((sum, s) => sum + (s.total_return_rate ?? 0), 0));
const totalClosed = computed(() => statsList.value.reduce((sum, s) => sum + s.closed_count, 0));
const totalWin = computed(() => statsList.value.reduce((sum, s) => sum + s.win_count, 0));

// ================================================================
// 自动刷新（持仓跟踪 Tab 交易时段自动刷新）
// ================================================================
const { lastRefreshTime } = useAutoRefresh(
  async (silent: boolean) => {
    if (activeTab.value === 'positions') await loadPositions(silent);
  },
  { interval: 60_000 }
);

watch(activeTab, tab => {
  if (tab === 'positions') loadPositions();
  if (tab === 'stats') {
    loadStats();
    // 默认选中首个策略以联动净值曲线与归因
    if (!statsStrategyId.value && strategyFilterOptions.value.length) {
      statsStrategyId.value = strategyFilterOptions.value[0].value;
    }
  }
});

onMounted(() => {
  loadStrategies();
  loadStrategyFilterOptions();
});
</script>

<template>
  <div class="min-h-500px flex-col-stretch gap-16px overflow-hidden lt-sm:overflow-auto">
    <NCard :bordered="false" size="small" class="card-wrapper sm:flex-1-hidden">
      <template #header>
        <NTabs v-model:value="activeTab" type="line" animated size="large">
          <NTabPane name="strategies" :tab="$t('page.aiStrategy.tabStrategies')" />
          <NTabPane name="positions" :tab="$t('page.aiStrategy.tabPositions')" />
          <NTabPane name="stats" :tab="$t('page.aiStrategy.tabStats')" />
          <NTabPane name="templates" :tab="$t('page.aiStrategy.tabTemplates')" />
        </NTabs>
      </template>

      <template #header-extra>
        <!-- ============ 策略管理 ============ -->
        <NSpace v-if="activeTab === 'strategies'" align="center" :size="12">
          <NInput
            v-model:value="strategySearch.name"
            size="small"
            clearable
            :placeholder="$t('page.aiStrategy.searchName')"
            class="w-160px"
            @keyup.enter="searchStrategies"
          />
          <NSelect
            v-model:value="strategySearch.category"
            size="small"
            clearable
            :placeholder="$t('page.aiStrategy.searchCategory')"
            :options="CATEGORY_OPTIONS"
            class="w-130px"
            @update:value="searchStrategies"
          />
          <NButton size="small" type="primary" @click="openCreate">
            <template #icon><icon-mdi-plus class="text-icon" /></template>
            {{ $t('page.aiStrategy.createStrategy') }}
          </NButton>
        </NSpace>

        <!-- ============ 持仓跟踪 ============ -->
        <NSpace v-else-if="activeTab === 'positions'" align="center" :size="12" :wrap="false">
          <NSelect
            v-model:value="positionSearch.strategy_id"
            size="small"
            clearable
            filterable
            :placeholder="$t('page.aiStrategy.filterStrategy')"
            :options="strategyFilterOptions"
            class="w-140px"
            @update:value="searchPositions"
          />
          <NDatePicker
            v-model:value="positionTimeRange"
            type="datetimerange"
            size="small"
            clearable
            :placeholder="$t('page.aiStrategy.filterTimeRange')"
            class="w-280px"
            @update:value="searchPositions"
          />
          <NInput
            v-model:value="positionSearch.stock_code"
            size="small"
            clearable
            :placeholder="$t('page.aiStrategy.searchCode')"
            class="w-140px"
            @keyup.enter="searchPositions"
          />
          <NButton
            size="small"
            :type="positionSearch.status === 'holding' ? 'primary' : 'default'"
            @click="
              () => {
                positionSearch.status = 'holding';
                searchPositions();
              }
            "
          >
            {{ $t('page.aiStrategy.statusHolding') }}
          </NButton>
          <NButton
            size="small"
            :type="positionSearch.status === 'closed' ? 'primary' : 'default'"
            @click="
              () => {
                positionSearch.status = 'closed';
                searchPositions();
              }
            "
          >
            {{ $t('page.aiStrategy.statusClosed') }}
          </NButton>
          <NButton
            size="small"
            quaternary
            @click="
              () => {
                positionSearch.status = undefined;
                searchPositions();
              }
            "
          >
            {{ $t('page.aiStrategy.statusAll') }}
          </NButton>
          <NButton size="small" type="primary" ghost :loading="tracking" @click="onTrack">
            <template #icon><icon-mdi-radar class="text-icon" /></template>
            {{ $t('page.aiStrategy.trackNow') }}
          </NButton>
        </NSpace>
      </template>

      <template v-if="activeTab === 'strategies'">
        <NDataTable
          :columns="strategyColumns"
          :data="strategyList"
          size="small"
          :loading="strategyLoading"
          :scroll-x="1350"
          :row-key="(row: Api.Strategy.StrategyItem) => row.id"
        />
        <div class="mt-12px flex justify-end">
          <NPagination
            :page="strategyPage.page"
            :page-size="strategyPage.pageSize"
            :item-count="strategyTotal"
            @update:page="onStrategyPageChange"
          />
        </div>
      </template>

      <!-- ============ 持仓跟踪 ============ -->
      <template v-else-if="activeTab === 'positions'">
        <div class="h-full flex-col-stretch">
          <NDataTable
            :columns="positionColumns"
            :data="positionList"
            size="small"
            :loading="positionLoading"
            :scroll-x="1550"
            :flex-height="!appStore.isMobile"
            remote
            class="flex-1-hidden"
            :row-key="(row: Api.Strategy.PositionItem) => row.id"
            @update:sorter="onPositionSorterChange"
          />
          <div class="mt-12px flex items-center justify-between">
            <NText depth="3" class="text-12px">
              <icon-mdi-clock-outline class="text-14px" />
              {{ $t('page.aiStrategy.lastTrack') }}
              {{ lastRefreshTime ? lastRefreshTime.format('HH:mm:ss') : '-' }}
            </NText>
            <NPagination
              :page="positionPage.page"
              :page-size="positionPage.pageSize"
              :item-count="positionTotal"
              @update:page="onPositionPageChange"
            />
          </div>
        </div>
      </template>

      <!-- ============ 策略模板 ============ -->
      <template v-else-if="activeTab === 'templates'">
        <StrategyTemplate @changed="loadStrategies(true)" />
      </template>

      <!-- ============ 回报率统计 ============ -->
      <template v-else-if="activeTab === 'stats'">
        <NSpace :size="24" class="mb-16px">
          <NStatistic :label="$t('page.aiStrategy.totalReturn')" tabular-nums>
            <span :style="{ color: pnlColor(totalReturn), fontWeight: '600' }">
              {{ totalReturn > 0 ? '+' : '' }}{{ totalReturn.toFixed(2) }}%
            </span>
          </NStatistic>
          <NStatistic :label="$t('page.aiStrategy.closedCount')" :value="totalClosed" tabular-nums />
          <NStatistic :label="$t('page.aiStrategy.winRate')" tabular-nums>
            <span style="font-weight: 600">
              {{ totalClosed > 0 ? ((totalWin / totalClosed) * 100).toFixed(1) : '--' }}%
            </span>
          </NStatistic>
        </NSpace>
        <NDataTable
          :columns="statsColumns"
          :data="statsList"
          size="small"
          :loading="statsLoading"
          :scroll-x="1250"
          :row-key="(row: Api.Strategy.StrategyStatsItem) => row.strategy_id"
        />

        <!-- 净值曲线 + 归因（按选定策略联动） -->
        <NSpace align="center" :size="12" class="mb-12px mt-16px">
          <NText class="font-500">{{ $t('page.aiStrategy.equityCurve') }}</NText>
          <NSelect
            v-model:value="statsStrategyId"
            size="small"
            filterable
            :placeholder="$t('page.aiStrategy.filterStrategy')"
            :options="strategyFilterOptions"
            class="w-200px"
          />
        </NSpace>
        <template v-if="statsStrategyId">
          <NSpin :show="curveLoading">
            <EquityChart v-if="equityCurve.length" :data="equityCurve" />
            <div v-else class="h-60px flex-center">
              <NText depth="3" class="text-12px">{{ $t('common.noData') }}</NText>
            </div>
          </NSpin>
          <NGrid :cols="2" :x-gap="16" responsive="screen" item-responsive class="mt-16px">
            <NGi span="2 m:1">
              <NText class="mb-8px block font-500">{{ $t('page.aiStrategy.bySellReason') }}</NText>
              <NDataTable
                :columns="sellReasonColumns"
                :data="attribution?.by_sell_reason ?? []"
                size="small"
                :loading="attributionLoading"
                :row-key="(row: Api.Strategy.SellReasonAttributionItem) => row.reason"
              />
            </NGi>
            <NGi span="2 m:1">
              <NText class="mb-8px block font-500">{{ $t('page.aiStrategy.byRunPeriod') }}</NText>
              <NDataTable
                :columns="runPeriodColumns"
                :data="attribution?.by_run_period ?? []"
                size="small"
                :loading="attributionLoading"
                :row-key="(row: Api.Strategy.RunPeriodAttributionItem) => row.period"
              />
            </NGi>
          </NGrid>
        </template>
        <div v-else class="mt-8px">
          <NText depth="3" class="text-12px">{{ $t('page.aiStrategy.statsSelectStrategy') }}</NText>
        </div>
      </template>
    </NCard>

    <!-- 策略配置抽屉 -->
    <StrategyOperateDrawer v-model:visible="drawerVisible" :editing="editingStrategy" @submitted="onDrawerSubmitted" />

    <!-- 发布为模板弹窗（可覆盖标签） -->
    <NModal
      v-model:show="publishVisible"
      preset="card"
      :title="$t('page.aiStrategy.publishTitle', { name: publishingStrategy?.name ?? '' })"
      class="w-480px"
    >
      <NSpace vertical :size="12">
        <NText depth="2">{{ $t('page.aiStrategy.publishTags') }}</NText>
        <NDynamicTags v-model:value="publishTags" :max="10" />
        <NText depth="3" class="text-12px">{{ $t('page.aiStrategy.publishTip') }}</NText>
      </NSpace>
      <template #footer>
        <NSpace justify="end" :size="12">
          <NButton @click="publishVisible = false">{{ $t('common.cancel') }}</NButton>
          <NButton type="primary" :loading="publishing" @click="onPublishSubmit">
            {{ $t('page.aiStrategy.publish') }}
          </NButton>
        </NSpace>
      </template>
    </NModal>

    <!-- 执行记录抽屉 -->
    <NDrawer v-model:show="runDrawerVisible" :width="640">
      <NDrawerContent
        :title="$t('page.aiStrategy.runHistoryOf', { name: runHistoryStrategy?.name ?? '' })"
        closable
        :native-scrollbar="false"
      >
        <NDataTable
          :columns="runColumns"
          :data="runList"
          size="small"
          :loading="runLoading"
          :row-key="(row: Api.Strategy.StrategyRunItem) => row.id"
          :flex-height="false"
        />
      </NDrawerContent>
    </NDrawer>
  </div>
</template>

<style scoped></style>
