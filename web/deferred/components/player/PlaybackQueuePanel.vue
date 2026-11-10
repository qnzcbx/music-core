<script setup lang="ts">
import { computed } from "vue";
import CloseIcon from "~icons/lucide/x";
import TrashIcon from "~icons/lucide/trash-2";
import SettingsIcon from "~icons/lucide/settings-2";
import CoverArt from "../CoverArt.vue";
import { useLabSession } from "../../composables/useLabSession";
import { queuePresentation } from "../../player/queue-presentation";
import { providerName } from "../../composables/useProviders";
import { NEXT_MEDIA_WINDOW_SECONDS } from "../../composables/useNextMediaPreparation";
import type { QueueEntry } from "../../types/music";
const emit = defineEmits<{ choose: [entry: QueueEntry]; close: [] }>();
// Inject the existing root session. This component never creates an owner.
const { audio, queueController, nextPreparation, persistence, conversions } = useLabSession();
const { queue, currentQueueKey } = audio;
const { navigation } = queueController;
const { enabled, target, status, metrics } = nextPreparation;
const { canConvert, checking } = conversions;
const groups = computed(() =>
  queuePresentation(queue.value, currentQueueKey.value, navigation.value),
);
</script>
<template>
  <section id="play-queue" class="play-queue" aria-label="播放队列">
    <header>
      <div>
        <strong>播放队列</strong><small>{{ queue.length }} 首</small>
      </div>
      <div class="queue-actions">
        <button
          :disabled="!queue.length"
          aria-label="清空队列"
          title="清空队列"
          @click="queueController.clear"
        >
          <TrashIcon aria-hidden="true" /></button
        ><button aria-label="关闭队列" @click="emit('close')">
          <CloseIcon aria-hidden="true" />
        </button>
      </div>
    </header>
    <label class="queue-mode"
      >播放模式<select
        aria-label="播放模式"
        :value="navigation.mode"
        @change="
          queueController.setMode(
            ($event.target as HTMLSelectElement).value as typeof navigation.mode,
          )
        "
      >
        <option value="order">顺序播放</option>
        <option value="shuffle">随机播放</option>
        <option value="repeat_all">列表循环</option>
        <option value="repeat_one">单曲循环</option>
      </select></label
    >
    <p v-if="!queue.length" class="queue-empty">
      队列还是空的<br /><small>在搜索结果中播放一首歌，或安排下一首。</small>
    </p>
    <div v-else class="queue-sections">
      <section v-for="group in groups" :key="group.id" :data-queue-section="group.id">
        <h3>
          {{ group.title }} <span>{{ group.entries.length }}</span>
        </h3>
        <ol>
          <li
            v-for="song in group.entries"
            :key="song.key"
            :data-queue-key="song.key"
            :data-up-next="
              navigation.upNextKeys.includes(song.key)
                ? navigation.upNextKeys.indexOf(song.key) + 1
                : undefined
            "
          >
            <button
              class="queue-select"
              :aria-current="song.key === currentQueueKey ? 'true' : undefined"
              :title="`${song.metadata.title} · ${song.metadata.artist}`"
              @click="emit('choose', song)"
            >
              <CoverArt :src="song.metadata.cover" loading="lazy" />
              <span class="queue-meta"
                ><strong>{{ song.metadata.title }}</strong
                ><small
                  >{{ song.metadata.artist }} · {{ providerName(song.track.providerId) }}</small
                ></span
              >
              <small v-if="song.key === currentQueueKey" class="current-badge">当前</small>
              <small v-if="navigation.upNextKeys.includes(song.key)" class="priority-badge">{{
                navigation.upNextKeys.indexOf(song.key) === 0
                  ? "下一首"
                  : `优先 ${navigation.upNextKeys.indexOf(song.key) + 1}`
              }}</small>
            </button>
            <button
              class="queue-remove"
              :aria-label="`移除 ${song.metadata.title}`"
              @click="queueController.remove(song.key)"
            >
              <CloseIcon aria-hidden="true" />
            </button>
          </li>
        </ol>
      </section>
    </div>
    <details class="playback-settings">
      <summary><SettingsIcon aria-hidden="true" />播放设置</summary>
      <label class="queue-preparation-toggle"
        ><input
          v-model="enabled"
          type="checkbox"
          aria-describedby="next-preparation-help"
        />提前准备下一首</label
      >
      <p id="next-preparation-help">
        接近结束时获取下一首资源，减少切歌等待；可能产生额外网络请求。
      </p>
      <p v-if="enabled" data-next-preparation-summary>
        临近结束 {{ NEXT_MEDIA_WINDOW_SECONDS }} 秒内准备 · 命中 {{ metrics.hits }} · 未使用
        {{ metrics.unused }} · 失败 {{ metrics.failures
        }}<span v-if="navigation.mode === 'repeat_one'"> · 单曲循环保持当前媒体</span>
      </p>
      <p
        v-if="target && status"
        :data-preparation-status="nextPreparation.preparation.value?.status ?? 'waiting'"
      >
        {{ target.metadata.title }} · {{ status }}
      </p>
      <p v-if="navigation.upNextKeys.length && navigation.mode === 'repeat_one'">
        单曲循环中，已安排的下一首需手动切换或更改模式。
      </p>
      <button
        v-if="canConvert"
        :disabled="checking"
        @click="
          emit('close');
          conversions.open();
        "
      >
        {{ checking ? "检测中…" : "转换当前歌曲格式" }}
      </button>
      <p v-if="persistence.message.value" role="status">{{ persistence.message.value }}</p>
    </details>
  </section>
