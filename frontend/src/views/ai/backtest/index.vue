<script setup lang="tsx">
import { computed, onMounted, reactive, ref, watch } from 'vue';
import {
  NButton,
  NCard,
  NCollapse,
  NCollapseItem,
  NDataTable,
  NDatePicker,
  NForm,
  NFormItem,
  NInputNumber,
  NPagination,
  NPopconfirm,
  NRadioButton,
  NRadioGroup,
  NSelect,
  NSpace,
  NTag,
  NText
} from 'naive-ui';
import type { DataTableColumns } from 'naive-ui';
import dayjs from 'dayjs';
import {
  fetchDeleteBacktest,
  fetchGetBacktestList,
  fetchGetStrategyList,
  fetchRunBacktest
} from '@/service/api';
import { useAutoRefresh } from '@/hooks/common/auto-refresh';
import { $t } from '@/locales';
import BacktestDetailDrawer from './modules/backtest-detail-drawer.vue';
import SweepModal from './modules/sweep-modal.vue';

defineOptions({ name: 'AiBacktest' });

// ================================================================
// 发起回测表单
// ================================================================
interface RunForm {
  strategy_id: number | null;
  /** 回测区间（时间戳毫秒） */
  range: [number, number] | null;
  initial_capital: number;
  slippage_pct: number;
  slippage_model: Api.Backtest.SlippageModel;
  commission_pct: number;
  stamp_tax_pct: number;
}

function defaultRange(): [number, number] {
  // 默认近 6 个月
  return [dayjs().subtract(6, 'month').startOf('day').valueOf(), dayjs().endOf('day').valueOf()];
}

const runForm = reactive<RunForm>({
  strategy_id: null,
  range: defaultRange(),
  initial_capital: 1000000,
  slippage_pct: 0.1,
  slippage_model: 'fixed',
  commission_pct: 0.025,
  stamp_tax_pct: 0.05
});

/** 滑点上限：fixed 固定百分比 ≤10，amp 振幅系数 ≤50 */
const slippageMax = computed(() => (runForm.slippage_model === 'amp' ? 50 : 10));

// 切回 fixed 时收紧超限的滑点值
watch(
  () => runForm.slippage_model,
  model => {
    if (model === 'fixed' && runForm.slippage_pct > 10) runForm.slippage_pct = 10;
  }
);

const strategyOptions = ref<{ value: number; label: string }[]>([]);
const submitting = ref(false);

async function loadStrategyOptions() {
  const { data, error } = await fetchGetStrategyList({ page: 1, page_size: 100 });
  if (!error) {
    strategyOptions.value = (data?.records ?? []).map(s => ({
      value: s.id,
      label: `${s.name} [${s.strategy_type === 'rule' ? $t('page.aiBacktest.tagRule') : $t('page.aiBacktest.tagAi')}]`
    }));
  }
}

/** 禁选未来日期 */
function disableFutureDate(ts: number) {
  return ts > Date.now();
}

async function onSubmitRun() {
  if (!runForm.strategy_id) {
    window.$message?.warning($t('page.aiBacktest.strategyRequired'));
    return;
  }
  if (!runForm.range) {
    window.$message?.warning($t('page.aiBacktest.rangeRequired'));
    return;
  }
  submitting.value = true;
  try {
    const { error } = await fetchRunBacktest({
      strategy_id: runForm.strategy_id,
      start_date: dayjs(runForm.range[0]).format('YYYY-MM-DD'),
      end_date: dayjs(runForm.range[1]).format('YYYY-MM-DD'),
      initial_capital: runForm.initial_capital,
      slippage_pct: runForm.slippage_pct,
      slippage_model: runForm.slippage_model,
      commission_pct: runForm.commission_pct,
      stamp_tax_pct: runForm.stamp_tax_pct
    });
    if (!error) {
      // 回测异步执行：接口提交即返回，后台回放真实 AI 信号按历史日线撮合
      window.$message?.success($t('page.aiBacktest.submitSuccess'));
      await loadList(true);
    }
  } finally {
    submitting.value = false;
  }
}

