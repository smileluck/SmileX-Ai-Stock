<script setup lang="tsx">
import { computed, reactive, ref, watch } from 'vue';
import { NAlert, NDataTable, NDrawer, NDrawerContent, NGi, NGrid, NPagination, NSpace, NSpin, NStatistic, NTag, NText } from 'naive-ui';
import type { DataTableColumns } from 'naive-ui';
import { fetchGetBacktestDetail, fetchGetBacktestTrades } from '@/service/api';
import { useAutoRefresh } from '@/hooks/common/auto-refresh';
import { $t } from '@/locales';
import EquityChart from '@/components/common/equity-chart.vue';

/**
 * 回测详情抽屉：绩效卡片网格 + 收益曲线 + 告警 + 成交明细分页表
 * 运行中的回测每 10s 轮询刷新，success/failed 后停止
 */
defineOptions({ name: 'BacktestDetailDrawer' });

interface Props {
  visible: boolean;
  backtestId: number | null;
}

const props = defineProps<Props>();

const emit = defineEmits<{
  (e: 'update:visible', visible: boolean): void;
}>();

const drawerVisible = computed({
  get: () => props.visible,
  set: v => emit('update:visible', v)
});

const detail = ref<Api.Backtest.BacktestDetail | null>(null);
const detailLoading = ref(false);

const tradeList = ref<Api.Backtest.BacktestTradeItem[]>([]);
const tradeTotal = ref(0);
const tradePage = reactive({ page: 1, pageSize: 10 });
const tradeLoading = ref(false);

async function loadDetail(silent = false) {
  if (!props.backtestId) return;
  if (!silent) detailLoading.value = true;
  try {
    const { data, error } = await fetchGetBacktestDetail(props.backtestId);
    if (!error) detail.value = data ?? null;
  } finally {
    if (!silent) detailLoading.value = false;
  }
}

async function loadTrades(silent = false) {
  if (!props.backtestId) return;
  if (!silent) tradeLoading.value = true;
  try {
    const { data, error } = await fetchGetBacktestTrades(props.backtestId, {
      page: tradePage.page,
      page_size: tradePage.pageSize
    });
    if (!error) {
      tradeList.value = data?.records ?? [];
      tradeTotal.value = data?.total ?? 0;
    }
  } finally {
    if (!silent) tradeLoading.value = false;
  }
}

function onTradePageChange(page: number) {
  tradePage.page = page;
  loadTrades();
}

// 运行中的回测每 10s 轮询刷新详情与成交明细，终态（success/failed）自动停止
useAutoRefresh(
  async (silent: boolean) => {
    await Promise.all([loadDetail(silent), loadTrades(silent)]);
  },
  { interval: 10_000, shouldRefresh: () => props.visible && detail.value?.status === 'running' }
);

watch(
  () => [props.visible, props.backtestId] as const,
  ([visible, id]) => {
    if (visible && id) {
      tradePage.page = 1;
      loadDetail();
      loadTrades();
    }
  }
);

// ------------------------------------------------------------------
// 展示辅助
// ------------------------------------------------------------------
function pnlColor(val: number | null) {
  if (val === null || val === undefined) return '#8c8c8c';
  if (val > 0) return '#f5222d';
  if (val < 0) return '#52c41a';
  return '#8c8c8c';
}

function fmtPct(val: number | null) {
  if (val === null || val === undefined) return '--';
  return `${val > 0 ? '+' : ''}${Number(val).toFixed(2)}%`;
}

function fmtNum(val: number | null) {
  if (val === null || val === undefined) return '--';
  return Number(val).toFixed(2);
}

function fmtMoney(val: number | null) {
  if (val === null || val === undefined) return '--';
  return Number(val).toLocaleString('zh-CN', { maximumFractionDigits: 2 });
}

const STATUS_TAG: Record<Api.Backtest.BacktestStatus, 'info' | 'success' | 'error'> = {
  running: 'info',
  success: 'success',
  failed: 'error'
};

