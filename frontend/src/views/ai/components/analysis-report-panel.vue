<script setup lang="tsx">
/**
 * AI 分析报告面板（大盘/板块/资讯/轮动分析页共用）
 * - 生成分析按钮（analysis:run 权限）：提交后异步生成，自动轮询最新记录
 * - 分析策略按钮（analysis:strategy 权限）：策略提示词 + 明日研判开关，放在历史记录旁编辑
 * - 报告展示：摘要卡（情绪/温度 或 轮动总结）+ 统一区块（主题热度/标签云/资讯列表）
 *   + 明日研判条 + 核心观察 + markdown 正文（AnalysisMarkdown 统一渲染）
 * - 历史记录抽屉：分页列表，点击回看指定记录
 */
import { computed, onBeforeUnmount, ref } from 'vue';
import {
  NButton,
  NCard,
  NDataTable,
  NDrawer,
  NDrawerContent,
  NEmpty,
  NInput,
  NPagination,
  NProgress,
  NSpace,
  NSwitch,
  NTag,
  NText
} from 'naive-ui';
import type { DataTableColumns } from 'naive-ui';
import dayjs from 'dayjs';
import {
  fetchGetAnalysisConfig,
  fetchGetAnalysisRunDetail,
  fetchGetAnalysisRuns,
  fetchGetLatestAnalysis,
  fetchRunAnalysis,
  fetchUpdateAnalysisConfig
} from '@/service/api';
import { useAuth } from '@/hooks/business/auth';
import { $t } from '@/locales';
import AnalysisMarkdown from './analysis-markdown.vue';
import AnalysisSection from './analysis-section.vue';
import AnalysisStatusView from './analysis-status-view.vue';
import AnalysisSummaryCard from './analysis-summary-card.vue';

defineOptions({ name: 'AnalysisReportPanel' });

const props = defineProps<{
  analysisType: Api.Analysis.AnalysisType;
  session?: Api.Analysis.SessionType;
}>();

const { hasAuth } = useAuth();
const canRun = hasAuth('analysis:run');
const canEditStrategy = hasAuth('analysis:strategy');

// ==================== 最新报告与轮询 ====================
const latest = ref<Api.Analysis.AnalysisRunDetail | null>(null);
const current = ref<Api.Analysis.AnalysisRunDetail | null>(null);
const submitting = ref(false);
/** 当前展示的是否为历史记录（非最新一条） */
const viewingHistoryId = ref<number | null>(null);

let pollTimer: ReturnType<typeof setTimeout> | null = null;

function stopPoll() {
  if (pollTimer) {
    clearTimeout(pollTimer);
    pollTimer = null;
  }
}

function schedulePoll() {
  stopPoll();
  pollTimer = setTimeout(async () => {
    await loadLatest(true);
    if (latest.value?.status === 'running') schedulePoll();
  }, 5000);
}

async function loadLatest(silent = false) {
  const { data, error } = await fetchGetLatestAnalysis(props.analysisType, props.session);
  if (!error) {
    latest.value = data;
    // 正在看最新记录（非历史回看）时同步刷新展示
    if (viewingHistoryId.value === null) current.value = data;
    if (data?.status === 'running') schedulePoll();
  }
}

async function onGenerate() {
  submitting.value = true;
  try {
    const { error } = await fetchRunAnalysis(props.analysisType, props.session);
    if (!error) {
      window.$message?.success($t('page.aiAnalysis.runSubmitted'));
      viewingHistoryId.value = null;
      await loadLatest(true);
    }
  } finally {
    submitting.value = false;
  }
}

// ==================== 历史记录 ====================
const historyVisible = ref(false);
const historyList = ref<Api.Analysis.AnalysisRunItem[]>([]);
const historyTotal = ref(0);
const historyPage = ref(1);
const historyLoading = ref(false);

async function loadHistory() {
  historyLoading.value = true;
  try {
    const { data, error } = await fetchGetAnalysisRuns(
      props.analysisType,
      {
        page: historyPage.value,
        page_size: 20
      },
      props.session
    );
    if (!error) {
      historyList.value = data?.records ?? [];
      historyTotal.value = data?.total ?? 0;
    }
  } finally {
    historyLoading.value = false;
  }
}