// ================================================================
// 回测记录列表
// ================================================================
const listSearch = reactive({ strategy_id: null as number | null, status: null as Api.Backtest.BacktestStatus | null });
const backtestList = ref<Api.Backtest.BacktestItem[]>([]);
const listTotal = ref(0);
const listPage = reactive({ page: 1, pageSize: 20 });
const listLoading = ref(false);

const STATUS_OPTIONS: Array<{ value: Api.Backtest.BacktestStatus; label: string }> = [
  { value: 'running', label: $t('page.aiBacktest.statusRunning') },
  { value: 'success', label: $t('page.aiBacktest.statusSuccess') },
  { value: 'failed', label: $t('page.aiBacktest.statusFailed') }
];

const STATUS_TAG: Record<Api.Backtest.BacktestStatus, 'info' | 'success' | 'error'> = {
  running: 'info',
  success: 'success',
  failed: 'error'
};

async function loadList(silent = false) {
  if (!silent) listLoading.value = true;
  try {
    const { data, error } = await fetchGetBacktestList({
      strategy_id: listSearch.strategy_id ?? undefined,
      status: listSearch.status ?? undefined,
      page: listPage.page,
      page_size: listPage.pageSize
    });
    if (!error) {
      backtestList.value = data?.records ?? [];
      listTotal.value = data?.total ?? 0;
    }
  } finally {
    if (!silent) listLoading.value = false;
  }
}

function searchList() {
  listPage.page = 1;
  loadList();
}

function onListPageChange(page: number) {
  listPage.page = page;
  loadList();
}

/** 存在运行中的回测时每 10s 轮询列表，全部进入终态后自动停止 */
const hasRunning = computed(() => backtestList.value.some(b => b.status === 'running'));

const { lastRefreshTime } = useAutoRefresh(
  async (silent: boolean) => {
    await loadList(silent);
  },
  { interval: 10_000, shouldRefresh: () => hasRunning.value }
);

// ================================================================
// 详情抽屉 / 参数寻优 / 删除
// ================================================================
const detailVisible = ref(false);
const detailBacktestId = ref<number | null>(null);
const sweepVisible = ref(false);

function openDetail(row: Api.Backtest.BacktestItem) {
  detailBacktestId.value = row.id;
  detailVisible.value = true;
}

async function onDelete(row: Api.Backtest.BacktestItem) {
  const { error } = await fetchDeleteBacktest(row.id);
  if (!error) {
    window.$message?.success($t('common.deleteSuccess'));
    await loadList();
  }
}

// ------------------------------------------------------------------
// 展示辅助
// ------------------------------------------------------------------
function pnlColor(val: number | null | undefined) {
  if (val === null || val === undefined) return '#8c8c8c';
  if (val > 0) return '#f5222d';
  if (val < 0) return '#52c41a';
  return '#8c8c8c';
}

function renderPct(val: number | null | undefined) {
  if (val === null || val === undefined) return <NText depth={3}>-</NText>;
  return (
    <span style={{ color: pnlColor(val), fontWeight: '500' }}>
      {val > 0 ? '+' : ''}
      {Number(val).toFixed(2)}%
    </span>
  );
}

function fmtTime(t: string | null) {
  return t ? dayjs(t).format('YYYY-MM-DD HH:mm') : '-';
}

