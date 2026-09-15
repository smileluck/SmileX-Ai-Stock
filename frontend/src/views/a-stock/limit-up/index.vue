<script setup lang="tsx">
import { computed, onMounted, ref } from 'vue';
import {
  NButton,
  NCard,
  NDataTable,
  NDatePicker,
  NGrid,
  NGridItem,
  NPagination,
  NRadioButton,
  NRadioGroup,
  NSpace,
  NStatistic,
  NTag,
  NText,
  NTooltip
} from 'naive-ui';
import type { DataTableColumns } from 'naive-ui';
import dayjs from 'dayjs';
import { fetchGetLimitUpDates, fetchGetLimitUpList, fetchGetLimitUpStats, fetchSyncLimitUp } from '@/service/api';
import { useAppStore } from '@/store/modules/app';
import { useAutoRefresh } from '@/hooks/common/auto-refresh';
import { $t } from '@/locales';
import { isStockAutoRefreshTime } from '../utils';

defineOptions({
  name: 'LimitUp'
});

const appStore = useAppStore();

const UP = '#f5222d';
const DOWN = '#52c41a';
const FLAT = '#8c8c8c';

const selectedDate = ref<number | null>(null);
const marketBoard = ref<Api.StockLimitUp.MarketBoard>('all');
const poolType = ref<Api.StockLimitUp.PoolType>('all');
const page = ref(1);
const pageSize = ref(50);
const total = ref(0);
const availableDates = ref<string[]>([]);
const data = ref<Api.StockLimitUp.LimitUpStockItem[]>([]);
const stats = ref<Api.StockLimitUp.LimitUpStats | null>(null);
const loading = ref(false);
const syncing = ref(false);

const BOARD_LABEL: Record<string, string> = {
  main: '主板',
  chinext: '创业板',
  star: '科创板',
  bse: '北交所'
};
const BOARD_TAG_TYPE: Record<string, 'default' | 'primary' | 'info' | 'warning' | 'success' | 'error'> = {
  main: 'default',
  chinext: 'primary',
  star: 'warning',
  bse: 'info'
};

function renderPoolStatus(row: Api.StockLimitUp.LimitUpStockItem) {
  const broken = row.pool_type === 'broken';
  return (
    <NTag size="small" type={broken ? 'warning' : 'error'} bordered={false}>
      {broken ? $t('page.aStock.limitUp.statusBroken') : $t('page.aStock.limitUp.statusSealed')}
    </NTag>
  );
}

function fmtPct(val: number | null) {
  if (val === null || val === undefined) return '-';
  return `${val > 0 ? '+' : ''}${val.toFixed(2)}%`;
}

function fmtNum(val: number | null, digits = 2) {
  if (val === null || val === undefined) return '-';
  return val.toFixed(digits);
}

function fmtMoney(val: number | null) {
  if (val === null || val === undefined) return '-';
  if (val >= 100000000) return `${(val / 100000000).toFixed(2)}亿`;
  if (val >= 10000) return `${(val / 10000).toFixed(1)}万`;
  return val.toFixed(0);
}

function pctColor(val: number | null) {
  if (val === null || val === undefined) return FLAT;
  return val > 0 ? UP : val < 0 ? DOWN : FLAT;
}

function renderPct(val: number | null) {
  if (val === null || val === undefined) return <NText depth={3}>-</NText>;
  return <span style={{ color: pctColor(val), fontWeight: '500' }}>{fmtPct(val)}</span>;
}

function renderConsecutive(val: number | null) {
  if (!val || val <= 1) return <NText depth={3}>-</NText>;
  const color = val >= 4 ? '#cf1322' : val >= 2 ? '#fa541c' : '#fa8c16';
  return (
    <span class="inline-flex-center" style={{ color, fontWeight: '700', fontSize: '13px' }}>
      {val}
      {'\u8FDE'}
    </span>
  );
}

/** 封板时间 092500 / 09:25:00 → 09:25 展示 */
function fmtSealTime(val: string | null) {
  if (!val) return '-';
  const s = val.replace(':', '');
  if (s.length < 4) return val;
  return `${s.slice(0, 2)}:${s.slice(2, 4)}`;
}

