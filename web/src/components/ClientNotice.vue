<script setup lang="ts">
import { computed, ref, watch, onScopeDispose } from 'vue';
import { activeDownload } from '../composables/useDownloads';
import { useCoreClient } from '../composables/useCoreClient';
const { player, downloads } = useCoreClient();
const deliveryNotices = computed(() =>
  downloads.tasks.value.filter((task) => downloads.deliveries.value[task.id]),
);
const text = ref('');
let timer: ReturnType<typeof setTimeout>;
function show(message: string) {
  text.value = message;
  clearTimeout(timer);
  timer = setTimeout(() => (text.value = ''), 6000);
}
watch(
  () => [player.phase.value, player.selectedId.value],
  () => {
    if (['error', 'network', 'blocked'].includes(player.phase.value)) {
      console.error('播放失败', {
        identity: player.selectedId.value,
        phase: player.phase.value,
        detail: player.message.value,
      });
      show(
        player.selected.value && 'fileId' in player.selected.value
          ? player.message.value
          : '歌曲播放失败，请稍后重试或选择其他歌曲',
      );
    }
  },
);
watch(
  () => downloads.feedback.value,
  (value) => {
    if (value?.error) show('下载失败，请稍后重试');
  },
);
watch(
  () => downloads.tasks.value,
  (tasks, previous) => {
    for (const task of tasks)
      if (
        task.status === 'failed' &&
        previous?.some((t) => t.id === task.id && t.status !== 'failed')
      ) {
        console.error('下载失败', { identity: task.identity, code: task.errorCode });
        show(
          task.sourcePreserved
            ? '转换失败，已保留 FLAC'
            : task.errorCode === 'conversion_failed'
              ? '转换失败，请到下载页重试'
              : task.errorCode === 'source_verification_failed'
                ? '源文件校验失败'
                : '下载失败，请到下载页查看任务',
        );
      }
  },
);
// 只通知本次观察到的任务完成；首次加载的历史成品不重复弹出。
const awaitingFiles = new Set<string>(),
  notified = new Set<string>();
watch(
  [() => downloads.tasks.value, () => downloads.files.value, () => downloads.feedback.value],
  ([tasks, files, feedback], [previous]) => {
    if (feedback?.taskId && !feedback.error) awaitingFiles.add(feedback.taskId);
    const completed: string[] = [];
    for (const task of tasks) {
      if (activeDownload(task) || previous.some((old) => old.id === task.id && activeDownload(old)))
        awaitingFiles.add(task.id);
      if (task.status === 'failed' || task.status === 'cancelled') awaitingFiles.delete(task.id);
      if (
        task.status === 'completed' &&
        task.fileId &&
        files.some((file) => file.fileId === task.fileId) &&
        awaitingFiles.has(task.id) &&
        !notified.has(task.id)
      ) {
        notified.add(task.id);
        awaitingFiles.delete(task.id);
        completed.push(task.title || '');
      }
    }
    if (completed.length)
      show(
        completed.length === 1
          ? `下载成功${completed[0] ? '：《' + completed[0] + '》' : ''}`
          : `${completed.length} 首歌曲下载成功`,
      );
  },
);
onScopeDispose(() => clearTimeout(timer));
</script>
<template>
  <div
    v-if="deliveryNotices.length"
    class="device-download-notices"
    aria-live="polite"
  >
    <div
      v-for="task in deliveryNotices"
      :key="task.id"
    >
      <span>{{ task.title }}：{{ downloads.deliveries.value[task.id]?.text }}</span>
      <button
        v-if="task.artifactUrl"
        @click="downloads.deliver(task)"
      >
        {{ task.sourcePreserved ? '保存 FLAC 到此设备' : '保存到此设备' }}
      </button>
      <button
        v-if="!['queued', 'resolving', 'downloading'].includes(task.status)"
        aria-label="关闭下载交付提示"
        @click="delete downloads.deliveries.value[task.id]"
      >
        ×
      </button>
    </div>
  </div>
  <aside
    v-if="text"
    class="client-notice"
    role="status"
  >
    <span>{{ text }}</span>
    <button
      aria-label="关闭提示"
      @click="text = ''"
    >
      ×
    </button>
  </aside>
</template>
<style scoped>
.client-notice {
  position: fixed;
  z-index: 120;
  top: 16px;
  right: 16px;
  width: max-content;
  max-width: calc(100vw - 24px);
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  background: var(--app-surface-raised);
  color: var(--app-text);
  border: 1px solid var(--app-border-soft);
  border-radius: 10px;
  box-shadow: var(--app-shadow-panel);
  font-size: 13px;
}
.client-notice button {
  border: 0;
  background: transparent;
  color: inherit;
  font-size: 20px;
  cursor: pointer;
  min-width: 28px;
  min-height: 28px;
}
</style>

<style scoped>
.device-download-notices {
  position: fixed;
  right: 16px;
  top: 80px;
  z-index: 120;
  max-width: calc(100vw - 32px);
  display: grid;
  gap: 8px;
}
.device-download-notices > div {
  padding: 12px 16px;
  background: var(--app-surface-raised);
  border: 1px solid var(--app-border);
  border-radius: 10px;
  box-shadow: var(--app-shadow-panel);
  font-size: 13px;
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}
.device-download-notices button {
  cursor: pointer;
  padding: 6px 10px;
  background: var(--app-surface);
  color: var(--app-text);
  border: 1px solid var(--app-border);
  border-radius: 6px;
}
</style>
