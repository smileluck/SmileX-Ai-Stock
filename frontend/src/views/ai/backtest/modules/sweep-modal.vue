<script setup lang="tsx">
import { computed, reactive, ref, watch } from 'vue';
import {
  NButton,
  NDataTable,
  NDatePicker,
  NForm,
  NFormItem,
  NInput,
  NModal,
  NPopconfirm,
  NRadioButton,
  NRadioGroup,
  NSelect,
  NSpace,
  NSpin,
  NTag,
  NText
} from 'naive-ui';
import type { DataTableColumns } from 'naive-ui';
import dayjs from 'dayjs';
import {
  fetchGetFactorList,
  fetchGetStrategyList,
  fetchRunBacktestSweep,
  fetchUpdateStrategy
} from '@/service/api';
import { $t } from '@/locales';

/**
 * 参数寻优弹窗（POST /admin/backtest/sweep，同步接口、不落库、组合 ≤27）
 * 风控网格逗号分隔候选值，实时计算笛卡尔积；rule 型可加单条买入条件阈值扫描；
 * 结果表支持「应用该组参数」整体写回策略配置
 */
defineOptions({ name: 'BacktestSweepModal' });

interface Props {
  visible: boolean;
}

const props = defineProps<Props>();

const emit = defineEmits<{
  (e: 'update:visible', visible: boolean): void;
  /** 参数写回策略成功（父级可刷新策略下拉） */
  (e: 'applied'): void;
}>();

const modalVisible = computed({
  get: () => props.visible,
  set: v => emit('update:visible', v)
});

// ================================================================
// 数据源：策略（含 rule_config 全量）与因子名映射
// ================================================================
const strategies = ref<Api.Strategy.StrategyItem[]>([]);
const factorMap = ref<Record<number, Api.Factor.FactorItem>>({});

async function loadStrategies() {
  const { data, error } = await fetchGetStrategyList({ page: 1, page_size: 100 });
  if (!error) strategies.value = data?.records ?? [];
}

async function loadFactors() {
  const { data, error } = await fetchGetFactorList({ page: 1, page_size: 100 });
  if (!error) {
    const map: Record<number, Api.Factor.FactorItem> = {};
    for (const f of data?.records ?? []) map[f.id] = f;
    factorMap.value = map;
  }
}

const strategyOptions = computed(() =>
  strategies.value.map(s => ({
    value: s.id,
    label: `${s.name} [${s.strategy_type === 'rule' ? $t('page.aiBacktest.tagRule') : $t('page.aiBacktest.tagAi')}]`
  }))
);

const currentStrategy = computed(
  () => strategies.value.find(s => s.id === form.strategy_id) ?? null
);
const isRule = computed(() => currentStrategy.value?.strategy_type === 'rule');

// ================================================================
// 表单
// ================================================================
function defaultRange(): [number, number] {
  return [dayjs().subtract(3, 'month').startOf('day').valueOf(), dayjs().endOf('day').valueOf()];
}

const form = reactive({
  strategy_id: null as number | null,
  range: defaultRange() as [number, number] | null,
  stopInput: '',
  takeInput: '',
  trailInput: '',
  slippage_model: 'fixed' as Api.Backtest.SlippageModel,
  scanConditionIndex: 0,
  scanValuesInput: ''
});

/** 逗号/空格分隔候选值解析（空片段与非法值丢弃） */
function parseValues(input: string): number[] {
  return input
    .split(/[,，\s]+/)
    .map(s => s.trim())
    .filter(s => s !== '')
    .map(Number)
    .filter(Number.isFinite);
}

const stopValues = computed(() => parseValues(form.stopInput));
const takeValues = computed(() => parseValues(form.takeInput));
const trailValues = computed(() => parseValues(form.trailInput));
const scanValues = computed(() => parseValues(form.scanValuesInput));
/** 启用买入条件扫描 = rule 型且填了候选值 */
const scanEnabled = computed(() => isRule.value && scanValues.value.length > 0);

const buyConditions = computed(() => currentStrategy.value?.rule_config?.buy_conditions ?? []);

const scanConditionOptions = computed(() =>
  buyConditions.value.map((c, i) => ({
    value: i,
    label: condText(c)
  }))
);

const OP_SYMBOL: Record<string, string> = { gt: '>', gte: '≥', lt: '<', lte: '≤' };

