<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { NEmpty, NSelect } from 'naive-ui';
import dayjs from 'dayjs';
import { useEcharts } from '@/hooks/common/echarts';
import { $t } from '@/locales';

interface Props {
  data?: Api.DataSource.StatRecord[];
  /** 可筛选的数据源选项 */
  sourceOptions?: { label: string; value: string }[];
}

const props = withDefaults(defineProps<Props>(), {
  data: () => [],
  sourceOptions: () => []
});

/** 选中的数据源 key，null 表示全部 */
const selectedSources = ref<string[]>([]);

/** 按小时聚合所选数据源的总调用量与成功率 */
const hourlySeries = computed(() => {
  const selected = selectedSources.value;
  const rows = props.data.filter(item => selected.length === 0 || selected.includes(item.source_key));
  const bucketMap = new Map<string, { total: number; success: number }>();
  rows.forEach(item => {
    const bucket = bucketMap.get(item.stat_hour) ?? { total: 0, success: 0 };
    bucket.total += item.total_calls;
    bucket.success += item.success_calls;
    bucketMap.set(item.stat_hour, bucket);
  });
  const hours = Array.from(bucketMap.keys()).sort();
  return {
    hours: hours.map(h => dayjs(h).format('MM-DD HH:mm')),
    totals: hours.map(h => bucketMap.get(h)?.total ?? 0),
    rates: hours.map(h => {
      const bucket = bucketMap.get(h);
      if (!bucket || bucket.total === 0) return 0;
      return Number(((bucket.success / bucket.total) * 100).toFixed(1));
    })
  };
});

const { domRef, updateOptions } = useEcharts(() => ({
  tooltip: {
    trigger: 'axis' as const,
    axisPointer: {
      type: 'cross' as const
    }
  },
  legend: {
    data: [$t('page.manage.datasource.stats.totalCalls'), $t('page.manage.datasource.stats.successRate')],
    top: '0'
  },
  grid: {
    left: '3%',
    right: '4%',
    bottom: '3%',
    top: '15%',
    containLabel: true
  },
  xAxis: {
    type: 'category' as const,
    boundaryGap: true,
    data: [] as string[]
  },
  yAxis: [
    {
      type: 'value' as const,
      name: $t('page.manage.datasource.stats.totalCalls'),
      position: 'left' as const
    },
    {
      type: 'value' as const,
      name: $t('page.manage.datasource.stats.successRate'),
      position: 'right' as const,
      min: 0,
      max: 100,
      axisLabel: {
        formatter: '{value} %'
      }
    }
  ],
  series: [
    {
      name: $t('page.manage.datasource.stats.totalCalls'),
      type: 'bar' as const,
      yAxisIndex: 0,
      data: [] as number[]
    },
    {
      name: $t('page.manage.datasource.stats.successRate'),
      type: 'line' as const,
      smooth: true,
      yAxisIndex: 1,
      data: [] as number[]
    }
  ]
}));

watch(
  hourlySeries,
  val => {
    updateOptions(opts => {
      opts.xAxis.data = val.hours;
      opts.series[0].data = val.totals;
      opts.series[1].data = val.rates;
      return opts;
    });
  },
  { immediate: true, deep: true }
);
</script>

<template>
  <div class="flex-col-stretch gap-12px">
    <NSelect
      v-model:value="selectedSources"
      multiple
      clearable
      max-tag-count="responsive"
      :options="sourceOptions"
      :placeholder="$t('page.manage.datasource.stats.filterSources')"
      class="max-w-480px"
    />
    <NEmpty v-if="hourlySeries.hours.length === 0" :description="$t('page.manage.datasource.stats.noData')" />
    <div v-else ref="domRef" class="h-360px overflow-hidden"></div>
  </div>
</template>

<style scoped></style>