const STATUS_LABEL: Record<Api.Backtest.BacktestStatus, string> = {
  running: $t('page.aiBacktest.statusRunning'),
  success: $t('page.aiBacktest.statusSuccess'),
  failed: $t('page.aiBacktest.statusFailed')
};

const SELL_REASON_LABEL: Record<string, string> = {
  stop_loss: $t('page.aiBacktest.reasonStopLoss'),
  target_reached: $t('page.aiBacktest.reasonTarget'),
  trailing_stop: $t('page.aiBacktest.reasonTrailingStop'),
  ai_signal: $t('page.aiBacktest.reasonAi'),
  backtest_end: $t('page.aiBacktest.reasonBacktestEnd')
};

const tradeColumns = computed<DataTableColumns<Api.Backtest.BacktestTradeItem>>(() => [
  {
    key: 'action',
    title: $t('page.aiBacktest.action'),
    width: 70,
    align: 'center',
    render: row =>
      row.action === 'buy' ? (
        <NTag type="error" size="small" bordered={false}>
          {$t('page.aiBacktest.actionBuy')}
        </NTag>
      ) : (
        <NTag type="success" size="small" bordered={false}>
          {$t('page.aiBacktest.actionSell')}
        </NTag>
      )
  },
  {
    key: 'stock_name',
    title: $t('page.aiBacktest.stock'),
    width: 150,
    render: row => (
      <div class="flex items-center gap-6px">
        <span class="font-500">{row.stock_name}</span>
        <NText depth={3} style={{ fontSize: '12px', fontFamily: 'monospace' }}>
          {row.stock_code}
        </NText>
      </div>
    )
  },
  { key: 'trade_date', title: $t('page.aiBacktest.tradeDate'), width: 100 },
  {
    key: 'price',
    title: $t('page.aiBacktest.price'),
    width: 90,
    align: 'right',
    render: row => <span>{Number(row.price).toFixed(2)}</span>
  },
  { key: 'quantity', title: $t('page.aiBacktest.quantity'), width: 80, align: 'right' },
  {
    key: 'amount',
    title: $t('page.aiBacktest.amount'),
    width: 110,
    align: 'right',
    render: row => <span>{fmtMoney(row.amount)}</span>
  },
  {
    key: 'fee',
    title: $t('page.aiBacktest.fee'),
    width: 80,
    align: 'right',
    render: row => <span>{fmtNum(row.fee)}</span>
  },
  {
    key: 'return_rate',
    title: $t('page.aiBacktest.returnRate'),
    width: 90,
    align: 'right',
    render: row => {
      if (row.action === 'buy' || row.return_rate === null) return <NText depth={3}>-</NText>;
      return (
        <span style={{ color: pnlColor(row.return_rate), fontWeight: '500' }}>{fmtPct(row.return_rate)}</span>
      );
    }
  },
  {
    key: 'reason',
    title: $t('page.aiBacktest.reason'),
    minWidth: 140,
    render: row => {
      if (row.action === 'sell') return <span>{SELL_REASON_LABEL[row.reason ?? ''] ?? row.reason ?? '-'}</span>;
      return (
        <NText depth={2} class="text-12px">
          {row.reason ?? '-'}
        </NText>
      );
    }
  }
]);
</script>

