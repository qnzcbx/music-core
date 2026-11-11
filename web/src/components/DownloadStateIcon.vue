<script setup lang="ts">
import { computed } from 'vue';
import { useCoreClient } from '../composables/useCoreClient';
import { queueKey } from '../utils/player-queue';
import type { TrackIdentity } from '../types/core';
import Download from '~icons/lucide/download';
import Clock from '~icons/lucide/clock-3';
import Loader from '~icons/lucide/loader-circle';
import Check from '~icons/lucide/circle-check';
import Failed from '~icons/lucide/circle-alert';
const props=defineProps<{identity:TrackIdentity|null}>();
const {downloads}=useCoreClient();
const state=computed(()=>{
 const task=[...downloads.tasks.value].reverse().find(t=>props.identity&&queueKey(t.identity)===queueKey(props.identity));
 if(!task)return 'none';
 if(task.status==='downloading'&&['transcoding','verifying'].includes(task.phase||''))return task.phase!;
 if(task.status==='completed')return task.fileId&&downloads.files.value.some(f=>f.fileId===task.fileId)?'completed':'unconfirmed';
 return task.status;
});
const labels:Record<string,string>={transcoding:'转换中',verifying:'验证中',none:'下载',queued:'等待下载',resolving:'等待下载',downloading:'正在下载',completed:'下载完成，文件存在',failed:'下载失败',cancelled:'下载已取消',unconfirmed:'等待确认文件'};
</script>
<template><span class="download-state-icon" :data-download-state="state" role="img" :aria-label="labels[state]" :title="labels[state]"><Check v-if="state==='completed'" class="completed"/><Clock v-else-if="['queued','resolving','unconfirmed'].includes(state)"/><Loader v-else-if="['downloading','transcoding','verifying'].includes(state)" class="loading"/><Failed v-else-if="state==='failed'"/><Download v-else/></span></template>
<style scoped>
.download-state-icon{display:inline-flex;align-items:center;justify-content:center}.download-state-icon[data-download-state="completed"]{background:#26864c;border-radius:50%;color:#fff}.completed{color:#fff;stroke-width:2}.loading{animation:download-spin 1s linear infinite}@keyframes download-spin{to{transform:rotate(360deg)}}@media(prefers-reduced-motion:reduce){.loading{animation:none}}
</style>