</template>
<style scoped>
.play-queue {
  width: min(380px, calc(100vw - 32px));
  font-size: 13px;
}
header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 10px 12px;
}
header > div:first-child {
  display: flex;
  align-items: baseline;
  gap: 10px;
}
small {
  color: var(--app-text-muted);
  font-size: 11px;
}
.queue-actions {
  display: flex;
  gap: 4px;
}
.queue-actions button,
.queue-remove {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  flex-shrink: 0;
}
.queue-mode {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 10px 12px;
  color: var(--app-text-muted);
  font-size: 12px;
  border-bottom: 1px solid var(--app-border-soft);
}
.queue-mode select {
  max-width: 65%;
  border: 0;
  background: var(--app-surface-raised);
  color: var(--app-link);
  padding: 6px;
  font: inherit;
  border-radius: 6px;
}
.queue-sections {
  max-height: min(390px, calc(100dvh - 330px));
  min-height: 80px;
  overflow: auto;
  overscroll-behavior: contain;
}
h3 {
  margin: 12px 10px 4px;
  color: var(--app-text-muted);
  font-size: 11px;
  font-weight: 500;
}
h3 span {
  margin-left: 4px;
}
ol {
  padding: 0;
  margin: 0;
  list-style: none;
}
li {
  display: flex;
  align-items: center;
  min-width: 0;
}
.queue-select {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 1;
  min-width: 0;
  padding: 8px;
  text-align: left;
}
.queue-select[aria-current] {
  background: var(--app-hover);
}
.queue-select :deep(.cover-art) {
  width: 36px;
  height: 36px;
  flex-shrink: 0;
  border-radius: 5px;
}
.queue-meta {
  flex: 1;
  min-width: 0;
}
.queue-meta strong,
.queue-meta small {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.queue-meta strong {
  font-size: 12px;
  font-weight: 500;
  margin-bottom: 4px;
}
.current-badge,
.priority-badge {
  font-size: 10px;
  color: var(--app-link);
  white-space: nowrap;
}
.queue-empty {
  padding: 25px 10px;
  line-height: 2;
  text-align: center;
}
.playback-settings {
  border-top: 1px solid var(--app-border-soft);
  padding: 10px;
  color: var(--app-text-muted);
  font-size: 11px;
}
summary {
  display: flex;
  align-items: center;
  gap: 7px;
  cursor: pointer;
  width: fit-content;
  padding: 4px 0;
}
summary::-webkit-details-marker {
  display: none;
}
.queue-preparation-toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 10px;
  color: var(--app-text);
}
.playback-settings p {
  font-size: 11px;
  line-height: 1.7;
  margin: 8px 0;
}
.playback-settings button {
  padding: 8px;
}
@media (max-height: 500px) {
  .queue-sections {
    max-height: 130px;
  }
}
</style>
