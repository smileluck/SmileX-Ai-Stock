<script setup lang="ts">
import { ref } from 'vue';
import { NTabPane, NTabs } from 'naive-ui';
import { $t } from '@/locales';
import FactorLibrary from './modules/factor-library.vue';
import FactorCalc from './modules/factor-calc.vue';
import FactorScreen from './modules/factor-screen.vue';

defineOptions({ name: 'AiFactor' });

const activeTab = ref<'library' | 'calc' | 'screen'>('library');
</script>

<template>
  <div class="min-h-500px flex-col-stretch overflow-hidden lt-sm:overflow-auto">
    <NTabs v-model:value="activeTab" type="line" animated size="large" class="factor-tabs h-full flex-col-stretch">
      <NTabPane name="library" :tab="$t('page.aiFactor.tabLibrary')" display-directive="show:lazy">
        <FactorLibrary />
      </NTabPane>
      <NTabPane name="calc" :tab="$t('page.aiFactor.tabCalc')" display-directive="show:lazy">
        <FactorCalc />
      </NTabPane>
      <NTabPane name="screen" :tab="$t('page.aiFactor.tabScreen')" display-directive="show:lazy">
        <FactorScreen />
      </NTabPane>
    </NTabs>
  </div>
</template>

<style scoped>
.factor-tabs :deep(.n-tabs-pane-wrapper) {
  flex: 1;
  overflow: hidden;
}
</style>
