<script setup lang="tsx">
import { computed, reactive, ref, watch } from 'vue';
import { NButton, NCard, NDataTable, NPopconfirm, NSelect, NSwitch, NTabPane, NTabs, NTag, useMessage } from 'naive-ui';
import { enableStatusRecord } from '@/constants/business';
import {
  fetchDeleteAiModel,
  fetchDeleteAiModelBinding,
  fetchGetAiModelBindingList,
  fetchGetAiModelList,
  fetchGetAllAiModels,
  fetchTestAiModel,
  fetchUpsertAiModelBinding
} from '@/service/api';
import { useAppStore } from '@/store/modules/app';
import { defaultTransform, useNaivePaginatedTable, useTableOperate } from '@/hooks/common/table';
import { useAuth } from '@/hooks/business/auth';
import { booleanToEnableStatus } from '@/utils/status';
import { $t } from '@/locales';
import AiModelOperateDrawer from './modules/ai-model-operate-drawer.vue';
import AiModelSearch from './modules/ai-model-search.vue';

const appStore = useAppStore();
const message = useMessage();
const { hasAuth } = useAuth();

const activeTab = ref<'model' | 'binding'>('model');

// ==================== 模型管理 ====================

const modelSearchParams: Api.SystemManage.AiModelSearchParams = reactive({
  page: 1,
  page_size: 10,
  name: null,
  provider: null,
  billing_mode: null,
  status: null,
  is_default: null
});

const providerLabelMap: Record<string, string> = {
  openai: 'OpenAI',
  anthropic: 'Anthropic',
  deepseek: 'DeepSeek',
  qwen: '通义千问',
  zhipu: '智谱',
  minimax: 'MiniMax',
  custom: '自定义'
};

const providerColorMap: Record<string, NaiveUI.ThemeColor> = {
  openai: 'success',
  anthropic: 'warning',
  deepseek: 'info',
  qwen: 'error',
  zhipu: 'info',
  minimax: 'primary',
  custom: 'default'
};

const billingModeLabelMap: Record<string, string> = {
  pay_as_you_go: $t('page.manage.aiModel.payAsYouGo'),
  coding_plan: $t('page.manage.aiModel.codingPlan')
};