function openHistory() {
  historyVisible.value = true;
  loadHistory();
}

function onHistoryPageChange(page: number) {
  historyPage.value = page;
  loadHistory();
}

async function viewHistoryRow(row: Api.Analysis.AnalysisRunItem) {
  const { data, error } = await fetchGetAnalysisRunDetail(row.id);
  if (!error && data) {
    current.value = data;
    viewingHistoryId.value = row.id;
    historyVisible.value = false;
  }
}

function backToLatest() {
  viewingHistoryId.value = null;
  current.value = latest.value;
}

// ==================== 分析策略配置 ====================
const strategyVisible = ref(false);
const strategyForm = ref<Api.Analysis.AnalysisConfigSaveParams>({
  prompt_template: '',
  include_tomorrow: true,
  tomorrow_prompt_template: ''
});
const strategyLoading = ref(false);
const strategySaving = ref(false);

async function openStrategy() {
  strategyVisible.value = true;
  strategyLoading.value = true;
  try {
    const { data, error } = await fetchGetAnalysisConfig(props.analysisType, props.session);
    if (!error) {
      strategyForm.value = {
        prompt_template: data?.prompt_template ?? '',
        include_tomorrow: data?.include_tomorrow ?? true,
        tomorrow_prompt_template: data?.tomorrow_prompt_template ?? ''
      };
    }
  } finally {
    strategyLoading.value = false;
  }
}

async function saveStrategy() {
  strategySaving.value = true;
  try {
    const { error } = await fetchUpdateAnalysisConfig(
      props.analysisType,
      {
        prompt_template: strategyForm.value.prompt_template?.trim() || null,
        include_tomorrow: strategyForm.value.include_tomorrow,
        tomorrow_prompt_template: strategyForm.value.include_tomorrow
          ? strategyForm.value.tomorrow_prompt_template?.trim() || null
          : null
      },
      props.session
    );
    if (!error) {
      window.$message?.success($t('page.aiAnalysis.strategySaved'));
      strategyVisible.value = false;
    }
  } finally {
    strategySaving.value = false;
  }
}

const TRIGGER_LABEL: Record<string, string> = {
  schedule: $t('page.aiAnalysis.triggerSchedule'),
  manual: $t('page.aiAnalysis.triggerManual')
};

function statusTag(status: string) {
  if (status === 'running') {
    return (
      <NTag type="info" size="small" bordered={false}>
        {$t('page.aiAnalysis.statusRunning')}
      </NTag>
    );
  }
  return status === 'success' ? (
    <NTag type="success" size="small" bordered={false}>
      {$t('page.aiAnalysis.statusSuccess')}
    </NTag>
  ) : (
    <NTag type="error" size="small" bordered={false}>
      {$t('page.aiAnalysis.statusFailed')}
    </NTag>
  );
}

function summaryText(row: Api.Analysis.AnalysisRunItem | Api.Analysis.AnalysisRunDetail | null) {
  if (!row?.parsed_result) return '-';
  const parsed = row.parsed_result as Record<string, unknown>;
  return String(parsed.summary ?? parsed.rotation_summary ?? '-');
}

