<script setup lang="ts">
import { reactive, ref, watch } from 'vue';
import { NAlert, NButton, NInput, NModal, NRadioButton, NRadioGroup, NSpace, NTag, NText } from 'naive-ui';
import { fetchImportFactors } from '@/service/api';
import { $t } from '@/locales';

defineOptions({ name: 'FactorImportModal' });

interface Props {
  visible: boolean;
}

const props = defineProps<Props>();

const emit = defineEmits<{
  (e: 'update:visible', visible: boolean): void;
  (e: 'imported'): void;
}>();

const mode = ref<'url' | 'content'>('url');
const form = reactive({ url: '', content: '' });
const submitting = ref(false);
const result = ref<Api.Factor.FactorImportResult | null>(null);

watch(
  () => props.visible,
  visible => {
    if (visible) {
      mode.value = 'url';
      form.url = '';
      form.content = '';
      result.value = null;
    }
  }
);

function closeModal() {
  emit('update:visible', false);
}

async function handleSubmit() {
  const payload: Api.Factor.FactorImportParams =
    mode.value === 'url' ? { url: form.url.trim() } : { content: form.content };
  if ((mode.value === 'url' && !payload.url) || (mode.value === 'content' && !payload.content?.trim())) {
    window.$message?.warning($t('page.aiFactor.importModal.inputRequired'));
    return;
  }
  submitting.value = true;
  try {
    const { data, error } = await fetchImportFactors(payload);
    if (!error && data) {
      result.value = data;
      if (data.imported > 0) emit('imported');
    }
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <NModal
    :show="visible"
    preset="card"
    :title="$t('page.aiFactor.importModal.title')"
    class="w-640px"
    @update:show="v => emit('update:visible', v)"
  >
    <NSpace vertical :size="12">
      <NRadioGroup v-model:value="mode" size="small">
        <NRadioButton value="url">{{ $t('page.aiFactor.importModal.byUrl') }}</NRadioButton>
        <NRadioButton value="content">{{ $t('page.aiFactor.importModal.byContent') }}</NRadioButton>
      </NRadioGroup>

      <NInput
        v-if="mode === 'url'"
        v-model:value="form.url"
        placeholder="https://example.com/factors.json"
        clearable
      />
      <NInput
        v-else
        v-model:value="form.content"
        type="textarea"
        :rows="8"
        class="font-mono"
        :placeholder="'[{&quot;name&quot;: &quot;BIAS20&quot;, &quot;code&quot;: &quot;bias20&quot;, &quot;formula&quot;: &quot;(close - MA(close, 20)) / MA(close, 20) * 100&quot;}]'"
      />

      <NAlert type="info" :bordered="false">
        <div class="text-12px whitespace-pre-line">{{ $t('page.aiFactor.importModal.formatTip') }}</div>
      </NAlert>

      <template v-if="result">
        <NSpace align="center" :size="12">
          <NText strong>{{ $t('page.aiFactor.importModal.resultTitle') }}</NText>
          <NTag size="small" type="success" :bordered="false">
            {{ $t('page.aiFactor.importModal.importedCount', { count: result.imported }) }}
          </NTag>
          <NTag size="small" type="warning" :bordered="false">
            {{ $t('page.aiFactor.importModal.skippedCount', { count: result.skipped }) }}
          </NTag>
        </NSpace>
        <NAlert v-if="result.errors.length" type="warning" :bordered="false">
          <div v-for="(err, i) in result.errors" :key="i" class="text-12px">{{ err }}</div>
        </NAlert>
      </template>
    </NSpace>

    <template #footer>
      <NSpace justify="end" :size="12">
        <NButton @click="closeModal">{{ $t('common.cancel') }}</NButton>
        <NButton type="primary" :loading="submitting" @click="handleSubmit">
          {{ $t('page.aiFactor.importModal.submit') }}
        </NButton>
      </NSpace>
    </template>
  </NModal>
</template>

<style scoped></style>