const listColumns = computed<DataTableColumns<Api.Backtest.BacktestItem>>(() => [
  {
    key: 'strategy_name',
    title: $t('page.aiBacktest.strategyCol'),
    width: 140,
    render: row => (
      <NTag size="small" bordered={false}>
        {row.strategy_name}
      </NTag>
    )
  },
  {
    key: 'range',
    title: $t('page.aiBacktest.rangeCol'),
    width: 190,
    render: row => <span class="text-12px">{`${row.start_date} ~ ${row.end_date}`}</span>
  },
  {
    key: 'status',
    title: $t('page.aiBacktest.statusCol'),
    width: 90,
    align: 'center',
    render: row => (
      <NTag size="small" bordered={false} type={STATUS_TAG[row.status]}>
        {STATUS_OPTIONS.find(o => o.value === row.status)?.label ?? row.status}
      </NTag>
    )
  },
  {
    key: 'total_return_pct',
    title: $t('page.aiBacktest.totalReturn'),
    width: 100,
    align: 'right',
    render: row => renderPct(row.result?.total_return_pct)
  },
  {
    key: 'max_drawdown_pct',
    title: $t('page.aiBacktest.maxDrawdown'),
    width: 100,
    align: 'right',
    render: row => renderPct(row.result?.max_drawdown_pct)
  },
  {
    key: 'win_rate',
    title: $t('page.aiBacktest.winRate'),
    width: 90,
    align: 'right',
    render: row => {
      const v = row.result?.win_rate;
      return v === null || v === undefined ? <NText depth={3}>-</NText> : <span>{`${Number(v).toFixed(1)}%`}</span>;
    }
  },
  {
    key: 'trade_count',
    title: $t('page.aiBacktest.tradeCount'),
    width: 90,
    align: 'right',
    render: row => <span>{row.result?.trade_count ?? '-'}</span>
  },
  {
    key: 'created_at',
    title: $t('page.aiBacktest.createdAt'),
    width: 140,
    render: row => <span class="text-12px">{fmtTime(row.created_at)}</span>
  },
  {
    key: 'actions',
    title: $t('common.action'),
    width: 130,
    align: 'center',
    render: row => (
      <NSpace size={4} justify="center">
        <NButton size="tiny" type="primary" ghost onClick={() => openDetail(row)}>
          {$t('page.aiBacktest.detail')}
        </NButton>
        {row.status !== 'running' ? (
          <NPopconfirm onPositiveClick={() => onDelete(row)}>
            {{
              trigger: () => (
                <NButton size="tiny" type="error" ghost>
                  {$t('common.delete')}
                </NButton>
              ),
              default: () => $t('page.aiBacktest.deleteConfirm')
            }}
          </NPopconfirm>
        ) : null}
      </NSpace>
    )
  }
]);

onMounted(() => {
  loadStrategyOptions();
  loadList();
});
</script>

