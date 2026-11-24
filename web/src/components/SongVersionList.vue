<script setup lang="ts">
import SongItem from './SongItem.vue';
import type { SearchEntry as Song, DownloadJob } from '../types/music';

defineProps<{
  versions: Song[];
  now: number;
  activeId?: string;
  submitting: boolean;
  downloadJobs: Record<string, DownloadJob>;
}>();
const emit = defineEmits<{
  play: [song: Song];
  download: [song: Song];
  playNext: [song: Song, origin: HTMLElement];
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
      v-for="(song, index) in versions"
      :key="`${song.source}:${song.id}`"
      :song="song"
      :now="now"
      :index="index"
      version
      :selected="
        activeId === song.id ||
        (!!activeId && 'resolveState' in song && activeId === song.resolvedId)
      "
      :submitting="submitting"
      :job="downloadJobs[song.id]"
      @play="emit('play', $event)"
      @download="emit('download', $event)"
      @play-next="(song, origin) => emit('playNext', song, origin)"
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
