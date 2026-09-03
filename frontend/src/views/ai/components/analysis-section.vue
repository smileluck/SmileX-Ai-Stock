<script setup lang="ts">
/**
 * AI 分析报告统一区块：左侧主色竖条 + 标题，内容经 slot 传入
 */

defineOptions({ name: 'AnalysisSection' });

defineProps<{
  title: string;
}>();
</script>

<template>
  <div class="analysis-section">
    <div class="analysis-section-title">{{ title }}</div>
    <slot />
  </div>
</template>

<style scoped>
.analysis-section {
  margin-top: 14px;
}
.analysis-section-title {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 600;
}
.analysis-section-title::before {
  content: '';
  flex-shrink: 0;
  width: 3px;
  height: 14px;
  border-radius: 2px;
  background: var(--primary-color);
}
</style>