function condText(c: Api.Strategy.RuleCondition, valueOverride?: number) {
  const f = factorMap.value[c.factor_id];
  const name = f ? `${f.name}(${f.code})` : `#${c.factor_id}`;
  return `${name} ${OP_SYMBOL[c.op] ?? c.op} ${valueOverride ?? c.value}`;
}

/** 笛卡尔积组合数（仅网格与扫描，不含后端可能追加的 baseline 组） */
const comboCount = computed(() => {
  let n = 1;
  let any = false;
  for (const list of [stopValues.value, takeValues.value, trailValues.value]) {
    if (list.length) {
      n *= list.length;
      any = true;
    }
  }
  if (scanEnabled.value) {
    n *= scanValues.value.length;
    any = true;
  }
  return any ? n : 0;
});

const canSubmit = computed(
  () =>
    Boolean(form.strategy_id) &&
    Boolean(form.range) &&
    comboCount.value >= 1 &&
    comboCount.value <= 27
);

function disableFutureDate(ts: number) {
  return ts > Date.now();
}

// 切换策略时重置条件扫描下标
watch(
  () => form.strategy_id,
  () => {
    form.scanConditionIndex = 0;
  }
);

// ================================================================
// 提交与结果
// ================================================================
const sweeping = ref(false);
const sweepResult = ref<Api.Backtest.BacktestSweepResult | null>(null);

async function onSubmit() {
  if (!form.strategy_id || !form.range) return;
  sweeping.value = true;
  try {
    const { data, error } = await fetchRunBacktestSweep({
      strategy_id: form.strategy_id,
      start_date: dayjs(form.range[0]).format('YYYY-MM-DD'),
      end_date: dayjs(form.range[1]).format('YYYY-MM-DD'),
      slippage_model: form.slippage_model,
      grid: {
        stop_loss_pct: stopValues.value.length ? stopValues.value : undefined,
        take_profit_pct: takeValues.value.length ? takeValues.value : undefined,
        trailing_drawdown_pct: trailValues.value.length ? trailValues.value : undefined
      },
      buy_condition_scan: scanEnabled.value
        ? { condition_index: form.scanConditionIndex, values: scanValues.value }
        : undefined
    });
    if (!error) sweepResult.value = data ?? null;
  } finally {
    sweeping.value = false;
  }
}

// ================================================================
// 结果表
// ================================================================
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

function renderNum(val: number | null | undefined, digits = 2) {
  if (val === null || val === undefined) return <NText depth={3}>-</NText>;
  return <span>{Number(val).toFixed(digits)}</span>;
}

function paramsText(p: Api.Backtest.SweepParams) {
  const parts: string[] = [];
  if (p.buy_condition) {
    const cond = buyConditions.value[p.buy_condition.index];
    if (cond) parts.push(condText(cond, p.buy_condition.value));
  }
  parts.push(
    `${$t('page.aiBacktest.sweep.stopLoss')} ${p.stop_loss_pct ?? '-'}`,
    `${$t('page.aiBacktest.sweep.takeProfit')} ${p.take_profit_pct ?? '-'}`,
    `${$t('page.aiBacktest.sweep.trailing')} ${p.trailing_drawdown_pct ?? '-'}`
  );
  return parts;
}

/** 应用该组参数：整体写回策略风控参数；rule 且含 buy_condition 时同步覆盖 rule_config 对应行 value */
async function onApply(row: Api.Backtest.SweepResultItem) {
  const strategy = currentStrategy.value;
  if (!strategy) return;
  const bc = row.params.buy_condition;
  let ruleConfig = strategy.rule_config;
  if (ruleConfig && bc) {
    ruleConfig = {
      buy_conditions: ruleConfig.buy_conditions.map((c, i) => (i === bc.index ? { ...c, value: bc.value } : c)),
      sell_conditions: ruleConfig.sell_conditions
    };
  }
  const { error } = await fetchUpdateStrategy(strategy.id, {
    name: strategy.name,
    description: strategy.description,
    category: strategy.category,
    strategy_type: strategy.strategy_type,
    rule_config: ruleConfig,
    prompt_template: strategy.prompt_template,
    stock_pool: strategy.stock_pool?.codes ? { codes: strategy.stock_pool.codes } : null,
    execute_periods: strategy.execute_periods ?? [],
    max_positions: strategy.max_positions,
    stop_loss_pct: row.params.stop_loss_pct,
    take_profit_pct: row.params.take_profit_pct,
    trailing_drawdown_pct: row.params.trailing_drawdown_pct,
    status: strategy.status
  });
  if (!error) {
    window.$message?.success($t('page.aiBacktest.sweep.applySuccess'));
    await loadStrategies();
    emit('applied');
  }
}

