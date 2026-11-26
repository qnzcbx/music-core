<script setup lang="ts">
import { computed, ref } from 'vue';
import type { DownloadTask, SavedDownloadFile } from '../../types/core';
import PlayIcon from '~icons/lucide/play';
import PauseIcon from '~icons/lucide/pause';
import LoadingIcon from '~icons/lucide/loader-circle';
import CopyIcon from '~icons/lucide/copy';
import DownloadIcon from '~icons/lucide/download';
import RetryIcon from '~icons/lucide/rotate-cw';
import TrashIcon from '~icons/lucide/trash-2';
import {
  ContextMenuRoot,
  ContextMenuTrigger,
  ContextMenuPortal,
  ContextMenuContent,
  ContextMenuItem,
} from 'reka-ui';
import CoverArt from '../CoverArt.vue';
import { providerName } from '../../composables/useProviders';
import { formatDownloadBytes, downloadStatus, downloadPercent } from '../../utils/download-display';

const props = defineProps<{
  delivery?: { state: string; text: string };
  task?: DownloadTask;
  file?: SavedDownloadFile;
  cover?: string | null;
  pending?: boolean;
  retried?: boolean;
  current?: boolean;
  playing?: boolean;
  busy?: boolean;
}>();
const emit = defineEmits<{ cancel: []; retry: []; play: []; remove: []; save: []; dismiss: [] }>();
const browserAction = computed(() =>
  props.task?.status !== 'completed' || props.delivery?.state === 'failed'
    ? '重试'
    : props.delivery?.state === 'handed'
      ? '重新下载'
      : '下载',
);
const playbackText = computed(() =>
  props.busy ? '正在加载' : props.playing ? '正在播放' : '已暂停',
);
const actionText = computed(() =>
  props.current && (props.playing || props.busy) ? '暂停' : '播放',
);
const percent = computed(() => (props.task ? downloadPercent(props.task) : null));
const pressed = ref(false);
const copyNotice = ref(''),
  menuOpen = ref(false),
  trigger = ref<HTMLElement>();
let suppressClick = false;
function opened(open: boolean) {
  menuOpen.value = open;
  if (open) suppressClick = true;
}
function playRow() {
  play();
}
function play() {
  if (!props.file || menuOpen.value || suppressClick) return;
  emit('play');
}
function keyboardMenu(event: KeyboardEvent) {
  if (event.key === 'ContextMenu' || (event.key === 'F10' && event.shiftKey)) {
    event.preventDefault();
    event.currentTarget instanceof HTMLElement && openMenu(event.currentTarget);
  }
}
function openMenu(element: HTMLElement) {
  const rect = element.getBoundingClientRect();
  element.dispatchEvent(
    new MouseEvent('contextmenu', {
      bubbles: true,
      cancelable: true,
      clientX: rect.left + 24,
      clientY: rect.bottom,
    }),
  );
}

async function copy() {
  try {
    await navigator.clipboard.writeText(
      props.task?.title || props.file?.filename || props.task?.filename || '',
    );
    copyNotice.value = '已复制';
  } catch {
    copyNotice.value = '无法复制，请检查剪贴板权限';
  }
}
</script>

