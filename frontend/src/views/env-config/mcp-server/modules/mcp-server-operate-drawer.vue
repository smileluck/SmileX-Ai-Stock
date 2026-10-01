<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue';
import { useVModel } from '@vueuse/core';
import type { FormItemRule } from 'naive-ui';
import {
  NButton,
  NDrawer,
  NDrawerContent,
  NForm,
  NFormItemGi,
  NGrid,
  NInput,
  NInputNumber,
  NSpace,
  NSwitch,
  useMessage
} from 'naive-ui';
import { fetchCreateMcpServer, fetchUpdateMcpServer } from '@/service/api';
import { $t } from '@/locales';

defineOptions({ name: 'McpServerOperateDrawer' });

interface Props {
  visible: boolean;
  operateType: Api.OperateType;
  rowData?: Api.McpServer.Server | null;
}

const props = defineProps<Props>();
const emit = defineEmits<{
  'update:visible': [visible: boolean];
  submitted: [];
}>();

const message = useMessage();
const visible = useVModel(props, 'visible');

const drawerTitle = computed(() =>
  props.operateType === 'add' ? $t('page.manage.mcpServer.addServer') : $t('page.manage.mcpServer.editServer')
);

const formRef = ref();

const CODE_PATTERN = /^[a-z][a-z0-9_]*$/;
const URL_PATTERN = /^https?:\/\/.+/;

const formRules = {
  code: [
    { required: true, message: $t('form.required'), trigger: 'blur' },
    {
      validator: (_rule: FormItemRule, value: string) => {
        if (value && !CODE_PATTERN.test(value)) {
          return new Error($t('page.manage.mcpServer.form.codeInvalid'));
        }
        return true;
      },
      trigger: 'blur'
    }
  ],
  name: { required: true, message: $t('form.required'), trigger: 'blur' },
  url: [
    { required: true, message: $t('form.required'), trigger: 'blur' },
    {
      validator: (_rule: FormItemRule, value: string) => {
        if (value && !URL_PATTERN.test(value)) {
          return new Error($t('page.manage.mcpServer.form.urlInvalid'));
        }
        return true;
      },
      trigger: 'blur'
    }
  ]
};

const defaultFormValue = {
  code: '',
  name: '',
  url: '',
  headersText: '',
  enabled: true,
  timeout_s: 30,
  remark: ''
};

const form = reactive({ ...defaultFormValue });

watch(
  () => props.visible,
  val => {
    if (val) {
      if (props.operateType === 'edit' && props.rowData) {
        form.code = props.rowData.code;
        form.name = props.rowData.name;
        form.url = props.rowData.url;
        form.headersText = props.rowData.headers ? JSON.stringify(props.rowData.headers, null, 2) : '';
        form.enabled = props.rowData.enabled;
        form.timeout_s = props.rowData.timeout_s;
        form.remark = props.rowData.remark || '';
      } else {
        Object.assign(form, defaultFormValue);
      }
    }
  }
);

/** 解析 headers JSON 文本，空文本返回 null；格式非法时返回 undefined 并提示 */
function parseHeaders(): Record<string, string> | null | undefined {
  const text = form.headersText.trim();
  if (!text) return null;
  try {
    const parsed = JSON.parse(text);
    if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
      message.error($t('page.manage.mcpServer.form.headersInvalid'));
      return undefined;
    }
    return parsed as Record<string, string>;
  } catch {
    message.error($t('page.manage.mcpServer.form.headersInvalid'));
    return undefined;
  }
}

async function handleSubmit() {
  try {
    await formRef.value?.validate();
  } catch {
    return;
  }
  const headers = parseHeaders();
  if (headers === undefined) return;
  try {
    if (props.operateType === 'add') {
      const payload: Api.McpServer.CreatePayload = {
        code: form.code,
        name: form.name,
        url: form.url,
        headers,
        enabled: form.enabled,
        timeout_s: form.timeout_s,
        remark: form.remark || null
      };
      await fetchCreateMcpServer(payload);
      message.success($t('common.addSuccess'));
    } else if (props.operateType === 'edit' && props.rowData) {
      const payload: Api.McpServer.UpdatePayload = {
        name: form.name,
        url: form.url,
        headers,
        enabled: form.enabled,
        timeout_s: form.timeout_s,
        remark: form.remark || null
      };
      await fetchUpdateMcpServer(props.rowData.id, payload);
      message.success($t('common.updateSuccess'));
    }
    emit('submitted');
    visible.value = false;
  } catch (error) {
    console.error('提交失败:', error);
  }
}
</script>

<template>
  <NDrawer v-model:show="visible" :width="520">
    <NDrawerContent :title="drawerTitle" closable>
      <NForm ref="formRef" :model="form" :rules="formRules" label-placement="top">
        <NGrid responsive="screen" item-responsive>
          <NFormItemGi span="24" :label="$t('page.manage.mcpServer.code')" path="code">
            <NInput
              v-model:value="form.code"
              :disabled="operateType === 'edit'"
              :placeholder="$t('page.manage.mcpServer.form.code')"
            />
          </NFormItemGi>
          <NFormItemGi span="24" :label="$t('page.manage.mcpServer.name')" path="name">
            <NInput v-model:value="form.name" :placeholder="$t('page.manage.mcpServer.form.name')" />
          </NFormItemGi>
          <NFormItemGi span="24" :label="$t('page.manage.mcpServer.url')" path="url">
            <NInput v-model:value="form.url" :placeholder="$t('page.manage.mcpServer.form.url')" />
          </NFormItemGi>
          <NFormItemGi span="24" :label="$t('page.manage.mcpServer.headers')" path="headersText">
            <NInput
              v-model:value="form.headersText"
              type="textarea"
              :rows="4"
              :placeholder="$t('page.manage.mcpServer.form.headers')"
            />
          </NFormItemGi>
          <NFormItemGi span="24 m:12" :label="$t('page.manage.mcpServer.timeout')" path="timeout_s">
            <NInputNumber v-model:value="form.timeout_s" :min="1" :max="300" class="w-full" />
          </NFormItemGi>
          <NFormItemGi span="24 m:12" :label="$t('page.manage.mcpServer.enabled')">
            <NSwitch v-model:value="form.enabled" />
          </NFormItemGi>
          <NFormItemGi span="24" :label="$t('page.manage.mcpServer.remark')" path="remark">
            <NInput
              v-model:value="form.remark"
              type="textarea"
              :rows="2"
              :placeholder="$t('page.manage.mcpServer.form.remark')"
            />
          </NFormItemGi>
        </NGrid>
      </NForm>
      <template #footer>
        <NSpace>
          <NButton @click="visible = false">{{ $t('common.cancel') }}</NButton>
          <NButton type="primary" @click="handleSubmit">{{ $t('common.confirm') }}</NButton>
        </NSpace>
      </template>
    </NDrawerContent>
  </NDrawer>
</template>

<style scoped></style>