const resultColumns = computed<DataTableColumns<Api.Backtest.SweepResultItem>>(() => [
  {
    key: 'params',
    title: $t('page.aiBacktest.sweep.colParams'),
    minWidth: 260,
    render: (row, index) => (
      <NSpace size={4} align="center" wrapItem={false}>
        {index === 0 ? (
          <NTag size="small" type="success" bordered={false}>
            {$t('page.aiBacktest.sweep.best')}
          </NTag>
        ) : null}
        {row.is_baseline ? (
          <NTag size="small" type="info" bordered={false}>
            {$t('page.aiBacktest.sweep.baseline')}
          </NTag>
        ) : null}
        <span class="text-12px">{paramsText(row.params).join(' / ')}</span>
      </NSpace>
    )
  },
  {
    key: 'total_return_pct',
    title: $t('page.aiBacktest.totalReturn'),
    width: 90,
    align: 'right',
    render: row => renderPct(row.total_return_pct)
  },
  {
    key: 'annual_return_pct',
    title: $t('page.aiBacktest.annualReturn'),
    width: 90,
    align: 'right',
    render: row => renderPct(row.annual_return_pct)
  },
  {
    key: 'max_drawdown_pct',
    title: $t('page.aiBacktest.maxDrawdown'),
    width: 90,
    align: 'right',
    render: row => renderPct(row.max_drawdown_pct === null ? null : -Math.abs(row.max_drawdown_pct))
  },
  {
    key: 'sharpe',
    title: $t('page.aiBacktest.sharpe'),
    width: 80,
    align: 'right',
    render: row => renderNum(row.sharpe)
  },
  {
    key: 'win_rate',
    title: $t('page.aiBacktest.winRate'),
    width: 80,
    align: 'right',
    render: row =>
      row.win_rate === null || row.win_rate === undefined ? (
        <NText depth={3}>-</NText>
      ) : (
        <span>{`${Number(row.win_rate).toFixed(1)}%`}</span>
      )
  },
  {
    key: 'profit_factor',
    title: $t('page.aiBacktest.profitFactor'),
    width: 80,
    align: 'right',
    render: row => renderNum(row.profit_factor)
  },
  {
    key: 'trade_count',
    title: $t('page.aiBacktest.tradeCount'),
    width: 70,
    align: 'right'
  },
  {
    key: 'final_equity',
    title: $t('page.aiBacktest.finalEquity'),
    width: 110,
    align: 'right',
    render: row =>
      row.final_equity === null ? (
        <NText depth={3}>-</NText>
      ) : (
        <span>{Number(row.final_equity).toLocaleString('zh-CN', { maximumFractionDigits: 2 })}</span>
      )
  },
  {
    key: 'actions',
    title: $t('common.action'),
    width: 110,
    align: 'center',
    render: row => (
      <NPopconfirm onPositiveClick={() => onApply(row)}>
        {{
          trigger: () => (
            <NButton size="tiny" type="primary" ghost disabled={row.is_baseline}>
              {$t('page.aiBacktest.sweep.apply')}
            </NButton>
          ),
          default: () => $t('page.aiBacktest.sweep.applyConfirm')
        }}
      </NPopconfirm>
    )
  }
]);

watch(
  () => props.visible,
  visible => {
    if (visible) {
      sweepResult.value = null;
      loadStrategies();
      loadFactors();
    }
  }
);
</script>