<template>
  <ContextMenuRoot
    :open="menuOpen"
    @update:open="opened"
  >
    <ContextMenuTrigger
      as-child
      :disabled="!file"
    >
      <article
        ref="trigger"
        class="download-row"
        :class="{ 'saved-row': file, 'is-current': current, 'is-pressed': pressed }"
        @pointerdown="
          suppressClick = false;
          pressed = $event.pointerType !== 'mouse';
        "
        @pointerup="pressed = false"
        @pointercancel="pressed = false"
        @pointerleave="pressed = false"
        @contextmenu="pressed = false"
        @click="playRow"
        @keydown="keyboardMenu"
        :data-task-id="task?.id"
        :data-status="task?.status ?? 'saved'"
        :data-filename="file?.filename"
        :data-file-id="file?.fileId"
        :data-playback="current ? (busy ? 'loading' : playing ? 'playing' : 'paused') : undefined"
      >
        <div
          class="download-identity"
          :role="file ? 'button' : undefined"
          :tabindex="file ? 0 : undefined"
          :aria-label="file ? actionText + ' ' + (task?.title || file.filename) : undefined"
          @click.stop="play"
          @keydown.enter.prevent="play"
          @keydown.space.prevent="play"
        >
          <div class="download-cover">
            <CoverArt
              clover-fallback
              :src="cover"
            />
            <span
              v-if="file"
              class="download-cover-play"
              :data-icon="current && busy ? 'loading' : current && playing ? 'pause' : 'play'"
              aria-hidden="true"
            >
              <LoadingIcon
                v-if="current && busy"
                class="loading-icon"
              />
              <PauseIcon v-else-if="current && playing" />
              <PlayIcon v-else />
            </span>
          </div>
          <div class="download-title">
            <h3>{{ file?.title || task?.title || file?.filename || '未命名歌曲' }}</h3>
            <p v-if="file?.artist || task?.artist || !file">
              {{ file?.artist || task?.artist || '本地文件' }}
              <span v-if="task && !file"> · {{ providerName(task.identity.providerId) }}</span>
            </p>
            <p v-if="file?.album">{{ file.album }}</p>
          </div>
        </div>
        <span class="download-size">
          {{
            formatDownloadBytes(
              file?.sizeBytes ??
                (task?.status === 'completed'
                  ? (task.finalSizeBytes ?? task.receivedBytes)
                  : task?.receivedBytes),
            )
          }}
          <template v-if="!file && task?.totalBytes && task.status !== 'completed'">
            / {{ formatDownloadBytes(task.totalBytes) }}
          </template>
        </span>
        <div class="download-state">
          <span>
            {{
              file
                ? '已保存'
                : task
                  ? task.deliveryMode === 'browser' && task.status === 'completed'
                    ? delivery?.state === 'failed'
                      ? delivery.text
                      : delivery?.state === 'handed'
                        ? '已发起下载'
                        : '准备完成'
                    : downloadStatus(task)
                  : ''
            }}
            <template v-if="file">
              · {{ file.format.toUpperCase() }}
              <span class="compact-size"> · {{ formatDownloadBytes(file.sizeBytes) }} </span>
            </template>
            <template v-else-if="task?.status === 'completed'">
              · {{ task.format?.toUpperCase() }}
              <span class="compact-size">
                · {{ formatDownloadBytes(task.finalSizeBytes ?? task.receivedBytes) }}
              </span>
            </template>
          </span>
          <template
            v-if="
              !file &&
              task?.status === 'downloading' &&
              (!task.phase || task.phase === 'downloading')
            "
          >
            <progress
              v-if="task.totalBytes"
              :max="task.totalBytes"
              :value="task.receivedBytes"
              aria-label="下载进度"
            />
            <progress
              v-else
              aria-label="下载进度未知"
            />
            <small>
              {{ percent !== null ? percent + '% · ' : '' }}
              {{ formatDownloadBytes(task.finalSizeBytes ?? task.receivedBytes) }}
              <template v-if="task.totalBytes">
                / {{ formatDownloadBytes(task.totalBytes) }}
              </template>
              <template v-else> · 总大小未知</template>
            </small>
          </template>
          <progress
            v-if="
              !file &&
              task?.status === 'downloading' &&
              [
                'source_verifying',
                'transcoding',
                'output_verifying',
                'publishing',
                'verifying',
              ].includes(task.phase || '')
            "
            aria-label="正在处理音频"
          />
          <small
            v-if="
              !file &&
              task?.cleanupError &&
              !['temporary_cleanup_failed', 'saved_temporary_cleanup_failed'].includes(
                task.errorCode ?? '',
              )
            "
          >
            临时文件清理失败
          </small>
          <small v-if="!file && task?.status === 'completed'">{{ task.filename }}</small>
        </div>
        <div class="download-actions">
          <button
            v-if="!file && task?.deliveryMode === 'desktop' && task.status === 'failed'"
            :disabled="pending"
            @click="emit('dismiss')"
          >
            移除
          </button>
          <button
            v-if="!file && task && ['queued', 'resolving', 'downloading'].includes(task.status)"
            :disabled="pending"
            @click="emit('cancel')"
          >
            取消
          </button>
          <button
            v-if="
              !file &&
              task &&
              task.deliveryMode !== 'browser' &&
              ['failed', 'cancelled'].includes(task.status) &&
              !retried
            "
            :disabled="pending"
            @click="emit('retry')"
          >
            重试
          </button>
          <span
            v-if="retried"
            class="download-muted"
            >已发起重试，请查看新任务</span
          >
          <button
            v-if="
              !file &&
              task?.deliveryMode === 'browser' &&
              ['completed', 'failed', 'cancelled'].includes(task.status)
            "
            :disabled="pending"
            class="file-icon"
            :title="browserAction"
            :aria-label="browserAction"
            @click.stop="emit('save')"
          >
            <DownloadIcon v-if="browserAction === '下载'" />
            <RetryIcon v-else />
          </button>
          <template v-if="file">
            <button
              class="file-icon"
              aria-label="复制名称"
              title="复制名称"
              @click.stop="copy"
            >
              <CopyIcon />
            </button>
            <button
              class="file-icon delete-icon"
              aria-label="删除下载记录"
              title="删除下载记录"
              @click.stop="emit('remove')"
            >
              <TrashIcon />
            </button>
            <button
              class="accessible-actions"
              aria-label="文件操作"
              @click.stop="openMenu(trigger!)"
            >
              文件操作
            </button>
          </template>
          <small
            v-if="copyNotice"
            role="status"
          >
            {{ copyNotice }}
          </small>
        </div>
      </article>
    </ContextMenuTrigger>
    <ContextMenuPortal>
      <ContextMenuContent
        class="local-file-menu"
        :side-offset="6"
        @close-auto-focus="trigger?.querySelector<HTMLElement>('[role=button]')?.focus()"
      >
        <ContextMenuItem @select="copy"> <CopyIcon />复制名称 </ContextMenuItem>
        <ContextMenuItem @select="emit('remove')"> <TrashIcon />删除 </ContextMenuItem>
      </ContextMenuContent>
    </ContextMenuPortal>
  </ContextMenuRoot>
