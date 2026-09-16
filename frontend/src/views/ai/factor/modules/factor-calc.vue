<script setup lang="tsx">
import { computed, onMounted, ref } from 'vue';
import {
  NAlert,
  NButton,
  NCard,
  NDataTable,
  NDatePicker,
  NForm,
  NFormItem,
  NInput,
  NInputNumber,
  NSelect,
  NSpace,
  NTag
} from 'naive-ui';
import type { DataTableColumns } from 'naive-ui';
import dayjs from 'dayjs';
import { fetchCalcFactor, fetchGetFactorList, fetchGetStrategyList } from '@/service/api';
import { $t } from '@/locales';

defineOptions({ name: 'FactorCalc' });

// ------------------------------------------------------------------
// 选项加载（因子 + 策略股票池带入）
// ------------------------------------------------------------------
const factorOptions = ref<{ value: number; label: string }[]>([]);
const strategyOptions = ref<{ value: number; label: string }[]>([]);
const strategyPools = ref<Record<number, string[]>>({});

async function loadFactorOptions() {
  const { data, error } = await fetchGetFactorList({ page: 1, page_size: 100 });
  if (!error) {
    factorOptions.value = (data?.records ?? [])
      .filter(f => f.status)
      .map(f => ({ value: f.id, label: `${f.name} (${f.code})` }));
  }
}

async function loadStrategyOptions() {
  const { data, error } = await fetchGetStrategyList({ page: 1, page_size: 100 });
  if (!error) {
    const records = data?.records ?? [];
    strategyOptions.value = records.map(s => ({ value: s.id, label: s.name }));
    strategyPools.value = Object.fromEntries(records.map(s => [s.id, s.stock_pool?.codes ?? []]));
  }
}

/** 从策略股票池带入代码 */
function onPickStrategy(strategyId: number | null) {
  if (!strategyId) return;
  const codes = strategyPools.value[strategyId] ?? [];
  if (codes.length) codesText.value = codes.join(', ');
  else window.$message?.warning($t('page.aiFactor.calc.poolEmpty'));
}

// ------------------------------------------------------------------
// 试算表单与结果
// ------------------------------------------------------------------
const factorId = ref<number | null>(null);
const codesText = ref('');
const endDate = ref<number | null>(null);
const lookback = ref<number>(120);
const running = ref(false);
const calcResult = ref<Api.Factor.FactorCalcResult | null>(null);

function disableFutureDate(ts: number) {
  return ts > Date.now();
}

function parseCodes(text: string): string[] {
  return [...new Set(text.split(/[,，\s]+/).map(s => s.trim()).filter(Boolean))];
}

async function onRun() {
  if (!factorId.value) {
    window.$message?.warning($t('page.aiFactor.calc.factorRequired'));
    return;
  }
  const codes = parseCodes(codesText.value);
  if (!codes.length) {
    window.$message?.warning($t('page.aiFactor.calc.codesRequired'));
    return;
  }
  running.value = true;
  try {
    const { data, error } = await fetchCalcFactor({
      factor_id: factorId.value,
      codes,
      end_date: endDate.value ? dayjs(endDate.value).format('YYYY-MM-DD') : undefined,
      lookback: lookback.value
    });
    if (!error && data) calcResult.value = data;
  } finally {
    running.value = false;
  }
}

const resultColumns = computed<DataTableColumns<Api.Factor.FactorValueItem>>(() => [
  {
    key: 'code',
    title: $t('page.aiFactor.calc.stockCol'),
    width: 140,
    render: row => <span class="font-mono">{row.code}</span>
  },
  {
    key: 'value',
    title: calcResult.value
      ? `${$t('page.aiFactor.calc.valueCol')} (${calcResult.value.factor_code})`
      : $t('page.aiFactor.calc.valueCol'),
    align: 'right',
    render: row => (
      <span class="font-mono font-500">
        {row.value > 0 ? `+${row.value.toFixed(4)}` : row.value.toFixed(4)}
      </span>
    )
  }
]);

onMounted(() => {
  loadFactorOptions();
  loadStrategyOptions();
});
</script>

<template>
  <div class="flex-col-stretch gap-16px">
    <NCard :title="$t('page.aiFactor.calc.formTitle')" :bordered="false" size="small" class="card-wrapper">
      <NForm label-placement="left" :label-width="80" :show-feedback="false">
        <NSpace align="center" :size="16" class="flex-wrap">
          <NFormItem :label="$t('page.aiFactor.calc.factor')" class="mb-0">
            <NSelect
              v-model:value="factorId"
              filterable
              :placeholder="$t('page.aiFactor.calc.factorPlaceholder')"
              :options="factorOptions"
              class="w-220px"
            />
          </NFormItem>
          <NFormItem :label="$t('page.aiFactor.calc.date')" class="mb-0">
            <NDatePicker
              v-model:value="endDate"
              type="date"
              clearable
              :is-date-disabled="disableFutureDate"
              :placeholder="$t('page.aiFactor.calc.datePlaceholder')"
              class="w-150px"
            />
          </NFormItem>
          <NFormItem :label="$t('page.aiFactor.calc.lookback')" class="mb-0">
            <NInputNumber v-model:value="lookback" :min="5" :max="750" class="w-120px" />
          </NFormItem>
          <NButton type="primary" :loading="running" @click="onRun">
            <template #icon><icon-mdi-calculator-variant-outline class="text-icon" /></template>
            {{ $t('page.aiFactor.calc.run') }}
          </NButton>
        </NSpace>
        <NSpace align="center" :size="16" class="mt-12px flex-wrap">
          <NFormItem :label="$t('page.aiFactor.calc.codes')" class="mb-0 flex-1">
            <NInput
              v-model:value="codesText"
              :placeholder="$t('page.aiFactor.calc.codesPlaceholder')"
              clearable
              class="w-420px"
            />
          </NFormItem>
          <NFormItem :label="$t('page.aiFactor.calc.fromStrategy')" class="mb-0">
            <NSelect
              filterable
              clearable
              :placeholder="$t('page.aiFactor.calc.fromStrategyPlaceholder')"
              :options="strategyOptions"
              class="w-200px"
              @update:value="onPickStrategy"
            />
          </NFormItem>
        </NSpace>
      </NForm>
    </NCard>

    <NCard v-if="calcResult" :bordered="false" size="small" class="card-wrapper sm:flex-1-hidden">
      <template #header>
        <NSpace align="center" :size="8">
          <span>{{ $t('page.aiFactor.calc.resultTitle') }}</span>
          <NTag size="small" :bordered="false" type="info">{{ calcResult.end_date }}</NTag>
        </NSpace>
      </template>
      <NAlert v-if="calcResult.warnings.length" type="warning" :bordered="false" class="mb-12px">
        <div v-for="(w, i) in calcResult.warnings" :key="i" class="text-12px">{{ w }}</div>
      </NAlert>
      <NDataTable
        :columns="resultColumns"
        :data="calcResult.values"
        size="small"
        :max-height="420"
        :row-key="(row: Api.Factor.FactorValueItem) => row.code"
      />
    </NCard>
  </div>
</template>

<style scoped></style>
