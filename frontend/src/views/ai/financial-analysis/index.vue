<script setup lang="tsx">
/**
 * 财报分析页：按股票代码查询财报关键指标 + AI 解读预测（手动触发，异步轮询），
 * 下方为解读历史记录（含持仓股定时自动解读）
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import {
  NButton,
  NCard,
  NDataTable,
  NDescriptions,
  NDescriptionsItem,
  NDrawer,
  NDrawerContent,
  NEmpty,
  NInput,
  NPagination,
  NSelect,
  NSpace,
  NTag,
  NText
} from 'naive-ui';
import type { DataTableColumns } from 'naive-ui';
import dayjs from 'dayjs';
import MarkdownIt from 'markdown-it';
import {
  fetchGetFinancialInterpretationDetail,
  fetchGetFinancialInterpretations,
  fetchGetFinancialReports,
  fetchRunFinancialInterpretation
} from '@/service/api';
import { useAuth } from '@/hooks/business/auth';
import { $t } from '@/locales';

defineOptions({ name: 'AiFinancialAnalysis' });

const { hasAuth } = useAuth();
const canRun = hasAuth('financial:run');

const md = new MarkdownIt({ breaks: true, linkify: true, html: false });

// ==================== 股票查询与解读 ====================
const stockCode = ref('');
const stockInput = ref('');
const submitting = ref(false);
const reports = ref<Api.Financial.FinancialReportItem[]>([]);
const current = ref<Api.Financial.FinancialInterpretDetail | null>(null);

let pollTimer: ReturnType<typeof setTimeout> | null = null;

function stopPoll() {
  if (pollTimer) {
    clearTimeout(pollTimer);
    pollTimer = null;
  }
}

function normCode(v: string) {
  const digits = (v.match(/\d/g) ?? []).join('');
  return digits ? digits.padStart(6, '0') : '';
}

async function loadReports(code: string) {
  const { data, error } = await fetchGetFinancialReports(code, 8);
  if (!error) reports.value = data ?? [];
}

async function loadCurrent(code: string) {
  // 取该股最新一条解读记录
  const { data, error } = await fetchGetFinancialInterpretations({
    page: 1,
    page_size: 1,
    stock_code: code
  });
  if (!error && data?.records?.length) {
    const detailRes = await fetchGetFinancialInterpretationDetail(data.records[0].id);
    if (!detailRes.error) current.value = detailRes.data;
    if (current.value?.status === 'running') schedulePoll(code);
  } else {
    current.value = null;
  }
}

function schedulePoll(code: string) {
  stopPoll();
  pollTimer = setTimeout(async () => {
    await loadCurrent(code);
    if (current.value?.status === 'running') schedulePoll(code);
  }, 5000);
}

async function onQuery() {
  const code = normCode(stockInput.value);
  if (!code) {
    window.$message?.warning($t('page.financial.codeInvalid'));
    return;
  }
  stockCode.value = code;
  stopPoll();
  await Promise.all([loadReports(code), loadCurrent(code)]);
}

async function onInterpret() {
  const code = normCode(stockInput.value) || stockCode.value;
  if (!code) {
    window.$message?.warning($t('page.financial.codeInvalid'));
    return;
  }
  submitting.value = true;
  try {
    const { error } = await fetchRunFinancialInterpretation(code);
    if (!error) {
      window.$message?.success($t('page.financial.interpretSubmitted'));
      stockCode.value = code;
      await loadCurrent(code);
      await loadHistory();
    }
  } finally {
    submitting.value = false;
  }
}

// ==================== 解读历史列表 ====================
const historyList = ref<Api.Financial.FinancialInterpretItem[]>([]);
const historyTotal = ref(0);
const historyPage = ref(1);
const historyLoading = ref(false);

const RATING_OPTIONS = ['优秀', '良好', '一般', '较差'].map(v => ({ label: v, value: v }));
const DIRECTION_OPTIONS = ['改善', '持平', '恶化'].map(v => ({ label: v, value: v }));
const filterQualityRating = ref<string | null>(null);
const filterForecastDirection = ref<string | null>(null);

async function loadHistory() {
  historyLoading.value = true;
  try {
    const { data, error } = await fetchGetFinancialInterpretations({
      page: historyPage.value,
      page_size: 20,
      quality_rating: filterQualityRating.value ?? undefined,
      forecast_direction: filterForecastDirection.value ?? undefined
    });
    if (!error) {
      historyList.value = data?.records ?? [];
      historyTotal.value = data?.total ?? 0;
    }
  } finally {
    historyLoading.value = false;
  }
}

function onHistoryPageChange(page: number) {
  historyPage.value = page;
  loadHistory();
}

function onRatingFilterChange() {
  historyPage.value = 1;
  loadHistory();
}

async function viewHistoryRow(row: Api.Financial.FinancialInterpretItem) {
  // 右侧抽屉查看详情，不替换上方查询结果
  drawerShow.value = true;
  drawerDetail.value = null;
  drawerLoading.value = true;
  try {
    const { data, error } = await fetchGetFinancialInterpretationDetail(row.id);
    if (!error) {
      drawerDetail.value = data;
      return;
    }
    drawerShow.value = false;
  } finally {
    drawerLoading.value = false;
  }
}

// ==================== 详情抽屉 ====================
const drawerShow = ref(false);
const drawerDetail = ref<Api.Financial.FinancialInterpretDetail | null>(null);
const drawerLoading = ref(false);

const drawerParsed = computed(() => drawerDetail.value?.parsed_result ?? null);

const drawerMarkdown = computed(() => {
  const raw = drawerDetail.value?.ai_raw_response ?? '';
  const stripped = raw
    .replace(/```json\s*\{[\s\S]*?\}\s*```/, '')
    .replace(/<think>[\s\S]*?<\/think>/, '')
    .trim();
  return md.render(stripped);
});

const TRIGGER_LABEL: Record<string, string> = {
  schedule: $t('page.aiAnalysis.triggerSchedule'),
  manual: $t('page.aiAnalysis.triggerManual')
};

function statusTag(status: string) {
  if (status === 'running') {
    return <NTag type="info" size="small" bordered={false}>{$t('page.aiAnalysis.statusRunning')}</NTag>;
  }
  return status === 'success' ? (
    <NTag type="success" size="small" bordered={false}>{$t('page.aiAnalysis.statusSuccess')}</NTag>
  ) : (
    <NTag type="error" size="small" bordered={false}>{$t('page.aiAnalysis.statusFailed')}</NTag>
  );
}

const historyColumns = computed<DataTableColumns<Api.Financial.FinancialInterpretItem>>(() => [
  {
    key: 'stock_code',
    title: $t('page.financial.stockCol'),
    width: 140,
    render: row => (
      <span class="text-12px">
        {row.stock_code} {row.stock_name ? `- ${row.stock_name}` : ''}
      </span>
    )
  },
  {
    key: 'report_period',
    title: $t('page.financial.periodCol'),
    width: 110,
    render: row => <span class="text-12px">{row.report_period ?? '-'}</span>
  },
  {
    key: 'quality_rating',
    title: $t('page.financial.ratingLabel'),
    width: 100,
    render: row =>
      row.status === 'success' && row.parsed_result?.quality_rating ? (
        <NTag type={ratingType(row.parsed_result.quality_rating)} size="small">
          {row.parsed_result.quality_rating}
        </NTag>
      ) : (
        <span class="text-12px">-</span>
      )
  },
  {
    key: 'next_forecast',
    title: $t('page.financial.forecastLabel'),
    width: 150,
    render: row => {
      if (row.status !== 'success') return <span class="text-12px">-</span>;
      const next = row.parsed_result?.next_quality_rating;
      const dir = row.parsed_result?.forecast?.direction;
      if (!next && !dir) return <span class="text-12px">-</span>;
      return (
        <NSpace align="center" size={4} wrap={false}>
          {next ? (
            <NTag type={ratingType(next)} size="small" bordered={false}>
              {next}
            </NTag>
          ) : null}
          {dir ? (
            <NTag type={forecastType(dir)} size="small" bordered={false}>
              {dir}
            </NTag>
          ) : null}
        </NSpace>
      );
    }
  },
  {
    key: 'created_at',
    title: $t('page.aiAnalysis.execTime'),
    width: 140,
    render: row => (
      <span class="text-12px">
        {row.created_at ? dayjs(row.created_at).format('YYYY-MM-DD HH:mm') : '-'}
      </span>
    )
  },
  {
    key: 'trigger_type',
    title: $t('page.aiAnalysis.triggerCol'),
    width: 80,
    render: row => (
      <NTag size="small" bordered={false}>
        {TRIGGER_LABEL[row.trigger_type] ?? row.trigger_type}
      </NTag>
    )
  },
  {
    key: 'status',
    title: $t('page.aiAnalysis.statusCol'),
    width: 80,
    render: row => statusTag(row.status)
  },
  {
    key: 'actions',
    title: $t('common.action'),
    width: 70,
    align: 'center',
    render: row => (
      <NButton size="tiny" tertiary onClick={() => viewHistoryRow(row)}>
        {$t('page.aiAnalysis.viewBtn')}
      </NButton>
    )
  }
]);

// ==================== 展示 ====================
const parsed = computed(() => current.value?.parsed_result ?? null);
const latestReport = computed(() => reports.value[0] ?? null);

function ratingType(rating?: string): 'error' | 'success' | 'warning' | 'default' {
  if (rating?.includes('优秀')) return 'error';
  if (rating?.includes('良好')) return 'warning';
  if (rating?.includes('较差')) return 'success';
  return 'default';
}

function forecastType(direction?: string): 'error' | 'success' | 'warning' {
  if (direction?.includes('改善')) return 'error';
  if (direction?.includes('恶化')) return 'success';
  return 'warning';
}

const renderedMarkdown = computed(() => {
  const raw = current.value?.ai_raw_response ?? '';
  const stripped = raw
    .replace(/```json\s*\{[\s\S]*?\}\s*```/, '')
    .replace(/<think>[\s\S]*?<\/think>/, '')
    .trim();
  return md.render(stripped);
});

/** 财报指标表（最新一期） */
const metricRows = computed(() => {
  const metrics = latestReport.value?.metrics ?? {};
  return Object.entries(metrics).filter(([, v]) => v !== null && v !== undefined);
});