function formatFactor(factor: Api.StockLimitUp.ContinuationFactor) {
  const key = 'page.aStock.limitUp';
  const v = factor.value;
  switch (factor.type) {
    case 'consecutive':
      return $t(`${key}.factorConsecutive`, { n: v ?? '-' });
    case 'seal_ratio':
      return $t(`${key}.factorSealRatio`, { v: v ?? '-' });
    case 'break_count':
      return v === 0
        ? $t(`${key}.factorBreakCountZero`)
        : $t(`${key}.factorBreakCount`, { n: v ?? '-' });
    case 'first_seal':
      return $t(`${key}.factorFirstSeal`, { time: fmtSealTime(typeof v === 'string' ? v : null) });
    case 'turnover_rate':
      return $t(`${key}.factorTurnoverRate`, { v: v ?? '-' });
    default:
      return `${factor.type}: ${v ?? '-'}`;
  }
}

function renderContinuation(row: Api.StockLimitUp.LimitUpStockItem) {
  const prob = row.continuation_probability;
  if (prob === null || prob === undefined) return <NText depth={3}>-</NText>;
  const tagType = prob >= 65 ? 'error' : prob >= 40 ? 'warning' : 'default';
  const label = prob >= 65
    ? $t('page.aStock.limitUp.probHigh')
    : prob >= 40
      ? $t('page.aStock.limitUp.probMid')
      : $t('page.aStock.limitUp.probLow');
  const factors = row.continuation_factors || [];
  return (
    <NTooltip trigger="hover" placement="left">
      {{
        trigger: () => (
          <NTag size="small" type={tagType} bordered={false} style={{ fontWeight: '600' }}>
            {prob}% {label}
          </NTag>
        ),
        default: () => (
          <div class="flex-col gap-2px">
            <span class="font-500">{$t('page.aStock.limitUp.probFactors')}</span>
            {factors.map(f => (
              <span key={f.type} class="text-12px whitespace-nowrap">
                {formatFactor(f)}
              </span>
            ))}
          </div>
        )
      }}
    </NTooltip>
  );
}

async function loadData(silent = false) {
  if (!silent) loading.value = true;
  try {
    const { data: resp, error } = await fetchGetLimitUpList({
      date: selectedDate.value ? dayjs(selectedDate.value).format('YYYY-MM-DD') : null,
      market_board: marketBoard.value,
      pool_type: poolType.value,
      page: page.value,
      page_size: pageSize.value
    });
    if (!error && resp) {
      data.value = resp.records || [];
      total.value = resp.total;
    }
  } finally {
    if (!silent) loading.value = false;
  }
}

async function loadStats() {
  const { data: s, error } = await fetchGetLimitUpStats(
    selectedDate.value ? dayjs(selectedDate.value).format('YYYY-MM-DD') : null
  );
  if (!error) stats.value = s || null;
}

async function loadDates() {
  const { data: dates, error } = await fetchGetLimitUpDates();
  if (!error) availableDates.value = dates || [];
}

async function syncData() {
  syncing.value = true;
  try {
    const { error } = await fetchSyncLimitUp();
    if (!error) {
      window.$message?.success($t('page.aStock.limitUp.syncSuccess'));
      await refresh();
    }
  } finally {
    syncing.value = false;
  }
}

/** 最后刷新时间 + 定时自动刷新（退出页面自动停止计时器） */
const { lastRefreshTime, refresh } = useAutoRefresh(
  async (silent: boolean) => {
    await Promise.all([loadData(silent), loadStats(), loadDates()]);
  },
  { shouldRefresh: isStockAutoRefreshTime }
);

function onFilterChange() {
  page.value = 1;
  loadData();
  loadStats();
}

function onPageChange(p: number) {
  page.value = p;
  loadData();
}

