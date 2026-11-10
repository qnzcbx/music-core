<script setup lang="ts">
import SongItem from './SongItem.vue';
import type { SearchEntry as Song, DownloadJob } from '../types/music';
defineProps<{ versions: Song[]; now: number; activeId?: string; submitting: boolean; downloadJobs: Record<string, DownloadJob> }>();
const emit = defineEmits<{ play: [song: Song]; download: [song: Song]; playNext:[song:Song,origin:HTMLElement] }>();
</script>
<template>
  <TransitionGroup name="version-row" tag="div" class="song-versions" aria-label="歌曲版本">
    <SongItem v-for="(song, index) in versions" :key="`${song.source}:${song.id}`" :song="song" :now="now" :index="index" version
      :selected="activeId === song.id || (!!activeId && 'resolveState' in song && activeId === song.resolvedId)" :submitting="submitting" :job="downloadJobs[song.id]"
      @play="emit('play', $event)" @download="emit('download', $event)" @play-next="(song,origin)=>emit('playNext',song,origin)" />
  </TransitionGroup>
</template>
<style scoped>
.song-versions { padding:0 0 0 18px; margin:0 0 8px 18px; border-left:2px solid var(--app-border-strong); background:var(--app-surface-subtle); }
.song-versions :deep(.song-row) { min-height:68px; }
@media(max-width:600px) { .song-versions { margin-left:4px; padding-left:8px; } }
.song-versions:deep(.download-status) { padding-left: 0; }
.version-row-enter-active { transition: opacity 140ms ease-out, transform 140ms ease-out; }
.version-row-enter-from { opacity: 0; transform: translateY(4px); }
@media (prefers-reduced-motion: reduce) { .version-row-enter-active { transition: none; } .version-row-enter-from { opacity: 1; transform: none; } }
</style>
