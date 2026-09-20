<script setup lang="ts">
import { ref } from 'vue';
import { NTabPane, NTabs } from 'naive-ui';
import { $t } from '@/locales';
import TodayMarket from './modules/today-market.vue';
import HistoryMarket from './modules/history-market.vue';

defineOptions({
  name: 'MarketOverview'
});

const activeTab = ref('today');
</script>

<template>
  <div class="flex-col-stretch gap-16px">
    <NTabs v-model:value="activeTab" type="line" animated>
      <NTabPane name="today" :tab="$t('page.aStock.marketOverview.todayMarket')">
        <TodayMarket v-if="activeTab === 'today'" />
      </NTabPane>
      <NTabPane name="history" :tab="$t('page.aStock.marketOverview.historyMarket')">
        <HistoryMarket v-if="activeTab === 'history'" />
      </NTabPane>
    </NTabs>
  </div>
</template>