</template>

<style scoped>
.preserved-source-note {
  display: none;
}
@media (max-width: 600px) {
  .preserved-source-note {
    display: block;
    grid-column: 1 / -1;
    color: var(--app-text-muted);
    font-size: 12px;
  }
}
.download-row {
  display: grid;
  grid-template-columns: minmax(0, 2fr) minmax(110px, 0.7fr) minmax(160px, 1fr) 110px;
  align-items: center;
  gap: 22px;
  padding: 18px 8px;
  border-bottom: 1px solid var(--app-border-soft);
  min-width: 0;
}
.download-identity {
  display: flex;
  align-items: center;
  gap: 14px;
  min-width: 0;
}
.download-cover {
  width: 44px;
  height: 44px;
  flex-shrink: 0;
  border-radius: 5px;
  overflow: hidden;
}
.download-title {
  min-width: 0;
}
.download-title h3 {
  font-size: 14px;
  font-weight: 500;
  margin: 0 0 6px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.download-title p {
  margin: 0;
  color: var(--app-text-muted);
  font-size: 11px;
}
.saved-filename {
  display: block;
  font-size: 10px;
  color: var(--app-text-muted);
  margin-top: 6px;
  overflow-wrap: anywhere;
}
.download-size,
.download-state {
  font-size: 12px;
  color: var(--app-text-muted);
}
.download-state {
  display: flex;
  flex-direction: column;
  gap: 7px;
  min-width: 0;
}
.download-state small {
  font-size: 11px;
  overflow-wrap: anywhere;
}
.download-state progress {
  width: 100%;
  height: 5px;
  border: 0;
  border-radius: 3px;
  accent-color: var(--app-accent);
}
progress::-webkit-progress-bar {
  background: var(--app-surface);
  border-radius: 3px;
}
progress::-webkit-progress-value {
  background: var(--app-accent);
  border-radius: 3px;
}
.download-actions {
  position: relative;
  min-width: 0;
  display: flex;
  justify-content: flex-start;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}
.download-actions button {
  padding: 8px 10px;
  min-height: 36px;
  border: 1px solid var(--app-border-soft);
  border-radius: 7px;
  background: transparent;
  color: var(--app-link);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
}
.download-actions button:hover {
  background: var(--app-hover);
}
button:disabled {
  opacity: 0.5;
  cursor: default;
}
.download-muted,
.download-actions small {
  font-size: 11px;
  color: var(--app-text-muted);
}
.compact-size {
  display: none;
}
@media (max-width: 1000px) {
  .download-row {
    grid-template-columns: minmax(0, 1fr) 140px 90px;
    gap: 16px;
  }
  .download-size {
    display: none;
  }
  .compact-size {
    display: inline;
  }
}
@media (max-width: 600px) {
  .download-row {
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 14px;
    padding: 18px 0;
  }
  .download-identity {
    grid-column: 1/-1;
  }
  .download-state {
    grid-column: 1;
    grid-row: 2;
    padding-left: 58px;
  }
  .download-actions {
    grid-column: 2;
    grid-row: 2;
  }
  .download-actions button {
    min-height: 40px;
  }
  .download-state small {
    font-size: 10px;
  }
}
.saved-row .download-identity {
  cursor: pointer;
}
.saved-row {
  cursor: pointer;
}
.saved-row:hover,
.saved-row:focus-within {
  background: var(--app-hover);
}
.saved-row.is-current,
.saved-row.is-pressed,
.saved-row:active,
.saved-row[data-state='open'] {
  background: var(--app-selected);
}
.saved-row .download-cover {
  position: relative;
}
.download-cover-play {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  opacity: 0;
  background: #17352d70;
  color: #fff;
  border-radius: 5px;
  transition: opacity 0.12s;
}
.download-cover-play svg {
  width: 20px;
  height: 20px;
}
.saved-row:hover .download-cover-play,
.saved-row:focus-within .download-cover-play,
.saved-row.is-current .download-cover-play {
  opacity: 1;
}
.local-playback-status {
  display: block;
  font-size: 11px;
  color: var(--app-text-muted);
  margin: 0 0 5px;
}
.loading-icon {
  animation: local-loading 1s linear infinite;
}
@keyframes local-loading {
  to {
    transform: rotate(360deg);
  }
}
@media (prefers-reduced-motion: reduce) {
  .download-cover-play {
    transition: none;
  }
  .loading-icon {
    animation: none;
  }
}
.download-actions .file-icon {
  border: 0;
  color: var(--app-text-muted);
  padding: 9px;
  width: 36px;
  height: 36px;
  display: grid;
  place-items: center;
}
.file-icon svg {
  width: 16px;
  height: 16px;
}
.download-actions .delete-icon:hover {
  color: #b86b6b;
}
.download-actions .accessible-actions {
  position: absolute !important;
  right: 0;
  top: 0;
  width: 1px;
  height: 1px;
  min-width: 0;
  min-height: 0;
  padding: 0;
  border: 0;
  overflow: hidden;
  clip-path: inset(50%);
}
.download-actions .accessible-actions:focus-visible {
  position: static !important;
  width: auto;
  height: auto;
  min-height: 40px;
  padding: 8px 10px;
  border: 1px solid var(--app-border-soft);
  clip-path: none;
}
.saved-row .download-identity:focus-visible {
  outline: 2px solid var(--app-focus);
  outline-offset: 4px;
  border-radius: 3px;
}
@media (max-width: 600px) {
  .saved-row {
    display: block;
    padding: 16px 0;
    position: relative;
    user-select: none;
    -webkit-user-select: none;
    -webkit-tap-highlight-color: transparent;
  }
  .saved-row .download-cover,
  .saved-row .download-size,
  .saved-row .download-state,
  .saved-row .file-icon,
  .saved-row .saved-filename {
    display: none;
  }
  .saved-row .download-title {
    width: 100%;
  }
  .saved-row .download-title h3 {
    margin-bottom: 5px;
  }
  .saved-row .download-title p {
    font-size: 12px;
  }
  .saved-row .download-actions {
    position: absolute;
    right: 0;
    top: 0;
  }
  .saved-row .download-actions small {
    position: absolute;
    right: 4px;
    top: 4px;
    white-space: nowrap;
  }
}
</style>
<style>
.local-file-menu {
  z-index: 100;
  min-width: 160px;
  padding: 5px;
  background: var(--app-surface);
  color: var(--app-text);
  border: 1px solid var(--app-border);
  border-radius: 8px;
  box-shadow: 0 8px 32px #0002;
}
.local-file-menu [role='menuitem'] {
  padding: 10px 12px;
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13px;
  cursor: pointer;
  outline: none;
  border-radius: 4px;
}
.local-file-menu [data-highlighted] {
  background: var(--app-hover);
}
.local-file-menu svg {
  width: 16px;
  height: 16px;
}
</style>
