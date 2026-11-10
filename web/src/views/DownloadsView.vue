<script setup lang="ts">import {RouterLink} from 'vue-router';import DownloadIcon from '~icons/lucide/download';</script>
<template><section class="downloads-view"><h1 class="page-title">下载任务</h1><div class="download-empty"><DownloadIcon/><h2>还没有下载任务</h2><p>下载任务将在下一阶段接入新 Core。</p><RouterLink to="/search">去搜索音乐</RouterLink></div></section></template>
<style scoped>
.downloads-view {
  min-width: 0;
}
h1 {
  font-size: 26px;
  font-weight: 500;
  margin: 0 0 10px;
}
.download-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 46vh;
  gap: 12px;
  text-align: center;
}
.download-empty svg {
  width: 48px;
  height: 48px;
  color: var(--app-accent);
  stroke-width: 1.5;
}
.download-empty h2 {
  font-size: 16px;
  font-weight: 500;
  margin: 12px 0 0;
}
.download-empty p {
  font-size: 12px;
  color: var(--app-text-muted);
  line-height: 1.8;
}
.download-empty a {
  padding: 10px 20px;
  color: var(--app-link);
  border: 1px solid var(--app-border);
  border-radius: 8px;
  font-size: 12px;
  text-decoration: none;
}
.download-empty a:hover {
  background: var(--app-hover);
}
article {
  overflow-wrap: anywhere;
}
</style>
