<script setup lang="ts">
import { computed, reactive, watch } from 'vue';
import {
  NButton,
  NDrawer,
  NDrawerContent,
  NForm,
  NFormItem,
  NInput,
  NSelect,
  NSpace,
  NSwitch,
  NText
} from 'naive-ui';
import type { FormInst, FormRules } from 'naive-ui';
import { $t } from '@/locales';

defineOptions({ name: 'FactorOperateDrawer' });

interface Props {
  visible: boolean;
  editing: Api.Factor.FactorItem | null;
}

const props = defineProps<Props>();

interface SubmitPayload {
  data: Api.Factor.FactorCreateParams | Api.Factor.FactorUpdateParams;
  isEdit: boolean;
  id?: number;
}

const emit = defineEmits<{
  (e: 'update:visible', visible: boolean): void;
  (e: 'submitted', payload: SubmitPayload): void;
}>();

const CATEGORY_OPTIONS: Array<{ value: string; label: string }> = [
  { value: 'price', label: $t('page.aiFactor.categoryPrice') },
  { value: 'momentum', label: $t('page.aiFactor.categoryMomentum') },
  { value: 'volume', label: $t('page.aiFactor.categoryVolume') },
  { value: 'volatility', label: $t('page.aiFactor.categoryVolatility') },
  { value: 'custom', label: $t('page.aiFactor.categoryCustom') }
];

const isEdit = computed(() => props.editing !== null);
const drawerTitle = computed(() =>
  isEdit.value ? $t('page.aiFactor.editTitle') : $t('page.aiFactor.createTitle')
);

const formRef = reactive<Partial<FormInst>>({});

type Model = {
  name: string;
  code: string;
  category: string;
  formula: string;
  description: string | null;
  source_url: string | null;
  status: boolean;
};

const model = reactive<Model>({
  name: '',
  code: '',
  category: 'custom',
  formula: '',
  description: null,
  source_url: null,
  status: true
});

const rules: FormRules = {
  name: [{ required: true, message: $t('page.aiFactor.form.nameRequired'), trigger: 'blur' }],
  code: [{ required: true, message: $t('page.aiFactor.form.codeRequired'), trigger: 'blur' }],
  formula: [{ required: true, message: $t('page.aiFactor.form.formulaRequired'), trigger: 'blur' }]
};

watch(
  () => props.visible,
  visible => {
    if (!visible) return;
    const e = props.editing;
    model.name = e?.name ?? '';
    model.code = e?.code ?? '';
    model.category = e?.category ?? 'custom';
    model.formula = e?.formula ?? '';
    model.description = e?.description ?? null;
    model.source_url = e?.source_url ?? null;
    model.status = e?.status ?? true;
  }
);

function closeDrawer() {
  emit('update:visible', false);
}

async function handleSubmit() {
  await formRef.validate?.();
  const base = {
    name: model.name.trim(),
    category: model.category,
    formula: model.formula.trim(),
    description: model.description || null,
    source_url: model.source_url || null,
    status: model.status
  };
  // 编辑时 code 不可改，不随请求提交
  const data = isEdit.value ? base : { ...base, code: model.code.trim() };
  emit('submitted', { data, isEdit: isEdit.value, id: props.editing?.id });
  closeDrawer();
}
</script>

<template>
  <NDrawer :show="visible" :width="520" @update:show="v => emit('update:visible', v)">
    <NDrawerContent :title="drawerTitle" closable :native-scrollbar="false">
      <NForm ref="formRef" :model="model" :rules="rules" label-placement="top">
        <NFormItem :label="$t('page.aiFactor.form.name')" path="name">
          <NInput v-model:value="model.name" :placeholder="$t('page.aiFactor.form.namePlaceholder')" />
        </NFormItem>
        <NFormItem path="code">
          <template #label>
            <span>{{ $t('page.aiFactor.form.code') }}</span>
            <NText v-if="isEdit" depth="3" class="ml-8px text-12px">
              {{ $t('page.aiFactor.form.codeImmutable') }}
            </NText>
          </template>
          <NInput
            v-model:value="model.code"
            :disabled="isEdit"
            :placeholder="$t('page.aiFactor.form.codePlaceholder')"
          />
        </NFormItem>
        <NFormItem :label="$t('page.aiFactor.form.category')" path="category">
          <NSelect v-model:value="model.category" :options="CATEGORY_OPTIONS" />
        </NFormItem>
        <NFormItem path="formula">
          <template #label>
            <span>{{ $t('page.aiFactor.form.formula') }}</span>
            <NText depth="3" class="ml-8px text-12px">{{ $t('page.aiFactor.form.formulaTip') }}</NText>
          </template>
          <NInput
            v-model:value="model.formula"
            type="textarea"
            :rows="3"
            class="font-mono"
            placeholder="(close - MA(close, 20)) / MA(close, 20) * 100"
          />
        </NFormItem>
        <NFormItem :label="$t('page.aiFactor.form.description')" path="description">
          <NInput v-model:value="model.description" type="textarea" :rows="2" />
        </NFormItem>
        <NFormItem :label="$t('page.aiFactor.form.sourceUrl')" path="source_url">
          <NInput v-model:value="model.source_url" placeholder="https://" />
        </NFormItem>
        <NFormItem :label="$t('page.aiFactor.form.status')" path="status">
          <NSwitch v-model:value="model.status">
            <template #checked>{{ $t('page.aiFactor.enabled') }}</template>
            <template #unchecked>{{ $t('page.aiFactor.disabled') }}</template>
          </NSwitch>
        </NFormItem>
      </NForm>
      <template #footer>
        <NSpace :size="12" justify="end">
          <NButton @click="closeDrawer">{{ $t('common.cancel') }}</NButton>
          <NButton type="primary" @click="handleSubmit">{{ $t('common.confirm') }}</NButton>
        </NSpace>
      </template>
    </NDrawerContent>
  </NDrawer>
</template>

<style scoped></style>
