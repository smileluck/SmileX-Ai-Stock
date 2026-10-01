<script setup lang="ts">
import { toRaw } from 'vue';
import { NCollapse, NCollapseItem, NForm, NFormItemGi, NGrid, NInput, NSelect, NSpace, NButton } from 'naive-ui';
import { jsonClone } from '@sa/utils';
import { enableStatusOptions, yesOrNoOptions } from '@/constants/business';
import { $t } from '@/locales';
import { getGridActionSpan } from '@/utils/common';

defineOptions({ name: 'AiModelSearch' });

interface Emits {
  (e: 'search'): void;
  (e: 'reset'): void;
}

const emit = defineEmits<Emits>();

const model = defineModel<Api.SystemManage.AiModelSearchParams>('model', { required: true });

const defaultModel = jsonClone(toRaw(model.value));

const actionSpan = getGridActionSpan(5);

const providerOptions = [
  { label: 'OpenAI', value: 'openai' },
  { label: 'Anthropic', value: 'anthropic' },
  { label: 'DeepSeek', value: 'deepseek' },
  { label: '通义千问', value: 'qwen' },
  { label: '智谱', value: 'zhipu' },
  { label: 'MiniMax', value: 'minimax' },
  { label: '自定义', value: 'custom' }
];

const billingModeOptions = [
  { label: $t('page.manage.aiModel.payAsYouGo'), value: 'pay_as_you_go' },
  { label: $t('page.manage.aiModel.codingPlan'), value: 'coding_plan' }
];

function resetModel() {
  Object.assign(model.value, defaultModel);
  emit('reset');
}

function search() {
  emit('search');
}
</script>

<template>
  <NCollapse :default-expanded-names="['ai-model-search']">
    <NCollapseItem :title="$t('common.search')" name="ai-model-search">
      <NForm :model="model" label-placement="left" :label-width="80">
        <NGrid responsive="screen" item-responsive>
          <NFormItemGi span="24 s:12 m:6" :label="$t('page.manage.aiModel.modelName')" path="name" class="pr-24px">
            <NInput v-model:value="model.name" :placeholder="$t('page.manage.aiModel.form.modelName')" clearable />
          </NFormItemGi>
          <NFormItemGi span="24 s:12 m:6" :label="$t('page.manage.aiModel.provider')" path="provider" class="pr-24px">
            <NSelect v-model:value="model.provider" :options="providerOptions" :placeholder="$t('page.manage.aiModel.form.provider')" clearable />
          </NFormItemGi>
          <NFormItemGi span="24 s:12 m:6" :label="$t('page.manage.aiModel.billingMode')" path="billing_mode" class="pr-24px">
            <NSelect v-model:value="model.billing_mode" :options="billingModeOptions" :placeholder="$t('page.manage.aiModel.form.billingMode')" clearable />
          </NFormItemGi>
          <NFormItemGi span="24 s:12 m:6" :label="$t('page.manage.aiModel.status')" path="status" class="pr-24px">
            <NSelect v-model:value="model.status" :options="enableStatusOptions" :placeholder="$t('page.manage.aiModel.form.status')" clearable />
          </NFormItemGi>
          <NFormItemGi span="24 s:12 m:6" :label="$t('page.manage.aiModel.isDefault')" path="is_default" class="pr-24px">
            <NSelect v-model:value="model.is_default" :options="yesOrNoOptions" :placeholder="$t('page.manage.aiModel.form.isDefault')" clearable />
          </NFormItemGi>
          <NFormItemGi :span="actionSpan" class="pr-24px">
            <NSpace class="w-full" justify="end">
              <NButton @click="resetModel">
                <template #icon>
                  <icon-ic-round-refresh class="text-icon" />
                </template>
                {{ $t('common.reset') }}
              </NButton>
              <NButton type="primary" ghost @click="search">
                <template #icon>
                  <icon-ic-round-search class="text-icon" />
                </template>
                {{ $t('common.search') }}
              </NButton>
            </NSpace>
          </NFormItemGi>
        </NGrid>
      </NForm>
    </NCollapseItem>
  </NCollapse>
</template>

<style scoped></style>