const historyColumns = computed<DataTableColumns<Api.Analysis.AnalysisRunItem>>(() => [
  {
    key: 'created_at',
    title: $t('page.aiAnalysis.execTime'),
    width: 150,
    render: row => <span class="text-12px">{row.created_at ? dayjs(row.created_at).format('YYYY-MM-DD HH:mm') : '-'}</span>
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
    key: 'summary',
    title: $t('page.aiAnalysis.summaryCol'),
    minWidth: 180,
    ellipsis: { tooltip: true },
    render: row => <span class="text-12px">{summaryText(row)}</span>
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

// ==================== 报告展示 ====================
const marketParsed = computed(() => {
  if (props.analysisType !== 'market' || !current.value?.parsed_result) return null;
  return current.value.parsed_result as Api.Analysis.MarketParsedResult;
});

const sectorParsed = computed(() => {
  if (props.analysisType !== 'sector' || !current.value?.parsed_result) return null;
  return current.value.parsed_result as Api.Analysis.SectorParsedResult;
});

const newsParsed = computed(() => {
  if (props.analysisType !== 'news' || !current.value?.parsed_result) return null;
  return current.value.parsed_result as Api.Analysis.NewsParsedResult;
});

const rotationParsed = computed(() => {
  if (props.analysisType !== 'rotation' || !current.value?.parsed_result) return null;
  return current.value.parsed_result as Api.Analysis.RotationParsedResult;
});

/** 轮动阶段标签配色：启动-蓝 / 发酵-橙 / 高潮-红 / 退潮-绿 / 蓄势-灰 */
function stageTagType(stage?: string): 'info' | 'warning' | 'error' | 'success' | 'default' {
  switch (stage) {
    case 'start':
      return 'info';
    case 'ferment':
      return 'warning';
    case 'climax':
      return 'error';
    case 'ebb':
      return 'success';
    default:
      return 'default';
  }
}

/** 轮动操作建议标签配色：主攻-红 / 潜伏-橙 / 回避-绿 / 其他-灰 */
function actionTagType(action?: string): 'error' | 'warning' | 'success' | 'default' {
  if (action?.includes('主攻')) return 'error';
  if (action?.includes('潜伏')) return 'warning';
  if (action?.includes('回避')) return 'success';
  return 'default';
}

/** 主题热度状态配色：集结升温-蓝(埋伏窗口) / 发酵走强-橙 / 高位过热-红 / 退潮-绿 / 其他-灰 */
function themeStatusTagType(status?: string): 'info' | 'warning' | 'error' | 'success' | 'default' {
  switch (status) {
    case 'gathering':
      return 'info';
    case 'active':
      return 'warning';
    case 'hot':
      return 'error';
    case 'cooling':
      return 'success';
    default:
      return 'default';
  }
}

/** 资讯分析不涉及研判章节开关 */
const isNewsType = computed(() => props.analysisType === 'news');

const keyPoints = computed(() => {
  const parsed = current.value?.parsed_result as { key_points?: string[] } | null | undefined;
  return parsed?.key_points ?? [];
});

/** 明日研判（market/sector 摘要共用字段，未开启或未输出时为空；早盘时段语义为「今日展望」） */
const tomorrowOutlook = computed(() => {
  const parsed = current.value?.parsed_result as Api.Analysis.MarketParsedResult | undefined;
  return parsed?.tomorrow_outlook ?? null;
});

/** 研判标签按时段切换：收盘=明日研判，早盘=今日展望 */
const outlookLabelKey = computed(() =>
  props.session === 'morning' ? 'page.aiAnalysis.todayOutlookLabel' : 'page.aiAnalysis.tomorrowLabel'
);

/** 策略抽屉标题按时段区分 */
const strategyTitleKey = computed(() =>
  props.session === 'morning' ? 'page.aiAnalysis.morningStrategyTitle' : 'page.aiAnalysis.strategyTitle'
);

/** 策略抽屉内各文案按时段区分：收盘=复盘+明日预判，早盘=当日推演 */
const isMorningSession = computed(() => props.session === 'morning');
const outlookSwitchLabelKey = computed(() =>
  isMorningSession.value ? 'page.aiAnalysis.includeTodayOutlook' : 'page.aiAnalysis.includeTomorrow'
);
const outlookSwitchTipKey = computed(() =>
  isMorningSession.value ? 'page.aiAnalysis.includeTodayTip' : 'page.aiAnalysis.includeTomorrowTip'
);
const strategyPromptPlaceholderKey = computed(() =>
  isMorningSession.value
    ? 'page.aiAnalysis.morningPromptPlaceholder'
    : 'page.aiAnalysis.strategyPromptPlaceholder'
);
const outlookPromptLabelKey = computed(() =>
  isMorningSession.value ? 'page.aiAnalysis.todayPromptLabel' : 'page.aiAnalysis.tomorrowPromptLabel'
);
const outlookPromptPlaceholderKey = computed(() =>
  isMorningSession.value
    ? 'page.aiAnalysis.todayPromptPlaceholder'
    : 'page.aiAnalysis.tomorrowPromptPlaceholder'
);

function tomorrowType(direction?: string): 'error' | 'success' | 'warning' {
  if (!direction) return 'warning';
  if (/看涨|偏多|延续|上涨/.test(direction)) return 'error';
  if (/看跌|偏空|退潮|下跌/.test(direction)) return 'success';
  return 'warning';
}

function sentimentType(sentiment?: string): 'error' | 'success' | 'warning' {
  if (sentiment?.includes('看多')) return 'error';
  if (sentiment?.includes('看空')) return 'success';
  return 'warning';
}

/** 资讯影响标签：利好-红，利空-绿，中性-默认 */
function impactTagType(impact?: string): 'error' | 'success' | 'default' {
  if (impact?.includes('利好')) return 'error';
  if (impact?.includes('利空')) return 'success';
  return 'default';
}

function pctColor(val: number | null | undefined) {
  if (val === null || val === undefined) return '#8c8c8c';
  return val > 0 ? '#f5222d' : val < 0 ? '#52c41a' : '#8c8c8c';
}

function scoreColor(score?: number) {
  if (score === undefined) return '#8c8c8c';
  if (score >= 70) return '#f5222d';
  if (score >= 40) return '#faad14';
  return '#52c41a';
}

loadLatest();
onBeforeUnmount(stopPoll);
</script>

<template>
  <NCard
    :bordered="false"
    size="small"
    class="card-wrapper min-h-0 flex flex-1 flex-col"
    content-style="flex: 1 1 0%; overflow-y: auto;"
  >
    <template #header>
      <div class="flex-y-center gap-8px">
        <span class="text-16px font-500">{{ $t('page.aiAnalysis.reportTitle') }}</span>
        <NTag v-if="current" size="small" :bordered="false">
          {{ current.created_at ? current.created_at.substring(0, 10) : '' }}
        </NTag>
        <NTag v-if="current && current.status === 'success'" size="small" :bordered="false">
          {{ TRIGGER_LABEL[current.trigger_type] ?? current.trigger_type }}
        </NTag>
      </div>
    </template>
    <template #header-extra>
      <NSpace align="center" :size="8">
        <NButton v-if="viewingHistoryId !== null" size="small" tertiary @click="backToLatest">
          {{ $t('page.aiAnalysis.backToLatest') }}
        </NButton>
        <NButton size="small" tertiary @click="openHistory">
          <template #icon><icon-mdi-history class="text-icon" /></template>
          {{ $t('page.aiAnalysis.historyBtn') }}
        </NButton>
        <NButton v-if="canEditStrategy" size="small" tertiary @click="openStrategy">
          <template #icon><icon-mdi-tune-vertical class="text-icon" /></template>
          {{ $t('page.aiAnalysis.strategyBtn') }}
        </NButton>
        <NButton
          v-if="canRun"
          size="small"
          type="primary"
          :loading="submitting || current?.status === 'running'"
          :disabled="current?.status === 'running'"
          @click="onGenerate"
        >
          <template #icon><icon-mdi-auto-fix class="text-icon" /></template>
          {{ current?.status === 'running' ? $t('page.aiAnalysis.statusRunning') : $t('page.aiAnalysis.generate') }}
        </NButton>
      </NSpace>
    </template>

    <!-- 生成中 -->
    <AnalysisStatusView v-if="current?.status === 'running'" status="running" />

    <!-- 失败 -->
    <AnalysisStatusView
      v-else-if="current?.status === 'failed'"
      status="failed"
      :error-msg="current.error_msg"
    />

    <!-- 成功报告 -->
    <template v-else-if="current?.status === 'success' && current.ai_raw_response">
      <!-- 大盘：情绪 + 温度 + 总评摘要卡 -->
      <AnalysisSummaryCard v-if="marketParsed">
        <div class="flex flex-wrap items-center gap-x-24px gap-y-8px">
          <div class="flex-y-center gap-8px">
            <NText depth="3" class="text-12px">{{ $t('page.aiAnalysis.sentimentLabel') }}</NText>
            <NTag :type="sentimentType(marketParsed.sentiment)" size="small">
              {{ marketParsed.sentiment ?? '-' }}
            </NTag>
          </div>
          <div class="flex-y-center gap-8px">
            <NText depth="3" class="text-12px">{{ $t('page.aiAnalysis.scoreLabel') }}</NText>
            <NSpace align="center" :size="6">
              <NProgress
                type="circle"
                :percentage="marketParsed.score ?? 0"
                :color="scoreColor(marketParsed.score)"
                :stroke-width="6"
                :show-indicator="false"
                style="width: 18px"
              />
              <span :style="{ color: scoreColor(marketParsed.score), fontWeight: '600' }">
                {{ marketParsed.score ?? '-' }}
              </span>
            </NSpace>
          </div>
        </div>
        <NText depth="3" class="mb-2px mt-8px block text-12px">{{ $t('page.aiAnalysis.summaryLabel') }}</NText>
        <NText depth="2" class="block text-13px leading-22px">
          {{ marketParsed.summary ?? '-' }}
        </NText>
      </AnalysisSummaryCard>

      <!-- 板块/轮动：轮动总结摘要卡 -->
      <AnalysisSummaryCard v-if="sectorParsed">
        <NText depth="3" class="mb-2px block text-12px">{{ $t('page.aiAnalysis.rotationLabel') }}</NText>
        <NText depth="2" class="block text-13px leading-22px">
          {{ sectorParsed.rotation_summary ?? '-' }}
        </NText>
      </AnalysisSummaryCard>
      <AnalysisSummaryCard v-if="rotationParsed">
        <NText depth="3" class="mb-2px block text-12px">{{ $t('page.aiAnalysis.rotationLabel') }}</NText>
        <NText depth="2" class="block text-13px leading-22px">
          {{ rotationParsed.rotation_summary ?? '-' }}
        </NText>
      </AnalysisSummaryCard>

      <!-- 资讯：总评摘要卡 -->
      <AnalysisSummaryCard v-if="newsParsed">
        <NText depth="3" class="mb-2px block text-12px">{{ $t('page.aiAnalysis.summaryLabel') }}</NText>
        <NText depth="2" class="block text-13px leading-22px">
          {{ newsParsed.summary ?? '-' }}
        </NText>
      </AnalysisSummaryCard>

      <!-- 板块：关注板块标签云 -->
      <AnalysisSection
        v-if="sectorParsed?.hot_boards?.length"
        :title="$t('page.aiAnalysis.hotBoardsLabel')"
      >
        <NSpace :size="6" wrap>
          <NTag
            v-for="(board, idx) in sectorParsed.hot_boards"
            :key="idx"
            size="small"
            :bordered="false"
            type="info"
          >
            {{ board.board_name }}
            <span
              v-if="board.change_pct !== null && board.change_pct !== undefined"
              :style="{ color: pctColor(board.change_pct) }"
            >
              {{ board.change_pct! > 0 ? '+' : '' }}{{ board.change_pct!.toFixed(2) }}%
            </span>
          </NTag>
        </NSpace>
      </AnalysisSection>

      <!-- 轮动：主题热度 -->
      <AnalysisSection
        v-if="rotationParsed?.theme_heat?.length"
        :title="$t('page.aiAnalysis.rotation.themeHeatLabel')"
      >
        <div class="flex flex-col gap-6px">
          <div v-for="(t, idx) in rotationParsed.theme_heat" :key="idx" class="flex-y-center">
            <NTag size="small" :bordered="false" :type="themeStatusTagType(t.status)" class="flex-shrink-0">
              <span class="font-500">{{ t.theme }}</span>
              <span v-if="t.heat !== null && t.heat !== undefined" class="ml-4px">{{ t.heat }}</span>
            </NTag>
            <NText v-if="t.viewpoint" class="ml-8px text-12px leading-20px">{{ t.viewpoint }}</NText>
          </div>
        </div>
      </AnalysisSection>

      <!-- 轮动：近期板块 -->
      <AnalysisSection
        v-if="rotationParsed?.recent_boards?.length"
        :title="$t('page.aiAnalysis.rotation.recentBoardsLabel')"
      >
        <NSpace :size="6" wrap>
          <NTag
            v-for="(board, idx) in rotationParsed.recent_boards"
            :key="idx"
            size="small"
            :bordered="false"
            :type="stageTagType(board.stage)"
          >
            {{ board.board_name }}
            <span
              v-if="board.change_pct !== null && board.change_pct !== undefined"
              :style="{ color: pctColor(board.change_pct) }"
            >
              {{ board.change_pct! > 0 ? '+' : '' }}{{ board.change_pct!.toFixed(2) }}%
            </span>
          </NTag>
        </NSpace>
      </AnalysisSection>

      <!-- 轮动：明日候选 -->
      <AnalysisSection
        v-if="rotationParsed?.tomorrow_boards?.length"
        :title="$t('page.aiAnalysis.rotation.tomorrowBoardsLabel')"
      >
        <NSpace :size="6" wrap>
          <NTag
            v-for="(board, idx) in rotationParsed.tomorrow_boards"
            :key="idx"
            size="small"
            :bordered="false"
            :type="actionTagType(board.action)"
          >
            {{ board.board_name }}
            <span v-if="board.action">{{ board.action }}</span>
            <span v-if="board.confidence" class="text-11px opacity-70">{{ board.confidence }}</span>
          </NTag>
        </NSpace>
      </AnalysisSection>

      <!-- 轮动：切换信号 -->
      <AnalysisSection
        v-if="rotationParsed?.switch_signals?.length"
        :title="$t('page.aiAnalysis.rotation.switchSignalsLabel')"
      >
        <div class="flex flex-col gap-4px">
          <NText v-for="(sig, idx) in rotationParsed.switch_signals" :key="idx" class="text-12px leading-20px">
            <span class="font-500">{{ sig.board_name }}</span>
            <span class="ml-6px">{{ sig.summary }}</span>
          </NText>
        </div>
      </AnalysisSection>

      <!-- 资讯：宏观/行业 与 个股 两个分区 -->
      <template v-if="newsParsed">
        <AnalysisSection
          v-for="section in (['macro_industry_news', 'stock_news'] as const)"
          :key="section"
          :title="
            $t(section === 'macro_industry_news' ? 'page.aiAnalysis.macroNewsLabel' : 'page.aiAnalysis.stockNewsLabel')
          "
        >
          <div class="flex flex-col gap-6px">
            <div
              v-for="(item, idx) in newsParsed[section] ?? []"
              :key="idx"
              class="rounded-6px border border-gray-200 px-10px py-6px dark:border-gray-700"
            >
              <div class="flex items-start gap-8px">
                <NTag size="small" :bordered="false" :type="impactTagType(item.impact)">
                  {{ item.impact || '-' }}
                </NTag>
                <div class="min-w-0 flex-1">
                  <div class="flex flex-wrap items-center gap-x-8px gap-y-2px">
                    <span class="text-13px font-500">{{ item.title || '-' }}</span>
                    <NTag v-if="item.category" size="tiny" :bordered="false">{{ item.category }}</NTag>
                    <NTag v-if="item.stock_name" size="tiny" :bordered="false" type="info">
                      {{ item.stock_name }}
                    </NTag>
                  </div>
                  <NText depth="2" class="text-12px leading-20px">{{ item.viewpoint || '' }}</NText>
                  <NText depth="3" class="ml-8px text-12px">{{ item.source || '' }}</NText>
                </div>
              </div>
            </div>
            <NEmpty
              v-if="!(newsParsed[section] ?? []).length"
              size="small"
              :description="$t('page.aiAnalysis.newsSectionEmpty')"
            />
          </div>
        </AnalysisSection>
      </template>

      <!-- 明日研判/今日展望 -->
      <div
        v-if="tomorrowOutlook"
        class="mt-14px flex items-center gap-8px rounded-8px border border-primary-200 py-8px pl-10px pr-12px dark:border-primary-800"
      >
        <span class="h-14px w-3px shrink-0 rounded-2px bg-primary" />
        <NText class="shrink-0 text-13px font-600">{{ $t(outlookLabelKey) }}</NText>
        <NTag size="small" :type="tomorrowType(tomorrowOutlook.direction)" :bordered="false">
          {{ tomorrowOutlook.direction || '-' }}
        </NTag>
        <NText depth="2" class="text-13px leading-22px">{{ tomorrowOutlook.summary || '' }}</NText>
      </div>

      <!-- 核心观察 -->
      <AnalysisSection v-if="keyPoints.length" :title="$t('page.aiAnalysis.keyPointsLabel')">
        <ul class="m-0 pl-20px">
          <li v-for="(point, idx) in keyPoints" :key="idx" class="text-13px leading-22px">
            {{ point }}
          </li>
        </ul>
      </AnalysisSection>

      <!-- markdown 报告正文 -->
      <AnalysisMarkdown class="mt-14px block" :raw="current.ai_raw_response" />
      <div class="mt-8px flex justify-end">
        <NText depth="3" class="text-12px">
          {{ $t('page.aiAnalysis.execTime') }}:
          {{ current.created_at ? current.created_at.replace('T', ' ').substring(0, 16) : '-' }}
        </NText>
      </div>
    </template>

    <!-- 无记录 -->
    <AnalysisStatusView v-else status="empty" />

    <!-- 分析策略配置抽屉 -->
    <NDrawer v-model:show="strategyVisible" :width="480">
      <NDrawerContent :title="$t(strategyTitleKey)" closable :native-scrollbar="false">
        <!-- 研判设置 -->
        <AnalysisSection v-if="!isNewsType" :title="$t(outlookSwitchLabelKey)">
          <NSpace align="center" :size="12">
            <NSwitch v-model:value="strategyForm.include_tomorrow" />
            <NText depth="3" class="text-12px">{{ $t(outlookSwitchTipKey) }}</NText>
          </NSpace>
        </AnalysisSection>

        <!-- 策略提示词 -->
        <AnalysisSection :title="$t('page.aiAnalysis.strategyPromptLabel')">
          <NInput
            v-model:value="strategyForm.prompt_template"
            type="textarea"
            :rows="6"
            :maxlength="2000"
            show-count
            :loading="strategyLoading"
            :placeholder="$t(strategyPromptPlaceholderKey)"
          />
          <NText depth="3" class="mt-6px block text-12px">
            {{ $t('page.aiAnalysis.newsInjectTip') }}
          </NText>
        </AnalysisSection>

        <!-- 研判提示词 -->
        <AnalysisSection
          v-if="strategyForm.include_tomorrow && !isNewsType"
          :title="$t(outlookPromptLabelKey)"
        >
          <NInput
            v-model:value="strategyForm.tomorrow_prompt_template"
            type="textarea"
            :rows="6"
            :maxlength="2000"
            show-count
            :loading="strategyLoading"
            :placeholder="$t(outlookPromptPlaceholderKey)"
          />
        </AnalysisSection>

        <NText depth="3" class="mt-8px block text-12px">
          {{ $t('page.aiAnalysis.strategyEffectTip') }}
        </NText>
        <template #footer>
          <NButton type="primary" :loading="strategySaving" @click="saveStrategy">
            {{ $t('page.aiAnalysis.saveBtn') }}
          </NButton>
        </template>
      </NDrawerContent>
    </NDrawer>

    <!-- 历史记录抽屉 -->
    <NDrawer v-model:show="historyVisible" :width="620">
      <NDrawerContent :title="$t('page.aiAnalysis.historyTitle')" closable :native-scrollbar="false">
        <NDataTable
          :columns="historyColumns"
          :data="historyList"
          size="small"
          :loading="historyLoading"
          :row-key="(row: Api.Analysis.AnalysisRunItem) => row.id"
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
      </NDrawerContent>
    </NDrawer>
  </NCard>
</template>
