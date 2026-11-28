<script setup lang="ts">
import { computed, ref, watch, nextTick, onScopeDispose } from 'vue';
import XIcon from '~icons/lucide/x';
import { useCoreClient } from '../composables/useCoreClient';
import { ApiError } from '../api/http';
import { checkDownloadQuality, supportedDownloadQualities } from '../api/downloads';
import { downloadQualitySummary } from '../utils/download-quality';
import { trackIdentity } from '../utils/player-queue';
import type { DownloadQuality, DownloadQualityOption, OutputMode } from '../types/core';

const { downloads } = useCoreClient();
const dialog = ref<HTMLDialogElement>();
const quality = ref<DownloadQuality>('auto');
const submitting = ref(false);
const outputMode = ref<OutputMode>('original');
const expanded = ref(false);
const results = ref<Partial<Record<DownloadQuality, DownloadQualityOption>>>({});
const pending = ref(new Set<DownloadQuality>());
const result = computed(() => results.value[quality.value]);
const checking = computed(() => pending.value.has(quality.value));
const canCompress = computed(
  () =>
    result.value?.availability === 'available' &&
    result.value.representation?.codec === 'flac' &&
    result.value.conversion?.available,
);
const choices = [
  { id: 'auto', name: '自动' },
  { id: 'standard', name: '标准品质' },
  { id: 'high', name: '高品质' },
  { id: 'lossless', name: '无损品质' },
] as const;
let revision = 0;
const controllers = new Set<AbortController>();
let origin: HTMLElement | null = null;
function resetOutput() {
  expanded.value = false;
  outputMode.value = 'original';
}
function close() {
  if (!submitting.value) downloads.closeChoice();
}
function retryable(option?: DownloadQualityOption) {
  return (
    option?.availability === 'unavailable' &&
    (option.retryable ??
      ['upstream_timeout', 'upstream_failure', 'upstream_rate_limited', 'request_timeout'].includes(
        option.errorCode ?? '',
      ))
  );
}
async function inspect(selected: DownloadQuality, retry = false) {
  const song = downloads.downloadSong.value;
  if (!song || pending.value.has(selected) || (results.value[selected] && !retry)) return;
  const token = revision;
  const controller = new AbortController();
  controllers.add(controller);
  pending.value = new Set([...pending.value, selected]);
  try {
    const value = await checkDownloadQuality(
      { identity: trackIdentity(song), quality: selected },
      controller.signal,
    );
    if (token === revision) results.value = { ...results.value, [selected]: value };
  } catch (reason) {
    if (token === revision)
      results.value = {
        ...results.value,
        [selected]: {
          quality: selected,
          availability: 'unavailable',
          representation: null,
          retryable: reason instanceof ApiError ? reason.retryable : true,
          errorCode:
            reason instanceof ApiError
              ? reason.code ||
                (reason.status >= 500 ? 'upstream_failure' : 'capability_unsupported')
              : 'upstream_failure',
        },
      };
  } finally {
    controllers.delete(controller);
    if (token === revision)
      pending.value = new Set([...pending.value].filter((q) => q !== selected));
  }
}
watch(
  () => downloads.downloadSong.value,
  async (song) => {
    revision++;
    controllers.forEach((c) => c.abort());
    controllers.clear();
    results.value = {};
    pending.value = new Set();
    quality.value = 'auto';
    resetOutput();
    if (song) {
      origin = document.activeElement as HTMLElement;
      void inspect('auto');
      await nextTick();
      if (downloads.downloadSong.value && !dialog.value?.open) dialog.value?.showModal();
    } else {
      dialog.value?.close();
      origin?.focus();
    }
  },
);
watch(canCompress, (available) => {
  if (!available) resetOutput();
});
watch(quality, (selected) => {
  resetOutput();
  void inspect(selected);
});
async function confirm() {
  const song = downloads.downloadSong.value;
  if (!song || submitting.value || checking.value || result.value?.availability !== 'available')
    return;
  submitting.value = true;
  try {
    await downloads.create(
      song,
      quality.value,
      outputMode.value,
      result.value.representation?.codec === 'flac' ? 'flac' : null,
    );
    downloads.closeChoice();
  } finally {
    submitting.value = false;
  }
}
function estimated(bitrate: number) {
  const rep = result.value?.representation;
  const value =
    rep?.durationSeconds || rep?.expectedDurationSeconds || downloads.downloadSong.value?.duration;
  const seconds = value ?? 0;
  return seconds > 0 && Number.isFinite(seconds)
    ? `预计 ${((seconds * bitrate) / 8 / 1048576).toFixed(1)} MB`
    : '';
}
function summary(selected: DownloadQuality) {
  if (pending.value.has(selected)) return '正在检测…';
  const option = results.value[selected];
  if (!option) return '选择后检测';
  if (option.availability === 'available') return downloadQualitySummary(option.representation);
  if (retryable(option)) return '检测暂时失败';
  return (
    (
      {
        access_denied: '当前访问条件下无法下载此音质',
        capability_unsupported: '此来源暂不支持该品质',
        source_verification_failed: '无法确认该品质的资源',
        media_unavailable: '暂无此品质资源',
      } as Record<string, string>
    )[option.errorCode || ''] || '暂无可用资源'
  );
}
onScopeDispose(() => {
  revision++;
  controllers.forEach((c) => c.abort());
});
</script>

