<script setup lang="tsx">
/**
 * 轮动策略分析页（双轨制）
 * - 左：规则计算的轮动指标（近期轮动 / 明日候选 / 板块内高低切换，读时计算透明可回验）
 * - 右：AI 轮动策略报告（rotation 类型，复用 analysis 异步生成基建；AI 只推演到板块层）
 */
import { computed, onMounted, ref } from 'vue';
import {
  NButton,
  NCard,
  NDataTable,
  NEmpty,
  NRadioButton,
  NRadioGroup,
  NSpace,
  NTabPane,
  NTabs,
  NTag,
  NText
} from 'naive-ui';
import type { DataTableColumns } from 'naive-ui';
import { useMessage } from 'naive-ui';
import dayjs from 'dayjs';
import {
  fetchBackfillRotationHistory,
  fetchGetRotationOverview,
  fetchGetRotationSwitch,
  fetchSyncRotationStocks
} from '@/service/api';
import { useAuth } from '@/hooks/business/auth';
import { $t } from '@/locales';
import { fmtAmountCn } from '../utils';
import AnalysisReportPanel from '../components/analysis-report-panel.vue';

defineOptions({ name: 'AiRotationAnalysis' });

const UP = '#f5222d';
const DOWN = '#52c41a';
const FLAT = '#8c8c8c';

/** 明日候选表展示条数 */
const TOP_N = 20;

const { hasAuth } = useAuth();
const canSync = hasAuth('stock:board:sync');
const message = useMessage();

const boardType = ref<Api.StockRotation.BoardType>('industry');
const overview = ref<Api.StockRotation.RotationOverviewResponse | null>(null);
const switchData = ref<Api.StockRotation.RotationSwitchResponse | null>(null);
const loading = ref(false);
const syncing = ref(false);
const backfilling = ref(false);
/** 当前页签：overview-近期轮动 / tomorrow-明日候选 / switch-高低切换 */
const activeTab = ref('overview');

function pctColor(val: number | null | undefined) {
  if (val === null || val === undefined) return FLAT;
  return val > 0 ? UP : val < 0 ? DOWN : FLAT;
}

function fmtPct(val: number | null | undefined) {
  if (val === null || val === undefined) return '-';
  return `${val > 0 ? '+' : ''}${val.toFixed(2)}%`;
}

/** 轮动阶段标签（key 静态枚举，保证 I18nKey 类型收窄） */
const STAGE_LABEL_KEYS = {
  start: 'page.aiAnalysis.rotation.stage_start',
  ferment: 'page.aiAnalysis.rotation.stage_ferment',
  climax: 'page.aiAnalysis.rotation.stage_climax',
  ebb: 'page.aiAnalysis.rotation.stage_ebb',
  observe: 'page.aiAnalysis.rotation.stage_observe'
} as const;

function stageLabel(stage: string) {
  const key = STAGE_LABEL_KEYS[stage as keyof typeof STAGE_LABEL_KEYS];
  return key ? $t(key) : stage;
}

