<script setup lang="ts">
import { watch } from 'vue';
import { useEcharts } from '@/hooks/common/echarts';
import type { ECOption } from '@/hooks/common/echarts';
import { $t } from '@/locales';

/**
 * 回测收益曲线图（每日净值）
 * 复用项目 ECharts 封装（hooks/common/echarts），红涨绿跌与行情页一致
 */
interface Props {
  /** 净值曲线点（按日期升序） */
  data: Api.Backtest.EquityPoint[];
}

const props = defineProps<Props>();

const { domRef, updateOptions } = useEcharts<ECOption>(() => ({
  grid: { left: 12, right: 16, top: 32, bottom: 48, containLabel: true },
  tooltip: { trigger: 'axis' as const },
  xAxis: { type: 'category' as const, boundaryGap: false, data: [] },
  yAxis: { type: 'value' as const, scale: true },
  dataZoom: [{ type: 'inside' as const }, { type: 'slider' as const, height: 18, bottom: 8 }],
  series: [
    {
      name: $t('page.aiBacktest.equity'),
      type: 'line' as const,
      data: [],
      showSymbol: false,
      smooth: true,
      lineStyle: { width: 1.5 },
      areaStyle: { opacity: 0.12 }
    }
  ]
}));

async function renderData() {
  const items = props.data;
  if (!items.length) return;
  const dates = items.map(d => d.date);
  const equities = items.map(d => Number(d.equity));
  const first = equities[0];
  const last = equities[equities.length - 1];
  // 区间首尾净值定涨跌色，红涨绿跌
  const color = last < first ? '#52c41a' : '#f5222d';
  await updateOptions(() => ({
    xAxis: { type: 'category' as const, boundaryGap: false, data: dates },
    series: [
      {
        name: $t('page.aiBacktest.equity'),
        type: 'line' as const,
        data: equities,
        showSymbol: false,
        smooth: true,
        lineStyle: { width: 1.5, color },
        areaStyle: { opacity: 0.12, color }
      }
    ]
  }));
}

watch(() => props.data, renderData, { immediate: true });
</script>

<template>
  <div ref="domRef" class="h-320px w-full" />
</template>
