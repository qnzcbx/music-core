<script setup lang="ts">
import {ref,watch,onScopeDispose} from 'vue';
import {activeDownload} from '../composables/useDownloads';
import {useCoreClient} from '../composables/useCoreClient';
const {player,downloads}=useCoreClient();
const text=ref('');let timer:ReturnType<typeof setTimeout>;
function show(message:string){text.value=message;clearTimeout(timer);timer=setTimeout(()=>text.value='',6000);}
watch(()=>[player.phase.value,player.selectedId.value],()=>{if(['error','network','blocked'].includes(player.phase.value)){console.error('播放失败',{identity:player.selectedId.value,phase:player.phase.value,detail:player.message.value});show(player.selected.value&&'fileId' in player.selected.value?'本地文件无法读取，请刷新下载列表确认文件存在':'歌曲播放失败，请稍后重试或选择其他歌曲');}});
watch(()=>downloads.feedback.value,value=>{if(value?.error)show('下载失败，请稍后重试');});
watch(()=>downloads.tasks.value,(tasks,previous)=>{for(const task of tasks)if(task.status==='failed'&&previous?.some(t=>t.id===task.id&&t.status!=='failed')){console.error('下载失败',{identity:task.identity,code:task.errorCode});show('下载失败，请到下载页查看任务');}});
// 只通知本次观察到的任务完成；首次加载的历史成品不重复弹出。
const awaitingFiles=new Set<string>(),notified=new Set<string>();
watch([()=>downloads.tasks.value,()=>downloads.files.value,()=>downloads.feedback.value],([tasks,files,feedback],[previous])=>{
 if(feedback?.taskId&&!feedback.error)awaitingFiles.add(feedback.taskId);
 const completed:string[]=[];
 for(const task of tasks){
  if(activeDownload(task)||previous.some(old=>old.id===task.id&&activeDownload(old)))awaitingFiles.add(task.id);
  if(task.status==='failed'||task.status==='cancelled')awaitingFiles.delete(task.id);
  if(task.status==='completed'&&task.fileId&&files.some(file=>file.fileId===task.fileId)&&awaitingFiles.has(task.id)&&!notified.has(task.id)){
   notified.add(task.id);awaitingFiles.delete(task.id);completed.push(task.title||'');
  }
 }
 if(completed.length)show(completed.length===1?`下载成功${completed[0]?'：《'+completed[0]+'》':''}`:`${completed.length} 首歌曲下载成功`);
});
onScopeDispose(()=>clearTimeout(timer));
</script>
<template><aside v-if="text" class="client-notice" role="status"><span>{{text}}</span><button aria-label="关闭提示" @click="text=''">×</button></aside></template>
<style scoped>
.client-notice{position:fixed;z-index:120;top:16px;right:16px;width:max-content;max-width:calc(100vw - 24px);display:flex;align-items:center;gap:12px;padding:12px 16px;background:var(--app-surface-raised);color:var(--app-text);border:1px solid var(--app-border-soft);border-radius:10px;box-shadow:var(--app-shadow-panel);font-size:13px}.client-notice button{border:0;background:transparent;color:inherit;font-size:20px;cursor:pointer;min-width:28px;min-height:28px}
</style>
