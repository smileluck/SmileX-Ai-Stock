<script setup lang="ts">
import { NButton, NCard } from 'naive-ui';

const FQGATE_DEMO_URL = 'https://fqgate.github.io/demo/';

function openInNewTab() {
  window.open(FQGATE_DEMO_URL, '_blank');
}
</script>

<template>
  <NCard size="small" class="h-full flex flex-col" content-class="min-h-0 flex-1">
    <template #header-extra>
      <NButton text type="primary" size="small" @click="openInNewTab">
        <template #icon>
          <icon-ic-round-open-in-new />
        </template>
        新标签打开
      </NButton>
    </template>
    <!--
      demo 页直连本机 FQGate 网关（fetch/WebSocket → http://127.0.0.1:17281）。
      嵌在 iframe 里时受 Chrome 私有网络访问（PNA/LNA）限制：公共站点→回环地址
      需服务端在预检响应里带 Access-Control-Allow-Private-Network（FQGate 未返回），
      iframe 场景还需权限策略委托（allow="local-network-access"）。
      若仍停留在「连接中」，点右上角新标签打开并允许「本地网络访问」权限。
    -->
    <iframe
      id="fqgateDemo"
      class="size-full"
      :src="FQGATE_DEMO_URL"
      allow="local-network-access"
    ></iframe>
  </NCard>
</template>

<style scoped></style>
