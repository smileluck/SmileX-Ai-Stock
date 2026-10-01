<script setup lang="ts">
import { computed, nextTick, reactive, ref, watch } from 'vue';
import { useVModel } from '@vueuse/core';
import {
  NButton,
  NDrawer,
  NDrawerContent,
  NForm,
  NFormItemGi,
  NGrid,
  NInput,
  NInputGroup,
  NInputNumber,
  NSelect,
  NSwitch,
  useMessage
} from 'naive-ui';
import { fetchAiModelModels, fetchCreateAiModel, fetchTestAiModelLive, fetchUpdateAiModel } from '@/service/api';
import { $t } from '@/locales';

interface Props {
  visible: boolean;
  operateType: Api.OperateType;
  rowData?: Api.SystemManage.AiModel | null;
}

const props = defineProps<Props>();
const emit = defineEmits<{
  'update:visible': [visible: boolean];
  submitted: [];
}>();

const message = useMessage();
const visible = useVModel(props, 'visible');

const formRef = ref();
const formRules = {
  name: { required: true, message: $t('form.required'), trigger: 'blur' },
  provider: { required: true, message: $t('form.required'), trigger: 'change' },
  base_url: { required: true, message: $t('form.required'), trigger: 'blur' },
  model_name: { required: true, message: $t('form.required'), trigger: 'blur' }
};

const defaultFormValue: Api.SystemManage.AiModelCreate = {
  name: '',
  provider: 'openai',
  base_url: 'https://api.openai.com/v1',
  billing_mode: 'pay_as_you_go',
  api_key: '',
  model_name: '',
  temperature: 0.7,
  max_tokens: null,
  is_default: '2',
  status: '1',
  remark: ''
};

const form = reactive<Api.SystemManage.AiModelCreate>({ ...defaultFormValue });

const providerOptions = [
  { label: 'OpenAI', value: 'openai' },
  { label: 'Anthropic Claude', value: 'anthropic' },
  { label: 'DeepSeek', value: 'deepseek' },
  { label: '通义千问', value: 'qwen' },
  { label: '智谱 GLM', value: 'zhipu' },
  { label: 'MiniMax', value: 'minimax' },
  { label: '自定义 (OpenAI 兼容)', value: 'custom' }
];

const billingModeOptions = [
  { label: $t('page.manage.aiModel.payAsYouGo'), value: 'pay_as_you_go' },
  { label: $t('page.manage.aiModel.codingPlan'), value: 'coding_plan' }
];

// 与后端 AI_PROVIDER_DEFAULT_BASE_URL 保持一致：按 (provider, billing_mode) 取默认端点
const providerDefaultBaseUrl: Record<string, Record<string, string>> = {
  openai: {
    pay_as_you_go: 'https://api.openai.com/v1',
    coding_plan: 'https://api.openai.com/v1'
  },
  anthropic: {
    pay_as_you_go: 'https://api.anthropic.com',
    coding_plan: 'https://api.anthropic.com'
  },
  deepseek: {
    pay_as_you_go: 'https://api.deepseek.com/v1',
    coding_plan: 'https://api.deepseek.com/v1'
  },
  qwen: {
    pay_as_you_go: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    coding_plan: 'https://dashscope.aliyuncs.com/compatible-mode/v1'
  },
  zhipu: {
    pay_as_you_go: 'https://open.bigmodel.cn/api/paas/v4',
    coding_plan: 'https://open.bigmodel.cn/api/coding/paas/v4'
  },
  minimax: {
    pay_as_you_go: 'https://api.minimaxi.com/v1',
    coding_plan: 'https://api.minimaxi.com/v1'
  },
  custom: { pay_as_you_go: '', coding_plan: '' }
};

const knownDefaultBaseUrls = Object.values(providerDefaultBaseUrl).flatMap(m => Object.values(m));

// ==================== 拉取模型列表 ====================
const modelOptions = ref<string[]>([]);
const fetchingModels = ref(false);
const modelNameSelectRef = ref<InstanceType<typeof NSelect> | null>(null);

const modelNameOptions = computed(() =>
  modelOptions.value.map(m => ({ label: m, value: m }))
);

const drawerTitle = computed(() => {
  return props.operateType === 'add' ? $t('page.manage.aiModel.addModel') : $t('page.manage.aiModel.editModel');
});

