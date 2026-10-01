<script setup lang="tsx">
import { reactive, ref, toRaw } from 'vue';
import { NButton, NPopconfirm, NSwitch, useMessage } from 'naive-ui';
import { jsonClone } from '@sa/utils';
import { enableStatusOptions } from '@/constants/business';
import {
  fetchDeleteMcpServer,
  fetchGetMcpServerList,
  fetchGetMcpServerTools,
  fetchTestMcpServer,
  fetchUpdateMcpServerStatus
} from '@/service/api';
import { useAppStore } from '@/store/modules/app';
import { defaultTransform, useNaivePaginatedTable, useTableOperate } from '@/hooks/common/table';
import { useAuth } from '@/hooks/business/auth';
import { getGridActionSpan } from '@/utils/common';
import { $t } from '@/locales';
import McpServerOperateDrawer from './modules/mcp-server-operate-drawer.vue';

const appStore = useAppStore();
const message = useMessage();
const { hasAuth } = useAuth();

const searchParams: Api.McpServer.QueryParams = reactive({
  page: 1,
  page_size: 10,
  name: null,
  code: null,
  enabled: null
});

// 正在更新启用状态 / 正在测试的行 id（供列渲染的 loading 态使用）
const statusUpdatingId = ref<number | null>(null);
const testingId = ref<number | null>(null);

