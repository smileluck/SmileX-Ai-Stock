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
  NInput,
  NPagination,
  NPopover,
  NSelect,
  NSpace,
  NTag,
  NText
} from 'naive-ui';
import type { DataTableColumns } from 'naive-ui';
import dayjs from 'dayjs';
import {
  fetchGetFinancialConfig,
  fetchGetFinancialInterpretationDetail,
  fetchGetFinancialInterpretations,
  fetchGetFinancialReports,
  fetchRunFinancialInterpretation,
  fetchUpdateFinancialConfig
} from '@/service/api';
import { useAuth } from '@/hooks/business/auth';
import { $t } from '@/locales';
import AnalysisMarkdown from '../components/analysis-markdown.vue';
import AnalysisSection from '../components/analysis-section.vue';
import AnalysisStatusView from '../components/analysis-status-view.vue';
import AnalysisSummaryCard from '../components/analysis-summary-card.vue';

defineOptions({ name: 'AiFinancialAnalysis' });

const { hasAuth } = useAuth();
const canRun = hasAuth('financial:run');

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

/** 券商盈利预测对照文案：机构 评级 · 年份EPS/PE */
function researchBriefText(brief: Api.Financial.ResearchBrief | null): string {
  if (!brief) return '';
  const parts: string[] = [];
  if (brief.org_name) parts.push(brief.org_name);
  if (brief.rating) parts.push(brief.rating);
  const years = Object.keys(brief.forecast ?? {})
    .sort()
    .slice(0, 2)
    .map(y => {
      const f = brief.forecast?.[y] ?? {};
      const seg: string[] = [];
      if (f.eps !== undefined && f.eps !== null) seg.push(`EPS ${f.eps}`);
      if (f.pe !== undefined && f.pe !== null) seg.push(`PE ${f.pe}`);
      return seg.length ? `${y} ${seg.join(' / ')}` : '';
    })
    .filter(Boolean);
  const head = parts.length ? parts.join(' ') : '';
  return [head, ...years].filter(Boolean).join(' · ');
}

// ==================== 分析策略配置 ====================
const strategyShow = ref(false);
const strategyPrompt = ref('');
const strategySaving = ref(false);
const strategyPlaceholder = $t('page.financial.strategyPlaceholder');

async function openStrategy() {
  strategyShow.value = true;
  const { data, error } = await fetchGetFinancialConfig();
  if (!error) strategyPrompt.value = data?.prompt_template ?? '';
}