const columns = computed<DataTableColumns<Api.StockLimitUp.LimitUpStockItem>>(() => [
  {
    key: 'stock_code',
    title: $t('page.aStock.limitUp.stockCode'),
    width: 100,
    render: row => <span style={{ fontFamily: 'monospace', fontSize: '12px' }}>{row.stock_code}</span>
  },
  {
    key: 'stock_name',
    title: $t('page.aStock.limitUp.stockName'),
    width: 110,
    render: row => <span class="font-500">{row.stock_name}</span>
  },
  {
    key: 'market_board',
    title: $t('page.aStock.limitUp.marketBoard'),
    width: 90,
    align: 'center',
    render: row => (
      <NTag size="small" type={BOARD_TAG_TYPE[row.market_board] || 'default'} bordered={false}>
        {BOARD_LABEL[row.market_board] || row.market_board}
      </NTag>
    )
  },
  {
    key: 'pool_type',
    title: $t('page.aStock.limitUp.poolStatus'),
    width: 80,
    align: 'center',
    render: row => renderPoolStatus(row)
  },
  {
    key: 'latest_price',
    title: $t('page.aStock.limitUp.latestPrice'),
    width: 90,
    align: 'right',
    render: row => (
      <span style={{ color: pctColor(row.change_pct), fontWeight: '500' }}>{fmtNum(row.latest_price)}</span>
    )
  },
  {
    key: 'change_pct',
    title: $t('page.aStock.limitUp.changePct'),
    width: 100,
    align: 'right',
    render: row => renderPct(row.change_pct)
  },
  {
    key: 'turnover_rate',
    title: $t('page.aStock.limitUp.turnoverRate'),
    width: 90,
    align: 'right',
    render: row => renderPct(row.turnover_rate)
  },
  {
    key: 'turnover',
    title: $t('page.aStock.limitUp.turnover'),
    width: 110,
    align: 'right',
    render: row => <span>{fmtMoney(row.turnover)}</span>
  },
  {
    key: 'amplitude',
    title: $t('page.aStock.limitUp.amplitude'),
    width: 90,
    align: 'right',
    render: row => renderPct(row.amplitude)
  },
  {
    key: 'first_limit_up_time',
    title: $t('page.aStock.limitUp.firstSeal'),
    width: 100,
    align: 'center',
    render: row => <span class="text-12px">{row.first_limit_up_time || '-'}</span>
  },
  {
    key: 'last_limit_up_time',
    title: $t('page.aStock.limitUp.lastSeal'),
    width: 100,
    align: 'center',
    render: row => <span class="text-12px">{row.last_limit_up_time || '-'}</span>
  },
  {
    key: 'consecutive_limit_up',
    title: $t('page.aStock.limitUp.consecutive'),
    width: 90,
    align: 'center',
    sorter: (a, b) => (a.consecutive_limit_up ?? 0) - (b.consecutive_limit_up ?? 0),
    render: row => renderConsecutive(row.consecutive_limit_up)
  },
  {
    key: 'continuation_probability',
    title: $t('page.aStock.limitUp.continuationProb'),
    width: 110,
    align: 'center',
    sorter: (a, b) => (a.continuation_probability ?? 0) - (b.continuation_probability ?? 0),
    render: row => renderContinuation(row)
  },
  {
    key: 'industry',
    title: $t('page.aStock.limitUp.industry'),
    width: 110,
    render: row => <span class="text-12px">{row.industry || '-'}</span>
  },
  {
    key: 'limit_up_reason',
    title: $t('page.aStock.limitUp.reason'),
    minWidth: 140,
    ellipsis: { tooltip: true },
    render: row => <span class="text-12px">{row.limit_up_reason || '-'}</span>
  }
]);

onMounted(() => {
  refresh();
});
</script>

