<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue';
import { useVModel } from '@vueuse/core';
import {
  NButton,
  NDrawer,
  NDrawerContent,
  NForm,
  NFormItem,
  NInputNumber,
  NRadio,
  NRadioGroup,
  NSwitch,
  useMessage
} from 'naive-ui';
import { fetchUpdateDataSourceConfig } from '@/service/api';
import { useNaiveForm } from '@/hooks/common/form';
import { $t } from '@/locales';
import { circuitModeOptions } from '../shared';

interface Props {
  visible: boolean;
  rowData?: Api.DataSource.SourceInfo | null;
}

const props = defineProps<Props>();
const emit = defineEmits<{
  'update:visible': [visible: boolean];
  submitted: [];
}>();

const message = useMessage();
const visible = useVModel(props, 'visible');

const { formRef, validate, restoreValidation } = useNaiveForm();
const submitting = ref(false);

const defaultFormValue: Api.DataSource.SourceConfig = {
  enabled: true,
  max_concurrency: 2,
  min_interval_ms: 300,
  timeout_s: 30,
  failure_threshold: 5,
  cooldown_s: 300,
  circuit_mode: 'auto'
};

const form = reactive<Api.DataSource.SourceConfig>({ ...defaultFormValue });

const drawerTitle = computed(() =>
  props.rowData
    ? `${$t('page.manage.datasource.editConfig')} - ${props.rowData.name} (${props.rowData.key})`
    : $t('page.manage.datasource.editConfig')
);

const modeOptions = circuitModeOptions();

watch(
  () => props.visible,
  val => {
    if (val) {
      restoreValidation();
      if (props.rowData) {
        Object.assign(form, props.rowData.config);
      } else {
        Object.assign(form, defaultFormValue);
      }
    }
  }
);

async function handleSubmit() {
  if (!props.rowData) return;
  await validate();
  submitting.value = true;
  try {
    const { error } = await fetchUpdateDataSourceConfig({
      source: props.rowData.key,
      config: { ...form }
    });
    if (!error) {
      message.success($t('common.updateSuccess'));
      emit('submitted');
      visible.value = false;
    }
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <NDrawer v-model:show="visible" :width="480" preset="card">
    <NDrawerContent :title="drawerTitle" :native-scrollbar="false">
      <NForm ref="formRef" :model="form" label-placement="left" :label-width="140" size="small">
        <NFormItem :label="$t('page.manage.datasource.enabled')" path="enabled">
          <NSwitch v-model:value="form.enabled" />
        </NFormItem>
        <NFormItem :label="$t('page.manage.datasource.configForm.maxConcurrency')" path="max_concurrency">
          <NInputNumber v-model:value="form.max_concurrency" :min="1" :max="64" class="w-full" />
        </NFormItem>
        <NFormItem :label="$t('page.manage.datasource.configForm.minIntervalMs')" path="min_interval_ms">
          <NInputNumber v-model:value="form.min_interval_ms" :min="0" :step="100" class="w-full" />
        </NFormItem>
        <NFormItem :label="$t('page.manage.datasource.configForm.timeoutS')" path="timeout_s">
          <NInputNumber v-model:value="form.timeout_s" :min="1" class="w-full" />
        </NFormItem>
        <NFormItem :label="$t('page.manage.datasource.configForm.failureThreshold')" path="failure_threshold">
          <NInputNumber v-model:value="form.failure_threshold" :min="1" class="w-full" />
        </NFormItem>
        <NFormItem :label="$t('page.manage.datasource.configForm.cooldownS')" path="cooldown_s">
          <NInputNumber v-model:value="form.cooldown_s" :min="0" :step="60" class="w-full" />
        </NFormItem>
        <NFormItem :label="$t('page.manage.datasource.configForm.circuitMode')" path="circuit_mode">
          <NRadioGroup v-model:value="form.circuit_mode">
            <NRadio v-for="opt in modeOptions" :key="opt.value" :value="opt.value">
              {{ opt.label }}
            </NRadio>
          </NRadioGroup>
        </NFormItem>
      </NForm>
      <template #footer>
        <div class="gap-12px flex-justify-end">
          <NButton size="small" @click="visible = false">
            {{ $t('common.cancel') }}
          </NButton>
          <NButton type="primary" size="small" :loading="submitting" @click="handleSubmit">
            {{ $t('common.confirm') }}
          </NButton>
        </div>
      </template>
    </NDrawerContent>
  </NDrawer>
</template>

<style scoped></style>
