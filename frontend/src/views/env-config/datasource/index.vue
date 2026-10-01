<script setup lang="tsx">
import { computed, onMounted, ref } from 'vue';
import type { DataTableColumns } from 'naive-ui';
import { NButton, NCard, NDataTable, NInput, NModal, NSpace, NSpin, NSwitch, NTag, NTooltip, useMessage } from 'naive-ui';
import {
  fetchGetDataSourceEvents,
  fetchGetDataSourceList,
  fetchGetDataSourceStats,
  fetchTestFqgateGateway,
  fetchUpdateDataSourceConfig,
  fetchUpdateFqgateConfig
} from '@/service/api';
import { useAuth } from '@/hooks/business/auth';
import { useAutoRefresh } from '@/hooks/common/auto-refresh';
import { $t } from '@/locales';
import DataSourceConfigDrawer from './modules/datasource-config-drawer.vue';
import DataSourceStatsChart from './modules/datasource-stats-chart.vue';
import { circuitStateLabel, circuitStateTagMap, eventOutcomeLabel, fqgateTestStepLabel, successRate } from './shared';

defineOptions({ name: 'ManageDatasourcePage' });

const message = useMessage();
const { hasAuth } = useAuth();

const loading = ref(false);
const sources = ref<Api.DataSource.SourceInfo[]>([]);
const fqgateGateway = ref<Api.DataSource.FqgateGateway>({ base_url: '' });
const stats = ref<Api.DataSource.StatRecord[]>([]);

/** 图表筛选用的数据源选项 */
const sourceOptions = computed(() => sources.value.map(item => ({ label: item.name, value: item.key })));

/** 静默刷新时不展示 loading，避免定时刷新造成闪烁 */
async function refresh(silent = false) {
  if (!silent) loading.value = true;
  try {
    const [{ data: listData }, { data: statsData }] = await Promise.all([
      fetchGetDataSourceList(),
      fetchGetDataSourceStats(7)
    ]);
    if (listData) {
      sources.value = listData.sources;
      fqgateGateway.value = listData.fqgate_gateway;
      fqgateBaseUrl.value = listData.fqgate_gateway.base_url;
    }
    if (statsData) {
      stats.value = statsData;
    }
  } finally {
    if (!silent) loading.value = false;
  }
}

onMounted(() => {
  refresh();
});

// 30s 自动刷新（静默）
useAutoRefresh(silent => refresh(silent), { interval: 30_000 });

/** ==================== FQGate 网关 ==================== */

const fqgateBaseUrl = ref('');
const fqgateSaving = ref(false);
const testLoading = ref(false);
const testResult = ref<Api.DataSource.FqgateTestResult | null>(null);

async function handleSaveFqgate() {
  const baseUrl = fqgateBaseUrl.value.trim();
  if (!baseUrl) {
    message.warning($t('page.manage.datasource.fqgate.baseUrlPlaceholder'));
    return;
  }
  fqgateSaving.value = true;
  try {
    const { error, data } = await fetchUpdateFqgateConfig(baseUrl);
    if (!error) {
      message.success($t('page.manage.datasource.fqgate.baseUrlSaved'));
      if (data) fqgateGateway.value = data;
    }
  } finally {
    fqgateSaving.value = false;
  }
}

async function handleTestFqgate() {
  testLoading.value = true;
  testResult.value = null;
  try {
    const { error, data } = await fetchTestFqgateGateway();
    if (!error && data) {
      testResult.value = data;
      if (data.ok) {
        message.success($t('page.manage.datasource.fqgate.testPassed'));
      } else {
        message.error($t('page.manage.datasource.fqgate.testFailed'));
      }
    }
  } finally {
    testLoading.value = false;
  }
}

/** ==================== 数据源操作 ==================== */

async function handleToggleEnabled(row: Api.DataSource.SourceInfo, enabled: boolean) {
  const { error } = await fetchUpdateDataSourceConfig({ source: row.key, config: { enabled } });
  if (!error) {
    message.success($t('common.updateSuccess'));
    row.config.enabled = enabled;
  }
}

const configDrawerVisible = ref(false);
const configRow = ref<Api.DataSource.SourceInfo | null>(null);

