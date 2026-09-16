<script setup lang="tsx">
import { computed, onMounted, reactive, ref } from 'vue';
import {
  NButton,
  NCard,
  NDataTable,
  NInput,
  NPagination,
  NPopconfirm,
  NSelect,
  NSpace,
  NSwitch,
  NTag,
  NText,
  NTooltip
} from 'naive-ui';
import type { DataTableColumns } from 'naive-ui';
import { fetchCreateFactor, fetchDeleteFactor, fetchGetFactorList, fetchUpdateFactor } from '@/service/api';
import { $t } from '@/locales';
import FactorOperateDrawer from './factor-operate-drawer.vue';
import FactorImportModal from './factor-import-modal.vue';

defineOptions({ name: 'FactorLibrary' });

const SOURCE_LABEL: Record<Api.Factor.FactorSource, string> = {
  preset: $t('page.aiFactor.sourcePreset'),
  imported: $t('page.aiFactor.sourceImported'),
  custom: $t('page.aiFactor.sourceCustom')
};

const SOURCE_TAG: Record<Api.Factor.FactorSource, 'warning' | 'info' | 'default'> = {
  preset: 'warning',
  imported: 'info',
  custom: 'default'
};

const CATEGORY_LABEL: Record<string, string> = {
  price: $t('page.aiFactor.categoryPrice'),
  momentum: $t('page.aiFactor.categoryMomentum'),
  volume: $t('page.aiFactor.categoryVolume'),
  volatility: $t('page.aiFactor.categoryVolatility'),
  imported: $t('page.aiFactor.categoryImported'),
  custom: $t('page.aiFactor.categoryCustom')
};

const CATEGORY_OPTIONS = Object.entries(CATEGORY_LABEL).map(([value, label]) => ({ value, label }));

const SOURCE_OPTIONS = (['preset', 'imported', 'custom'] as Api.Factor.FactorSource[]).map(v => ({
  value: v,
  label: SOURCE_LABEL[v]
}));

// ------------------------------------------------------------------
// 列表查询
// ------------------------------------------------------------------
const search = reactive({ category: null as string | null, source: null as Api.Factor.FactorSource | null, keyword: '' });
const factorList = ref<Api.Factor.FactorItem[]>([]);
const listTotal = ref(0);
const listPage = reactive({ page: 1, pageSize: 20 });
const listLoading = ref(false);

async function loadList() {
  listLoading.value = true;
  try {
    const { data, error } = await fetchGetFactorList({
      category: search.category ?? undefined,
      source: search.source ?? undefined,
      keyword: search.keyword || undefined,
      page: listPage.page,
      page_size: listPage.pageSize
    });
    if (!error) {
      factorList.value = data?.records ?? [];
      listTotal.value = data?.total ?? 0;
    }
  } finally {
    listLoading.value = false;
  }
}

function searchList() {
  listPage.page = 1;
  loadList();
}

function onPageChange(page: number) {
  listPage.page = page;
  loadList();
}

// ------------------------------------------------------------------
// 新建 / 编辑 / 删除 / 启停
// ------------------------------------------------------------------
const drawerVisible = ref(false);
const editingFactor = ref<Api.Factor.FactorItem | null>(null);
const importVisible = ref(false);

function openCreate() {
  editingFactor.value = null;
  drawerVisible.value = true;
}

function openEdit(row: Api.Factor.FactorItem) {
  editingFactor.value = row;
  drawerVisible.value = true;
}

interface DrawerSubmit {
  data: Api.Factor.FactorCreateParams | Api.Factor.FactorUpdateParams;
  isEdit: boolean;
  id?: number;
}

async function onDrawerSubmitted(payload: DrawerSubmit) {
  const { error } = payload.isEdit && payload.id
    ? await fetchUpdateFactor(payload.id, payload.data)
    : await fetchCreateFactor(payload.data as Api.Factor.FactorCreateParams);
  if (!error) {
    window.$message?.success(payload.isEdit ? $t('common.updateSuccess') : $t('common.addSuccess'));
    await loadList();
  }
}

async function onDelete(row: Api.Factor.FactorItem) {
  const { error } = await fetchDeleteFactor(row.id);
  if (!error) {
    window.$message?.success($t('common.deleteSuccess'));
    await loadList();
  }
}

/** 状态开关（preset 只能停用不能删除，启停走更新接口） */
async function onToggleStatus(row: Api.Factor.FactorItem, status: boolean) {
  const { error } = await fetchUpdateFactor(row.id, { status });
  if (error) return;
  row.status = status;
  window.$message?.success($t('common.updateSuccess'));
}