const { columns, columnChecks, data, getData, getDataByPage, loading, mobilePagination } = useNaivePaginatedTable({
  api: () => fetchGetMcpServerList(searchParams),
  transform: response => defaultTransform(response),
  onPaginationParamsChange: params => {
    searchParams.page = params.page;
    searchParams.page_size = params.pageSize;
  },
  columns: () => [
    { key: 'index', title: $t('common.index'), align: 'center', width: 64, render: (_, index) => index + 1 },
    { key: 'name', title: $t('page.manage.mcpServer.name'), align: 'center', minWidth: 140 },
    { key: 'code', title: $t('page.manage.mcpServer.code'), align: 'center', minWidth: 120 },
    {
      key: 'url',
      title: $t('page.manage.mcpServer.url'),
      align: 'center',
      minWidth: 220,
      ellipsis: { tooltip: true }
    },
    {
      key: 'enabled',
      title: $t('page.manage.mcpServer.enabled'),
      align: 'center',
      width: 90,
      render: (row: Api.McpServer.Server) => (
        <NSwitch
          value={row.enabled}
          disabled={!hasAuth('mcp:manage')}
          loading={statusUpdatingId.value === row.id}
          onUpdate:value={(val: boolean) => handleToggleStatus(row, val)}
        />
      )
    },
    { key: 'timeout_s', title: $t('page.manage.mcpServer.timeout'), align: 'center', width: 100 },
    {
      key: 'remark',
      title: $t('page.manage.mcpServer.remark'),
      align: 'center',
      minWidth: 160,
      ellipsis: { tooltip: true }
    },
    {
      key: 'operate',
      title: $t('common.operate'),
      align: 'center',
      minWidth: 280,
      render: (row: Api.McpServer.Server) => (
        <div class="flex flex-wrap justify-center gap-8px">
          {hasAuth('mcp:test') && (
            <NButton
              type="primary"
              ghost
              size="small"
              loading={testingId.value === row.id}
              onClick={() => handleTest(row.id)}
            >
              {$t('page.manage.mcpServer.test')}
            </NButton>
          )}
          {hasAuth('mcp:list') && (
            <NButton type="default" ghost size="small" onClick={() => handleViewTools(row)}>
              {$t('page.manage.mcpServer.viewTools')}
            </NButton>
          )}
          {hasAuth('mcp:manage') && (
            <NButton type="info" ghost size="small" onClick={() => editServer(row.id)}>
              {$t('common.edit')}
            </NButton>
          )}
          {hasAuth('mcp:manage') && (
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

function editServer(id: number) {
  handleEdit(id);
}

async function handleDelete(id: number) {
  try {
    await fetchDeleteMcpServer(id);
    onDeleted();
  } catch (error) {
    console.error('删除 MCP 服务失败:', error);
  }
}

// ==================== 启用/停用 ====================

async function handleToggleStatus(row: Api.McpServer.Server, enabled: boolean) {
  statusUpdatingId.value = row.id;
  try {
    await fetchUpdateMcpServerStatus(row.id, enabled);
    row.enabled = enabled;
  } catch (error) {
    console.error('更新状态失败:', error);
  } finally {
    statusUpdatingId.value = null;
  }
}

// ==================== 连通性测试 ====================

async function handleTest(id: number) {
  testingId.value = id;
  try {
    const res = await fetchTestMcpServer(id);
    if (res.data) {
      if (res.data.success) {
        message.success(`${res.data.message} (${res.data.latency_ms}ms, ${res.data.tool_count} tools)`);
      } else {
        message.error(res.data.message);
      }
    }
  } catch (error) {
    console.error('测试失败:', error);
  } finally {
    testingId.value = null;
  }
}

// ==================== 查看工具 ====================
const toolsVisible = ref(false);
const toolsLoading = ref(false);
const tools = ref<Api.McpServer.ToolItem[]>([]);
const toolsServerName = ref('');

const toolColumns = [
  { key: 'name', title: $t('page.manage.mcpServer.toolName'), minWidth: 160 },
  { key: 'description', title: $t('page.manage.mcpServer.toolDescription'), minWidth: 300, ellipsis: { tooltip: true } }
];

async function handleViewTools(row: Api.McpServer.Server) {
  toolsVisible.value = true;
  toolsLoading.value = true;
  toolsServerName.value = row.name;
  tools.value = [];
  try {
    const res = await fetchGetMcpServerTools(row.id);
    tools.value = res.data || [];
  } catch (error) {
    console.error('获取工具列表失败:', error);
  } finally {
    toolsLoading.value = false;
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
          <NFormItemGi span="24 s:12 m:6" :label="$t('page.manage.mcpServer.name')" path="name" class="pr-24px">
            <NInput v-model:value="searchParams.name" :placeholder="$t('page.manage.mcpServer.form.name')" clearable />
          </NFormItemGi>
          <NFormItemGi span="24 s:12 m:6" :label="$t('page.manage.mcpServer.code')" path="code" class="pr-24px">
            <NInput v-model:value="searchParams.code" :placeholder="$t('page.manage.mcpServer.form.code')" clearable />
          </NFormItemGi>
          <NFormItemGi span="24 s:12 m:6" :label="$t('page.manage.mcpServer.enabled')" path="enabled" class="pr-24px">
            <NSelect v-model:value="searchParams.enabled" :options="enableStatusOptions" clearable />
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
    <NCard :title="$t('page.manage.mcpServer.title')" :bordered="false" size="small" class="flex-1-hidden card-wrapper">
      <template #header-extra>
        <TableHeaderOperation
          v-model:columns="columnChecks"
          :loading="loading"
          add-auth="mcp:manage"
          @add="handleAdd"
          @refresh="getData"
        />
      </template>
      <NDataTable
        :columns="columns as any"
        :data="data"
        size="small"
        :flex-height="!appStore.isMobile"
        :scroll-x="1200"
        :loading="loading"
        remote
        :row-key="row => row.id"
        :pagination="mobilePagination"
        class="sm:h-full"
      />
      <McpServerOperateDrawer
        v-model:visible="drawerVisible"
        :operate-type="operateType"
        :row-data="editingData"
        @submitted="getDataByPage"
      />
    </NCard>

    <NModal
      v-model:show="toolsVisible"
      preset="card"
      :title="`${toolsServerName} - ${$t('page.manage.mcpServer.toolsTitle')}`"
      class="w-720px"
    >
      <NDataTable :columns="toolColumns as any" :data="tools" :loading="toolsLoading" size="small" :max-height="420" />
    </NModal>
  </div>
</template>

<style scoped></style>
