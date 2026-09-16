<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue';
import {
  NButton,
  NCheckbox,
  NCheckboxGroup,
  NDrawer,
  NDrawerContent,
  NForm,
  NFormItem,
  NInput,
  NInputNumber,
  NRadioButton,
  NRadioGroup,
  NSelect,
  NSwitch,
  NText
} from 'naive-ui';
import type { FormInst, FormRules } from 'naive-ui';
import { $t } from '@/locales';

defineOptions({ name: 'StrategyOperateDrawer' });

interface Props {
  visible: boolean;
  editing: Api.Strategy.StrategyItem | null;
}

const props = defineProps<Props>();

interface SubmitPayload {
  data: Api.Strategy.StrategySaveParams;
  isEdit: boolean;
  id?: number;
}

const emit = defineEmits<{
  (e: 'update:visible', visible: boolean): void;
  (e: 'submitted', payload: SubmitPayload): void;
}>();

const PERIOD_OPTIONS: Array<{ value: Api.Strategy.ExecutePeriod; label: string }> = [
  { value: 'pre_market', label: $t('page.aiStrategy.periodPreMarket') },
  { value: 'morning', label: $t('page.aiStrategy.periodMorning') },
  { value: 'noon', label: $t('page.aiStrategy.periodNoon') },
  { value: 'tail', label: $t('page.aiStrategy.periodTail') },
  { value: 'post_close', label: $t('page.aiStrategy.periodPostClose') }
];

const CATEGORY_OPTIONS: Array<{ value: Api.Strategy.StrategyCategory; label: string }> = [
  { value: 'pre_market_auction', label: $t('page.aiStrategy.categoryAuction') },
  { value: 'noon', label: $t('page.aiStrategy.categoryNoon') },
  { value: 'tail', label: $t('page.aiStrategy.categoryTail') },
  { value: 'blue_chip', label: $t('page.aiStrategy.categoryBlueChip') },
  { value: 'general', label: $t('page.aiStrategy.categoryGeneral') }
];

const isEdit = computed(() => props.editing !== null);
const drawerTitle = computed(() =>
  isEdit.value ? $t('page.aiStrategy.editStrategy') : $t('page.aiStrategy.createStrategy')
);

const TYPE_OPTIONS: Array<{ value: Api.Strategy.StrategyType; label: string }> = [
  { value: 'prompt', label: $t('page.aiStrategy.typePrompt') },
  { value: 'rule', label: $t('page.aiStrategy.typeRule') }
];

const formRef = reactive<Partial<FormInst>>({});

/** 规则条件行（op 复用选股器类型；规则模式不提供 top_n 选项，提交时收窄为 RuleOp） */
interface ConditionRow {
  factor_id: number | null;
  op: Api.Factor.ScreenOp;
  value: number | null;
}

type Model = {
  name: string;
  description: string | null;
  category: Api.Strategy.StrategyCategory | string;
  strategy_type: Api.Strategy.StrategyType;
  prompt_template: string | null;
  stockPoolCodes: string;
  execute_periods: Api.Strategy.ExecutePeriod[];
  max_positions: number;
  stop_loss_pct: number | null;
  take_profit_pct: number | null;
  trailing_drawdown_pct: number | null;
  status: boolean;
};

const model = reactive<Model>({
  name: '',
  description: null,
  category: 'general',
  strategy_type: 'prompt',
  prompt_template: null,
  stockPoolCodes: '',
  execute_periods: ['morning'],
  max_positions: 10,
  stop_loss_pct: 5,
  take_profit_pct: 10,
  trailing_drawdown_pct: 5,
  status: true
});

const buyConditions = ref<ConditionRow[]>([{ factor_id: null, op: 'lt', value: null }]);
const sellConditions = ref<ConditionRow[]>([]);

const rules: FormRules = {
  name: [{ required: true, message: $t('page.aiStrategy.form.nameRequired'), trigger: 'blur' }],
  execute_periods: [
    {
      required: true,
      type: 'array',
      message: $t('page.aiStrategy.form.periodRequired'),
      trigger: 'change'
    }
  ]
};

/** 空值回退（拆出以降低 watch 回调复杂度） */
function or<T>(v: T | null | undefined, fallback: T): T {
  return v ?? fallback;
}

