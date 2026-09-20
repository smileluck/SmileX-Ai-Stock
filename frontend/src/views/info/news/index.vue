<script setup lang="tsx">
import { computed, onMounted, reactive, ref } from 'vue';
import { NButton, NCard, NDataTable, NTag } from 'naive-ui';
import type { DataTableColumns } from 'naive-ui';
import { fetchGetNewsList, fetchGetNewsSources } from '@/service/api';
import { useAppStore } from '@/store/modules/app';
import { $t } from '@/locales';
import NewsDetailDrawer from './modules/news-detail-drawer.vue';
import NewsWebModal from './modules/news-web-modal.vue';
import NewsSearch from './modules/news-search.vue';
import NewsSourceTabs from './modules/news-source-tabs.vue';

defineOptions({
  name: 'News'
});

const appStore = useAppStore();

/** 来源 -> 颜色映射，保证多源视觉区分 */
const SOURCE_COLOR_MAP: Record<string, NaiveUI.ThemeColor> = {
  eastmoney: 'success',
  eastmoney_global: 'info',
  cls: 'error',
  tonghuashun: 'info',
  sina: 'success',
 yicai: 'warning',
  jin10: 'error',
  jin10_important: 'warning',
 futu: 'default',
  wscn_global: 'error',
  wscn_a_stock: 'success',
  wscn_hk_stock: 'warning',
  wscn_us_stock: 'info',
  wscn_forex: 'default',
  wscn_gold: 'warning',
  wscn_oil: 'info',
  wscn_commodity: 'success',
  wscn_bond: 'default',
  wscn_tech: 'info',
  wscn_finance: 'error'
};

function sourceColor(source: string): NaiveUI.ThemeColor {
  return SOURCE_COLOR_MAP[source] ?? 'default';
}

/** 搜索参数 */
const searchParams = reactive<Api.News.NewsSearchParams>({
  page: 1,
  page_size: 10,
  keyword: null,
  source: null,
  group: null,
  start_time: null,
  end_time: null
});

/** 新闻源统计 */
const sources = ref<Api.News.NewsSourceItem[]>([]);

async function loadSources() {
  try {
    const { data, error } = await fetchGetNewsSources();
    if (!error) {
      sources.value = data || [];
    }
  } catch {
    // ignore — sources list is non-critical
  }
}

/** 列表数据 */
const newsData = ref<Api.News.News[]>([]);
const loading = ref(false);

async function getNewsData() {
  loading.value = true;
  try {
    const { data: resp, error } = await fetchGetNewsList(searchParams);
    if (!error && resp) {
      newsData.value = resp.records || [];
      pagination.itemCount = resp.total || 0;
      pagination.page = resp.page;
      pagination.pageSize = resp.page_size;
    }
  } finally {
    loading.value = false;
  }
}

function handlePageChange(page: number) {
  searchParams.page = page;
  getNewsData();
}

function handlePageSizeChange(pageSize: number) {
  searchParams.page_size = pageSize;
  searchParams.page = 1;
  getNewsData();
}

function onSearch() {
  searchParams.page = 1;
  getNewsData();
  loadSources();
}

/** 来源 Tab 选择 */
function onSelectSource(payload: { source: string | null; group: string | null }) {
  searchParams.source = payload.source;
  searchParams.group = payload.group;
  searchParams.page = 1;
  getNewsData();
}

/** 详情抽屉 */
const drawerVisible = ref(false);
const currentNewsId = ref<number | null>(null);

function openDetail(id: number) {
  currentNewsId.value = id;
  drawerVisible.value = true;
}

/** 网页预览弹窗 */
const webModalVisible = ref(false);
const currentWebUrl = ref<string | null>(null);
const currentWebTitle = ref('');

function openWebPreview(url: string, title: string) {
  currentWebUrl.value = url;
  currentWebTitle.value = title;
  webModalVisible.value = true;
}

/** 表格列 */
const columns = computed<DataTableColumns<Api.News.News>>(() => [
  {
    key: 'title',
    title: $t('common.title'),
    ellipsis: { tooltip: true },
    render: row => (
      <NButton text type="primary" class="font-500" onClick={() => openDetail(row.id)}>
        {row.title}
      </NButton>
    )
  },
  {
    key: 'source_name',
    title: $t('page.news.source'),
    width: 130,
    render: row => (
      <NTag type={sourceColor(row.source) as 'success'} size="small">
        {row.source_name}
      </NTag>
    )
  },
  {
    key: 'summary',
    title: $t('page.news.summary'),
    minWidth: 240,
    ellipsis: { tooltip: true },
    render: row => <span class="text-secondary">{row.summary || '-'}</span>
  },
  {
    key: 'published_at',
    title: $t('page.news.publishedAt'),
    width: 170,
    render: row => <span class="text-secondary">{row.published_at || row.created_at || '-'}</span>
  },
  {
    key: 'actions',
    title: $t('common.action'),
    width: 80,
    fixed: 'right',
    render: row => (
      <div class="flex-center gap-4px">
        <NButton text type="primary" onClick={() => openWebPreview(row.url, row.title)}>
          <icon-ic-round-open-in-new class="text-icon" />
        </NButton>
      </div>
    )
  }
]);

/** 分页配置 */
const pagination = reactive({
  page: 1,
  pageSize: 10,
  itemCount: 0,
  showSizePicker: true,
  pageSizes: [10, 15, 20, 30, 50],
  prefix: ({ itemCount }: { itemCount: number }) => $t('datatable.itemCount', { total: itemCount }),
  onUpdatePage: (page: number) => handlePageChange(page),
  onUpdatePageSize: (pageSize: number) => handlePageSizeChange(pageSize)
});

onMounted(async () => {
  await Promise.all([getNewsData(), loadSources()]);
});
</script>

<template>
  <div class="min-h-500px flex-col-stretch gap-16px overflow-hidden lt-sm:overflow-auto">
    <NewsSourceTabs :sources="sources" @select="onSelectSource" />
    <NewsSearch v-model:model="searchParams" @search="onSearch" @reset="onSearch" />
    <NCard
      :title="$t('page.news.title')"
      :bordered="false"
      size="small"
      class="card-wrapper sm:flex-1-hidden"
      content-style="min-height: 0"
    >
      <template #header-extra>
        <NButton size="small" :loading="loading" @click="getNewsData">
          <template #icon>
            <icon-ic-round-refresh class="text-icon" />
          </template>
          {{ $t('common.refresh') }}
        </NButton>
      </template>
      <NDataTable
        :columns="columns"
        :data="newsData"
        size="small"
        :flex-height="!appStore.isMobile"
        :scroll-x="1000"
        :loading="loading"
        remote
        :row-key="(row: Api.News.News) => row.id"
        :pagination="pagination"
        class="sm:h-full"
      />
    </NCard>
    <NewsDetailDrawer v-model:visible="drawerVisible" :news-id="currentNewsId" />
    <NewsWebModal v-model:visible="webModalVisible" :url="currentWebUrl" :title="currentWebTitle" />
  </div>
</template>

<style scoped>
</style>