onMounted(() => loadHistory());
onBeforeUnmount(stopPoll);
</script>

<template>
  <div class="min-h-500px h-full flex flex-col gap-12px overflow-auto">
    <!-- 查询与解读 -->
    <NCard :bordered="false" size="small" class="card-wrapper">
      <template #header>
        <div class="flex-y-center gap-8px">
          <span class="text-16px font-500">{{ $t('page.financial.title') }}</span>
          <NText depth="3" class="text-12px">{{ $t('page.financial.subtitle') }}</NText>
        </div>
      </template>
      <NSpace align="center" :size="12" wrap>
        <NInput
          v-model:value="stockInput"
          :placeholder="$t('page.financial.codePlaceholder')"
          style="width: 260px"
          clearable
          @keyup.enter="onQuery"
        />
        <NButton size="small" type="primary" tertiary @click="onQuery">
          {{ $t('page.financial.queryBtn') }}
        </NButton>
        <NButton
          v-if="canRun"
          size="small"
          type="primary"
          :loading="submitting || current?.status === 'running'"
          :disabled="current?.status === 'running'"
          @click="onInterpret"
        >
          {{ $t('page.financial.interpretBtn') }}
        </NButton>
      </NSpace>
    </NCard>

    <!-- AI 解读结果 -->
    <NCard
      v-if="stockCode"
      :bordered="false"
      size="small"
      class="card-wrapper"
      :title="$t('page.financial.reportTitle')"
    >
      <!-- 生成中 -->
      <div v-if="current?.status === 'running'" class="flex-col items-center gap-12px py-48px">
        <icon-mdi-robot-excited class="text-48px" style="color: var(--primary-color)" />
        <NText depth="3">{{ $t('page.aiAnalysis.generatingTip') }}</NText>
      </div>

      <!-- 失败 -->
      <div v-else-if="current?.status === 'failed'" class="py-24px">
        <NEmpty :description="$t('page.aiAnalysis.failedTip')">
          <template #icon><icon-mdi-alert-circle-outline class="text-48px" style="color: #e0a240" /></template>
          <template #extra>
            <NText type="error" class="text-12px">{{ current.error_msg }}</NText>
          </template>
        </NEmpty>
      </div>

      <!-- 成功解读 -->
      <template v-else-if="current?.status === 'success' && current.ai_raw_response">
        <NDescriptions v-if="parsed" label-placement="left" :column="3" size="small" bordered class="mb-12px">
          <NDescriptionsItem :label="$t('page.financial.ratingLabel')">
            <NTag :type="ratingType(parsed.quality_rating)" size="small">
              {{ parsed.quality_rating ?? '-' }}
            </NTag>
          </NDescriptionsItem>
          <NDescriptionsItem :label="$t('page.financial.nextRatingLabel')">
            <NTag :type="ratingType(parsed.next_quality_rating)" size="small" :bordered="false">
              {{ parsed.next_quality_rating ?? '-' }}
            </NTag>
          </NDescriptionsItem>
          <NDescriptionsItem :label="$t('page.financial.forecastLabel')">
            <NSpace align="center" :size="8">
              <NTag :type="forecastType(parsed.forecast?.direction)" size="small" :bordered="false">
                {{ parsed.forecast?.direction || '-' }}
              </NTag>
              <NText depth="2" class="text-13px">{{ parsed.forecast?.summary || '' }}</NText>
            </NSpace>
          </NDescriptionsItem>
          <NDescriptionsItem :label="$t('page.aiAnalysis.summaryLabel')">
            {{ current.report_period ?? '-' }}
          </NDescriptionsItem>
        </NDescriptions>
        <div v-if="parsed?.highlights?.length" class="mb-12px">
          <NText class="mb-4px block text-13px font-500">{{ $t('page.financial.highlightsLabel') }}</NText>
          <ul class="m-0 pl-20px">
            <li v-for="(p, i) in parsed.highlights" :key="i" class="text-13px leading-22px">{{ p }}</li>
          </ul>
        </div>
        <div v-if="parsed?.risks?.length" class="mb-12px">
          <NText class="mb-4px block text-13px font-500">{{ $t('page.financial.risksLabel') }}</NText>
          <ul class="m-0 pl-20px">
            <li v-for="(p, i) in parsed.risks" :key="i" class="text-13px leading-22px">{{ p }}</li>
          </ul>
        </div>
        <div class="analysis-markdown text-13px" v-html="renderedMarkdown" />
      </template>

      <NEmpty v-else class="py-48px" :description="$t('page.financial.emptyTip')" />
    </NCard>

    <!-- 最新一期财报指标 -->
    <NCard
      v-if="metricRows.length"
      :bordered="false"
      size="small"
      class="card-wrapper"
      :title="`${$t('page.financial.metricsTitle')}（${latestReport?.report_period ?? ''}）`"
    >
      <NDescriptions label-placement="left" :column="2" s:3 l:4 size="small" bordered>
        <NDescriptionsItem v-for="[key, val] in metricRows" :key="key" :label="key">
          {{ val }}
        </NDescriptionsItem>
      </NDescriptions>
    </NCard>

    <!-- 解读历史（含持仓自动解读） -->
    <NCard :bordered="false" size="small" class="card-wrapper" :title="$t('page.financial.historyTitle')">
      <NSpace align="center" :size="12" wrap class="mb-12px">
        <NSelect
          v-model:value="filterQualityRating"
          :options="RATING_OPTIONS"
          :placeholder="$t('page.financial.ratingLabel')"
          clearable
          style="width: 140px"
          @update:value="onRatingFilterChange"
        />
        <NSelect
          v-model:value="filterForecastDirection"
          :options="DIRECTION_OPTIONS"
          :placeholder="$t('page.financial.forecastLabel')"
          clearable
          style="width: 140px"
          @update:value="onRatingFilterChange"
        />
      </NSpace>
      <NDataTable
        :columns="historyColumns"
        :data="historyList"
        size="small"
        :loading="historyLoading"
        :row-key="(row: Api.Financial.FinancialInterpretItem) => row.id"
        :flex-height="false"
      />
      <div class="mt-12px flex justify-end">
        <NPagination
          :page="historyPage"
          :page-size="20"
          :item-count="historyTotal"
          @update:page="onHistoryPageChange"
        />
      </div>
    </NCard>

    <!-- 历史详情抽屉（右侧） -->
    <NDrawer v-model:show="drawerShow" :width="560" placement="right">
      <NDrawerContent
        :title="`${drawerDetail?.stock_code ?? ''} ${drawerDetail?.stock_name ?? ''}`.trim() || $t('page.financial.reportTitle')"
        closable
      >
        <div v-if="drawerLoading" class="py-48px text-center">
          <NText depth="3">{{ $t('page.financial.drawerLoading') }}</NText>
        </div>

        <!-- 生成中 -->
        <div v-else-if="drawerDetail?.status === 'running'" class="flex-col items-center gap-12px py-48px">
          <icon-mdi-robot-excited class="text-48px" style="color: var(--primary-color)" />
          <NText depth="3">{{ $t('page.aiAnalysis.generatingTip') }}</NText>
        </div>

        <!-- 失败 -->
        <div v-else-if="drawerDetail?.status === 'failed'" class="py-24px">
          <NEmpty :description="$t('page.aiAnalysis.failedTip')">
            <template #icon><icon-mdi-alert-circle-outline class="text-48px" style="color: #e0a240" /></template>
            <template #extra>
              <NText type="error" class="text-12px">{{ drawerDetail.error_msg }}</NText>
            </template>
          </NEmpty>
        </div>

        <!-- 成功解读 -->
        <template v-else-if="drawerDetail?.status === 'success' && drawerDetail.ai_raw_response">
          <NDescriptions v-if="drawerParsed" label-placement="left" :column="1" size="small" bordered class="mb-12px">
            <NDescriptionsItem :label="$t('page.financial.periodCol')">
              {{ drawerDetail.report_period ?? '-' }}
            </NDescriptionsItem>
            <NDescriptionsItem :label="$t('page.financial.ratingLabel')">
              <NTag :type="ratingType(drawerParsed.quality_rating)" size="small">
                {{ drawerParsed.quality_rating ?? '-' }}
              </NTag>
            </NDescriptionsItem>
            <NDescriptionsItem :label="$t('page.financial.nextRatingLabel')">
              <NTag :type="ratingType(drawerParsed.next_quality_rating)" size="small" :bordered="false">
                {{ drawerParsed.next_quality_rating ?? '-' }}
              </NTag>
            </NDescriptionsItem>
            <NDescriptionsItem :label="$t('page.financial.forecastLabel')">
              <NSpace align="center" :size="8">
                <NTag :type="forecastType(drawerParsed.forecast?.direction)" size="small" :bordered="false">
                  {{ drawerParsed.forecast?.direction || '-' }}
                </NTag>
                <NText depth="2" class="text-13px">{{ drawerParsed.forecast?.summary || '' }}</NText>
              </NSpace>
            </NDescriptionsItem>
          </NDescriptions>
          <div v-if="drawerParsed?.highlights?.length" class="mb-12px">
            <NText class="mb-4px block text-13px font-500">{{ $t('page.financial.highlightsLabel') }}</NText>
            <ul class="m-0 pl-20px">
              <li v-for="(p, i) in drawerParsed.highlights" :key="i" class="text-13px leading-22px">{{ p }}</li>
            </ul>
          </div>
          <div v-if="drawerParsed?.risks?.length" class="mb-12px">
            <NText class="mb-4px block text-13px font-500">{{ $t('page.financial.risksLabel') }}</NText>
            <ul class="m-0 pl-20px">
              <li v-for="(p, i) in drawerParsed.risks" :key="i" class="text-13px leading-22px">{{ p }}</li>
            </ul>
          </div>
          <div class="analysis-markdown text-13px" v-html="drawerMarkdown" />
        </template>

        <NEmpty v-else class="py-48px" :description="$t('page.financial.emptyTip')" />
      </NDrawerContent>
    </NDrawer>
  </div>
</template>

<style scoped>
.analysis-markdown :deep(h2) {
  margin: 14px 0 8px;
  font-size: 15px;
  font-weight: 600;
}
.analysis-markdown :deep(h3) {
  margin: 10px 0 6px;
  font-size: 14px;
  font-weight: 600;
}
.analysis-markdown :deep(p) {
  margin: 6px 0;
  line-height: 22px;
}
.analysis-markdown :deep(ul),
.analysis-markdown :deep(ol) {
  margin: 6px 0;
  padding-left: 20px;
}
.analysis-markdown :deep(li) {
  line-height: 22px;
}
.analysis-markdown :deep(table) {
  border-collapse: collapse;
  margin: 8px 0;
}
.analysis-markdown :deep(th),
.analysis-markdown :deep(td) {
  border: 1px solid rgba(128, 128, 128, 0.3);
  padding: 4px 10px;
}
</style>
