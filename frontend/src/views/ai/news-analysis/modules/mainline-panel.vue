<script setup lang="ts">
/**
 * 长期主线面板：LLM 主线分析（每日资讯分析 morning 产出）+ 主线分组资讯
 */
import { onMounted, ref } from 'vue';
import { NBadge, NButton, NCard, NCollapse, NCollapseItem, NEmpty, NSpin, NTag } from 'naive-ui';
import { fetchGetNewsMainlines } from '@/service/api';
import { $t } from '@/locales';
import NewsDetailDrawer from '@/views/info/news/modules/news-detail-drawer.vue';

defineOptions({ name: 'NewsMainlinePanel' });

const loading = ref(false);
const result = ref<Api.Analysis.NewsMainlinesResult | null>(null);

/** trend → 标签颜色 */
const TREND_COLOR_MAP: Record<string, NaiveUI.ThemeColor> = {
  走强: 'error',
  走弱: 'success',
  延续: 'info',
  分歧: 'warning'
};

function trendColor(trend: string | null | undefined): NaiveUI.ThemeColor {
  return TREND_COLOR_MAP[trend || ''] ?? 'default';
}

/** 资讯详情抽屉 */
const drawerVisible = ref(false);
const currentNewsId = ref<number | null>(null);

function openDetail(id: number) {
  currentNewsId.value = id;
  drawerVisible.value = true;
}

async function loadData() {
  loading.value = true;
  try {
    const { data, error } = await fetchGetNewsMainlines();
    if (!error) {
      result.value = data;
    }
  } finally {
    loading.value = false;
  }
}

onMounted(loadData);
</script>

<template>
  <NSpin :show="loading" class="min-h-0 flex-1">
    <div class="h-full overflow-y-auto">
      <div class="flex flex-col gap-12px p-4px">
        <!-- LLM 主线分析 -->
        <NCard size="small" :title="$t('page.aiAnalysis.mainlineAnalysis')">
          <template #header-extra>
            <span v-if="result?.analysis_time" class="text-12px text-secondary">
              {{ result.analysis_time }}
            </span>
            <NButton text type="primary" size="small" @click="loadData">
              {{ $t('common.refresh') }}
            </NButton>
          </template>
          <NEmpty
            v-if="!result?.analysis?.length"
            :description="$t('page.aiAnalysis.mainlineAnalysisEmpty')"
          />
          <div v-else class="grid grid-cols-1 gap-12px md:grid-cols-2 xl:grid-cols-3">
            <NCard v-for="item in result.analysis" :key="item.name" size="small" embedded>
              <div class="flex items-center gap-8px">
                <span class="text-15px font-600">{{ item.name }}</span>
                <NTag v-if="item.trend" size="small" :type="trendColor(item.trend)">
                  {{ item.trend }}
                </NTag>
                <span v-if="item.news_count != null" class="ml-auto text-12px text-secondary">
                  {{ item.news_count }} {{ $t('page.aiAnalysis.mainlineNewsUnit') }}
                </span>
              </div>
              <p v-if="item.summary" class="mt-8px text-13px">{{ item.summary }}</p>
              <p v-if="item.logic" class="mt-4px text-12px text-secondary">{{ item.logic }}</p>
              <div v-if="item.related_sectors?.length" class="mt-8px flex flex-wrap gap-4px">
                <NTag v-for="s in item.related_sectors" :key="s" size="tiny" :bordered="false">
                  {{ s }}
                </NTag>
              </div>
            </NCard>
          </div>
        </NCard>

        <!-- 主线分组资讯 -->
        <NCard size="small" :title="$t('page.aiAnalysis.mainlineGroups')">
          <NCollapse>
            <NCollapseItem v-for="g in result?.groups || []" :key="g.name" :name="g.name">
              <template #header>
                <div class="flex items-center gap-8px">
                  <span>{{ g.name }}</span>
                  <NBadge :value="g.news_count_7d" :max="9999" type="info" />
                </div>
              </template>
              <NEmpty
                v-if="!g.latest_news.length"
                size="small"
                :description="$t('page.aiAnalysis.mainlineGroupEmpty')"
              />
              <div v-else class="flex flex-col gap-6px">
                <div
                  v-for="n in g.latest_news"
                  :key="n.id"
                  class="cursor-pointer flex items-baseline gap-8px hover:text-primary"
                  @click="openDetail(n.id)"
                >
                  <span class="shrink-0 text-12px text-secondary">{{ n.published_at || '-' }}</span>
                  <span class="text-13px">{{ n.title }}</span>
                  <NTag size="tiny" :bordered="false" class="shrink-0">{{ n.source_name }}</NTag>
                </div>
              </div>
            </NCollapseItem>
          </NCollapse>
        </NCard>
      </div>
    </div>
  </NSpin>
  <NewsDetailDrawer v-model:visible="drawerVisible" :news-id="currentNewsId" />
</template>

<style scoped></style>