/** provider / billing_mode 变化时自动填充默认 base_url（仅当为空或等于已知默认值时） */
function autoFillBaseUrl() {
  const preset = providerDefaultBaseUrl[form.provider]?.[form.billing_mode];
  if (preset === undefined) return;
  if (!form.base_url || knownDefaultBaseUrls.includes(form.base_url)) {
    form.base_url = preset;
  }
}

function handleProviderChange() {
  autoFillBaseUrl();
  modelOptions.value = [];
}

function handleBillingModeChange() {
  autoFillBaseUrl();
}

async function handleFetchModels() {
  if (!form.api_key) {
    message.warning($t('page.manage.aiModel.form.apiKeyRequired'));
    return;
  }
  fetchingModels.value = true;
  try {
    const { data, error } = await fetchAiModelModels({
      provider: form.provider,
      base_url: form.base_url || null,
      billing_mode: form.billing_mode,
      api_key: form.api_key
    });
    if (!error && data) {
      if (data.success) {
        modelOptions.value = data.models ?? [];
        if (modelOptions.value.length === 0) {
          message.warning($t('page.manage.aiModel.form.noModels'));
        } else {
          message.success($t('page.manage.aiModel.form.modelsFetched', { count: modelOptions.value.length }));
          // 拉取成功后自动聚焦模型下拉并展开候选列表
          await nextTick();
          modelNameSelectRef.value?.focus();
        }
      } else {
        message.error(data.message || $t('page.manage.aiModel.form.noModels'));
      }
    }
  } finally {
    fetchingModels.value = false;
  }
}

watch(
  () => props.visible,
  val => {
    if (val) {
      modelOptions.value = [];
      if (props.operateType === 'edit' && props.rowData) {
        form.name = props.rowData.name;
        form.provider = props.rowData.provider;
        form.base_url = props.rowData.base_url;
        form.billing_mode = props.rowData.billing_mode || 'pay_as_you_go';
        form.api_key = '';
        form.model_name = props.rowData.model_name;
        form.temperature = props.rowData.temperature;
        form.max_tokens = props.rowData.max_tokens;
        form.is_default = props.rowData.is_default || '2';
        form.status = props.rowData.status || '1';
        form.remark = props.rowData.remark || '';
      } else {
        Object.assign(form, defaultFormValue);
      }
    }
  }
);

async function handleSubmit() {
  try {
    await formRef.value?.validate();
    if (props.operateType === 'add') {
      await fetchCreateAiModel(form);
      message.success($t('common.addSuccess'));
      emit('submitted');
      visible.value = false;
    } else if (props.operateType === 'edit' && props.rowData) {
      // 编辑时 api_key 留空表示不修改
      const updateData: Api.SystemManage.AiModelUpdate = { ...form };
      if (!form.api_key) {
        updateData.api_key = undefined;
      }
      await fetchUpdateAiModel(props.rowData.id, updateData);
      message.success($t('common.updateSuccess'));
      emit('submitted');
      visible.value = false;
    }
  } catch (error) {
    console.error('提交失败:', error);
  }
}

// ==================== 即时测试连接 ====================
const testing = ref(false);

async function handleTestConnection() {
  if (!form.model_name) {
    message.warning($t('page.manage.aiModel.form.modelId'));
    return;
  }
  testing.value = true;
  try {
    const { data, error } = await fetchTestAiModelLive({
      provider: form.provider,
      base_url: form.base_url || null,
      billing_mode: form.billing_mode,
      model_name: form.model_name,
      // api_key 留空（编辑态）时传 model_id，后端使用已保存的 key
      api_key: form.api_key || null,
      model_id: props.operateType === 'edit' && props.rowData ? props.rowData.id : null
    });
    if (!error && data) {
      if (data.success) {
        message.success(`${$t('page.manage.aiModel.testConnection')}: ${data.message}`);
      } else {
        message.error(`${$t('page.manage.aiModel.testFailed')}: ${data.message}`);
      }
    }
  } finally {
    testing.value = false;
  }
}
</script>

