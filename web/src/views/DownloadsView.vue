<script setup lang="ts">
import {computed,onMounted,ref} from 'vue';
import {useCoreClient} from '../composables/useCoreClient';
import DownloadItem from '../components/download/DownloadItem.vue';
import {queueKey} from '../utils/player-queue';
const {downloads}=useCoreClient();const tab=ref<'files'|'tasks'>('files');
const tasks=computed(()=>[...downloads.tasks.value].sort((a,b)=>b.createdAt-a.createdAt));
function taskFor(filename:string){return tasks.value.find(task=>task.status==='completed'&&task.filename===filename);}
onMounted(()=>{void downloads.refresh();});
</script>
<template><section class="downloads-view"><h1 class="page-title">本地和下载</h1>
 <div class="download-tabs" role="tablist" aria-label="下载分类"><button role="tab" :aria-selected="tab==='files'" @click="tab='files'">下载歌曲</button><button role="tab" :aria-selected="tab==='tasks'" @click="tab='tasks'">正在下载</button><button class="refresh-downloads" :disabled="downloads.loading.value" @click="downloads.refresh()">刷新</button></div>
 <p v-if="downloads.error.value" role="alert">{{downloads.error.value}}</p><p v-if="tab==='files'&&downloads.fileError.value" role="alert">{{downloads.fileError.value}}</p><p v-if="downloads.feedback.value" class="download-notice" role="status">{{downloads.feedback.value.text}}</p>
 <div class="download-columns" aria-hidden="true"><span>歌曲 / 歌手</span><span>大小</span><span>状态</span><span>操作</span></div>
 <template v-if="tab==='files'"><DownloadItem v-for="file in downloads.files.value" :key="file.filename" :file="file" :task="taskFor(file.filename)" :cover="taskFor(file.filename)?downloads.covers.value[queueKey(taskFor(file.filename)!.identity)]:null"/><p v-if="!downloads.files.value.length&&!downloads.loading.value&&!downloads.fileError.value" class="download-empty">还没有下载的歌曲</p><p class="download-location">文件保存在运行服务的电脑上；任务历史仅保留到服务重启。</p></template>
 <template v-else><DownloadItem v-for="task in tasks" :key="task.id" :task="task" :cover="downloads.covers.value[queueKey(task.identity)]" :pending="downloads.pending.value.has(task.id)" :retried="!!downloads.retried.value[task.id]" @cancel="downloads.operate(task,'cancel')" @retry="downloads.operate(task,'retry')"/><p v-if="!tasks.length&&!downloads.loading.value&&!downloads.error.value" class="download-empty">暂无下载任务</p></template>
</section></template>
<style scoped>
.downloads-view {
  min-width: 0;
}
.download-tabs{display:flex;gap:28px;align-items:center;margin:26px 0 18px;border-bottom:1px solid var(--app-border-soft)}.download-tabs button{border:0;border-bottom:2px solid transparent;background:transparent;color:var(--app-text-muted);padding:0 0 14px;font:inherit;font-size:14px;cursor:pointer}.download-tabs button[aria-selected=true]{border-bottom-color:var(--app-accent);color:var(--app-text)}.download-tabs .refresh-downloads{margin-left:auto;font-size:12px}.download-columns{display:grid;grid-template-columns:minmax(0,2fr) minmax(110px,.7fr) minmax(160px,1fr) 110px;gap:22px;padding:15px 8px;color:var(--app-text-muted);font-size:11px;border-bottom:1px solid var(--app-border-soft)}.download-notice,.download-location{font-size:12px;color:var(--app-text-muted);line-height:1.8}.download-location{margin-top:24px}.downloads-view .download-empty{min-height:40vh;color:var(--app-text-muted);font-size:13px}.download-feedback{font-size:11px;color:var(--app-text-muted)}
@media(max-width:1000px){.download-columns{grid-template-columns:minmax(0,1fr) 140px 90px;gap:16px}.download-columns span:nth-child(2){display:none}}
@media(max-width:600px){.download-columns{display:none}.download-tabs{gap:24px;margin-top:24px}.downloads-view h1{font-size:25px}}
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
