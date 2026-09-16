<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { NButton, NInputNumber, NSelect, NSpace } from 'naive-ui';
import { fetchGetFactorList } from '@/service/api';
import { $t } from '@/locales';

defineOptions({ name: 'FactorConditionBuilder' });

/** 条件行（op 全集与选股器一致；allowTopN=false 时运行时不提供 top_n 选项） */
export interface ConditionRow {
  factor_id: number | null;
  op: Api.Factor.ScreenOp;
  value: number | null;
}

interface Props {
  /** 是否提供「前N名」运算符（选股器场景）；规则策略场景不传 */
  allowTopN?: boolean;
  /** 允许 0 行条件（如策略卖出条件可空） */
  allowEmpty?: boolean;
  /** 行数上限 */
  max?: number;
}

const props = withDefaults(defineProps<Props>(), { allowTopN: false, allowEmpty: false, max: 10 });

const rows = defineModel<ConditionRow[]>({ required: true });

const factorOptions = ref<{ value: number; label: string }[]>([]);

async function loadFactorOptions() {
  const { data, error } = await fetchGetFactorList({ page: 1, page_size: 100 });
  if (!error) {
    factorOptions.value = (data?.records ?? [])
      .filter(f => f.status)
      .map(f => ({ value: f.id, label: `${f.name} (${f.code})` }));
  }
}

const OP_OPTIONS: Array<{ value: Api.Factor.ScreenOp; label: string }> = [
  { value: 'gt', label: '>' },
  { value: 'gte', label: '≥' },
  { value: 'lt', label: '<' },
  { value: 'lte', label: '≤' }
];

const opOptions = computed(() =>
  props.allowTopN ? [...OP_OPTIONS, { value: 'top_n' as const, label: $t('page.aiFactor.screen.opTopN') }] : OP_OPTIONS
);

function addRow() {
  rows.value.push({ factor_id: null, op: 'gt', value: null });
}

function removeRow(index: number) {
  rows.value.splice(index, 1);
}

onMounted(loadFactorOptions);
</script>

<template>
  <NSpace vertical :size="8">
    <NSpace v-for="(cond, i) in rows" :key="i" align="center" :size="8">
      <NSelect
        v-model:value="cond.factor_id"
        filterable
        :placeholder="$t('page.aiFactor.screen.factorPlaceholder')"
        :options="factorOptions"
        class="w-240px"
      />
      <NSelect v-model:value="cond.op" :options="opOptions" class="w-110px" />
      <NInputNumber
        v-model:value="cond.value"
        :placeholder="cond.op === 'top_n' ? 'N' : $t('page.aiFactor.screen.valuePlaceholder')"
        class="w-140px"
      />
      <NButton
        size="tiny"
        type="error"
        ghost
        :disabled="rows.length <= (allowEmpty ? 0 : 1)"
        @click="removeRow(i)"
      >
        <template #icon><icon-mdi-minus class="text-icon" /></template>
      </NButton>
    </NSpace>
    <NSpace align="center" :size="12">
      <NButton size="small" dashed :disabled="rows.length >= max" @click="addRow">
        <template #icon><icon-mdi-plus class="text-icon" /></template>
        {{ $t('page.aiFactor.screen.addCondition') }}
      </NButton>
      <slot name="extra" />
    </NSpace>
  </NSpace>
</template>

<style scoped></style>