<template>
  <NDrawer v-model:show="visible" :width="520">
    <NDrawerContent :title="drawerTitle" closable>
      <NForm ref="formRef" :model="form" :rules="formRules" label-placement="top">
        <NGrid responsive="screen" item-responsive>
          <NFormItemGi span="24" :label="$t('page.manage.aiModel.modelName')" path="name">
            <NInput v-model:value="form.name" :placeholder="$t('page.manage.aiModel.form.modelName')" />
          </NFormItemGi>
          <NFormItemGi span="24 m:12" :label="$t('page.manage.aiModel.provider')" path="provider">
            <NSelect
              v-model:value="form.provider"
              :options="providerOptions"
              :placeholder="$t('page.manage.aiModel.form.provider')"
              @update:value="handleProviderChange"
            />
          </NFormItemGi>
          <NFormItemGi span="24 m:12" :label="$t('page.manage.aiModel.billingMode')" path="billing_mode">
            <NSelect
              v-model:value="form.billing_mode"
              :options="billingModeOptions"
              :placeholder="$t('page.manage.aiModel.form.billingMode')"
              @update:value="handleBillingModeChange"
            />
          </NFormItemGi>
          <NFormItemGi span="24" :label="$t('page.manage.aiModel.modelId')" path="model_name">
            <NInputGroup>
              <NSelect
                ref="modelNameSelectRef"
                v-model:value="form.model_name"
                :options="modelNameOptions"
                :placeholder="$t('page.manage.aiModel.form.modelId')"
                filterable
                tag
                clearable
                :loading="fetchingModels"
              />
              <NButton
                type="primary"
                ghost
                :loading="fetchingModels"
                :disabled="!form.api_key"
                @click="handleFetchModels"
              >
                {{ $t('page.manage.aiModel.fetchModels') }}
              </NButton>
            </NInputGroup>
          </NFormItemGi>
          <NFormItemGi span="24" :label="$t('page.manage.aiModel.baseUrl')" path="base_url">
            <NInput v-model:value="form.base_url" :placeholder="$t('page.manage.aiModel.form.baseUrl')" />
          </NFormItemGi>
          <NFormItemGi span="24" :label="$t('page.manage.aiModel.apiKey')" path="api_key">
            <NInput
              v-model:value="form.api_key"
              type="password"
              show-password-on="click"
              :placeholder="operateType === 'edit' ? $t('page.manage.aiModel.form.apiKeyEditHint') : $t('page.manage.aiModel.form.apiKey')"
            />
          </NFormItemGi>
          <NFormItemGi span="24 m:12" :label="$t('page.manage.aiModel.temperature')" path="temperature">
            <NInputNumber v-model:value="form.temperature" :step="0.1" :min="0" :max="2" class="w-full" />
          </NFormItemGi>
          <NFormItemGi span="24 m:12" :label="$t('page.manage.aiModel.maxTokens')" path="max_tokens">
            <NInputNumber v-model:value="form.max_tokens" :min="1" class="w-full" />
          </NFormItemGi>
          <NFormItemGi span="24" :label="$t('page.manage.aiModel.remark')" path="remark">
            <NInput v-model:value="form.remark" type="textarea" :rows="2" :placeholder="$t('page.manage.aiModel.form.remark')" />
          </NFormItemGi>
          <NFormItemGi span="24 m:12" :label="$t('page.manage.aiModel.isDefault')">
            <NSwitch
              :value="form.is_default === '1'"
              @update:value="val => (form.is_default = val ? '1' : '2')"
            />
          </NFormItemGi>
          <NFormItemGi span="24 m:12" :label="$t('page.manage.aiModel.status')">
            <NSwitch :value="form.status === '1'" @update:value="val => (form.status = val ? '1' : '2')" />
          </NFormItemGi>
        </NGrid>
      </NForm>
      <template #footer>
        <NSpace>
          <NButton :loading="testing" @click="handleTestConnection">
            <template #icon><icon-mdi-lan-connect class="text-icon" /></template>
            {{ $t('page.manage.aiModel.testConnection') }}
          </NButton>
          <NButton @click="visible = false">{{ $t('common.cancel') }}</NButton>
          <NButton type="primary" @click="handleSubmit">{{ $t('common.confirm') }}</NButton>
        </NSpace>
      </template>
    </NDrawerContent>
  </NDrawer>
</template>

<style scoped></style>