const {
  columns: modelColumns,
  columnChecks: modelColumnChecks,
  data: modelData,
  getData: getModelData,
  getDataByPage: getModelDataByPage,
  loading: modelLoading,
  mobilePagination: modelMobilePagination
} = useNaivePaginatedTable({
  api: () => fetchGetAiModelList(modelSearchParams),
  transform: response => {
    const result = defaultTransform(response);
    result.data = result.data.map((item: Api.SystemManage.AiModel) => ({
      ...item,
      status: booleanToEnableStatus(item.status),
      is_default: booleanToEnableStatus(item.is_default)
    }));
    return result;
  },
  onPaginationParamsChange: params => {
    modelSearchParams.page = params.page;
    modelSearchParams.page_size = params.pageSize;
  },
  columns: () => [
    { key: 'index', title: $t('common.index'), align: 'center', width: 64, render: (_, index) => index + 1 },
    {
      key: 'name',
      title: $t('page.manage.aiModel.modelName'),
      align: 'center',
      minWidth: 140
    },
    {
      key: 'provider',
      title: $t('page.manage.aiModel.provider'),
      align: 'center',
      width: 120,
      render: (row: Api.SystemManage.AiModel) => (
        <NTag type={providerColorMap[row.provider] || 'default'}>{providerLabelMap[row.provider] || row.provider}</NTag>
      )
    },
    {
      key: 'billing_mode',
      title: $t('page.manage.aiModel.billingMode'),
      align: 'center',
      width: 110,
      render: (row: Api.SystemManage.AiModel) => (
        <NTag type={row.billing_mode === 'coding_plan' ? 'warning' : 'default'} bordered={false}>
          {billingModeLabelMap[row.billing_mode] || row.billing_mode}
        </NTag>
      )
    },
    { key: 'model_name', title: $t('page.manage.aiModel.modelId'), align: 'center', minWidth: 140 },
    { key: 'base_url', title: $t('page.manage.aiModel.baseUrl'), align: 'center', minWidth: 200, ellipsis: { tooltip: true } },
    {
      key: 'api_key_masked',
      title: $t('page.manage.aiModel.apiKey'),
      align: 'center',
      minWidth: 140,
      render: (row: Api.SystemManage.AiModel) => row.api_key_masked || '-'
    },
    {
      key: 'is_default',
      title: $t('page.manage.aiModel.isDefault'),
      align: 'center',
      width: 100,
      render: (row: Api.SystemManage.AiModel) => {
        const isDefault = row.is_default === '1';
        return <NTag type={isDefault ? 'success' : 'default'}>{isDefault ? $t('common.yesOrNo.yes') : $t('common.yesOrNo.no')}</NTag>;
      }
    },
    {
      key: 'status',
      title: $t('page.manage.aiModel.status'),
      align: 'center',
      width: 90,
      render: (row: Api.SystemManage.AiModel) => {
        const status = row.status as Api.Common.EnableStatus;
        const tagMap: Record<Api.Common.EnableStatus, NaiveUI.ThemeColor> = { '1': 'success', '2': 'warning' };
        return <NTag type={tagMap[status]}>{$t(enableStatusRecord[status])}</NTag>;
      }
    },
    {
      key: 'operate',
      title: $t('common.operate'),
      align: 'center',
      minWidth: 260,
      render: (row: Api.SystemManage.AiModel) => (
        <div class="flex flex-wrap justify-center gap-8px">
          {hasAuth('sys:ai_model:edit') && (
            <NButton type="primary" ghost size="small" loading={testingId.value === row.id} onClick={() => handleTest(row.id)}>
              {$t('page.manage.aiModel.testConnection')}
            </NButton>
          )}
          {hasAuth('sys:ai_model:edit') && (
            <NButton type="info" ghost size="small" onClick={() => editModel(row.id)}>
              {$t('common.edit')}
            </NButton>
          )}
          {row.is_default !== '1' && hasAuth('sys:ai_model:delete') && (
            <NPopconfirm onPositiveClick={() => handleDeleteModel(row.id)}>
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

const { drawerVisible, operateType, editingData, handleAdd, handleEdit, onDeleted } = useTableOperate(modelData, 'id', getModelData);

function editModel(id: number) {
  handleEdit(id);
}

async function handleDeleteModel(id: number) {
  try {
    await fetchDeleteAiModel(id);
    onDeleted();
  } catch (error) {
    console.error('删除模型失败:', error);
  }
}

const testingId = ref<number | null>(null);

async function handleTest(id: number) {
  testingId.value = id;
  try {
    const res = await fetchTestAiModel(id);
    if (res.data) {
      if (res.data.success) {
        message.success(res.data.message);
      } else {
        message.error(res.data.message);
      }
    }
  } catch (error) {
    message.error($t('page.manage.aiModel.testFailed'));
    console.error('测试失败:', error);
  } finally {
    testingId.value = null;
  }
}

// ==================== 场景绑定管理 ====================

const allModels = ref<Api.SystemManage.AiModelSimple[]>([]);
const bindings = ref<Api.SystemManage.AiModelBinding[]>([]);
const bindingLoading = ref(false);

const functionLabelMap: Record<string, string> = {
  stock_picking: '智能选股',
  sentiment_analysis: '舆情分析',
  news_summary: '新闻摘要',
  chat_qa: '对话问答',
  trend_prediction: '趋势预测'
};

const allFunctions: Api.SystemManage.AiFunction[] = ['stock_picking', 'sentiment_analysis', 'news_summary', 'chat_qa', 'trend_prediction'];

const bindingEditing = reactive<Record<string, { model_id: number | null; status: Api.Common.EnableStatus }>>({});

async function loadBindings() {
  bindingLoading.value = true;
  try {
    const [bindRes, modelRes] = await Promise.all([fetchGetAiModelBindingList(), fetchGetAllAiModels()]);
    bindings.value = bindRes.data || [];
    allModels.value = modelRes.data || [];

    // 初始化编辑状态：已有绑定填入当前值，未绑定默认关闭
    const editing: Record<string, { model_id: number | null; status: Api.Common.EnableStatus }> = {};
    for (const fn of allFunctions) {
      const existing = bindings.value.find(b => b.function_code === fn);
      editing[fn] = {
        model_id: existing ? existing.model_id : null,
        status: existing ? (existing.status as Api.Common.EnableStatus) : '2'
      };
    }
    Object.assign(bindingEditing, editing);
  } catch (error) {
    console.error('加载绑定失败:', error);
  } finally {
    bindingLoading.value = false;
  }
}

const modelSelectOptions = computed(() => allModels.value.map(m => ({ label: `${m.name} (${m.model_name})`, value: m.id })));

const bindingColumns = computed(() => [
  {
    key: 'function',
    title: $t('page.manage.aiModel.function'),
    align: 'center',
    minWidth: 140,
    render: (row: { fn: Api.SystemManage.AiFunction }) => (
      <span>{functionLabelMap[row.fn]}</span>
    )
  },
  {
    key: 'model',
    title: $t('page.manage.aiModel.boundModel'),
    align: 'center',
    minWidth: 240,
    render: (row: { fn: Api.SystemManage.AiFunction; edit: any; existing: Api.SystemManage.AiModelBinding | undefined }) => (
      <NSelect
        value={row.edit?.model_id ?? null}
        options={modelSelectOptions.value}
        placeholder={$t('page.manage.aiModel.selectModel')}
        size="small"
        onUpdate:value={(val: number) => { if (bindingEditing[row.fn]) bindingEditing[row.fn].model_id = val; }}
      />
    )
  },
  {
    key: 'status',
    title: $t('page.manage.aiModel.bindingStatus'),
    align: 'center',
    width: 100,
    render: (row: { fn: Api.SystemManage.AiFunction; edit: any }) => (
      <NSwitch
        value={row.edit?.status === '1'}
        onUpdate:value={(val: boolean) => { if (bindingEditing[row.fn]) bindingEditing[row.fn].status = val ? '1' : '2'; }}
      />
    )
  },
  {
    key: 'operate',
    title: $t('common.operate'),
    align: 'center',
    minWidth: 200,
    render: (row: { fn: Api.SystemManage.AiFunction; existing: Api.SystemManage.AiModelBinding | undefined }) => (
      <div class="flex flex-wrap justify-center gap-8px">
        {hasAuth('sys:ai_model:edit') && (
          <NButton type="primary" size="small" onClick={() => handleSaveBinding(row.fn)}>
            {$t('common.confirm')}
          </NButton>
        )}
        {row.existing && hasAuth('sys:ai_model:delete') && (
          <NPopconfirm onPositiveClick={() => handleDeleteBinding(row.fn)}>
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
]);

const bindingTableData = computed(() =>
  allFunctions.map(fn => {
    const existing = bindings.value.find(b => b.function_code === fn);
    return {
      key: fn,
      fn,
      edit: bindingEditing[fn],
      existing
    };
  })
);

async function handleSaveBinding(functionCode: Api.SystemManage.AiFunction) {
  const edit = bindingEditing[functionCode];
  if (!edit || !edit.model_id) {
    message.warning($t('page.manage.aiModel.selectModelFirst'));
    return;
  }
    try {
    await fetchUpsertAiModelBinding(functionCode, { model_id: edit.model_id, status: edit.status });
    message.success($t('common.saveSuccess'));
    await loadBindings();
  } catch (error) {
    console.error('保存绑定失败:', error);
  }
}

async function handleDeleteBinding(functionCode: Api.SystemManage.AiFunction) {
  try {
    await fetchDeleteAiModelBinding(functionCode);
    message.success($t('common.deleteSuccess'));
    await loadBindings();
  } catch (error) {
    console.error('删除绑定失败:', error);
  }
}

watch(activeTab, tab => {
  if (tab === 'binding') {
    loadBindings();
  }
});
</script>

<template>
  <div class="min-h-500px flex-col-stretch gap-16px overflow-hidden lt-sm:overflow-auto">
    <NTabs v-model:value="activeTab" type="line" class="flex-1-hidden">
      <!-- 模型管理 Tab -->
      <NTabPane name="model" :tab="$t('page.manage.aiModel.modelManage')" class="flex-1-hidden">
        <AiModelSearch :model="modelSearchParams" @search="getModelDataByPage" />
        <NCard :title="$t('page.manage.aiModel.title')" :bordered="false" size="small" class="flex-1-hidden card-wrapper">
          <template #header-extra>
            <TableHeaderOperation
              v-model:columns="modelColumnChecks"
              :loading="modelLoading"
              add-auth="sys:ai_model:add"
              @add="handleAdd"
              @refresh="getModelData"
            />
          </template>
          <NDataTable
            :columns="modelColumns as any"
            :data="modelData"
            size="small"
            :flex-height="!appStore.isMobile"
            :scroll-x="1200"
            :loading="modelLoading"
            remote
            :row-key="row => row.id"
            :pagination="modelMobilePagination"
            class="sm:h-full"
          />
          <AiModelOperateDrawer
            v-model:visible="drawerVisible"
            :operate-type="operateType"
            :row-data="editingData as Api.SystemManage.AiModel | null"
            @submitted="getModelDataByPage"
          />
        </NCard>
      </NTabPane>

      <!-- 场景绑定 Tab -->
      <NTabPane name="binding" :tab="$t('page.manage.aiModel.bindingManage')" class="flex-1-hidden">
        <NCard :title="$t('page.manage.aiModel.bindingTitle')" :bordered="false" size="small" class="card-wrapper">
          <NDataTable
            :columns="bindingColumns as any"
            :data="bindingTableData"
            size="small"
            :loading="bindingLoading"
            :scroll-x="700"
            class="sm:h-full"
          />
          <p class="mt-16px text-gray-400 text-12px">{{ $t('page.manage.aiModel.bindingTip') }}</p>
        </NCard>
      </NTabPane>
    </NTabs>
  </div>
</template>

<style scoped>
:deep(.n-tabs) {
  display: flex;
  min-height: 0;
  flex-direction: column;
}
:deep(.n-tabs-pane-wrapper) {
  min-height: 0;
  flex: 1;
}
:deep(.n-tab-pane) {
  display: flex;
  min-height: 0;
  flex-direction: column;
  gap: 16px;
}
</style>
