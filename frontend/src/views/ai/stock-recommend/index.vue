<script setup lang="tsx">
/**
 * AI 推荐板块页（荐股）
 * - 头部工具区：生成推荐（recommend:run 权限，running 时禁用）+ 最近生成时间 + 历史推荐抽屉
 * - 主体：10 只推荐股表格（方向/综合分/买点/目标/止损/入场方式/六维依据/AI 理由）
 * - 下方：AI 综合研判 markdown 面板（复用 AnalysisMarkdown 渲染）
 * - running 状态每 5s 轮询 latest 直到终态；failed 展示 error_msg
 * - 头部回测/持仓入口：按本次 run 的 strategy_id 跳转（为空则禁用）
 */
import { computed, onBeforeUnmount, ref } from 'vue';
import {
  NButton,
  NCard,
  NDataTable,
  NDrawer,
  NDrawerContent,
  NEmpty,
  NPagination,
  NProgress,
  NSpace,
  NTag,
  NText,
  NTooltip
} from 'naive-ui';
import type { DataTableColumns } from 'naive-ui';
import dayjs from 'dayjs';
import { fetchRecommendDetail, fetchRecommendLatest, fetchRecommendRuns, fetchRunRecommend } from '@/service/api';
import { useAuth } from '@/hooks/business/auth';
import { useRouterPush } from '@/hooks/common/router';
import { $t } from '@/locales';
import AnalysisMarkdown from '../components/analysis-markdown.vue';

defineOptions({ name: 'AiStockRecommend' });

const { hasAuth } = useAuth();
const canRun = hasAuth('recommend:run');
const { routerPushByKey } = useRouterPush();

// ==================== 最新推荐与轮询 ====================
const latest = ref<Api.Recommend.RecommendRunDetail | null>(null);
const current = ref<Api.Recommend.RecommendRunDetail | null>(null);
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
    await loadLatest();
    if (latest.value?.status === 'running') schedulePoll();
  }, 5000);
}

async function loadLatest() {
  const { data, error } = await fetchRecommendLatest();
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
    const { error } = await fetchRunRecommend();
    if (!error) {
      window.$message?.success($t('page.aiRecommend.runSubmitted'));
      viewingHistoryId.value = null;
      await loadLatest();
    }
  } finally {
    submitting.value = false;
  }
}

// ==================== 历史推荐 ====================
const historyVisible = ref(false);
const historyList = ref<Api.Recommend.RecommendRunItem[]>([]);
const historyTotal = ref(0);
const historyPage = ref(1);
const historyLoading = ref(false);