const columns = computed<DataTableColumns<Api.Factor.FactorItem>>(() => [
  { key: 'name', title: $t('page.aiFactor.nameCol'), width: 180, ellipsis: { tooltip: true } },
  {
    key: 'code',
    title: $t('page.aiFactor.codeCol'),
    width: 150,
    render: row => <span class="font-mono text-12px">{row.code}</span>
  },
  {
    key: 'category',
    title: $t('page.aiFactor.categoryCol'),
    width: 90,
    align: 'center',
    render: row => (
      <NTag size="small" bordered={false}>
        {CATEGORY_LABEL[row.category] ?? row.category}
      </NTag>
    )
  },
  {
    key: 'source',
    title: $t('page.aiFactor.sourceCol'),
    width: 100,
    align: 'center',
    render: row => (
      <NTag size="small" bordered={false} type={SOURCE_TAG[row.source]}>
        {SOURCE_LABEL[row.source]}
      </NTag>
    )
  },
  {
    key: 'formula',
    title: $t('page.aiFactor.formulaCol'),
    minWidth: 240,
    render: row => (
      <NTooltip trigger="hover" style={{ maxWidth: '480px' }}>
        {{
          trigger: () => (
            <span class="inline-block max-w-full truncate align-middle font-mono text-12px">{row.formula}</span>
          ),
          default: () => <span class="font-mono text-12px">{row.formula}</span>
        }}
      </NTooltip>
    )
  },
  {
    key: 'status',
    title: $t('page.aiFactor.statusCol'),
    width: 80,
    align: 'center',
    render: row => (
      <NSwitch size="small" value={row.status} onUpdateValue={(v: boolean) => onToggleStatus(row, v)} />
    )
  },
  {
    key: 'actions',
    title: $t('common.action'),
    width: 130,
    align: 'center',
    render: row => (
      <NSpace size={4} justify="center">
        <NButton size="tiny" type="primary" ghost onClick={() => openEdit(row)}>
          {$t('common.edit')}
        </NButton>
        {row.source !== 'preset' ? (
          <NPopconfirm onPositiveClick={() => onDelete(row)}>
            {{
              trigger: () => (
                <NButton size="tiny" type="error" ghost>
                  {$t('common.delete')}
                </NButton>
              ),
              default: () => $t('page.aiFactor.deleteConfirm')
            }}
          </NPopconfirm>
        ) : (
          <NTooltip trigger="hover">
            {{
              trigger: () => (
                <NText depth={3} class="cursor-help text-12px">
                  {$t('page.aiFactor.presetTag')}
                </NText>
              ),
              default: () => $t('page.aiFactor.presetDeleteTip')
            }}
          </NTooltip>
        )}
      </NSpace>
    )
  }
]);

onMounted(loadList);
</script>

<template>
  <NCard :bordered="false" size="small" class="card-wrapper sm:flex-1-hidden">
    <template #header>
      <span>{{ $t('page.aiFactor.libraryTitle') }}</span>
    </template>
    <template #header-extra>
      <NSpace align="center" :size="12" :wrap="false">
        <NSelect
          v-model:value="search.category"
          size="small"
          clearable
          :placeholder="$t('page.aiFactor.filterCategory')"
          :options="CATEGORY_OPTIONS"
          class="w-120px"
          @update:value="searchList"
        />
        <NSelect
          v-model:value="search.source"
          size="small"
          clearable
          :placeholder="$t('page.aiFactor.filterSource')"
          :options="SOURCE_OPTIONS"
          class="w-120px"
          @update:value="searchList"
        />
        <NInput
          v-model:value="search.keyword"
          size="small"
          clearable
          :placeholder="$t('page.aiFactor.keywordPlaceholder')"
          class="w-160px"
          @keyup.enter="searchList"
          @clear="searchList"
        />
        <NButton size="small" @click="searchList">{{ $t('common.search') }}</NButton>
        <NButton size="small" type="primary" ghost @click="importVisible = true">
          <template #icon><icon-mdi-import class="text-icon" /></template>
          {{ $t('page.aiFactor.import') }}
        </NButton>
        <NButton size="small" type="primary" @click="openCreate">
          <template #icon><icon-mdi-plus class="text-icon" /></template>
          {{ $t('page.aiFactor.create') }}
        </NButton>
      </NSpace>
    </template>

    <NDataTable
      :columns="columns"
      :data="factorList"
      size="small"
      :loading="listLoading"
      :scroll-x="1100"
      :row-key="(row: Api.Factor.FactorItem) => row.id"
    />
    <div class="mt-12px flex justify-end">
      <NPagination
        :page="listPage.page"
        :page-size="listPage.pageSize"
        :item-count="listTotal"
        @update:page="onPageChange"
      />
    </div>

    <FactorOperateDrawer v-model:visible="drawerVisible" :editing="editingFactor" @submitted="onDrawerSubmitted" />
    <FactorImportModal v-model:visible="importVisible" @imported="loadList" />
  </NCard>
</template>

<style scoped></style>
