<script setup lang="ts">
import { nextTick, ref } from 'vue';
import {
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogOverlay,
  AlertDialogPortal,
  AlertDialogRoot,
  AlertDialogTitle,
  DropdownMenuRoot,
  DropdownMenuPortal,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from 'reka-ui';
import PlayIcon from '~icons/lucide/play';
import PauseIcon from '~icons/lucide/pause';
import MoreIcon from '~icons/lucide/ellipsis';
import TrashIcon from '~icons/lucide/trash-2';
import CoverArt from '../CoverArt.vue';
import { requestJson } from '../../api/http';
import { useCoreClient } from '../../composables/useCoreClient';
import { formatDownloadBytes } from '../../utils/download-display';

export type DesktopSong = {
  id: string;
  recordId?: string;
  path: string;
  title: string;
  artist: string;
  format: string;
  available: boolean;
  album?: string | null;
  cover?: string | null;
  durationSeconds?: number | null;
  sizeBytes?: number | null;
  savedAt?: number | null;
  sourcePreserved?: boolean;
};

defineProps<{ songs: DesktopSong[] }>();
const emit = defineEmits<{ removed: [] }>();
const { player, downloads } = useCoreClient();
const error = ref('');
const details = ref<HTMLDialogElement>();
const detailSong = ref<DesktopSong>();
const removal = ref<DesktopSong>();
const deleteFile = ref(false);
const removing = ref(false);
const removeError = ref('');

function filename(song: DesktopSong) {
  return song.path.split(/[\\/]/).pop() || song.path;
}
function title(song: DesktopSong) {
  return song.title.trim() || filename(song).replace(/\.[^.]+$/, '');
}
function displayPath(path: string) {
  if (path.startsWith('\\\\?\\UNC\\')) return '\\\\' + path.slice(8);
  return path.startsWith('\\\\?\\') ? path.slice(4) : path;
}
function duration(seconds?: number | null) {
  if (seconds == null || !Number.isFinite(seconds) || seconds < 0) return '—';
  const whole = Math.floor(seconds);
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, '0')}`;
}
function current(song: DesktopSong) {
  return player.selectedId.value === JSON.stringify(['local', song.id]);
}
function playing(song: DesktopSong) {
  return current(song) && player.playing.value;
}
function play(song: DesktopSong) {
  error.value = '';
  if (current(song)) void player.toggle();
  else void player.selectDesktopLocal({ id: song.id, title: title(song), artist: song.artist });
}
async function reveal(song: DesktopSong) {
  error.value = '';
  try {
    await requestJson('/api/local-library/reveal', {
      method: 'POST',
      body: JSON.stringify({ id: song.id }),
    });
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '无法打开文件位置';
  }
}
async function showDetails(song: DesktopSong) {
  detailSong.value = song;
  await nextTick();
  details.value?.showModal();
}
function confirmRemoval(song: DesktopSong) {
  removal.value = song;
  deleteFile.value = false;
  removeError.value = '';
}
async function remove() {
  const song = removal.value;
  if (!song || removing.value) return;
  removing.value = true;
  removeError.value = '';
  try {
    if (deleteFile.value) await player.removeLocal(song.id);
    await requestJson('/api/local-library/remove', {
      method: 'POST',
      body: JSON.stringify({ id: song.id, deleteFile: deleteFile.value }),
    });
    removal.value = undefined;
    if (!deleteFile.value) void player.removeLocal(song.id);
    void downloads.refresh();
    emit('removed');
  } catch (reason) {
    removeError.value = reason instanceof Error ? reason.message : '删除记录失败，请重试';
  } finally {
    removing.value = false;
  }
}
</script>

<template>
  <div class="desktop-song-list">
    <p
      v-if="error"
      role="alert"
    >
      {{ error }}
    </p>
    <div
      v-if="songs.length"
      role="table"
      aria-label="歌曲列表"
    >
      <div
        class="song-grid song-header"
        role="row"
      >
        <span role="columnheader">歌曲 / 歌手</span>
        <span
          role="columnheader"
          aria-label="更多操作"
        ></span>
        <span
          class="album"
          role="columnheader"
          >专辑</span
        >
        <span
          class="numeric"
          role="columnheader"
        >
          时长
        </span>
        <span
          class="numeric size"
          role="columnheader"
        >
          大小
        </span>
      </div>
      <div
        v-for="song in songs"
        :key="song.recordId ?? song.id"
        class="song-grid song-row"
        :class="{ selected: current(song), playing: playing(song) }"
        role="row"
        :data-local-id="song.id"
        :data-saved-id="song.recordId"
      >
        <div
          class="song-identity"
          role="cell"
        >
          <div
            class="cover-image"
            aria-hidden="true"
          >
            <CoverArt
              clover-fallback
              :src="song.cover"
              loading="lazy"
            />
            <span
              class="cover-action"
              aria-hidden="true"
            >
              <PauseIcon v-if="playing(song)" />
              <PlayIcon v-else />
            </span>
          </div>
          <div class="song-text">
            <div class="song-title-line">
              <span
                class="truncate song-title"
                :title="title(song)"
              >
                {{ title(song) }}
              </span>
              <span class="format">{{ song.format.toUpperCase() }}</span>
              <span
                v-if="!song.available"
                class="warning"
              >
                文件不可用
              </span>
              <span
                v-else-if="song.sourcePreserved"
                class="warning"
              >
                压缩失败，原文件已保存
              </span>
            </div>
            <div
              v-if="song.artist"
              class="artist truncate"
              :title="song.artist"
            >
              {{ song.artist }}
            </div>
          </div>
          <button
            class="song-cover"
            type="button"
            :disabled="!song.available || (current(song) && player.busy.value)"
            :aria-label="`${playing(song) ? '暂停' : '播放'} ${title(song)} · ${song.format.toUpperCase()}`"
            @click="play(song)"
          ></button>
        </div>
        <div
          class="more-cell"
          role="cell"
        >
          <button
            class="song-action song-delete"
            type="button"
            :aria-label="`删除记录：${title(song)} · ${song.format.toUpperCase()}`"
            title="删除记录"
            @click="confirmRemoval(song)"
          >
            <TrashIcon aria-hidden="true" />
          </button>
          <DropdownMenuRoot>
            <DropdownMenuTrigger as-child>
              <button
                class="song-action song-more"
                type="button"
                :aria-label="`更多操作：${title(song)} · ${song.format.toUpperCase()}`"
              >
                <MoreIcon aria-hidden="true" />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuPortal>
              <DropdownMenuContent
                class="music-layer song-menu"
                align="end"
              >
                <DropdownMenuItem
                  data-slot="dropdown-menu-item"
                  @select="reveal(song)"
                >
                  在文件夹中显示
                </DropdownMenuItem>
                <DropdownMenuItem
                  data-slot="dropdown-menu-item"
                  @select="showDetails(song)"
                >
                  文件详情
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenuPortal>
          </DropdownMenuRoot>
        </div>
        <span
          class="album truncate"
          role="cell"
          :title="song.album || undefined"
        >
          {{ song.album || '—' }}
        </span>
        <span
          class="numeric"
          role="cell"
        >
          {{ duration(song.durationSeconds) }}
        </span>
        <span
          class="numeric size"
          role="cell"
        >
          {{ song.sizeBytes == null ? '—' : formatDownloadBytes(song.sizeBytes) }}
        </span>
      </div>
    </div>
    <dialog
      ref="details"
      class="file-dialog"
      aria-labelledby="desktop-song-details"
    >
      <template v-if="detailSong">
        <h2 id="desktop-song-details">文件详情</h2>
        <dl class="file-details">
          <dt>文件名</dt>
          <dd>{{ filename(detailSong) }}</dd>
          <dt>完整路径</dt>
          <dd>{{ displayPath(detailSong.path) }}</dd>
          <template v-if="detailSong.savedAt != null">
            <dt>保存时间</dt>
            <dd>{{ new Date(detailSong.savedAt).toLocaleString() }}</dd>
          </template>
        </dl>
        <form method="dialog">
          <footer><button autofocus>关闭</button></footer>
        </form>
      </template>
    </dialog>
    <AlertDialogRoot
      :open="!!removal"
      @update:open="
        (open) => {
          if (!open && !removing) removal = undefined;
        }
      "
    >
      <AlertDialogPortal>
        <AlertDialogOverlay class="file-dialog-overlay" />
        <AlertDialogContent
          class="file-dialog"
          @escape-key-down="
            (event) => {
              if (removing) event.preventDefault();
            }
          "
        >
          <AlertDialogTitle>
            {{ removal?.recordId ? '删除下载记录？' : '移除本地歌曲？' }}
          </AlertDialogTitle>
          <AlertDialogDescription>
            「{{ removal ? filename(removal) : '' }}」将从本地歌曲和下载歌曲中移除。
          </AlertDialogDescription>
          <label>
            <input
              v-model="deleteFile"
              type="checkbox"
              :disabled="removing"
            />
            同时删除本地音频文件
          </label>
          <p
            v-if="deleteFile"
            class="file-delete-warning"
          >
            音频文件将从磁盘删除，此操作可能无法撤销。
          </p>
          <p
            v-if="removeError"
            role="alert"
          >
            {{ removeError }}
          </p>
          <footer>
            <AlertDialogCancel :disabled="removing">取消</AlertDialogCancel>
            <button
              type="button"
              :disabled="removing"
              @click="remove"
            >
              {{ removing ? '正在删除…' : '确认删除' }}
            </button>
          </footer>
        </AlertDialogContent>
      </AlertDialogPortal>
    </AlertDialogRoot>
  </div>
</template>

<style scoped>
.desktop-song-list {
  container-type: inline-size;
}
.song-grid {
  --actions-width: 92px;
  display: grid;
  grid-template-columns: minmax(0, 2.5fr) var(--actions-width) minmax(0, 1fr) 56px 74px;
  align-items: center;
  column-gap: 12px;
  padding-inline: 10px calc(10px + clamp(16px, 3cqi, 44px));
}
.song-header {
  min-height: 40px;
  color: var(--app-text-muted);
  font-size: 12px;
  border-bottom: 1px solid var(--app-border-soft);
}
.song-row {
  position: relative;
  min-height: 72px;
  border-bottom: 1px solid var(--app-border-soft);
  font-size: 13px;
}
.song-row:hover,
.song-row:focus-within {
  background: var(--app-hover);
}
.song-row.selected {
  background: var(--app-selected);
}
.song-identity,
.song-title-line {
  display: flex;
  align-items: center;
  min-width: 0;
}
.song-identity {
  gap: 12px;
}
.song-text {
  min-width: 0;
}
.song-title-line {
  gap: 7px;
}
.song-title {
  font-size: 14px;
  font-weight: 500;
}
.truncate {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.artist {
  margin-top: 3px;
  font-size: 12px;
}
.artist,
.album,
.numeric {
  color: var(--app-text-muted);
}
.format {
  flex: none;
  border: 1px solid var(--app-border-soft);
  border-radius: 4px;
  padding: 1px 4px;
  color: var(--app-text-muted);
  font-size: 10px;
}
.warning {
  color: var(--app-text-muted);
  font-size: 11px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 0 1 auto;
}
.numeric {
  text-align: start;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.song-cover,
.song-action {
  color: inherit;
  border: 0;
  padding: 0;
  background: transparent;
  cursor: pointer;
}
.song-cover {
  position: absolute;
  inset: 0;
  z-index: 1;
}
.cover-image {
  position: relative;
  flex: 0 0 44px;
  width: 44px;
  height: 44px;
  border-radius: 5px;
}
.song-cover:disabled {
  cursor: default;
}
.cover-action {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  border-radius: inherit;
  background: #17352d70;
  color: #fff;
  opacity: 0;
  transition: opacity 0.12s;
}
.cover-action svg {
  width: 20px;
  height: 20px;
}
.song-row:has(.song-cover:not(:disabled)):is(:hover, :focus-within, .selected) .cover-action {
  opacity: 1;
}
.song-cover:focus-visible {
  outline: 2px solid var(--app-focus);
  outline-offset: -2px;
}
.song-action:focus-visible {
  outline: 2px solid var(--app-focus);
  outline-offset: 2px;
}
.more-cell {
  position: relative;
  z-index: 2;
  display: flex;
  gap: 4px;
}
.song-action {
  display: grid;
  place-items: center;
  border-radius: 7px;
  width: 36px;
  height: 36px;
  color: var(--app-link);
}
.song-action svg {
  width: 18px;
  height: 18px;
}
@media (hover: hover) and (pointer: fine) {
  .song-action {
    opacity: 0;
    transition: opacity 0.12s;
  }
  .song-row:is(:hover, :focus-within, :has(.song-more[data-state='open'])) .song-action,
  .song-more[data-state='open'] {
    opacity: 1;
  }
}
.song-action:hover,
.song-more[data-state='open'] {
  background: var(--app-surface-raised);
}
.song-delete:hover {
  color: var(--app-danger);
}
.music-layer.song-menu {
  padding: 4px;
  border-radius: 8px;
}
.song-menu [data-slot='dropdown-menu-item'] {
  font-size: 13px;
  line-height: 1.4;
  padding: 6px 10px;
  border-radius: 5px;
}
.file-dialog {
  margin: 0;
}
.file-dialog::backdrop {
  background: #0006;
}
.file-details {
  display: grid;
  gap: 6px;
  font-size: 13px;
}
.file-details dt {
  color: var(--app-text-muted);
}
.file-details dd {
  margin: 0 0 8px;
  overflow-wrap: anywhere;
}
@container (max-width: 620px) {
  .song-grid {
    --actions-width: 84px;
    grid-template-columns: minmax(0, 1fr) var(--actions-width) 52px 70px;
    padding-inline-end: 10px;
  }
  .album {
    display: none;
  }
}
@container (max-width: 470px) {
  .song-grid {
    grid-template-columns: minmax(0, 1fr) var(--actions-width) 46px;
    column-gap: 8px;
  }
  .size {
    display: none;
  }
}
</style>