async function loadHistory() {
  historyLoading.value = true;
  try {
    const { data, error } = await fetchRecommendRuns({ page: historyPage.value, page_size: 20 });
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

async function viewHistoryRow(row: Api.Recommend.RecommendRunItem) {
  const { data, error } = await fetchRecommendDetail(row.id);
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

// ==================== 跳转回测 / 持仓 ====================
const strategyId = computed(() => current.value?.strategy_id ?? null);

function goBacktest() {
  if (strategyId.value === null) return;
  routerPushByKey('ai_backtest', { query: { strategy_id: String(strategyId.value) } });
}

function goPositions() {
  if (strategyId.value === null) return;
  routerPushByKey('ai_analysis', { query: { tab: 'positions', strategy_id: String(strategyId.value) } });
}

// ==================== 展示辅助 ====================
function statusTag(status: Api.Recommend.RecommendRunStatus) {
  if (status === 'running') {
    return (
      <NTag type="info" size="small" bordered={false}>
        {$t('page.aiRecommend.statusRunning')}
      </NTag>
    );
  }
  return status === 'success' ? (
    <NTag type="success" size="small" bordered={false}>
      {$t('page.aiRecommend.statusSuccess')}
    </NTag>
  ) : (
    <NTag type="error" size="small" bordered={false}>
      {$t('page.aiRecommend.statusFailed')}
    </NTag>
  );
}

/** 综合分配色：≥70 红 / ≥40 黄 / 其余绿 */
function scoreColor(score: number) {
  if (score >= 70) return '#f5222d';
  if (score >= 40) return '#faad14';
  return '#52c41a';
}

function fmtPrice(val: number | null | undefined) {
  return val === null || val === undefined ? '-' : Number(val).toFixed(2);
}

function fmtTime(t: string | null | undefined) {
  return t ? dayjs(t).format('YYYY-MM-DD HH:mm') : '-';
}

/** 六维度依据（key 静态枚举，保证 I18nKey 类型收窄；有的维度才显示） */
const REASON_DIMS = [
  { key: 'news', labelKey: 'page.aiRecommend.reasonNews' },
  { key: 'sentiment', labelKey: 'page.aiRecommend.reasonSentiment' },
  { key: 'factor', labelKey: 'page.aiRecommend.reasonFactor' },
  { key: 'sector_fund', labelKey: 'page.aiRecommend.reasonSectorFund' },
  { key: 'main_force', labelKey: 'page.aiRecommend.reasonMainForce' },
  { key: 'limit_up', labelKey: 'page.aiRecommend.reasonLimitUp' }
] as const;

function historySummary(row: Api.Recommend.RecommendRunItem) {
  if (!row.parsed_result) return '-';
  const parsed = row.parsed_result as Record<string, unknown>;
  return String(parsed.summary ?? '-');
}

// ==================== 推荐股表格 ====================
function rankTagType(rank: number): 'error' | 'warning' | 'info' {
  if (rank === 1) return 'error';
  if (rank === 2) return 'warning';
  return 'info';
}

const stockColumns = computed<DataTableColumns<Api.Recommend.RecommendStock>>(() => [
  {
    key: 'rank',
    title: $t('page.aiRecommend.rankCol'),
    width: 56,
    align: 'center',
    render: row => {
      if (row.rank <= 3) {
        return (
          <NTag size="tiny" bordered={false} type={rankTagType(row.rank)}>
            {row.rank}
          </NTag>
        );
      }
      return <NText depth={3}>{row.rank}</NText>;
    }
  },
  {
    key: 'stock_name',
    title: $t('page.aiRecommend.stockCol'),
    width: 160,
    render: row => (
      <div class="flex items-center gap-8px">
        <span class="font-500">{row.stock_name}</span>
        <NText depth={3} style={{ fontSize: '12px', fontFamily: 'monospace' }}>
          {row.stock_code}
        </NText>
      </div>
    )
  },
  {
    key: 'direction',
    title: $t('page.aiRecommend.directionCol'),
    width: 92,
    align: 'center',
    render: row => (
      <NTag size="small" bordered={false} type={row.direction === 'limit_up' ? 'error' : 'success'}>
        {row.direction === 'limit_up'
          ? $t('page.aiRecommend.directionLimitUp')
          : $t('page.aiRecommend.directionBottomFish')}
      </NTag>
    )
  },
  {
    key: 'score',
    title: $t('page.aiRecommend.scoreCol'),
    width: 110,
    align: 'center',
    render: row => (
      <div class="flex-y-center gap-6px">
        <NProgress
          type="line"
          percentage={row.score}
          color={scoreColor(row.score)}
          show-indicator={false}
          style="width: 48px"
        />
        <span style={{ color: scoreColor(row.score), fontWeight: '600' }}>{row.score}</span>
      </div>
    )
  },
  {
    key: 'buy_price',
    title: $t('page.aiRecommend.buyPriceCol'),
    width: 90,
    align: 'right',
    render: row => <span style={{ fontWeight: '500' }}>{fmtPrice(row.buy_price)}</span>
  },
  {
    key: 'target_price',
    title: $t('page.aiRecommend.targetPriceCol'),
    width: 90,
    align: 'right',
    render: row => <span style={{ color: '#faad14' }}>{fmtPrice(row.target_price)}</span>
  },
  {
    key: 'stop_loss_price',
    title: $t('page.aiRecommend.stopLossCol'),
    width: 90,
    align: 'right',
    render: row => <span style={{ color: '#52c41a' }}>{fmtPrice(row.stop_loss_price)}</span>
  },
  {
    key: 'entry_type',
    title: $t('page.aiRecommend.entryCol'),
    width: 96,
    align: 'center',
    render: row => (
      <NTag size="small" bordered={false} type={row.entry_type === 'market' ? 'info' : 'warning'}>
        {row.entry_type === 'market' ? $t('page.aiRecommend.entryMarket') : $t('page.aiRecommend.entryLimit')}
      </NTag>
    )
  },
  {
    key: 'reasons',
    title: $t('page.aiRecommend.reasonCol'),
    minWidth: 170,
    render: row => {
      const dims = REASON_DIMS.filter(d => row.reasons?.[d.key]);
      if (!dims.length) return <NText depth={3}>-</NText>;
      return (
        <NSpace size={4} wrap>
          {dims.map(d => (
            <NTooltip>
              {{
                trigger: () => (
                  <NTag size="tiny" bordered={false}>
                    {$t(d.labelKey)}
                  </NTag>
                ),
                default: () => <span class="text-12px">{row.reasons?.[d.key]}</span>
              }}
            </NTooltip>
          ))}
        </NSpace>
      );
    }
  },
  {
    key: 'summary',
    title: $t('page.aiRecommend.aiReasonCol'),
    minWidth: 220,
    ellipsis: { tooltip: true },
    render: row => <span class="text-12px">{row.summary || '-'}</span>
  }
]);

// ==================== 历史列表 ====================
const historyColumns = computed<DataTableColumns<Api.Recommend.RecommendRunItem>>(() => [
  {
    key: 'run_date',
    title: $t('page.aiRecommend.runDateCol'),
    width: 110,
    render: row => <span class="text-12px">{row.run_date}</span>
  },
  {
    key: 'created_at',
    title: $t('page.aiRecommend.execTime'),
    width: 150,
    render: row => <span class="text-12px">{fmtTime(row.created_at)}</span>
  },
  {
    key: 'status',
    title: $t('page.aiRecommend.statusCol'),
    width: 80,
    render: row => statusTag(row.status)
  },
  {
    key: 'summary',
    title: $t('page.aiRecommend.summaryCol'),
    minWidth: 180,
    ellipsis: { tooltip: true },
    render: row => <span class="text-12px">{historySummary(row)}</span>
  },
  {
    key: 'actions',
    title: $t('common.action'),
    width: 70,
    align: 'center',
    render: row => (
      <NButton size="tiny" tertiary onClick={() => viewHistoryRow(row)}>
        {$t('page.aiRecommend.viewBtn')}
      </NButton>
    )
  }
]);

loadLatest();
onBeforeUnmount(stopPoll);
</script>

<template>
  <div class="min-h-500px flex-col-stretch gap-16px overflow-hidden lt-sm:overflow-auto">
    <NCard
      :bordered="false"
      size="small"
      class="min-h-0 flex flex-col flex-1 card-wrapper"
      content-style="flex: 1 1 0%; overflow-y: auto;"
    >
      <template #header>
        <div class="flex-y-center gap-8px">
          <span class="text-16px font-500">{{ $t('page.aiRecommend.title') }}</span>
          <NTag v-if="current" size="small" :bordered="false">
            {{ current.run_date }}
          </NTag>
          <component :is="statusTag(current.status)" v-if="current" />
        </div>
      </template>
      <template #header-extra>
        <NSpace align="center" :size="8" wrap>
          <NText v-if="current" depth="3" class="text-12px">
            {{ $t('page.aiRecommend.execTime') }}: {{ fmtTime(current.created_at) }}
          </NText>
          <NTooltip :disabled="strategyId !== null">
            <template #trigger>
              <span class="inline-flex gap-8px">
                <NButton size="small" tertiary :disabled="strategyId === null" @click="goBacktest">
                  <template #icon><icon-mdi-chart-line class="text-icon" /></template>
                  {{ $t('page.aiRecommend.backtestBtn') }}
                </NButton>
                <NButton size="small" tertiary :disabled="strategyId === null" @click="goPositions">
                  <template #icon><icon-mdi-briefcase-outline class="text-icon" /></template>
                  {{ $t('page.aiRecommend.positionsBtn') }}
                </NButton>
              </span>
            </template>
            {{ $t('page.aiRecommend.strategyMissing') }}
          </NTooltip>
          <NButton v-if="viewingHistoryId !== null" size="small" tertiary @click="backToLatest">
            {{ $t('page.aiRecommend.backToLatest') }}
          </NButton>
          <NButton size="small" tertiary @click="openHistory">
            <template #icon><icon-mdi-history class="text-icon" /></template>
            {{ $t('page.aiRecommend.historyBtn') }}
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
            {{ current?.status === 'running' ? $t('page.aiRecommend.statusRunning') : $t('page.aiRecommend.generate') }}
          </NButton>
        </NSpace>
      </template>

      <!-- 生成中 -->
      <div v-if="current?.status === 'running'" class="flex-col items-center gap-12px py-48px">
        <icon-mdi-robot-excited class="text-48px" style="color: var(--primary-color)" />
        <NText depth="3">{{ $t('page.aiRecommend.generatingTip') }}</NText>
      </div>

      <!-- 失败 -->
      <div v-else-if="current?.status === 'failed'" class="py-24px">
        <NEmpty :description="$t('page.aiRecommend.failedTip')">
          <template #icon><icon-mdi-alert-circle-outline class="text-48px" style="color: #e0a240" /></template>
          <template #extra>
            <NText v-if="current.error_msg" type="error" class="text-12px">{{ current.error_msg }}</NText>
          </template>
        </NEmpty>
      </div>

      <!-- 成功推荐 -->
      <template v-else-if="current?.status === 'success'">
        <NText class="mb-8px block text-14px font-500">{{ $t('page.aiRecommend.tableTitle') }}</NText>
        <NDataTable
          :columns="stockColumns"
          :data="current.stocks ?? []"
          size="small"
          :scroll-x="1350"
          :row-key="(row: Api.Recommend.RecommendStock) => row.id"
        />

        <!-- AI 综合研判 -->
        <template v-if="current.ai_raw_response">
          <NText class="mb-8px mt-16px block text-14px font-500">{{ $t('page.aiRecommend.reportTitle') }}</NText>
          <AnalysisMarkdown :raw="current.ai_raw_response" />
        </template>
      </template>

      <!-- 无记录 -->
      <NEmpty v-else class="py-48px" :description="$t('page.aiRecommend.emptyTip')" />

      <!-- 历史推荐抽屉 -->
      <NDrawer v-model:show="historyVisible" :width="640">
        <NDrawerContent :title="$t('page.aiRecommend.historyTitle')" closable :native-scrollbar="false">
          <NDataTable
            :columns="historyColumns"
            :data="historyList"
            size="small"
            :loading="historyLoading"
            :row-key="(row: Api.Recommend.RecommendRunItem) => row.id"
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
  </div>
</template>

<style scoped></style>
