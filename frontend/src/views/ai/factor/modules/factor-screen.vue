<script setup lang="tsx">
import { computed, onMounted, ref } from 'vue';
import {
  NAlert,
  NButton,
  NCard,
  NDataTable,
  NInput,
  NModal,
  NRadioButton,
  NRadioGroup,
  NSelect,
  NSpace,
  NTag,
  NText
} from 'naive-ui';
import type { DataTableColumns } from 'naive-ui';
import { fetchGetFactorList, fetchGetStrategyList, fetchSaveScreenPool, fetchScreenStocks } from '@/service/api';
import { $t } from '@/locales';

defineOptions({ name: 'FactorScreen' });

// ------------------------------------------------------------------
// 选项加载
// ------------------------------------------------------------------
const factorOptions = ref<{ value: number; label: string; code: string }[]>([]);
const strategyOptions = ref<{ value: number; label: string }[]>([]);

async function loadFactorOptions() {
  const { data, error } = await fetchGetFactorList({ page: 1, page_size: 100 });
  if (!error) {
    factorOptions.value = (data?.records ?? [])
      .filter(f => f.status)
      .map(f => ({ value: f.id, label: `${f.name} (${f.code})`, code: f.code }));
  }
}

async function loadStrategyOptions() {
  const { data, error } = await fetchGetStrategyList({ page: 1, page_size: 100 });
  if (!error) {
    strategyOptions.value = (data?.records ?? []).map(s => ({ value: s.id, label: s.name }));
  }
}

// ------------------------------------------------------------------
// 股票池来源（手动 codes / 策略股票池，二选一）
// ------------------------------------------------------------------
const poolMode = ref<'manual' | 'strategy'>('manual');
const codesText = ref('');
const strategyId = ref<number | null>(null);

// ------------------------------------------------------------------
// 条件构建器（多条件 AND，行编辑由 FactorConditionBuilder 承担）
// ------------------------------------------------------------------
interface ConditionRow {
  factor_id: number | null;
  op: Api.Factor.ScreenOp;
  value: number | null;
}

const conditions = ref<ConditionRow[]>([{ factor_id: null, op: 'gt', value: null }]);

function parseCodes(text: string): string[] {
  return [...new Set(text.split(/[,，\s]+/).map(s => s.trim()).filter(Boolean))];
}

// ------------------------------------------------------------------
// 执行选股
// ------------------------------------------------------------------
const running = ref(false);
const screenResult = ref<Api.Factor.FactorScreenResult | null>(null);
/** 本次结果使用的条件因子（code → 列标题），驱动动态列 */
const resultFactors = ref<{ code: string; label: string }[]>([]);

async function onRun() {
  const valid = conditions.value.filter(c => c.factor_id !== null && c.value !== null);
  if (!valid.length) {
    window.$message?.warning($t('page.aiFactor.screen.conditionRequired'));
    return;
  }
  if (poolMode.value === 'manual' && !parseCodes(codesText.value).length) {
    window.$message?.warning($t('page.aiFactor.screen.poolRequired'));
    return;
  }
  if (poolMode.value === 'strategy' && !strategyId.value) {
    window.$message?.warning($t('page.aiFactor.screen.strategyRequired'));
    return;
  }
  running.value = true;
  try {
    const params: Api.Factor.FactorScreenParams = {
      conditions: valid.map(c => ({ factor_id: c.factor_id!, op: c.op, value: c.value! })),
      ...(poolMode.value === 'manual'
        ? { codes: parseCodes(codesText.value) }
        : { strategy_id: strategyId.value! })
    };
    const { data, error } = await fetchScreenStocks(params);
    if (!error && data) {
      screenResult.value = data;
      const usedIds = [...new Set(valid.map(c => c.factor_id))];
      resultFactors.value = usedIds.map(id => {
        const opt = factorOptions.value.find(o => o.value === id);
        return { code: opt?.code ?? String(id), label: opt?.label ?? String(id) };
      });
    }
  } finally {
    running.value = false;
  }
}

const resultColumns = computed<DataTableColumns<Api.Factor.ScreenMatchItem>>(() => [
  {
    key: 'code',
    title: $t('page.aiFactor.screen.stockCodeCol'),
    width: 110,
    render: row => <span class="font-mono">{row.code}</span>
  },
  { key: 'name', title: $t('page.aiFactor.screen.stockNameCol'), width: 110 },
  ...resultFactors.value.map(f => ({
    key: `fv_${f.code}`,
    title: f.label,
    align: 'right' as const,
    render: (row: Api.Factor.ScreenMatchItem) => {
      const v = row.factor_values[f.code];
      return v === null || v === undefined
        ? <NText depth={3}>-</NText>
        : <span class="font-mono">{v > 0 ? `+${v.toFixed(4)}` : v.toFixed(4)}</span>;
    }
  }))
]);

// ------------------------------------------------------------------
// 存为策略股票池
// ------------------------------------------------------------------
const saveVisible = ref(false);
const saveStrategyId = ref<number | null>(null);
const saving = ref(false);

function openSavePool() {
  saveStrategyId.value = null;
  saveVisible.value = true;
}

