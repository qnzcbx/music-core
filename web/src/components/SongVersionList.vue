<script setup lang="ts">
import SongItem from './SongItem.vue';
import type { SearchEntry as Song } from '../types/music';

defineProps<{
  versions: Song[];
  activeId?: string;
}>();
const emit = defineEmits<{
  play: [song: Song];
}>();
</script>

<template>
  <TransitionGroup
    name="version-row"
    tag="div"
    class="song-versions"
    aria-label="歌曲版本"
  >
    <SongItem
      v-for="song in versions"
      :key="song.id"
      :song="song"
      version
      :selected="activeId === song.id"
      @play="emit('play', $event)"
    />
  </TransitionGroup>
</template>

<style scoped>
.song-versions :deep(.song-row:last-child) {
  border-end-start-radius: 6px;
  border-end-end-radius: 6px;
}
.version-row-enter-active {
  transition:
    opacity 140ms ease-out,
    transform 140ms ease-out;
}
.version-row-enter-from {
  opacity: 0;
  transform: translateY(4px);
}
@media (prefers-reduced-motion: reduce) {
  .version-row-enter-active {
    transition: none;
  }
  .version-row-enter-from {
    opacity: 1;
    transform: none;
  }
}
</style>
