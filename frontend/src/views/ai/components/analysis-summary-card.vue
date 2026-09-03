<script setup lang="ts">
/**
 * AI 分析报告顶部摘要卡容器：轻边框 + 浅底，内容经 slot 传入
 */

defineOptions({ name: 'AnalysisSummaryCard' });
</script>

<template>
  <div class="rounded-8px border border-gray-200 bg-gray-500/3 px-14px py-10px dark:border-gray-700 dark:bg-transparent">
    <slot />
  </div>
</template>