<template>
  <div class="min-h-500px flex-col-stretch gap-16px overflow-hidden lt-sm:overflow-auto">
    <NCard v-if="stats" :bordered="false" size="small" class="card-wrapper">
      <NGrid responsive="screen" cols="2 s:3 m:7" :x-gap="16" :y-gap="8">
        <NGridItem>
          <NStatistic :label="$t('page.aStock.limitUp.totalCount')">
            <span style="color: #f5222d; font-weight: 700">{{ stats.total_count }}</span>
          </NStatistic>
        </NGridItem>
        <NGridItem>
          <NStatistic :label="$t('page.aStock.limitUp.brokenCount')">
            <span style="color: #fa8c16; font-weight: 700">{{ stats.broken_count }}</span>
          </NStatistic>
        </NGridItem>
        <NGridItem>
          <NStatistic :label="$t('page.aStock.limitUp.mainCount')" :value="stats.main_count" />
        </NGridItem>
        <NGridItem>
          <NStatistic :label="$t('page.aStock.limitUp.chinextCount')" :value="stats.chinext_count" />
        </NGridItem>
        <NGridItem>
          <NStatistic :label="$t('page.aStock.limitUp.starCount')" :value="stats.star_count" />
        </NGridItem>
        <NGridItem>
          <NStatistic :label="$t('page.aStock.limitUp.bseCount')" :value="stats.bse_count" />
        </NGridItem>
        <NGridItem>
          <NStatistic :label="$t('page.aStock.limitUp.maxConsecutive')">
            <span style="color: #fa541c; font-weight: 700">
              {{ stats.max_consecutive > 1 ? `${stats.max_consecutive}\u8fde` : '-' }}
            </span>
          </NStatistic>
        </NGridItem>
      </NGrid>
    </NCard>

    <NCard :bordered="false" size="small" class="card-wrapper">
      <div class="flex-y-center flex-wrap justify-between gap-12px">
        <NSpace align="center" :size="16">
          <NRadioGroup v-model:value="poolType" size="small" @update:value="onFilterChange">
            <NRadioButton value="all">{{ $t('page.aStock.limitUp.poolAll') }}</NRadioButton>
            <NRadioButton value="limit_up">{{ $t('page.aStock.limitUp.poolLimitUp') }}</NRadioButton>
            <NRadioButton value="broken">{{ $t('page.aStock.limitUp.poolBroken') }}</NRadioButton>
          </NRadioGroup>
          <NRadioGroup v-model:value="marketBoard" size="small" @update:value="onFilterChange">
            <NRadioButton value="all">{{ $t('page.aStock.limitUp.all') }}</NRadioButton>
            <NRadioButton value="main">{{ $t('page.aStock.limitUp.main') }}</NRadioButton>
            <NRadioButton value="chinext">{{ $t('page.aStock.limitUp.chinext') }}</NRadioButton>
            <NRadioButton value="star">{{ $t('page.aStock.limitUp.star') }}</NRadioButton>
          </NRadioGroup>
        </NSpace>
        <NSpace align="center" :size="12">
          <NText depth="3" class="flex-y-center gap-4px whitespace-nowrap text-12px">
            <icon-mdi-clock-outline class="text-14px" />
            {{ $t('page.aStock.limitUp.lastRefresh') }} {{ lastRefreshTime ? lastRefreshTime.format('HH:mm:ss') : '-' }}
          </NText>
          <NDatePicker
            v-model:value="selectedDate"
            type="date"
            :placeholder="$t('page.aStock.limitUp.datePlaceholder')"
            :is-date-disabled="(ts: number) => !availableDates.includes(dayjs(ts).format('YYYY-MM-DD'))"
            clearable
            size="small"
            class="w-180px"
            @update:value="onFilterChange"
          />
          <NButton size="small" type="primary" ghost :loading="syncing" @click="syncData">
            <template #icon><icon-mdi-cloud-download-outline class="text-icon" /></template>
            {{ $t('page.aStock.limitUp.sync') }}
          </NButton>
          <NButton size="small" :loading="loading" @click="() => refresh()">
            <template #icon><icon-ic-round-refresh class="text-icon" /></template>
            {{ $t('common.refresh') }}
          </NButton>
        </NSpace>
      </div>
    </NCard>

    <NCard :bordered="false" size="small" class="card-wrapper sm:flex-1-hidden">
      <div class="h-full flex-col-stretch gap-12px">
        <NDataTable
          :columns="columns"
          :data="data"
          size="small"
          :loading="loading"
          :flex-height="!appStore.isMobile"
          :scroll-x="1580"
          :row-key="(row: Api.StockLimitUp.LimitUpStockItem) => row.id"
          class="sm:flex-1-hidden"
        />
        <div class="flex justify-end">
          <NPagination :page="page" :page-size="pageSize" :item-count="total" @update:page="onPageChange" />
        </div>
      </div>
    </NCard>
  </div>
</template>