<template>
  <NModal
    v-model:show="modalVisible"
    preset="card"
    :title="$t('page.aiBacktest.sweep.title')"
    style="width: 1180px; max-width: 96vw"
  >
    <NForm label-placement="left" :label-width="96" :show-feedback="false">
      <NSpace align="center" :size="16" class="flex-wrap">
        <NFormItem :label="$t('page.aiBacktest.formStrategy')" class="mb-0">
          <NSelect
            v-model:value="form.strategy_id"
            filterable
            :placeholder="$t('page.aiBacktest.formStrategyPlaceholder')"
            :options="strategyOptions"
            class="w-240px"
          />
        </NFormItem>
        <NFormItem :label="$t('page.aiBacktest.formRange')" class="mb-0">
          <NDatePicker
            v-model:value="form.range"
            type="daterange"
            clearable
            :is-date-disabled="disableFutureDate"
            class="w-260px"
          />
        </NFormItem>
        <NFormItem :label="$t('page.aiBacktest.slippageModel')" class="mb-0">
          <NRadioGroup v-model:value="form.slippage_model" size="small">
            <NRadioButton value="fixed">{{ $t('page.aiBacktest.slippageFixed') }}</NRadioButton>
            <NRadioButton value="amp">{{ $t('page.aiBacktest.slippageAmp') }}</NRadioButton>
          </NRadioGroup>
        </NFormItem>
      </NSpace>

      <NText depth="3" class="mb-4px mt-12px block text-12px">{{ $t('page.aiBacktest.sweep.gridTip') }}</NText>
      <NSpace align="center" :size="16" class="flex-wrap">
        <NFormItem :label="$t('page.aiBacktest.sweep.stopLoss')" class="mb-0">
          <NInput v-model:value="form.stopInput" placeholder="3,5,7" class="w-140px" />
        </NFormItem>
        <NFormItem :label="$t('page.aiBacktest.sweep.takeProfit')" class="mb-0">
          <NInput v-model:value="form.takeInput" placeholder="6,10" class="w-140px" />
        </NFormItem>
        <NFormItem :label="$t('page.aiBacktest.sweep.trailing')" class="mb-0">
          <NInput v-model:value="form.trailInput" placeholder="5" class="w-140px" />
        </NFormItem>
      </NSpace>

      <template v-if="isRule">
        <NText depth="3" class="mb-4px mt-12px block text-12px">
          {{ $t('page.aiBacktest.sweep.scanTip') }}
        </NText>
        <NSpace align="center" :size="16" class="flex-wrap">
          <NFormItem :label="$t('page.aiBacktest.sweep.scanCondition')" class="mb-0">
            <NSelect
              v-model:value="form.scanConditionIndex"
              :options="scanConditionOptions"
              :disabled="!buyConditions.length"
              class="w-280px"
            />
          </NFormItem>
          <NFormItem :label="$t('page.aiBacktest.sweep.scanValues')" class="mb-0">
            <NInput v-model:value="form.scanValuesInput" placeholder="-3,-5,-8" class="w-180px" />
          </NFormItem>
        </NSpace>
      </template>

      <NSpace align="center" :size="12" class="mt-12px">
        <NButton type="primary" :loading="sweeping" :disabled="!canSubmit" @click="onSubmit">
          {{ $t('page.aiBacktest.sweep.submit') }}
        </NButton>
        <NText v-if="comboCount === 0" depth="3" class="text-12px">
          {{ $t('page.aiBacktest.sweep.comboEmpty') }}
        </NText>
        <NText v-else-if="comboCount > 27" type="error" class="text-12px">
          {{ $t('page.aiBacktest.sweep.comboOver', { n: comboCount }) }}
        </NText>
        <NText v-else depth="3" class="text-12px">
          {{ $t('page.aiBacktest.sweep.comboCount', { n: comboCount }) }}
        </NText>
      </NSpace>
    </NForm>

    <NSpin :show="sweeping" class="mt-16px block">
      <template v-if="sweepResult">
        <NText class="mb-8px block font-500">
          {{ $t('page.aiBacktest.sweep.resultTitle', { n: sweepResult.total_runs }) }}
        </NText>
        <NDataTable
          :columns="resultColumns"
          :data="sweepResult.results"
          size="small"
          :scroll-x="1150"
          :row-key="(row: Api.Backtest.SweepResultItem) => paramsText(row.params).join('/')"
          :row-props="(row: Api.Backtest.SweepResultItem) => ({
            style: sweepResult && sweepResult.results[0] === row ? 'background: rgba(82,196,26,0.08)' : ''
          })"
        />
      </template>
      <div v-else class="h-40px" />
    </NSpin>
  </NModal>
</template>

<style scoped></style>