<template>
  <div class="min-h-500px flex-col-stretch gap-16px overflow-hidden lt-sm:overflow-auto">
    <!-- 发起回测 -->
    <NCard :title="$t('page.aiBacktest.formTitle')" :bordered="false" size="small" class="card-wrapper">
      <NText depth="3" class="mb-8px block text-12px">{{ $t('page.aiBacktest.modeTip') }}</NText>
      <NForm label-placement="left" :label-width="80" :show-feedback="false">
        <NSpace align="center" :size="16" class="flex-wrap">
          <NFormItem :label="$t('page.aiBacktest.formStrategy')" class="mb-0">
            <NSelect
              v-model:value="runForm.strategy_id"
              filterable
              :placeholder="$t('page.aiBacktest.formStrategyPlaceholder')"
              :options="strategyOptions"
              class="w-200px"
            />
          </NFormItem>
          <NFormItem :label="$t('page.aiBacktest.formRange')" class="mb-0">
            <NDatePicker
              v-model:value="runForm.range"
              type="daterange"
              clearable
              :is-date-disabled="disableFutureDate"
              class="w-260px"
            />
          </NFormItem>
          <NFormItem :label="$t('page.aiBacktest.formCapital')" class="mb-0">
            <NInputNumber v-model:value="runForm.initial_capital" :min="1" :step="100000" class="w-150px" />
          </NFormItem>
          <NButton type="primary" :loading="submitting" @click="onSubmitRun">
            <template #icon><icon-mdi-play-circle-outline class="text-icon" /></template>
            {{ $t('page.aiBacktest.submit') }}
          </NButton>
          <NButton tertiary @click="sweepVisible = true">
            <template #icon><icon-mdi-tune-variant class="text-icon" /></template>
            {{ $t('page.aiBacktest.sweep.entry') }}
          </NButton>
        </NSpace>
      </NForm>
      <NCollapse class="mt-8px">
        <NCollapseItem name="advanced">
          <template #header>
            <NText depth="3" class="text-12px">{{ $t('page.aiBacktest.advanced') }}</NText>
          </template>
          <NSpace align="center" :size="16" class="flex-wrap">
            <NFormItem :label="$t('page.aiBacktest.slippageModel')" label-placement="left" class="mb-0">
              <NRadioGroup v-model:value="runForm.slippage_model" size="small">
                <NRadioButton value="fixed">{{ $t('page.aiBacktest.slippageFixed') }}</NRadioButton>
                <NRadioButton value="amp">{{ $t('page.aiBacktest.slippageAmp') }}</NRadioButton>
              </NRadioGroup>
            </NFormItem>
            <NFormItem
              :label="runForm.slippage_model === 'amp' ? $t('page.aiBacktest.slippageAmpLabel') : $t('page.aiBacktest.slippage')"
              label-placement="left"
              class="mb-0"
            >
              <NInputNumber v-model:value="runForm.slippage_pct" :min="0" :max="slippageMax" :step="0.05" class="w-120px" />
            </NFormItem>
            <NText v-if="runForm.slippage_model === 'amp'" depth="3" class="text-12px">
              {{ $t('page.aiBacktest.slippageAmpTip') }}
            </NText>
            <NFormItem :label="$t('page.aiBacktest.commission')" label-placement="left" class="mb-0">
              <NInputNumber v-model:value="runForm.commission_pct" :min="0" :max="10" :step="0.005" class="w-120px" />
            </NFormItem>
            <NFormItem :label="$t('page.aiBacktest.stampTax')" label-placement="left" class="mb-0">
              <NInputNumber v-model:value="runForm.stamp_tax_pct" :min="0" :max="10" :step="0.01" class="w-120px" />
            </NFormItem>
          </NSpace>
        </NCollapseItem>
      </NCollapse>
    </NCard>

    <!-- 回测记录 -->
    <NCard :bordered="false" size="small" class="card-wrapper sm:flex-1-hidden">
      <template #header>
        <span>{{ $t('page.aiBacktest.listTitle') }}</span>
      </template>
      <template #header-extra>
        <NSpace align="center" :size="12" :wrap="false">
          <NSelect
            v-model:value="listSearch.strategy_id"
            size="small"
            clearable
            filterable
            :placeholder="$t('page.aiBacktest.filterStrategy')"
            :options="strategyOptions"
            class="w-150px"
            @update:value="searchList"
          />
          <NSelect
            v-model:value="listSearch.status"
            size="small"
            clearable
            :placeholder="$t('page.aiBacktest.statusCol')"
            :options="STATUS_OPTIONS"
            class="w-110px"
            @update:value="searchList"
          />
        </NSpace>
      </template>

      <NDataTable
        :columns="listColumns"
        :data="backtestList"
        size="small"
        :loading="listLoading"
        :scroll-x="1250"
        :row-key="(row: Api.Backtest.BacktestItem) => row.id"
      />
      <div class="mt-12px flex items-center justify-between">
        <NText depth="3" class="text-12px">
          <icon-mdi-clock-outline class="text-14px" />
          {{ $t('page.aiBacktest.lastRefresh') }}
          {{ lastRefreshTime ? lastRefreshTime.format('HH:mm:ss') : '-' }}
        </NText>
        <NPagination
          :page="listPage.page"
          :page-size="listPage.pageSize"
          :item-count="listTotal"
          @update:page="onListPageChange"
        />
      </div>
    </NCard>

    <!-- 详情抽屉 -->
    <BacktestDetailDrawer v-model:visible="detailVisible" :backtest-id="detailBacktestId" />

    <!-- 参数寻优弹窗（应用参数后刷新策略下拉） -->
    <SweepModal v-model:visible="sweepVisible" @applied="loadStrategyOptions" />
  </div>
</template>

<style scoped></style>
