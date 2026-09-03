<script setup lang="ts">
/**
 * AI 分析报告 markdown 正文渲染（大盘/板块/资讯/轮动/财报共用）
 * 内部剥离开头 ```json 摘要块与 <think> 块后渲染，统一样式
 */
import { computed } from 'vue';
import { renderAnalysisMarkdown } from '../utils';

defineOptions({ name: 'AnalysisMarkdown' });

const props = defineProps<{
  raw: string;
}>();

const html = computed(() => renderAnalysisMarkdown(props.raw ?? ''));
</script>

<template>
  <div class="analysis-markdown text-13px" v-html="html" />
</template>

<style scoped>
.analysis-markdown {
  word-break: break-word;
}
.analysis-markdown > :deep(:first-child) {
  margin-top: 0;
}
.analysis-markdown > :deep(:last-child) {
  margin-bottom: 0;
}
.analysis-markdown :deep(h2) {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 18px 0 8px;
  font-size: 15px;
  font-weight: 600;
  line-height: 22px;
}
.analysis-markdown :deep(h2)::before {
  content: '';
  flex-shrink: 0;
  width: 3px;
  height: 14px;
  border-radius: 2px;
  background: var(--primary-color);
}
.analysis-markdown :deep(h3) {
  margin: 14px 0 6px;
  font-size: 14px;
  font-weight: 600;
}
.analysis-markdown :deep(h4) {
  margin: 10px 0 4px;
  font-size: 13px;
  font-weight: 600;
}
.analysis-markdown :deep(p) {
  margin: 8px 0;
  line-height: 24px;
}
.analysis-markdown :deep(ul),
.analysis-markdown :deep(ol) {
  margin: 8px 0;
  padding-left: 20px;
}
.analysis-markdown :deep(li) {
  margin: 2px 0;
  line-height: 24px;
}
.analysis-markdown :deep(strong) {
  font-weight: 600;
}
.analysis-markdown :deep(a) {
  color: var(--primary-color);
  text-decoration: none;
}
.analysis-markdown :deep(a:hover) {
  text-decoration: underline;
}
.analysis-markdown :deep(blockquote) {
  margin: 8px 0;
  padding: 6px 12px;
  border-left: 3px solid var(--primary-color);
  border-radius: 0 6px 6px 0;
  background: rgba(128, 128, 128, 0.06);
}
.analysis-markdown :deep(blockquote p) {
  margin: 4px 0;
}
.analysis-markdown :deep(hr) {
  margin: 14px 0;
  border: none;
  border-top: 1px solid rgba(128, 128, 128, 0.25);
}
.analysis-markdown :deep(table) {
  margin: 10px 0;
  border-collapse: collapse;
}
.analysis-markdown :deep(th),
.analysis-markdown :deep(td) {
  padding: 5px 10px;
  border: 1px solid rgba(128, 128, 128, 0.3);
}
.analysis-markdown :deep(th) {
  font-weight: 500;
  background: rgba(128, 128, 128, 0.1);
}
.analysis-markdown :deep(code) {
  padding: 1px 5px;
  border-radius: 4px;
  font-size: 12px;
  background: rgba(128, 128, 128, 0.12);
}
.analysis-markdown :deep(pre) {
  margin: 10px 0;
  padding: 10px 12px;
  border-radius: 6px;
  overflow-x: auto;
  background: rgba(128, 128, 128, 0.1);
}
.analysis-markdown :deep(pre code) {
  padding: 0;
  background: transparent;
}
</style>
