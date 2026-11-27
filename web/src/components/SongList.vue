<script setup lang="ts">
import SongGroupItem from "./SongGroupItem.vue";
import type { SongGroup } from "../utils/song-group";
import type { SearchEntry as Song } from "../types/music";

defineProps<{
  songs: Song[];
  groups: SongGroup[];
  busy: boolean;
  activeId?: string;
}>();
const emit = defineEmits<{
  play: [song: Song];
  toggle: [key: string];
}>();
</script>

<template>
  <section class="results">
    <div class="song-list-columns" aria-hidden="true">
      <span>歌曲 / 歌手</span><span></span>
      <span class="album-heading">专辑</span>
      <span class="duration-heading">时长</span>
      <span class="version-heading">版本</span>
    </div>

    <p v-if="!songs.length" class="empty">
      {{ busy ? "正在等待首个来源的候选…" : "搜索后，歌曲会出现在这里。" }}
    </p>
    
    <TransitionGroup name="result-row" tag="div">
      <SongGroupItem
        v-for="group in groups"
        :key="group.key"
        :group="group"
        :active-id="activeId"
        @play="emit('play', $event)"
        @toggle="emit('toggle', $event)"
      />
    </TransitionGroup>
    <slot />
  </section>
</template>

<style scoped>
.results {
  overflow-anchor: none;
}
.song-list-columns {
  display: grid;
  grid-template-columns: minmax(220px, 2fr) 76px minmax(130px, 1fr) 64px 104px;
  gap: 12px;
  padding: 16px 10px;
  border-bottom: 1px solid var(--app-border);
  color: var(--app-text-muted);
  font-size: 11px;
}
.version-heading {
  text-align: right;
}
@media (max-width: 1050px) {
  .song-list-columns {
    grid-template-columns: minmax(0, 1fr) 76px 104px;
    gap: 10px;
  }
  .album-heading,
  .duration-heading {
    display: none;
  }
}
@media (max-width: 600px) {
  .song-list-columns {
    display: flex;
    justify-content: space-between;
    padding-inline: 4px;
  }
  .song-list-columns > span:not(:first-child):not(:last-child) {
    display: none;
  }
}
.result-row-enter-active {
  transition:
    opacity 140ms ease-out,
    transform 140ms ease-out;
}
.result-row-enter-from {
  opacity: 0;
  transform: translateY(4px);
}
@media (prefers-reduced-motion: reduce) {
  .result-row-enter-active {
    transition: none;
  }
  .result-row-enter-from {
    opacity: 1;
    transform: none;
  }
}
</style>
