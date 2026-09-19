<script setup lang="tsx">
import { computed, onMounted, reactive, ref } from 'vue';
import {
  NAlert,
  NButton,
  NDataTable,
  NInput,
  NModal,
  NPagination,
  NPopconfirm,
  NSpace,
  NTag,
  NText
} from 'naive-ui';
import type { DataTableColumns } from 'naive-ui';
import { fetchCloneStrategy, fetchGetStrategyTemplates, fetchImportStrategy } from '@/service/api';
import { $t } from '@/locales';
import { useAppStore } from '@/store/modules/app';

defineOptions({ name: 'StrategyTemplate' });

const emit = defineEmits<{
  /** 克隆/导入成功后通知父级刷新策略管理列表 */
  (e: 'changed'): void;
}>();

const appStore = useAppStore();

const CATEGORY_LABEL: Record<string, string> = {
  pre_market_auction: $t('page.aiStrategy.categoryAuction'),
  noon: $t('page.aiStrategy.categoryNoon'),
  tail: $t('page.aiStrategy.categoryTail'),
  blue_chip: $t('page.aiStrategy.categoryBlueChip'),
  general: $t('page.aiStrategy.categoryGeneral')
};

// ------------------------------------------------------------------
// 模板市场列表
// ------------------------------------------------------------------
const templateList = ref<Api.Strategy.TemplateItem[]>([]);
const listTotal = ref(0);
const listPage = reactive({ page: 1, pageSize: 20 });
const listLoading = ref(false);

async function loadList() {
  listLoading.value = true;
  try {
    const { data, error } = await fetchGetStrategyTemplates({ page: listPage.page, page_size: listPage.pageSize });
    if (!error) {
      templateList.value = data?.records ?? [];
      listTotal.value = data?.total ?? 0;
    }
  } finally {
    listLoading.value = false;
  }
}

function onPageChange(page: number) {
  listPage.page = page;
  loadList();
}

// ------------------------------------------------------------------
// 克隆此模板（克隆件默认停用，去策略管理启用）
// ------------------------------------------------------------------
const cloningIds = ref<number[]>([]);

async function onClone(row: Api.Strategy.TemplateItem) {
  cloningIds.value.push(row.id);
  try {
    const { error } = await fetchCloneStrategy(row.id);
    if (!error) {
      window.$message?.success($t('page.aiStrategy.cloneSuccess'));
      await loadList();
      emit('changed');
    }
  } finally {
    cloningIds.value = cloningIds.value.filter(id => id !== row.id);
  }
}

// ------------------------------------------------------------------
// 导入策略
// ------------------------------------------------------------------
const importVisible = ref(false);
const importContent = ref('');
const importing = ref(false);

function openImport() {
  importContent.value = '';
  importVisible.value = true;
}

async function onImport() {
  if (!importContent.value.trim()) {
    window.$message?.warning($t('page.aiStrategy.importInputRequired'));
    return;
  }
  let payload: Api.Strategy.StrategyImportParams;
  try {
    payload = JSON.parse(importContent.value);
  } catch {
    window.$message?.error($t('page.aiStrategy.importInvalidJson'));
    return;
  }
  importing.value = true;
  try {
    const { data, error } = await fetchImportStrategy(payload);
    if (!error && data) {
      window.$message?.success($t('page.aiStrategy.importSuccess', { name: data.name }));
      importVisible.value = false;
      emit('changed');
    }
  } finally {
    importing.value = false;
  }
}

// ------------------------------------------------------------------
// 展示辅助
// ------------------------------------------------------------------
function pnlColor(val: number | null | undefined) {
  if (val === null || val === undefined) return '#8c8c8c';
  if (val > 0) return '#f5222d';
  if (val < 0) return '#52c41a';
  return '#8c8c8c';
}

function renderPct(val: number | null | undefined) {
  if (val === null || val === undefined) return <NText depth={3}>-</NText>;
  return (
    <span style={{ color: pnlColor(val), fontWeight: '500' }}>
      {val > 0 ? '+' : ''}
      {Number(val).toFixed(2)}%
    </span>
  );
}

