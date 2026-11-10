<script setup lang="ts">
import {computed,ref} from 'vue';
import type {DownloadTask,SavedDownloadFile} from '../../types/core';
import CoverArt from '../CoverArt.vue';
import {providerName} from '../../composables/useProviders';
import {formatDownloadBytes,downloadStatus,downloadPercent} from '../../utils/download-display';
const props=defineProps<{task?:DownloadTask;file?:SavedDownloadFile;cover?:string|null;pending?:boolean;retried?:boolean}>();
const emit=defineEmits<{cancel:[];retry:[]}>();
const percent=computed(()=>props.task?downloadPercent(props.task):null);
const copyNotice=ref('');
async function copy(){try{await navigator.clipboard.writeText(props.file?.filename??props.task?.filename??'');copyNotice.value='已复制';}catch{copyNotice.value='无法复制，请手动选择文件名';}}
</script>
<template><article class="download-row" :data-task-id="task?.id" :data-status="task?.status??'saved'" :data-filename="file?.filename">
 <div class="download-identity"><div class="download-cover"><CoverArt :src="cover"/></div><div class="download-title"><h3>{{task?.title||file?.filename||'未命名歌曲'}}</h3><p>{{task?.artist||'本地文件'}}<span v-if="task"> · {{providerName(task.identity.providerId)}}</span></p><small v-if="file&&task?.title" class="saved-filename">{{file.filename}}</small></div></div>
 <span class="download-size">{{formatDownloadBytes(file?.sizeBytes??task?.receivedBytes)}}<template v-if="!file&&task?.totalBytes"> / {{formatDownloadBytes(task.totalBytes)}}</template></span>
 <div class="download-state"><span>{{file?'已保存':task?downloadStatus(task):''}}<template v-if="file"> · {{file.format.toUpperCase()}}<span class="compact-size"> · {{formatDownloadBytes(file.sizeBytes)}}</span></template><template v-else-if="task?.status==='completed'"> · {{task.format?.toUpperCase()}}<span class="compact-size"> · {{formatDownloadBytes(task.receivedBytes)}}</span></template></span>
  <template v-if="!file&&task?.status==='downloading'"><progress v-if="task.totalBytes" :max="task.totalBytes" :value="task.receivedBytes" aria-label="下载进度"/><progress v-else aria-label="下载进度未知"/><small>{{percent!==null?percent+'% · ':''}}{{formatDownloadBytes(task.receivedBytes)}}<template v-if="task.totalBytes"> / {{formatDownloadBytes(task.totalBytes)}}</template><template v-else> · 总大小未知</template></small></template>
  <small v-if="!file&&task?.status==='completed'">{{task.filename}}</small>
 </div>
 <div class="download-actions"><button v-if="!file&&task&&['queued','resolving','downloading'].includes(task.status)" :disabled="pending" @click="emit('cancel')">取消</button><button v-if="!file&&task&&['failed','cancelled'].includes(task.status)&&!retried" :disabled="pending" @click="emit('retry')">重试</button><span v-if="retried" class="download-muted">已重试</span><button v-if="file" @click="copy">复制文件名</button><small v-if="copyNotice" role="status">{{copyNotice}}</small></div>
</article></template>
<style scoped>
.download-row{display:grid;grid-template-columns:minmax(0,2fr) minmax(110px,.7fr) minmax(160px,1fr) 110px;align-items:center;gap:22px;padding:18px 8px;border-bottom:1px solid var(--app-border-soft);min-width:0}.download-identity{display:flex;align-items:center;gap:14px;min-width:0}.download-cover{width:44px;height:44px;flex-shrink:0;border-radius:5px;overflow:hidden}.download-title{min-width:0}.download-title h3{font-size:14px;font-weight:500;margin:0 0 6px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.download-title p{margin:0;color:var(--app-text-muted);font-size:11px}.saved-filename{display:block;font-size:10px;color:var(--app-text-muted);margin-top:6px;overflow-wrap:anywhere}.download-size,.download-state{font-size:12px;color:var(--app-text-muted)}.download-state{display:flex;flex-direction:column;gap:7px;min-width:0}.download-state small{font-size:11px;overflow-wrap:anywhere}.download-state progress{width:100%;height:5px;border:0;border-radius:3px;accent-color:var(--app-accent)}progress::-webkit-progress-bar{background:var(--app-surface);border-radius:3px}progress::-webkit-progress-value{background:var(--app-accent);border-radius:3px}.download-actions{display:flex;justify-content:flex-end;gap:8px;align-items:center;flex-wrap:wrap}.download-actions button{padding:8px 10px;min-height:36px;border:1px solid var(--app-border-soft);border-radius:7px;background:transparent;color:var(--app-link);font:inherit;font-size:12px;cursor:pointer}.download-actions button:hover{background:var(--app-hover)}button:disabled{opacity:.5;cursor:default}.download-muted,.download-actions small{font-size:11px;color:var(--app-text-muted)}
.compact-size{display:none}
@media(max-width:1000px){.download-row{grid-template-columns:minmax(0,1fr) 140px 90px;gap:16px}.download-size{display:none}.compact-size{display:inline}}
@media(max-width:600px){.download-row{grid-template-columns:minmax(0,1fr) auto;gap:14px;padding:18px 0}.download-identity{grid-column:1/-1}.download-state{grid-column:1;grid-row:2;padding-left:58px}.download-actions{grid-column:2;grid-row:2}.download-actions button{min-height:40px}.download-state small{font-size:10px}}
</style>