function handleOpenConfig(row: Api.DataSource.SourceInfo) {
  configRow.value = row;
  configDrawerVisible.value = true;
}

const eventsModalVisible = ref(false);
const eventsLoading = ref(false);
const events = ref<Api.DataSource.EventRecord[]>([]);
const eventsSource = ref<Api.DataSource.SourceInfo | null>(null);

async function handleOpenEvents(row: Api.DataSource.SourceInfo) {
  eventsSource.value = row;
  eventsModalVisible.value = true;
  eventsLoading.value = true;
  events.value = [];
  try {
    const { error, data } = await fetchGetDataSourceEvents(row.key);
    if (!error && data) {
      events.value = data;
    }
  } finally {
    eventsLoading.value = false;
  }
}

const eventsTitle = computed(() =>
  eventsSource.value
    ? `${$t('page.manage.datasource.eventsTitle')} - ${eventsSource.value.name} (${eventsSource.value.key})`
    : $t('page.manage.datasource.eventsTitle')
);

const eventColumns: DataTableColumns<Api.DataSource.EventRecord> = [
  {
    key: 'time',
    title: $t('page.manage.datasource.eventTime'),
    align: 'center',
    width: 180
  },
  {
    key: 'outcome',
    title: $t('page.manage.datasource.eventOutcome'),
    align: 'center',
    width: 90,
    render: row => (
      <NTag type={row.outcome === 'timeout' ? 'warning' : 'error'} size="small">
        {eventOutcomeLabel(row.outcome)}
      </NTag>
    )
  },
  {
    key: 'error',
    title: $t('page.manage.datasource.eventError'),
    align: 'center',
    minWidth: 220,
    ellipsis: { tooltip: true }
  },
  {
    key: 'latency_ms',
    title: $t('page.manage.datasource.eventLatency'),
    align: 'center',
    width: 100,
    render: row => `${row.latency_ms} ms`
  }
];

const columns = computed<DataTableColumns<Api.DataSource.SourceInfo>>(() => [
  {
    key: 'name',
    title: $t('page.manage.datasource.name'),
    align: 'center',
    minWidth: 140,
    render: row => (
      <div class="flex-col-center">
        <span>{row.name}</span>
        <span class="text-12px op-60">{row.key}</span>
      </div>
    )
  },
  {
    key: 'category',
    title: $t('page.manage.datasource.category'),
    align: 'center',
    minWidth: 120,
    ellipsis: { tooltip: true }
  },
  {
    key: 'enabled',
    title: $t('page.manage.datasource.enabled'),
    align: 'center',
    width: 90,
    render: row => (
      <NSwitch
        value={row.config.enabled}
        size="small"
        disabled={!hasAuth('datasource:config')}
        onUpdateValue={(val: boolean) => handleToggleEnabled(row, val)}
      />
    )
  },
  {
    key: 'circuit_state',
    title: $t('page.manage.datasource.circuitState'),
    align: 'center',
    width: 140,
    render: row => (
      <NTag type={circuitStateTagMap[row.circuit_state]} size="small">
        {circuitStateLabel(row)}
      </NTag>
    )
  },
  {
    key: 'today',
    title: $t('page.manage.datasource.todayUsage'),
    align: 'center',
    width: 140,
    render: row => {
      if (!row.today) return '-';
      return (
        <div class="flex-col-center">
          <span>
            {$t('page.manage.datasource.usageCalls', { total: row.today.total })}
          </span>
          <span class="text-12px op-60">
            {$t('page.manage.datasource.successRate')}: {successRate(row.today.success, row.today.total)}
          </span>
        </div>
      );
    }
  },
  {
    key: 'avg_latency',
    title: $t('page.manage.datasource.avgLatency'),
    align: 'center',
    width: 100,
    render: row => (row.today ? `${row.today.avg_latency_ms} ms` : '-')
  },
  {
    key: 'last_error',
    title: $t('page.manage.datasource.lastError'),
    align: 'center',
    minWidth: 180,
    render: row => {
      if (!row.last_error_msg) return $t('page.manage.datasource.noError');
      return (
        <NTooltip>
          {{
            trigger: () => <span class="inline-block max-w-220px truncate align-middle">{row.last_error_msg}</span>,
            default: () => (
              <div class="max-w-360px whitespace-pre-wrap">
                <div>{row.last_error_msg}</div>
                <div class="op-60">{row.last_error_at || ''}</div>
              </div>
            )
          }}
        </NTooltip>
      );
    }
  },
  {
    key: 'operate',
    title: $t('common.operate'),
    align: 'center',
    width: 150,
    fixed: 'right',
    render: row => (
      <div class="flex-center gap-8px">
        {hasAuth('datasource:config') && (
          <NButton type="primary" ghost size="small" onClick={() => handleOpenConfig(row)}>
            {$t('common.config')}
          </NButton>
        )}
        <NButton type="info" ghost size="small" onClick={() => handleOpenEvents(row)}>
          {$t('page.manage.datasource.events')}
        </NButton>
      </div>
    )
  }
]);
</script>