/** 后端 rule_config 条件行转表单行（value 为 null 时保持空待用户补填） */
function toRows(conds: Api.Strategy.RuleCondition[] | undefined): ConditionRow[] {
  return (conds ?? []).map(c => ({ factor_id: c.factor_id, op: c.op, value: c.value }));
}

watch(
  () => props.visible,
  visible => {
    if (!visible) return;
    const e = props.editing;
    model.name = or(e?.name, '');
    model.description = or(e?.description, null);
    model.category = or(e?.category, 'general');
    model.strategy_type = or(e?.strategy_type, 'prompt');
    model.prompt_template = or(e?.prompt_template, null);
    model.stockPoolCodes = or(e?.stock_pool?.codes, []).join(', ');
    model.execute_periods = or(e?.execute_periods, ['morning']);
    model.max_positions = or(e?.max_positions, 10);
    model.stop_loss_pct = or(e?.stop_loss_pct, 5);
    model.take_profit_pct = or(e?.take_profit_pct, 10);
    model.trailing_drawdown_pct = or(e?.trailing_drawdown_pct, 5);
    model.status = or(e?.status, true);
    buyConditions.value = toRows(e?.rule_config?.buy_conditions);
    if (!buyConditions.value.length) buyConditions.value = [{ factor_id: null, op: 'lt', value: null }];
    sellConditions.value = toRows(e?.rule_config?.sell_conditions);
  }
);

function closeDrawer() {
  emit('update:visible', false);
}

/** 规则模式校验并组装 rule_config；不合法时提示并返回 null */
function buildRuleConfig(codes: string[]): Api.Strategy.RuleConfig | null | 'invalid' {
  if (model.strategy_type === 'prompt') return null;
  if (!codes.length) {
    window.$message?.warning($t('page.aiStrategy.form.rulePoolRequired'));
    return 'invalid';
  }
  const valid = (rows: ConditionRow[]) => rows.filter(c => c.factor_id !== null && c.value !== null);
  const buys = valid(buyConditions.value);
  if (!buys.length) {
    window.$message?.warning($t('page.aiStrategy.form.buyConditionRequired'));
    return 'invalid';
  }
  return {
    buy_conditions: buys.map(c => ({ factor_id: c.factor_id!, op: c.op as Api.Strategy.RuleOp, value: c.value! })),
    sell_conditions: valid(sellConditions.value).map(c => ({
      factor_id: c.factor_id!,
      op: c.op as Api.Strategy.RuleOp,
      value: c.value!
    }))
  };
}

async function handleSubmit() {
  await formRef.validate?.();
  const codes = model.stockPoolCodes
    .split(/[,，\s]+/)
    .map(s => s.trim())
    .filter(Boolean);
  const ruleConfig = buildRuleConfig(codes);
  if (ruleConfig === 'invalid') return;
  const data: Api.Strategy.StrategySaveParams = {
    name: model.name,
    description: model.description || null,
    category: model.category || 'general',
    strategy_type: model.strategy_type,
    rule_config: ruleConfig,
    prompt_template: model.strategy_type === 'prompt' ? model.prompt_template || null : null,
    stock_pool: codes.length > 0 ? { codes } : null,
    execute_periods: model.execute_periods,
    max_positions: model.max_positions,
    stop_loss_pct: model.stop_loss_pct,
    take_profit_pct: model.take_profit_pct,
    trailing_drawdown_pct: model.trailing_drawdown_pct,
    status: model.status
  };
  emit('submitted', { data, isEdit: isEdit.value, id: props.editing?.id });
  closeDrawer();
}
</script>