async function saveStrategy() {
  strategySaving.value = true;
  try {
    const prompt = strategyPrompt.value.trim() || null;
    const { error } = await fetchUpdateFinancialConfig(prompt);
    if (!error) {
      window.$message?.success($t('page.financial.strategySaved'));
      strategyShow.value = false;
    }
  } finally {
    strategySaving.value = false;
  }
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
    width: 150,
    render: row => (
      <div class="flex flex-col justify-center">
        <span class="text-13px font-500">{row.stock_name || row.stock_code}</span>
        <span class="text-12px" style="color: var(--n-text-color-3, #999)">
          {row.stock_name ? row.stock_code : ''}
        </span>
      </div>
    )
  },
  {
    key: 'industry',
    title: $t('page.financial.industryCol'),
    width: 100,
    ellipsis: { tooltip: true },
    render: row => <span class="text-12px">{row.industry || '-'}</span>
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
    width: 170,
    render: row => {
      if (row.status !== 'success') return <span class="text-12px">-</span>;
      const next = row.parsed_result?.next_quality_rating;
      const dir = row.parsed_result?.forecast?.direction;
      const drivers = row.parsed_result?.forecast?.drivers ?? [];
      const summary = row.parsed_result?.forecast?.summary ?? '';
      const briefText = researchBriefText(row.research_brief);
      const hasDetail = drivers.length > 0 || summary || briefText;
      const tags = (
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
      if (!hasDetail) return tags;
      return (
        <NPopover trigger="hover" placement="left" style={{ maxWidth: '360px' }}>
          {{
            trigger: () => tags,
            default: () => (
              <div class="flex flex-col gap-4px py-2px">
                {summary ? <div class="text-12px">{summary}</div> : null}
                {drivers.length > 0 ? (
                  <div>
                    <div class="mb-2px text-12px font-500">{$t('page.financial.forecastDriversLabel')}</div>
                    <ul class="m-0 pl-16px">
                      {drivers.map((p, i) => (
                        <li key={i} class="text-12px leading-20px">{p}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}
                {briefText ? (
                  <div>
                    <div class="mb-2px text-12px font-500">{$t('page.financial.researchBriefLabel')}</div>
                    <div class="text-12px">{briefText}</div>
                  </div>
                ) : null}
              </div>
            )
          }}
        </NPopover>
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
        <NButton v-if="canRun" size="small" tertiary @click="openStrategy">
          {{ $t('page.financial.strategyBtn') }}
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
      <AnalysisStatusView v-if="current?.status === 'running'" status="running" />

      <!-- 失败 -->
      <AnalysisStatusView
        v-else-if="current?.status === 'failed'"
        status="failed"
        :error-msg="current.error_msg"
      />

      <!-- 成功解读 -->
      <template v-else-if="current?.status === 'success' && current.ai_raw_response">
        <AnalysisSummaryCard v-if="parsed">
          <div class="flex flex-wrap items-center gap-x-24px gap-y-8px">
            <div class="flex-y-center gap-8px">
              <NText depth="3" class="text-12px">{{ $t('page.financial.ratingLabel') }}</NText>
              <NTag :type="ratingType(parsed.quality_rating)" size="small">
                {{ parsed.quality_rating ?? '-' }}
              </NTag>
            </div>
            <div class="flex-y-center gap-8px">
              <NText depth="3" class="text-12px">{{ $t('page.financial.nextRatingLabel') }}</NText>
              <NTag :type="ratingType(parsed.next_quality_rating)" size="small" :bordered="false">
                {{ parsed.next_quality_rating ?? '-' }}
              </NTag>
            </div>
            <div class="flex-y-center gap-8px">
              <NText depth="3" class="text-12px">{{ $t('page.financial.forecastLabel') }}</NText>
              <NTag :type="forecastType(parsed.forecast?.direction)" size="small" :bordered="false">
                {{ parsed.forecast?.direction || '-' }}
              </NTag>
            </div>
            <div class="flex-y-center gap-8px">
              <NText depth="3" class="text-12px">{{ $t('page.financial.periodCol') }}</NText>
              <NText class="text-13px">{{ current.report_period ?? '-' }}</NText>
            </div>
            <div class="flex-y-center gap-8px">
              <NText depth="3" class="text-12px">{{ $t('page.financial.industryCol') }}</NText>
              <NText class="text-13px">{{ current.industry ?? '-' }}</NText>
            </div>
          </div>
          <NText v-if="parsed.forecast?.summary" depth="2" class="mt-6px block text-13px leading-22px">
            {{ parsed.forecast.summary }}
          </NText>
        </AnalysisSummaryCard>

        <AnalysisSection v-if="parsed?.forecast?.drivers?.length" :title="$t('page.financial.forecastDriversLabel')">
          <ul class="m-0 pl-20px">
            <li v-for="(p, i) in parsed.forecast.drivers" :key="i" class="text-13px leading-22px">{{ p }}</li>
          </ul>
        </AnalysisSection>

        <AnalysisSection
          v-if="researchBriefText(current?.research_brief ?? null)"
          :title="$t('page.financial.researchBriefLabel')"
        >
          <div class="text-13px leading-22px">{{ researchBriefText(current?.research_brief ?? null) }}</div>
        </AnalysisSection>

        <AnalysisSection v-if="parsed?.highlights?.length" :title="$t('page.financial.highlightsLabel')">
          <ul class="m-0 pl-20px">
            <li v-for="(p, i) in parsed.highlights" :key="i" class="text-13px leading-22px">{{ p }}</li>
          </ul>
        </AnalysisSection>

        <AnalysisSection v-if="parsed?.risks?.length" :title="$t('page.financial.risksLabel')">
          <ul class="m-0 pl-20px">
            <li v-for="(p, i) in parsed.risks" :key="i" class="text-13px leading-22px">{{ p }}</li>
          </ul>
        </AnalysisSection>

        <AnalysisMarkdown class="mt-14px block" :raw="current.ai_raw_response" />
      </template>

      <AnalysisStatusView v-else status="empty" :empty-tip="$t('page.financial.emptyTip')" />
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
        <AnalysisStatusView v-else-if="drawerDetail?.status === 'running'" status="running" />

        <!-- 失败 -->
        <AnalysisStatusView
          v-else-if="drawerDetail?.status === 'failed'"
          status="failed"
          :error-msg="drawerDetail.error_msg"
        />

        <!-- 成功解读 -->
        <template v-else-if="drawerDetail?.status === 'success' && drawerDetail.ai_raw_response">
          <AnalysisSummaryCard v-if="drawerParsed">
            <div class="flex flex-wrap items-center gap-x-24px gap-y-8px">
              <div class="flex-y-center gap-8px">
                <NText depth="3" class="text-12px">{{ $t('page.financial.ratingLabel') }}</NText>
                <NTag :type="ratingType(drawerParsed.quality_rating)" size="small">
                  {{ drawerParsed.quality_rating ?? '-' }}
                </NTag>
              </div>
              <div class="flex-y-center gap-8px">
                <NText depth="3" class="text-12px">{{ $t('page.financial.nextRatingLabel') }}</NText>
                <NTag :type="ratingType(drawerParsed.next_quality_rating)" size="small" :bordered="false">
                  {{ drawerParsed.next_quality_rating ?? '-' }}
                </NTag>
              </div>
              <div class="flex-y-center gap-8px">
                <NText depth="3" class="text-12px">{{ $t('page.financial.forecastLabel') }}</NText>
                <NTag :type="forecastType(drawerParsed.forecast?.direction)" size="small" :bordered="false">
                  {{ drawerParsed.forecast?.direction || '-' }}
                </NTag>
              </div>
              <div class="flex-y-center gap-8px">
                <NText depth="3" class="text-12px">{{ $t('page.financial.periodCol') }}</NText>
                <NText class="text-13px">{{ drawerDetail.report_period ?? '-' }}</NText>
              </div>
              <div class="flex-y-center gap-8px">
                <NText depth="3" class="text-12px">{{ $t('page.financial.industryCol') }}</NText>
                <NText class="text-13px">{{ drawerDetail.industry ?? '-' }}</NText>
              </div>
            </div>
            <NText
              v-if="drawerParsed.forecast?.summary"
              depth="2"
              class="mt-6px block text-13px leading-22px"
            >
              {{ drawerParsed.forecast.summary }}
            </NText>
          </AnalysisSummaryCard>

          <AnalysisSection
            v-if="drawerParsed?.forecast?.drivers?.length"
            :title="$t('page.financial.forecastDriversLabel')"
          >
            <ul class="m-0 pl-20px">
              <li v-for="(p, i) in drawerParsed.forecast.drivers" :key="i" class="text-13px leading-22px">
                {{ p }}
              </li>
            </ul>
          </AnalysisSection>

          <AnalysisSection
            v-if="researchBriefText(drawerDetail?.research_brief ?? null)"
            :title="$t('page.financial.researchBriefLabel')"
          >
            <div class="text-13px leading-22px">{{ researchBriefText(drawerDetail?.research_brief ?? null) }}</div>
          </AnalysisSection>

          <AnalysisSection v-if="drawerParsed?.highlights?.length" :title="$t('page.financial.highlightsLabel')">
            <ul class="m-0 pl-20px">
              <li v-for="(p, i) in drawerParsed.highlights" :key="i" class="text-13px leading-22px">{{ p }}</li>
            </ul>
          </AnalysisSection>

          <AnalysisSection v-if="drawerParsed?.risks?.length" :title="$t('page.financial.risksLabel')">
            <ul class="m-0 pl-20px">
              <li v-for="(p, i) in drawerParsed.risks" :key="i" class="text-13px leading-22px">{{ p }}</li>
            </ul>
          </AnalysisSection>

          <AnalysisMarkdown class="mt-14px block" :raw="drawerDetail.ai_raw_response" />
        </template>

        <AnalysisStatusView v-else status="empty" :empty-tip="$t('page.financial.emptyTip')" />
      </NDrawerContent>
    </NDrawer>

    <!-- 分析策略配置抽屉（右侧） -->
    <NDrawer v-model:show="strategyShow" :width="480" placement="right">
      <NDrawerContent :title="$t('page.financial.strategyTitle')" closable>
        <NText depth="3" class="mb-8px block text-12px">
          {{ $t('page.financial.strategyTip') }}
        </NText>
        <NInput
          v-model:value="strategyPrompt"
          type="textarea"
          :rows="12"
          :maxlength="2000"
          show-count
          :placeholder="strategyPlaceholder"
        />
        <template #footer>
          <NSpace :size="12">
            <NButton size="small" @click="strategyShow = false">
              {{ $t('common.cancel') }}
            </NButton>
            <NButton size="small" type="primary" :loading="strategySaving" @click="saveStrategy">
              {{ $t('common.confirm') }}
            </NButton>
          </NSpace>
        </template>
      </NDrawerContent>
    </NDrawer>
  </div>
</template>