<template>
  <NDrawer v-model:show="drawerVisible" :width="860">
    <NDrawerContent
      :title="$t('page.aiBacktest.detailTitle', { name: detail?.strategy_name ?? '' })"
      closable
      :native-scrollbar="false"
    >
      <div v-if="detail" class="flex-col-stretch gap-16px">
        <NSpace align="center" :size="12">
          <NTag :type="STATUS_TAG[detail.status]" :bordered="false">{{ STATUS_LABEL[detail.status] }}</NTag>
          <NTag size="small" :bordered="false" type="default">
            {{ $t('page.aiBacktest.slippageModel') }}:
            {{ detail.slippage_model === 'amp' ? $t('page.aiBacktest.slippageAmp') : $t('page.aiBacktest.slippageFixed') }}
          </NTag>
          <NText depth="3" class="text-12px">{{ detail.start_date }} ~ {{ detail.end_date }}</NText>
          <NText depth="3" class="text-12px">
            {{ $t('page.aiBacktest.formCapital') }}: {{ fmtMoney(detail.initial_capital) }}
          </NText>
        </NSpace>

        <NAlert v-if="detail.status === 'failed' && detail.error_msg" type="error" :bordered="false">
          {{ detail.error_msg }}
        </NAlert>

        <template v-if="detail.result">
          <NGrid :cols="4" :x-gap="12" :y-gap="12" responsive="screen" item-responsive>
            <NGi span="4 s:2 m:1">
              <NStatistic :label="$t('page.aiBacktest.totalReturn')" tabular-nums>
                <span :style="{ color: pnlColor(detail.result.total_return_pct), fontWeight: '600' }">
                  {{ fmtPct(detail.result.total_return_pct) }}
                </span>
              </NStatistic>
            </NGi>
            <NGi span="4 s:2 m:1">
              <NStatistic :label="$t('page.aiBacktest.annualReturn')" tabular-nums>
                <span :style="{ color: pnlColor(detail.result.annual_return_pct) }">
                  {{ fmtPct(detail.result.annual_return_pct) }}
                </span>
              </NStatistic>
            </NGi>
            <NGi span="4 s:2 m:1">
              <NStatistic :label="$t('page.aiBacktest.maxDrawdown')" tabular-nums>
                <span style="color: #52c41a">{{ fmtPct(detail.result.max_drawdown_pct) }}</span>
              </NStatistic>
            </NGi>
            <NGi span="4 s:2 m:1">
              <NStatistic :label="$t('page.aiBacktest.sharpe')" tabular-nums>
                {{ fmtNum(detail.result.sharpe) }}
              </NStatistic>
            </NGi>
            <NGi span="4 s:2 m:1">
              <NStatistic :label="$t('page.aiBacktest.winRate')" tabular-nums>
                {{ detail.result.win_rate !== null ? `${Number(detail.result.win_rate).toFixed(1)}%` : '--' }}
              </NStatistic>
            </NGi>
            <NGi span="4 s:2 m:1">
              <NStatistic :label="$t('page.aiBacktest.profitFactor')" tabular-nums>
                {{ fmtNum(detail.result.profit_factor) }}
              </NStatistic>
            </NGi>
            <NGi span="4 s:2 m:1">
              <NStatistic :label="$t('page.aiBacktest.tradeCount')" :value="detail.result.trade_count" tabular-nums />
            </NGi>
            <NGi span="4 s:2 m:1">
              <NStatistic :label="$t('page.aiBacktest.finalEquity')" tabular-nums>
                {{ fmtMoney(detail.result.final_equity) }}
              </NStatistic>
            </NGi>
          </NGrid>

          <NAlert
            v-if="detail.result.warnings?.length"
            type="warning"
            :bordered="false"
            :title="$t('page.aiBacktest.warnings')"
          >
            <div v-for="(w, i) in detail.result.warnings" :key="i" class="text-12px">{{ w }}</div>
          </NAlert>
        </template>

        <template v-if="detail.equity_curve?.length">
          <NText class="font-500">{{ $t('page.aiBacktest.equityCurve') }}</NText>
          <EquityChart :data="detail.equity_curve" />
        </template>

        <template v-if="detail.status !== 'failed'">
          <NText class="font-500">{{ $t('page.aiBacktest.tradesTitle') }}</NText>
          <NDataTable
            :columns="tradeColumns"
            :data="tradeList"
            size="small"
            :loading="tradeLoading"
            :scroll-x="900"
            :row-key="(row: Api.Backtest.BacktestTradeItem) => row.id"
          />
          <div class="flex justify-end">
            <NPagination
              :page="tradePage.page"
              :page-size="tradePage.pageSize"
              :item-count="tradeTotal"
              @update:page="onTradePageChange"
            />
          </div>
        </template>
      </div>
      <NSpin v-else :show="detailLoading" class="h-200px" />
    </NDrawerContent>
  </NDrawer>
</template>

<style scoped></style>
