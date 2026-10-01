<script setup lang="tsx">
/**
 * 每日资讯分析页：早盘（近24h）/ 周度复盘（近7天）两个时段的 AI 资讯分类解读
 * （宏观经济/行业资讯 与 个股资讯 两个分类，各不超过 10 条）+ 长期主线 tab
 */
import { ref } from 'vue';
import { NTab, NTabs } from 'naive-ui';
import AnalysisReportPanel from '../components/analysis-report-panel.vue';
import MainlinePanel from './modules/mainline-panel.vue';

defineOptions({ name: 'AiNewsAnalysis' });

/** 页签：morning-早盘（9:25），weekly-周度复盘（周日 20:30），mainline-长期主线 */
const tab = ref<'morning' | 'weekly' | 'mainline'>('morning');
</script>

<template>
  <div class="flex h-full flex-col gap-8px overflow-hidden">
    <NTabs v-model:value="tab" type="line" size="small">
      <NTab name="morning">{{ $t('page.aiAnalysis.sessionMorning') }}</NTab>
      <NTab name="weekly">{{ $t('page.aiAnalysis.sessionWeekly') }}</NTab>
      <NTab name="mainline">{{ $t('page.aiAnalysis.mainlineTab') }}</NTab>
    </NTabs>
    <MainlinePanel v-if="tab === 'mainline'" class="min-h-0 flex-1" />
    <AnalysisReportPanel
      v-else
      :key="tab"
      analysis-type="news"
      :session="tab"
      class="min-h-0 flex-1"
    />
  </div>
</template>

<style scoped></style>