async function onSavePool() {
  if (!saveStrategyId.value) {
    window.$message?.warning($t('page.aiFactor.screen.targetStrategyRequired'));
    return;
  }
  saving.value = true;
  try {
    const codes = (screenResult.value?.matched ?? []).map(m => m.code);
    const { data, error } = await fetchSaveScreenPool({ strategy_id: saveStrategyId.value, codes });
    if (!error && data) {
      window.$message?.success($t('page.aiFactor.screen.saveSuccess', { total: data.total }));
      saveVisible.value = false;
    }
  } finally {
    saving.value = false;
  }
}

onMounted(() => {
  loadFactorOptions();
  loadStrategyOptions();
});
</script>

<template>
  <div class="h-full flex-col-stretch gap-16px overflow-y-auto">
    <NCard :title="$t('page.aiFactor.screen.formTitle')" :bordered="false" size="small" class="card-wrapper flex-shrink-0">
      <NSpace vertical :size="12">
        <!-- 股票池来源 -->
        <NSpace align="center" :size="12" class="flex-wrap">
          <NText depth="2" class="w-80px">{{ $t('page.aiFactor.screen.poolSource') }}</NText>
          <NRadioGroup v-model:value="poolMode" size="small">
            <NRadioButton value="manual">{{ $t('page.aiFactor.screen.poolManual') }}</NRadioButton>
            <NRadioButton value="strategy">{{ $t('page.aiFactor.screen.poolStrategy') }}</NRadioButton>
          </NRadioGroup>
          <NInput
            v-if="poolMode === 'manual'"
            v-model:value="codesText"
            :placeholder="$t('page.aiFactor.screen.codesPlaceholder')"
            clearable
            class="w-420px"
          />
          <NSelect
            v-else
            v-model:value="strategyId"
            filterable
            :placeholder="$t('page.aiFactor.screen.strategyPlaceholder')"
            :options="strategyOptions"
            class="w-240px"
          />
        </NSpace>

        <!-- 条件构建器 -->
        <NSpace vertical :size="8">
          <NSpace align="center" :size="12">
            <NText depth="2" class="w-80px">{{ $t('page.aiFactor.screen.conditions') }}</NText>
            <NText depth="3" class="text-12px">{{ $t('page.aiFactor.screen.conditionsTip') }}</NText>
          </NSpace>
          <FactorConditionBuilder v-model="conditions" allow-top-n>
            <template #extra>
              <NButton type="primary" :loading="running" @click="onRun">
                <template #icon><icon-mdi-filter-outline class="text-icon" /></template>
                {{ $t('page.aiFactor.screen.run') }}
              </NButton>
            </template>
          </FactorConditionBuilder>
        </NSpace>
      </NSpace>
    </NCard>

    <!-- 选股结果 -->
    <NCard v-if="screenResult" :bordered="false" size="small" class="card-wrapper flex-shrink-0">
      <template #header>
        <NSpace align="center" :size="8">
          <span>{{ $t('page.aiFactor.screen.resultTitle') }}</span>
          <NTag size="small" :bordered="false" type="info">{{ screenResult.end_date }}</NTag>
          <NTag size="small" :bordered="false" type="success">
            {{ $t('page.aiFactor.screen.matchedCount', { total: screenResult.total }) }}
          </NTag>
        </NSpace>
      </template>
      <template #header-extra>
        <NButton size="small" type="primary" ghost :disabled="!screenResult.total" @click="openSavePool">
          <template #icon><icon-mdi-content-save-outline class="text-icon" /></template>
          {{ $t('page.aiFactor.screen.savePool') }}
        </NButton>
      </template>
      <NAlert v-if="screenResult.warnings.length" type="warning" :bordered="false" class="mb-12px">
        <div v-for="(w, i) in screenResult.warnings" :key="i" class="text-12px">{{ w }}</div>
      </NAlert>
      <NDataTable
        :columns="resultColumns"
        :data="screenResult.matched"
        size="small"
        :max-height="420"
        :scroll-x="300 + resultFactors.length * 160"
        :row-key="(row: Api.Factor.ScreenMatchItem) => row.code"
      />
    </NCard>

    <!-- 存为策略股票池 -->
    <NModal
      :show="saveVisible"
      preset="card"
      :title="$t('page.aiFactor.screen.savePoolTitle')"
      class="w-480px"
      @update:show="v => (saveVisible = v)"
    >
      <NSpace vertical :size="12">
        <NSelect
          v-model:value="saveStrategyId"
          filterable
          :placeholder="$t('page.aiFactor.screen.targetStrategy')"
          :options="strategyOptions"
        />
        <NAlert type="warning" :bordered="false">
          <div class="text-12px">{{ $t('page.aiFactor.screen.savePoolTip') }}</div>
        </NAlert>
      </NSpace>
      <template #footer>
        <NSpace justify="end" :size="12">
          <NButton @click="saveVisible = false">{{ $t('common.cancel') }}</NButton>
          <NButton type="primary" :loading="saving" @click="onSavePool">{{ $t('common.confirm') }}</NButton>
        </NSpace>
      </template>
    </NModal>
  </div>
</template>

<style scoped></style>