function stageTagType(stage: string): 'info' | 'warning' | 'error' | 'success' | 'default' {
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

/** 操作建议标签 */
const ACTION_LABEL_KEYS = {
  attack: 'page.aiAnalysis.rotation.action_attack',
  ambush: 'page.aiAnalysis.rotation.action_ambush',
  avoid: 'page.aiAnalysis.rotation.action_avoid',
  watch: 'page.aiAnalysis.rotation.action_watch'
} as const;

function actionLabel(action: string) {
  const key = ACTION_LABEL_KEYS[action as keyof typeof ACTION_LABEL_KEYS];
  return key ? $t(key) : action;
}

function actionTagType(action: string): 'error' | 'warning' | 'success' | 'default' {
  switch (action) {
    case 'attack':
      return 'error';
    case 'ambush':
      return 'warning';
    case 'avoid':
      return 'success';
    default:
      return 'default';
  }
}

/** 高低切换信号标签 */
const SIGNAL_LABEL_KEYS = {
  switching: 'page.aiAnalysis.rotation.signal_switching',
  split: 'page.aiAnalysis.rotation.signal_split',
  resonance: 'page.aiAnalysis.rotation.signal_resonance',
  unknown: 'page.aiAnalysis.rotation.signal_unknown'
} as const;

function signalLabel(signal: string) {
  const key = SIGNAL_LABEL_KEYS[signal as keyof typeof SIGNAL_LABEL_KEYS];
  return key ? $t(key) : signal;
}

function signalTagType(signal: string): 'error' | 'warning' | 'info' | 'default' {
  switch (signal) {
    case 'switching':
      return 'error';
    case 'split':
      return 'warning';
    case 'resonance':
      return 'info';
    default:
      return 'default';
  }
}

/** 主题热度状态标签（key 静态枚举，保证 I18nKey 类型收窄） */
const THEME_STATUS_LABEL_KEYS = {
  gathering: 'page.aiAnalysis.rotation.themeStatus_gathering',
  active: 'page.aiAnalysis.rotation.themeStatus_active',
  hot: 'page.aiAnalysis.rotation.themeStatus_hot',
  cooling: 'page.aiAnalysis.rotation.themeStatus_cooling',
  flat: 'page.aiAnalysis.rotation.themeStatus_flat'
} as const;

function themeStatusLabel(status: string) {
  const key = THEME_STATUS_LABEL_KEYS[status as keyof typeof THEME_STATUS_LABEL_KEYS];
  return key ? $t(key) : status;
}

function themeStatusTagType(status: string): 'info' | 'warning' | 'error' | 'success' | 'default' {
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

async function loadData() {
  loading.value = true;
  try {
    const [overviewRes, switchRes] = await Promise.all([
      fetchGetRotationOverview(boardType.value),
      fetchGetRotationSwitch(boardType.value)
    ]);
    if (!overviewRes.error) overview.value = overviewRes.data ?? null;
    if (!switchRes.error) switchData.value = switchRes.data ?? null;
  } finally {
    loading.value = false;
  }
}

function onBoardTypeChange() {
  selectedTheme.value = '';
  loadData();
}

/** 手动同步当日活跃板块（行业全量 + 概念涨幅前30）成分股快照 */
async function onSyncStocks() {
  syncing.value = true;
  try {
    const { data, error } = await fetchSyncRotationStocks();
    if (!error) {
      message.success(
        $t('page.aiAnalysis.rotation.syncSuccessTip', {
          boards: data?.saved_boards ?? 0,
          stocks: data?.stocks ?? 0
        })
      );
      await loadData();
    }
  } finally {
    syncing.value = false;
  }
}

/** 提交板块历史日K回填（行业+概念合并为一个后台任务，立即返回） */
async function onBackfill() {
  backfilling.value = true;
  try {
    const result = await fetchBackfillRotationHistory('all');
    if (!result.error) {
      message.info($t('page.aiAnalysis.rotation.backfillTip'));
    }
  } finally {
    backfilling.value = false;
  }
}

const snapshotDate = computed(() => {
  const d = activeTab.value === 'switch' ? switchData.value?.snapshot_date : overview.value?.snapshot_date;
  return d ? dayjs(d).format('YYYY-MM-DD') : '';
});

const overviewItems = computed(() => overview.value?.items ?? []);
const themes = computed(() => overview.value?.themes ?? []);
/** 主题热度条点击筛选：空串=全部板块 */
const selectedTheme = ref('');

function toggleTheme(theme: string) {
  selectedTheme.value = selectedTheme.value === theme ? '' : theme;
}

/** 近期轮动页签：按今日涨幅降序（复盘视角），选中主题时过滤 */
const recentItems = computed(() => {
  let arr = [...overviewItems.value].sort((a, b) => (b.change_pct ?? -999) - (a.change_pct ?? -999));
  if (selectedTheme.value) arr = arr.filter(x => x.theme === selectedTheme.value);
  return arr;
});
/** 明日候选页签：接口已按评分降序，取前 TOP_N（选中主题时过滤后再取） */
const tomorrowItems = computed(() => {
  let arr = overviewItems.value;
  if (selectedTheme.value) arr = arr.filter(x => x.theme === selectedTheme.value);
  return arr.slice(0, TOP_N);
});

const overviewColumns = computed<DataTableColumns<Api.StockRotation.RotationOverviewItem>>(() => [
  {
    key: 'board_name',
    title: $t('page.aiAnalysis.rotation.boardCol'),
    width: 130,
    fixed: 'left',
    render: row => <span class="font-500">{row.board_name}</span>
  },
  {
    key: 'theme',
    title: $t('page.aiAnalysis.rotation.themeCol'),
    width: 82,
    align: 'center',
    render: row =>
      row.theme ? <NTag size="small" bordered={false}>{row.theme}</NTag> : <NText depth={3}>-</NText>
  },
  {
    key: 'change_pct',
    title: $t('page.aiAnalysis.rotation.changePctCol'),
    width: 84,
    align: 'right',
    render: row => (
      <span style={{ color: pctColor(row.change_pct), fontWeight: '500' }}>{fmtPct(row.change_pct)}</span>
    )
  },
  {
    key: 'gain_3d',
    title: $t('page.aiAnalysis.rotation.gain3dCol'),
    width: 84,
    align: 'right',
    render: row => <span style={{ color: pctColor(row.gain_3d) }}>{fmtPct(row.gain_3d)}</span>
  },
  {
    key: 'gain_5d',
    title: $t('page.aiAnalysis.rotation.gain5dCol'),
    width: 84,
    align: 'right',
    render: row => <span style={{ color: pctColor(row.gain_5d) }}>{fmtPct(row.gain_5d)}</span>
  },
  {
    key: 'gain_10d',
    title: $t('page.aiAnalysis.rotation.gain10dCol'),
    width: 84,
    align: 'right',
    render: row => <span style={{ color: pctColor(row.gain_10d) }}>{fmtPct(row.gain_10d)}</span>
  },
  {
    key: 'position_pct',
    title: $t('page.aiAnalysis.rotation.positionCol'),
    width: 68,
    align: 'center',
    render: row => {
      const v = row.position_pct;
      if (v === null || v === undefined) return <NText depth={3}>-</NText>;
      const color = v <= 0.3 ? '#1890ff' : v >= 0.85 ? UP : FLAT;
      return <span style={{ color }}>{`${Math.round(v * 100)}%`}</span>;
    }
  },
  {
    key: 'rank_change',
    title: $t('page.aiAnalysis.rotation.rankChangeCol'),
    width: 90,
    align: 'center',
    render: row => {
      const v = row.rank_change;
      if (v === null || v === undefined) return <NText depth={3}>-</NText>;
      if (v > 0) return <span style={{ color: UP }}>↑{v}</span>;
      if (v < 0) return <span style={{ color: DOWN }}>↓{-v}</span>;
      return <NText depth={3}>0</NText>;
    }
  },
  {
    key: 'volume_ratio',
    title: $t('page.aiAnalysis.rotation.volumeRatioCol'),
    width: 76,
    align: 'right',
    render: row => (row.volume_ratio === null ? <NText depth={3}>-</NText> : row.volume_ratio.toFixed(2))
  },
  {
    key: 'inflow_days',
    title: $t('page.aiAnalysis.rotation.inflowDaysCol'),
    width: 76,
    align: 'center',
    render: row =>
      row.inflow_days !== null && row.inflow_days >= 3 ? (
        <span style={{ color: UP, fontWeight: '500' }}>{row.inflow_days}天</span>
      ) : (
        <NText depth={3}>{row.inflow_days ?? '-'}天</NText>
      )
  },
  {
    key: 'limit_up',
    title: $t('page.aiAnalysis.rotation.limitUpCol'),
    width: 100,
    align: 'center',
    render: row => (
      <span class="text-12px">
        {row.limit_up_count && row.limit_up_count > 0 ? (
          <span>
            <span style={{ color: UP }}>{row.limit_up_count}家</span>
            {row.max_consecutive && row.max_consecutive > 1 ? (
              <span style={{ color: UP, fontWeight: '500' }}>/{row.max_consecutive}板</span>
            ) : null}
          </span>
        ) : (
          <NText depth={3}>-</NText>
        )}
      </span>
    )
  },
  {
    key: 'stage',
    title: $t('page.aiAnalysis.rotation.stageCol'),
    width: 88,
    align: 'center',
    render: row => (
      <NTag size="small" bordered={false} type={stageTagType(row.stage)}>
        {stageLabel(row.stage)}
      </NTag>
    )
  },
  {
    key: 'tomorrow_score',
    title: $t('page.aiAnalysis.rotation.scoreCol'),
    width: 76,
    align: 'center',
    sorter: (a, b) => a.tomorrow_score - b.tomorrow_score,
    render: row => {
      const score = row.tomorrow_score;
      const color = score >= 68 ? UP : score >= 55 ? '#faad14' : FLAT;
      return (
        <span style={{ color, fontWeight: '600' }}>{score}</span>
      );
    }
  },
  {
    key: 'action',
    title: $t('page.aiAnalysis.rotation.actionCol'),
    width: 80,
    align: 'center',
    render: row => (
      <NTag size="small" bordered={false} type={actionTagType(row.action)}>
        {actionLabel(row.action)}
      </NTag>
    )
  }
]);

const tomorrowColumns = computed<DataTableColumns<Api.StockRotation.RotationOverviewItem>>(() => [
  {
    key: 'rank',
    title: $t('page.aiAnalysis.rotation.rankCol'),
    width: 56,
    align: 'center',
    render: row => {
      const rank = tomorrowItems.value.indexOf(row) + 1;
      if (rank <= 3) {
        return (
          <NTag size="tiny" bordered={false} type={rank === 1 ? 'error' : rank === 2 ? 'warning' : 'info'}>
            {rank}
          </NTag>
        );
      }
      return <NText depth={3}>{rank}</NText>;
    }
  },
  {
    key: 'board_name',
    title: $t('page.aiAnalysis.rotation.boardCol'),
    width: 140,
    render: row => <span class="font-500">{row.board_name}</span>
  },
  {
    key: 'theme',
    title: $t('page.aiAnalysis.rotation.themeCol'),
    width: 82,
    align: 'center',
    render: row =>
      row.theme ? <NTag size="small" bordered={false}>{row.theme}</NTag> : <NText depth={3}>-</NText>
  },
  {
    key: 'action',
    title: $t('page.aiAnalysis.rotation.actionCol'),
    width: 88,
    align: 'center',
    render: row => (
      <NTag size="small" bordered={false} type={actionTagType(row.action)}>
        {actionLabel(row.action)}
      </NTag>
    )
  },
  {
    key: 'tomorrow_score',
    title: $t('page.aiAnalysis.rotation.scoreCol'),
    width: 90,
    align: 'center',
    sorter: (a, b) => a.tomorrow_score - b.tomorrow_score,
    render: row => {
      const score = row.tomorrow_score;
      const color = score >= 68 ? UP : score >= 55 ? '#faad14' : FLAT;
      return <span style={{ color, fontWeight: '600' }}>{score}</span>;
    }
  },
  {
    key: 'stage',
    title: $t('page.aiAnalysis.rotation.stageCol'),
    width: 96,
    align: 'center',
    render: row => (
      <NTag size="small" bordered={false} type={stageTagType(row.stage)}>
        {stageLabel(row.stage)}
      </NTag>
    )
  },
  {
    key: 'change_pct',
    title: $t('page.aiAnalysis.rotation.changePctCol'),
    width: 84,
    align: 'right',
    render: row => (
      <span style={{ color: pctColor(row.change_pct), fontWeight: '500' }}>{fmtPct(row.change_pct)}</span>
    )
  },
  {
    key: 'gain_10d',
    title: $t('page.aiAnalysis.rotation.gain10dCol'),
    width: 84,
    align: 'right',
    render: row => <span style={{ color: pctColor(row.gain_10d) }}>{fmtPct(row.gain_10d)}</span>
  },
  {
    key: 'rank_change',
    title: $t('page.aiAnalysis.rotation.rankChangeCol'),
    width: 90,
    align: 'center',
    render: row => {
      const v = row.rank_change;
      if (v === null || v === undefined) return <NText depth={3}>-</NText>;
      if (v > 0) return <span style={{ color: UP }}>↑{v}</span>;
      if (v < 0) return <span style={{ color: DOWN }}>↓{-v}</span>;
      return <NText depth={3}>0</NText>;
    }
  },
  {
    key: 'inflow_days',
    title: $t('page.aiAnalysis.rotation.inflowDaysCol'),
    width: 90,
    align: 'center',
    render: row =>
      row.inflow_days !== null && row.inflow_days >= 3 ? (
        <span style={{ color: UP, fontWeight: '500' }}>{row.inflow_days}天</span>
      ) : (
        <NText depth={3}>{row.inflow_days ?? '-'}天</NText>
      )
  },
  {
    key: 'limit_up',
    title: $t('page.aiAnalysis.rotation.limitUpCol'),
    width: 100,
    align: 'center',
    render: row => (
      <span class="text-12px">
        {row.limit_up_count && row.limit_up_count > 0 ? (
          <span>
            <span style={{ color: UP }}>{row.limit_up_count}家</span>
            {row.max_consecutive && row.max_consecutive > 1 ? (
              <span style={{ color: UP, fontWeight: '500' }}>/{row.max_consecutive}板</span>
            ) : null}
          </span>
        ) : (
          <NText depth={3}>-</NText>
        )}
      </span>
    )
  }
]);

/** 高低切换：个股明细子表（高位滞涨 / 低位启动共用列定义） */
function stockMiniColumns(): DataTableColumns<Api.StockRotation.RotationSwitchStockItem> {
  return [
    { key: 'stock_code', title: $t('page.aiAnalysis.rotation.codeCol'), width: 80 },
    {
      key: 'stock_name',
      title: $t('page.aiAnalysis.rotation.nameCol'),
      width: 100,
      render: row => <span class="font-500">{row.stock_name}</span>
    },
    {
      key: 'change_pct',
      title: $t('page.aiAnalysis.rotation.changePctCol'),
      width: 84,
      align: 'right',
      render: row => <span style={{ color: pctColor(row.change_pct) }}>{fmtPct(row.change_pct)}</span>
    },
    {
      key: 'price',
      title: $t('page.aiAnalysis.rotation.priceCol'),
      width: 76,
      align: 'right',
      render: row => (row.price === null ? <NText depth={3}>-</NText> : row.price.toFixed(2))
    },
    {
      key: 'amount',
      title: $t('page.aiAnalysis.rotation.amountCol'),
      width: 90,
      align: 'right',
      render: row => <span>{fmtAmountCn(row.amount)}</span>
    },
    {
      key: 'position_gain',
      title: $t('page.aiAnalysis.rotation.positionGainCol'),
      width: 96,
      align: 'right',
      render: row => <span style={{ color: pctColor(row.position_gain) }}>{fmtPct(row.position_gain)}</span>
    }
  ];
}

const switchColumns = computed<DataTableColumns<Api.StockRotation.RotationSwitchItem>>(() => [
  {
    type: 'expand',
    renderExpand: row => {
      const empty = !row.high_laggards?.length && !row.low_starters?.length;
      return (
        <div class="flex flex-col gap-8px py-4px">
          {empty ? <NEmpty size="small" description={$t('page.aiAnalysis.rotation.expandEmpty')} /> : null}
          {row.high_laggards?.length ? (
            <div>
              <NText type="error" class="mb-2px block text-12px font-500">
                {$t('page.aiAnalysis.rotation.highLaggardsLabel')}
              </NText>
              <NDataTable
                columns={stockMiniColumns()}
                data={row.high_laggards}
                size="small"
                bordered={false}
                row-key={(s: Api.StockRotation.RotationSwitchStockItem) => s.stock_code}
              />
            </div>
          ) : null}
          {row.low_starters?.length ? (
            <div>
              <NText type="info" class="mb-2px block text-12px font-500">
                {$t('page.aiAnalysis.rotation.lowStartersLabel')}
              </NText>
              <NDataTable
                columns={stockMiniColumns()}
                data={row.low_starters}
                size="small"
                bordered={false}
                row-key={(s: Api.StockRotation.RotationSwitchStockItem) => s.stock_code}
              />
            </div>
          ) : null}
        </div>
      );
    }
  },
  {
    key: 'board_name',
    title: $t('page.aiAnalysis.rotation.boardCol'),
    width: 140,
    render: row => <span class="font-500">{row.board_name}</span>
  },
  {
    key: 'change_pct',
    title: $t('page.aiAnalysis.rotation.changePctCol'),
    width: 90,
    align: 'right',
    render: row => (
      <span style={{ color: pctColor(row.change_pct), fontWeight: '500' }}>{fmtPct(row.change_pct)}</span>
    )
  },
  {
    key: 'signal',
    title: $t('page.aiAnalysis.rotation.signalCol'),
    width: 110,
    align: 'center',
    render: row => (
      <NTag size="small" bordered={false} type={signalTagType(row.signal)}>
        {signalLabel(row.signal)}
      </NTag>
    )
  },
  {
    key: 'high_avg_pct',
    title: $t('page.aiAnalysis.rotation.highAvgCol'),
    width: 96,
    align: 'right',
    render: row => <span style={{ color: pctColor(row.high_avg_pct) }}>{fmtPct(row.high_avg_pct)}</span>
  },
  {
    key: 'low_avg_pct',
    title: $t('page.aiAnalysis.rotation.lowAvgCol'),
    width: 96,
    align: 'right',
    render: row => <span style={{ color: pctColor(row.low_avg_pct) }}>{fmtPct(row.low_avg_pct)}</span>
  },
  {
    key: 'position_key',
    title: $t('page.aiAnalysis.rotation.positionKeyCol'),
    width: 90,
    align: 'center',
    render: row => <NText depth={3} class="text-12px">{row.position_key}</NText>
  }
]);

onMounted(() => {
  loadData();
});
</script>

<template>
  <div class="min-h-500px h-full flex gap-16px overflow-hidden lt-sm:flex-col lt-sm:overflow-auto">
    <!-- 左：规则计算的轮动指标（内容区独立滚动，头部固定） -->
    <NCard
      :bordered="false"
      size="small"
      class="card-wrapper h-full w-1/2 flex-shrink-0 flex flex-col lt-sm:h-auto lt-sm:w-full"
      content-style="flex: 1 1 0%; overflow-y: auto;"
    >
      <template #header>
        <div class="flex-y-center gap-8px">
          <span class="text-16px font-500">{{ $t('page.aiAnalysis.rotation.boardTitle') }}</span>
          <NText depth="3" class="text-12px">{{ snapshotDate }}</NText>
          <NText v-if="overview" depth="3" class="text-12px">
            {{ $t('page.aiAnalysis.rotation.historyDaysTip', { n: overview.history_days }) }}
          </NText>
        </div>
      </template>
      <template #header-extra>
        <NSpace align="center" :size="12" wrap>
          <NRadioGroup v-model:value="boardType" size="small" @update:value="onBoardTypeChange">
            <NRadioButton value="industry">{{ $t('page.aiAnalysis.sector.industryTab') }}</NRadioButton>
            <NRadioButton value="concept">{{ $t('page.aiAnalysis.sector.conceptTab') }}</NRadioButton>
          </NRadioGroup>
          <NButton v-if="canSync" size="small" tertiary :loading="syncing" @click="onSyncStocks">
            <template #icon><icon-mdi-cloud-download class="text-icon" /></template>
            {{ $t('page.aiAnalysis.rotation.syncStocksBtn') }}
          </NButton>
          <NButton v-if="canSync" size="small" tertiary :loading="backfilling" @click="onBackfill">
            <template #icon><icon-mdi-history class="text-icon" /></template>
            {{ $t('page.aiAnalysis.rotation.backfillBtn') }}
          </NButton>
        </NSpace>
      </template>

      <!-- 主题热度条：跨行业+概念聚合，点击筛选近期轮动/明日候选两表；集结升温=埋伏窗口 -->
      <div v-if="themes.length" class="mb-6px flex-y-center flex-wrap gap-6px">
        <NText depth="3" class="text-12px flex-shrink-0">
          {{ $t('page.aiAnalysis.rotation.themeHeatTitle') }}
        </NText>
        <NTag
          v-for="t in themes"
          :key="t.theme"
          size="small"
          round
          checkable
          :checked="selectedTheme === t.theme"
          :type="themeStatusTagType(t.status)"
          @update:checked="() => toggleTheme(t.theme)"
        >
          <span class="font-500">{{ t.theme }}</span>
          <span class="ml-4px">{{ t.heat }}</span>
          <span class="ml-4px text-11px opacity-75">{{ themeStatusLabel(t.status) }}</span>
        </NTag>
      </div>

      <NTabs v-model:value="activeTab" type="line" size="small">
        <NTabPane name="overview" :tab="$t('page.aiAnalysis.rotation.tabOverview')">
          <NDataTable
            :columns="overviewColumns"
            :data="recentItems"
            size="small"
            :loading="loading"
            :scroll-x="1140"
            :row-key="(row: Api.StockRotation.RotationOverviewItem) => row.board_code"
            max-height="calc(100vh - 330px)"
          />
        </NTabPane>
        <NTabPane name="tomorrow" :tab="$t('page.aiAnalysis.rotation.tabTomorrow')">
          <NDataTable
            :columns="tomorrowColumns"
            :data="tomorrowItems"
            size="small"
            :loading="loading"
            :scroll-x="990"
            :row-key="(row: Api.StockRotation.RotationOverviewItem) => row.board_code"
            max-height="calc(100vh - 330px)"
          />
        </NTabPane>
        <NTabPane name="switch" :tab="$t('page.aiAnalysis.rotation.tabSwitch')">
          <NEmpty
            v-if="!loading && !(switchData?.items ?? []).length"
            size="small"
            :description="$t('page.aiAnalysis.rotation.switchEmpty')"
            class="py-48px"
          />
          <NDataTable
            v-else
            :columns="switchColumns"
            :data="switchData?.items ?? []"
            size="small"
            :loading="loading"
            :scroll-x="760"
            :row-key="(row: Api.StockRotation.RotationSwitchItem) => row.board_code"
          />
        </NTabPane>
      </NTabs>
    </NCard>

    <!-- 右：AI 轮动策略报告（仅收盘时段；内容区独立滚动，生成/历史/策略按钮固定可见） -->
    <AnalysisReportPanel
      analysis-type="rotation"
      session="close"
      class="min-w-0 flex-1 lt-sm:h-auto lt-sm:flex-none"
    />
  </div>
</template>

<style scoped></style>
