<script setup lang="tsx">
import { reactive, ref, toRaw } from 'vue';
import { NButton, NPopconfirm, NSwitch } from 'naive-ui';
import { jsonClone } from '@sa/utils';
import { enableStatusOptions } from '@/constants/business';
import { fetchDeleteSkill, fetchGetSkillList, fetchUpdateSkillStatus } from '@/service/api';
import { useAppStore } from '@/store/modules/app';
import { defaultTransform, useNaivePaginatedTable, useTableOperate } from '@/hooks/common/table';
import { useAuth } from '@/hooks/business/auth';
import { booleanToEnableStatus } from '@/utils/status';
import { getGridActionSpan } from '@/utils/common';
import { $t } from '@/locales';
import SkillOperateDrawer from './modules/skill-operate-drawer.vue';

const appStore = useAppStore();
const { hasAuth } = useAuth();

const searchParams: Api.Skill.QueryParams = reactive({
  page: 1,
  page_size: 10,
  name: null,
  code: null,
  status: null
});

// 正在更新启用状态的行 id（供列渲染的 loading 态使用）
const statusUpdatingId = ref<number | null>(null);

const { columns, columnChecks, data, getData, getDataByPage, loading, mobilePagination } = useNaivePaginatedTable({
  api: () => fetchGetSkillList(searchParams),
  transform: response => defaultTransform(response),
  onPaginationParamsChange: params => {
    searchParams.page = params.page;
    searchParams.page_size = params.pageSize;
  },
  columns: () => [
    { key: 'index', title: $t('common.index'), align: 'center', width: 64, render: (_, index) => index + 1 },
    { key: 'name', title: $t('page.manage.skill.name'), align: 'center', minWidth: 140 },
    { key: 'code', title: $t('page.manage.skill.code'), align: 'center', minWidth: 120 },
    {
      key: 'description',
      title: $t('page.manage.skill.description'),
      align: 'center',
      minWidth: 200,
      ellipsis: { tooltip: true }
    },
    { key: 'sort', title: $t('page.manage.skill.sort'), align: 'center', width: 80 },
    {
      key: 'status',
      title: $t('page.manage.skill.status'),
      align: 'center',
      width: 90,
      render: (row: Api.Skill.Skill) => (
        <NSwitch
          value={row.status === '1'}
          disabled={!hasAuth('skill:manage')}
          loading={statusUpdatingId.value === row.id}
          onUpdate:value={(val: boolean) => handleToggleStatus(row, val)}
        />
      )
    },
    { key: 'updated_at', title: $t('page.manage.skill.updateTime'), align: 'center', width: 160 },
    {
      key: 'operate',
      title: $t('common.operate'),
      align: 'center',
      minWidth: 160,
      render: (row: Api.Skill.Skill) => (
        <div class="flex flex-wrap justify-center gap-8px">
          {hasAuth('skill:manage') && (
            <NButton type="info" ghost size="small" onClick={() => editSkill(row.id)}>
              {$t('common.edit')}
            </NButton>
          )}
          {hasAuth('skill:manage') && (
            <NPopconfirm onPositiveClick={() => handleDelete(row.id)}>
              {{
                default: () => $t('common.confirmDelete'),
                trigger: () => (
                  <NButton type="error" ghost size="small">
                    {$t('common.delete')}
                  </NButton>
                )
              }}
            </NPopconfirm>
          )}
        </div>
      )
    }
  ]
});

const { drawerVisible, operateType, editingData, handleAdd, handleEdit, onDeleted } = useTableOperate(
  data,
  'id',
  getData
);

function editSkill(id: number) {
  handleEdit(id);
}

async function handleDelete(id: number) {
  try {
    await fetchDeleteSkill(id);
    onDeleted();
  } catch (error) {
    console.error('删除技能失败:', error);
  }
}

// ==================== 启用/禁用 ====================

async function handleToggleStatus(row: Api.Skill.Skill, enabled: boolean) {
  statusUpdatingId.value = row.id;
  try {
    await fetchUpdateSkillStatus(row.id, enabled);
    row.status = booleanToEnableStatus(enabled);
  } catch (error) {
    console.error('更新状态失败:', error);
  } finally {
    statusUpdatingId.value = null;
  }
}

// ==================== 搜索区 ====================
const defaultSearchParams = jsonClone(toRaw(searchParams));
const actionSpan = getGridActionSpan(3);

function resetSearch() {
  Object.assign(searchParams, defaultSearchParams);
  getDataByPage();
}

function search() {
  getDataByPage();
}
</script>

<template>
  <div class="min-h-500px flex-col-stretch gap-16px overflow-hidden lt-sm:overflow-auto">
    <NCard :title="$t('common.search')" :bordered="false" size="small" class="card-wrapper">
      <NForm :model="searchParams" label-placement="left" :label-width="80">
        <NGrid responsive="screen" item-responsive>
          <NFormItemGi span="24 s:12 m:6" :label="$t('page.manage.skill.name')" path="name" class="pr-24px">
            <NInput v-model:value="searchParams.name" :placeholder="$t('page.manage.skill.form.name')" clearable />
          </NFormItemGi>
          <NFormItemGi span="24 s:12 m:6" :label="$t('page.manage.skill.code')" path="code" class="pr-24px">
            <NInput v-model:value="searchParams.code" :placeholder="$t('page.manage.skill.form.code')" clearable />
          </NFormItemGi>
          <NFormItemGi span="24 s:12 m:6" :label="$t('page.manage.skill.status')" path="status" class="pr-24px">
            <NSelect v-model:value="searchParams.status" :options="enableStatusOptions" clearable />
          </NFormItemGi>
          <NFormItemGi :span="actionSpan" class="pr-24px">
            <NSpace class="w-full" justify="end">
              <NButton @click="resetSearch">
                <template #icon>
                  <icon-ic-round-refresh class="text-icon" />
                </template>
                {{ $t('common.reset') }}
              </NButton>
              <NButton type="primary" ghost @click="search">
                <template #icon>
                  <icon-ic-round-search class="text-icon" />
                </template>
                {{ $t('common.search') }}
              </NButton>
            </NSpace>
          </NFormItemGi>
        </NGrid>
      </NForm>
    </NCard>
    <NCard :title="$t('page.manage.skill.title')" :bordered="false" size="small" class="flex-1-hidden card-wrapper">
      <template #header-extra>
        <TableHeaderOperation
          v-model:columns="columnChecks"
          :loading="loading"
          add-auth="skill:manage"
          @add="handleAdd"
          @refresh="getData"
        />
      </template>
      <NDataTable
        :columns="columns as any"
        :data="data"
        size="small"
        :flex-height="!appStore.isMobile"
        :scroll-x="1100"
        :loading="loading"
        remote
        :row-key="row => row.id"
        :pagination="mobilePagination"
        class="sm:h-full"
      />
      <SkillOperateDrawer
        v-model:visible="drawerVisible"
        :operate-type="operateType"
        :row-data="editingData"
        @submitted="getDataByPage"
      />
    </NCard>
  </div>
</template>

<style scoped></style>
