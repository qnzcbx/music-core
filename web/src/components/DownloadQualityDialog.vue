<script setup lang="ts">
import { ref, watch, nextTick, onScopeDispose } from "vue";
import XIcon from "~icons/lucide/x";
import { useCoreClient } from "../composables/useCoreClient";
import { checkDownloadQuality, desktopDownloads, supportedDownloadQualities } from "../api/downloads";
import { downloadQualitySummary } from "../utils/download-quality";
import { trackIdentity } from "../utils/player-queue";
import type { DownloadQuality, DownloadQualityOption, OutputMode } from "../types/core";
const { downloads } = useCoreClient();
const dialog = ref<HTMLDialogElement>(),
  quality = ref<DownloadQuality>("auto"),
  checking = ref(false),
  submitting = ref(false),
  result = ref<DownloadQualityOption | null>(null),
  error = ref("");
const outputMode = ref<OutputMode>("original");
const choices = ([
  { id: "auto", name: "自动" },
  { id: "standard", name: "标准品质" },
  { id: "high", name: "高品质" },
  { id: "lossless", name: "无损品质" },
] as const).filter((choice) => supportedDownloadQualities.includes(choice.id));
let controller: AbortController | undefined,
  revision = 0,
  origin: HTMLElement | null = null;
function close() {
  if (!submitting.value) downloads.closeChoice();
}
watch(
  () => downloads.downloadSong.value,
  async (song) => {
    if (song) {
      origin = document.activeElement as HTMLElement;
      quality.value = desktopDownloads ? "standard" : "auto";
      await nextTick();
      if (downloads.downloadSong.value && !dialog.value?.open) dialog.value?.showModal();
    } else {
      dialog.value?.close();
      origin?.focus();
    }
  },
);
watch([() => downloads.downloadSong.value, quality], async ([song, selected]) => {
  const token = ++revision;
  controller?.abort();
  result.value = null;
  outputMode.value = "original";
  error.value = "";
  checking.value = false;
  if (!song) return;
  controller = new AbortController();
  checking.value = true;
  try {
    const response = await checkDownloadQuality(
      { identity: trackIdentity(song), quality: selected },
      controller.signal,
    );
    if (token !== revision) return;
    result.value = response;
  } catch (reason) {
    if (token === revision) {
      console.error("音质检测失败", reason);
      error.value = "暂时无法检测音质，请稍后重试";
    }
  } finally {
    if (token === revision) checking.value = false;
  }
});
async function confirm() {
  const song = downloads.downloadSong.value;
  if (!song || submitting.value || checking.value || result.value?.availability !== "available")
    return;
  submitting.value = true;
  try {
    await downloads.create(
      song,
      quality.value,
      outputMode.value,
      result.value?.representation?.codec === "flac" ? "flac" : null,
    );
    downloads.closeChoice();
  } finally {
    submitting.value = false;
  }
}
function estimated(bitrate: number) {
  const duration = downloads.downloadSong.value?.duration;
  let seconds = typeof duration === "number" ? duration : 0;
  if (typeof duration === "string" && /^\d+:\d{2}$/.test(duration)) {
    const parts = duration.split(":").map(Number);
    seconds = parts[0]! * 60 + parts[1]!;
  }
  return seconds > 0
    ? `预计 ${((seconds * bitrate) / 8 / 1048576).toFixed(1)} MB`
    : "大小待保存后确认";
}
function unavailable(option: DownloadQualityOption | null) {
  if (!option) return "暂未发现可用资源";
  return (
    (
      {
        upstream_timeout: "检测超时，请稍后重试",
        access_denied: "当前访问条件下无法下载此音质",
        capability_unsupported: "此来源暂不支持该品质",
        upstream_failure: "服务暂时不可用，请稍后重试",
      } as Record<string, string>
    )[option.errorCode || ""] || "暂未发现可用资源"
  );
}
function describe(option: DownloadQualityOption) {
  return downloadQualitySummary(option.representation);
}
onScopeDispose(() => {
  revision++;
  controller?.abort();
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
      <button aria-label="关闭音质选择" :disabled="submitting" @click="close"><XIcon /></button>
    </header>
    <p class="quality-song">
      {{ downloads.downloadSong.value?.title || downloads.downloadSong.value?.name }} ·
      {{ downloads.downloadSong.value?.artist }}
    </p>
    <fieldset :disabled="submitting">
      <legend>选择音质</legend>
      <label 
        v-for="choice in choices" 
        :key="choice.id"
      >
        <input 
          v-model="quality" 
          type="radio" 
          name="download-quality" 
          :value="choice.id" 
        />
        <span>
          <strong>{{ choice.name }}</strong>
          <small v-if="quality === choice.id" role="status">
            {{
              checking
                ? "正在检测…"
                : error ||
                  (result?.availability === "available" ? describe(result) : unavailable(result))
            }}
          </small>
          <small v-else>选择后检测</small>
        </span>
      </label>
    </fieldset>
    <fieldset
      v-if="
        result?.availability === 'available' &&
        result.representation?.codec === 'flac' &&
        result.representation.lossless
      "
      class="save-options"
      :disabled="submitting"
    >
      <legend>保存方式</legend>
      <label>
        <input 
          v-model="outputMode" 
          type="radio" 
          name="output-mode" 
          value="original" 
        />
        <span>
          <strong>保留原格式</strong>
          <small>{{ describe(result) }}</small>
        </span>
      </label>
      <label>
        <input
          v-model="outputMode"
          type="radio"
          name="output-mode"
          value="mp3_320"
          :disabled="!result.conversion?.available"
        />
        <span>
          <strong>节省空间</strong>
          <small>MP3 320 kbps · {{ estimated(320000) }}</small>
        </span>
      </label>
      <label>
        <input
          v-model="outputMode"
          type="radio"
          name="output-mode"
          value="mp3_192"
          :disabled="!result.conversion?.available"
        />
        <span>
          <strong>更小的文件</strong>
          <small>MP3 192 kbps · {{ estimated(192000) }}</small>
        </span>
      </label>
      <p class="quality-hint">
        {{
          result.conversion?.available
            ? "转换为 MP3 会使用有损编码。"
            : result.conversion?.reason || "本机暂不可转换，仍可保留原格式"
        }}
      </p>
    </fieldset>
    <p class="quality-hint">明确选择的音质不可用时，不会自动降低品质。</p>
    <footer>
      <button
        class="quality-confirm"
        :disabled="checking || submitting || result?.availability !== 'available'"
        @click="confirm"
      >
        {{ submitting ? "正在创建任务…" : "确认下载" }}
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
  justify-content: flex-end;
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