const columns = computed<DataTableColumns<Api.Strategy.TemplateItem>>(() => [
  {
    key: 'name',
    title: $t('page.aiStrategy.form.name'),
    width: 200,
    render: row => (
      <div class="flex items-center gap-4px">
        <span class="font-500">{row.name}</span>
        {row.is_template ? (
          <NTag size="tiny" bordered={false} type="warning">
            {$t('page.aiStrategy.templateTag')}
          </NTag>
        ) : null}
        {row.is_preset ? (
          <NTag size="tiny" bordered={false} type="primary">
            {$t('page.aiStrategy.presetTag')}
          </NTag>
        ) : null}
      </div>
    )
  },
  {
    key: 'category',
    title: $t('page.aiStrategy.form.category'),
    width: 90,
    render: row => (
      <NTag size="small" bordered={false}>
        {CATEGORY_LABEL[row.category] ?? row.category}
      </NTag>
    )
  },
  {
    key: 'tags',
    title: $t('page.aiStrategy.tagsCol'),
    width: 150,
    render: row =>
      row.tags?.length ? (
        <NSpace size={4}>
          {row.tags.map(t => (
            <NTag size="small" type="info" bordered={false}>
              {t}
            </NTag>
          ))}
        </NSpace>
      ) : (
        <NText depth={3}>-</NText>
      )
  },
  {
    key: 'description',
    title: $t('page.aiStrategy.form.description'),
    minWidth: 200,
    ellipsis: { tooltip: true },
    render: row => <span class="text-12px">{row.description ?? '-'}</span>
  },
  {
    key: 'clone_count',
    title: $t('page.aiStrategy.cloneCountCol'),
    width: 90,
    align: 'right',
    render: row => <span>{row.clone_count}</span>
  },
  {
    key: 'last_backtest',
    title: $t('page.aiStrategy.lastBacktestCol'),
    minWidth: 260,
    render: row => {
      const bt = row.last_backtest;
      if (!bt) return <NText depth={3}>{$t('page.aiStrategy.noBacktest')}</NText>;
      return (
        <div class="flex-col gap-2px">
          <NText depth={3} class="text-12px">{`${bt.start_date} ~ ${bt.end_date}`}</NText>
          <NSpace size={8} align="center" class="text-12px">
            {renderPct(bt.total_return_pct)}
            {renderPct(bt.max_drawdown_pct)}
            <span>
              {$t('page.aiStrategy.winRate')}
              {bt.win_rate !== null && bt.win_rate !== undefined ? ` ${Number(bt.win_rate).toFixed(1)}%` : ' -'}
            </span>
            <span>{$t('page.aiStrategy.btTrades', { count: bt.trade_count ?? 0 })}</span>
          </NSpace>
        </div>
      );
    }
  },
  {
    key: 'actions',
    title: $t('common.action'),
    width: 120,
    align: 'center',
    render: row => (
      <NPopconfirm onPositiveClick={() => onClone(row)}>
        {{
          trigger: () => (
            <NButton size="tiny" type="primary" ghost loading={cloningIds.value.includes(row.id)}>
              {$t('page.aiStrategy.cloneThis')}
            </NButton>
          ),
          default: () => $t('page.aiStrategy.cloneConfirm')
        }}
      </NPopconfirm>
    )
  }
]);

onMounted(loadList);
</script>

<template>
  <div class="h-full flex-col-stretch">
    <div class="mb-12px flex items-center justify-between">
      <NText depth="3" class="text-12px">{{ $t('page.aiStrategy.templateTip') }}</NText>
      <NButton size="small" type="primary" @click="openImport">
        <template #icon><icon-mdi-import class="text-icon" /></template>
        {{ $t('page.aiStrategy.importStrategy') }}
      </NButton>
    </div>
    <NDataTable
      :columns="columns"
      :data="templateList"
      size="small"
      :loading="listLoading"
      :scroll-x="1200"
      :flex-height="!appStore.isMobile"
      remote
      class="flex-1-hidden"
      :row-key="(row: Api.Strategy.TemplateItem) => row.id"
    />
    <div class="mt-12px flex justify-end">
      <NPagination
        :page="listPage.page"
        :page-size="listPage.pageSize"
        :item-count="listTotal"
        @update:page="onPageChange"
      />
    </div>

    <!-- 导入策略弹窗 -->
    <NModal
      v-model:show="importVisible"
      preset="card"
      :title="$t('page.aiStrategy.importTitle')"
      class="w-640px"
    >
      <NSpace vertical :size="12">
        <NInput
          v-model:value="importContent"
          type="textarea"
          :rows="10"
          class="font-mono"
          :placeholder="$t('page.aiStrategy.importPlaceholder')"
        />
        <NAlert type="info" :bordered="false">
          <div class="text-12px whitespace-pre-line">{{ $t('page.aiStrategy.importTip') }}</div>
        </NAlert>
      </NSpace>
      <template #footer>
        <NSpace justify="end" :size="12">
          <NButton @click="importVisible = false">{{ $t('common.cancel') }}</NButton>
          <NButton type="primary" :loading="importing" @click="onImport">{{ $t('page.aiStrategy.importStrategy') }}</NButton>
        </NSpace>
      </template>
    </NModal>
  </div>
</template>

<style scoped></style>