<template>
  <div class="min-h-500px flex-col-stretch gap-16px overflow-hidden lt-sm:overflow-auto">
    <!-- FQGate 网关 -->
    <NCard :bordered="false" size="small" class="card-wrapper">
      <template #header>
        <span>{{ $t('page.manage.datasource.fqgate.title') }}</span>
      </template>
      <template #header-extra>
        <NSpace align="center" :size="8">
          <NButton
            type="primary"
            ghost
            size="small"
            :loading="loading"
            @click="refresh()"
          >
            <template #icon>
              <icon-ic-round-refresh class="text-icon" />
            </template>
            {{ $t('common.refresh') }}
          </NButton>
        </NSpace>
      </template>
      <div class="flex-col-stretch gap-12px">
        <div class="flex items-center gap-8px">
          <span class="shrink-0 text-13px op-80">{{ $t('page.manage.datasource.fqgate.baseUrl') }}</span>
          <NInput
            v-model:value="fqgateBaseUrl"
            :placeholder="$t('page.manage.datasource.fqgate.baseUrlPlaceholder')"
            class="max-w-420px"
            size="small"
          />
          <NButton
            type="primary"
            ghost
            size="small"
            :loading="fqgateSaving"
            :disabled="!hasAuth('datasource:config')"
            @click="handleSaveFqgate"
          >
            {{ $t('page.manage.datasource.fqgate.saveBaseUrl') }}
          </NButton>
          <NButton
            v-if="hasAuth('datasource:test')"
            type="info"
            ghost
            size="small"
            :loading="testLoading"
            @click="handleTestFqgate"
          >
            {{ $t('page.manage.datasource.fqgate.testConnection') }}
          </NButton>
        </div>
        <div v-if="testResult" class="flex-col-stretch gap-6px">
          <div
            v-for="step in testResult.steps"
            :key="step.step"
            class="flex items-center gap-8px"
          >
            <NTag :type="step.ok ? 'success' : 'error'" size="small">
              {{ fqgateTestStepLabel(step.step) }}
            </NTag>
            <span class="text-12px op-60">{{ step.latency_ms }} ms</span>
            <span v-if="!step.ok && step.error" class="text-12px color-#d03050">{{ step.error }}</span>
          </div>
        </div>
      </div>
    </NCard>

    <!-- 数据源状态列表 -->
    <NCard :title="$t('page.manage.datasource.title')" :bordered="false" size="small" class="card-wrapper">
      <NSpin :show="loading">
        <NDataTable
          :columns="columns"
          :data="sources"
          size="small"
          :scroll-x="1200"
          :row-key="row => row.key"
          :pagination="false"
        />
      </NSpin>
    </NCard>

    <!-- 近 7 天用量图表 -->
    <NCard :title="$t('page.manage.datasource.stats.title')" :bordered="false" size="small" class="card-wrapper">
      <DataSourceStatsChart :data="stats" :source-options="sourceOptions" />
    </NCard>

    <DataSourceConfigDrawer v-model:visible="configDrawerVisible" :row-data="configRow" @submitted="refresh(true)" />

    <!-- 失败事件弹窗 -->
    <NModal v-model:show="eventsModalVisible" preset="card" :title="eventsTitle" class="w-720px">
      <NDataTable
        :columns="eventColumns"
        :data="events"
        size="small"
        :loading="eventsLoading"
        :pagination="false"
        max-height="420"
      />
    </NModal>
  </div>
</template>

<style scoped></style>