<template>
  <NDrawer :show="visible" :width="520" @update:show="v => emit('update:visible', v)">
    <NDrawerContent :title="drawerTitle" closable :native-scrollbar="false">
      <NForm ref="formRef" :model="model" :rules="rules" label-placement="top">
        <NFormItem :label="$t('page.aiStrategy.form.strategyType')" path="strategy_type">
          <NSpace align="center" :size="12">
            <NRadioGroup v-model:value="model.strategy_type" :disabled="isEdit">
              <NRadioButton v-for="opt in TYPE_OPTIONS" :key="opt.value" :value="opt.value" :label="opt.label" />
            </NRadioGroup>
            <NText v-if="isEdit" depth="3" class="text-12px">{{ $t('page.aiStrategy.form.strategyTypeTip') }}</NText>
          </NSpace>
        </NFormItem>
        <NFormItem :label="$t('page.aiStrategy.form.name')" path="name">
          <NInput v-model:value="model.name" :placeholder="$t('page.aiStrategy.form.namePlaceholder')" />
        </NFormItem>
        <NFormItem :label="$t('page.aiStrategy.form.description')" path="description">
          <NInput v-model:value="model.description" type="textarea" :rows="2" />
        </NFormItem>
        <NFormItem :label="$t('page.aiStrategy.form.category')" path="category">
          <NSelect v-model:value="model.category" :options="CATEGORY_OPTIONS" />
        </NFormItem>
        <NFormItem v-if="model.strategy_type === 'prompt'" :label="$t('page.aiStrategy.form.prompt')" path="prompt_template">
          <NInput
            v-model:value="model.prompt_template"
            type="textarea"
            :rows="5"
            :placeholder="$t('page.aiStrategy.form.promptPlaceholder')"
          />
        </NFormItem>
        <template v-else>
          <NFormItem :label="$t('page.aiStrategy.form.buyConditions')" path="buyConditions">
            <FactorConditionBuilder v-model="buyConditions" />
          </NFormItem>
          <NFormItem path="sellConditions">
            <template #label>
              <NSpace align="center" :size="8">
                <span>{{ $t('page.aiStrategy.form.sellConditions') }}</span>
                <NText depth="3" class="text-12px">{{ $t('page.aiStrategy.form.sellConditionsTip') }}</NText>
              </NSpace>
            </template>
            <FactorConditionBuilder v-model="sellConditions" allow-empty />
          </NFormItem>
        </template>
        <NFormItem :label="$t('page.aiStrategy.form.stockPool')" path="stockPoolCodes">
          <NInput
            v-model:value="model.stockPoolCodes"
            :placeholder="
              model.strategy_type === 'rule'
                ? $t('page.aiStrategy.form.stockPoolPlaceholderRule')
                : $t('page.aiStrategy.form.stockPoolPlaceholder')
            "
          />
        </NFormItem>
        <NFormItem :label="$t('page.aiStrategy.form.periods')" path="execute_periods">
          <NCheckboxGroup v-model:value="model.execute_periods">
            <NSpace>
              <NCheckbox v-for="opt in PERIOD_OPTIONS" :key="opt.value" :value="opt.value" :label="opt.label" />
            </NSpace>
          </NCheckboxGroup>
        </NFormItem>
        <NFormItem :label="$t('page.aiStrategy.form.maxPositions')" path="max_positions">
          <NInputNumber v-model:value="model.max_positions" :min="1" :max="100" class="w-full" />
        </NFormItem>
        <NSpace>
          <NFormItem :label="$t('page.aiStrategy.form.stopLoss')" path="stop_loss_pct" class="w-200px">
            <NInputNumber v-model:value="model.stop_loss_pct" :min="0" :max="100">
              <template #suffix>%</template>
            </NInputNumber>
          </NFormItem>
          <NFormItem :label="$t('page.aiStrategy.form.takeProfit')" path="take_profit_pct" class="w-200px">
            <NInputNumber v-model:value="model.take_profit_pct" :min="0" :max="500">
              <template #suffix>%</template>
            </NInputNumber>
          </NFormItem>
        </NSpace>
        <NFormItem :label="$t('page.aiStrategy.form.trailingDrawdown')" path="trailing_drawdown_pct">
          <NInputNumber v-model:value="model.trailing_drawdown_pct" :min="0" :max="100">
            <template #suffix>%</template>
          </NInputNumber>
        </NFormItem>
        <NFormItem :label="$t('page.aiStrategy.form.status')" path="status">
          <NSwitch v-model:value="model.status">
            <template #checked>{{ $t('page.aiStrategy.enabled') }}</template>
            <template #unchecked>{{ $t('page.aiStrategy.disabled') }}</template>
          </NSwitch>
        </NFormItem>
      </NForm>
      <template #footer>
        <NSpace :size="12">
          <NText depth="3" class="flex-y-center text-12px">{{ $t('page.aiStrategy.form.tip') }}</NText>
          <NButton @click="closeDrawer">{{ $t('common.cancel') }}</NButton>
          <NButton type="primary" @click="handleSubmit">{{ $t('common.confirm') }}</NButton>
        </NSpace>
      </template>
    </NDrawerContent>
  </NDrawer>
</template>

<style scoped></style>