<template>
  <dialog
    ref="dialog"
    class="quality-dialog"
    aria-labelledby="quality-heading"
    @cancel.prevent="close"
    @click="
      (event) => {
        if (event.target === dialog) close();
      }
    "
  >
    <header>
      <h2 id="quality-heading">下载歌曲</h2>
      <button
        aria-label="关闭音质选择"
        :disabled="submitting"
        @click="close"
      >
        <XIcon />
      </button>
    </header>
    <p class="quality-song">
      {{ downloads.downloadSong.value?.title }} ·
      {{ downloads.downloadSong.value?.artist }}
    </p>
    <fieldset :disabled="submitting">
      <legend>选择音质</legend>
      <div
        v-for="choice in choices.filter((c) => supportedDownloadQualities.includes(c.id))"
        :key="choice.id"
        class="quality-row"
      >
        <label
          ><input
            v-model="quality"
            type="radio"
            name="download-quality"
            :value="choice.id"
          />
          <span>
            <strong>{{ choice.name }}</strong>
            <small role="status">{{ summary(choice.id) }}</small>
          </span>
        </label>
        <button
          v-if="retryable(results[choice.id]) && !pending.has(choice.id)"
          :disabled="submitting"
          @click="inspect(choice.id, true)"
        >
          重试
        </button>
      </div>
    </fieldset>
    <fieldset
      v-if="canCompress && expanded"
      class="save-options"
      :disabled="submitting"
    >
      <legend>压缩为 MP3</legend>
      <label>
        <input
          v-model="outputMode"
          type="radio"
          name="output-mode"
          value="mp3_320"
        />
        <span>
          <strong>节省空间 · MP3 320 kbps</strong><small>{{ estimated(320000) }}</small>
        </span>
      </label>
      <label>
        <input
          v-model="outputMode"
          type="radio"
          name="output-mode"
          value="mp3_192"
        />
        <span>
          <strong>更小的文件 · MP3 192 kbps</strong>
          <small>{{ estimated(192000) }}</small>
        </span>
      </label>
    </fieldset>
    <p
      v-if="outputMode !== 'original'"
      class="quality-hint"
    >
      转换为 MP3 会损失部分音质
    </p>
    <footer>
      <button
        v-if="canCompress"
        class="compress-toggle"
        :aria-expanded="expanded"
        :disabled="submitting"
        @click="expanded ? resetOutput() : (expanded = true)"
      >
        {{ expanded ? '收起压缩选项' : '压缩文件' }}
      </button>
      <button
        class="quality-confirm"
        :disabled="checking || submitting || result?.availability !== 'available'"
        @click="confirm()"
      >
        {{ submitting ? '正在创建任务…' : outputMode === 'original' ? '确认下载' : '确认下载 MP3' }}
      </button>
    </footer>
  </dialog>
</template>

<style scoped>
.quality-dialog {
  position: fixed;
  inset: 0;
  width: min(440px, calc(100vw - 24px));
  max-height: calc(100dvh - 32px);
  overflow: auto;
  overscroll-behavior: contain;
  scrollbar-width: none;
  margin: auto;
  padding: 24px;
  border: 1px solid var(--app-border-soft);
  border-radius: 16px;
  background: var(--app-surface-raised);
  color: var(--app-text);
  box-shadow: var(--app-shadow-panel);
}
.quality-dialog::-webkit-scrollbar {
  display: none;
}
.quality-dialog::backdrop {
  background: #0005;
}
.quality-dialog header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}
.quality-dialog h2 {
  font-size: 20px;
  font-weight: 500;
  margin: 0;
}
.quality-dialog button {
  /* font: inherit; */
  cursor: pointer;
  color: inherit;
}
.quality-dialog header button {
  border: 0;
  background: transparent;
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  border-radius: 8px;
}
.quality-dialog svg {
  width: 20px;
  height: 20px;
}
.quality-song {
  font-size: 13px;
  color: var(--app-text-muted);
  overflow-wrap: anywhere;
  margin: 8px 0 14px;
}
fieldset {
  border: 0;
  margin: 0;
  padding: 0;
  min-width: 0;
}
legend {
  font-size: 13px;
  margin-bottom: 12px;
}
label {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 12px;
  border-radius: 10px;
  cursor: pointer;
}
label:has(input:checked) {
  background: var(--app-selected);
}
input {
  accent-color: var(--app-text);
  flex-shrink: 0;
}
label span {
  min-width: 0;
}
strong {
  font-weight: 500;
  font-size: 14px;
}
small {
  display: block;
  font-size: 12px;
  color: var(--app-text-muted);
  margin-top: 2px;
  line-height: 1.4;
  overflow-wrap: anywhere;
}
.quality-hint {
  color: var(--app-text-muted);
  font-size: 12px;
  line-height: 1.6;
  margin: 10px 0;
}
footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  position: sticky;
  bottom: -24px;
  padding: 12px 0;
  background: var(--app-surface-raised);
}
.quality-confirm {
  border: 1px solid var(--app-border);
  background: var(--app-hover);
  padding: 10px 20px;
  border-radius: 8px;
}
button:disabled {
  opacity: 0.45;
  cursor: default;
}
button:focus-visible,
input:focus-visible {
  outline: 2px solid var(--app-focus);
  outline-offset: 2px;
}
</style>

<style scoped>
.save-options {
  margin-top: 12px;
}
label:has(input:disabled) {
  opacity: 0.5;
  cursor: default;
}
</style>

<style scoped>
.quality-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.quality-row label {
  flex: 1;
}
.compress-toggle {
  border: 0;
  background: transparent;
  padding: 8px 0;
}
.quality-confirm {
  margin-left: auto;
  flex-shrink: 0;
}
</style>
