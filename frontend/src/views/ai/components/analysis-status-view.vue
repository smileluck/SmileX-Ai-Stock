<script setup lang="ts">
/**
 * AI 分析报告三态占位视图（生成中 / 失败 / 无记录），分析面板与财报页共用
 */
import { NEmpty, NText } from 'naive-ui';
import { $t } from '@/locales';

defineOptions({ name: 'AnalysisStatusView' });

withDefaults(
  defineProps<{
    status: 'running' | 'failed' | 'empty';
    errorMsg?: string | null;
    emptyTip?: string;
  }>(),
  { errorMsg: null, emptyTip: undefined }
);
</script>

<template>
  <!-- 生成中 -->
  <div v-if="status === 'running'" class="flex-col items-center gap-12px py-48px">
    <icon-mdi-robot-excited class="text-48px" style="color: var(--primary-color)" />
    <NText depth="3">{{ $t('page.aiAnalysis.generatingTip') }}</NText>
  </div>

  <!-- 失败 -->
  <div v-else-if="status === 'failed'" class="py-24px">
    <NEmpty :description="$t('page.aiAnalysis.failedTip')">
      <template #icon><icon-mdi-alert-circle-outline class="text-48px" style="color: #e0a240" /></template>
      <template #extra>
        <NText v-if="errorMsg" type="error" class="text-12px">{{ errorMsg }}</NText>
      </template>
    </NEmpty>
  </div>

  <!-- 无记录 -->
  <NEmpty v-else class="py-48px" :description="emptyTip ?? $t('page.aiAnalysis.emptyTip')" />
</template>
