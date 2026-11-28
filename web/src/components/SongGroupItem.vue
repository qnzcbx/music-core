<script setup lang="ts">
import SongItem from "./SongItem.vue";
import SongVersionList from "./SongVersionList.vue";
import type { SongGroup } from "../utils/song-group";
import type { SearchEntry as Song } from "../types/music";
import { computed } from "vue";
import DownIcon from "~icons/lucide/chevron-down";
import UpIcon from "~icons/lucide/chevron-up";

const props = defineProps<{
  group: SongGroup;
  activeId?: string;
}>();
const emit = defineEmits<{
  play: [song: Song];
  toggle: [key: string];
}>();

const otherVersions = computed(() =>
  props.group.versions.filter((song) => song.id !== props.group.representative.id),
);

</script>

<template>
  <div
    class="song-group"
    :class="{ 'is-expanded': group.expanded }"
    :data-group-key="group.key"
  >
    <SongItem
      :song="group.representative"
      :selected="activeId === group.representative.id"
      :group-expanded="group.expanded"
      @play="emit('play', $event)"
    >
      <button
        v-if="otherVersions.length"
        class="versions-toggle"
        :aria-expanded="group.expanded"
        :aria-label="`${group.expanded ? '收起版本' : '多版本'} ${group.versions.length} · ${group.title}`"
        :title="group.expanded ? '收起版本' : '展开此曲的所有版本'"
        @click.stop="emit('toggle', group.key)"
      >
        <span>
          {{ group.expanded ? "收起" : `多版本 ${group.versions.length}` }}
        </span>
        <component :is="group.expanded ? UpIcon : DownIcon" aria-hidden="true" />
      </button>
    </SongItem>
    <Transition name="versions-expand">
      <SongVersionList
        v-if="group.expanded"
          :versions="otherVersions"
        :active-id="activeId"
        @play="emit('play', $event)"
      />
    </Transition>
  </div>
</template>

<style scoped>
.song-group {
  min-width: 0;
}
.song-group.is-expanded {
  border-radius: 6px;
  background: var(--app-surface-subtle);
}
.song-group.is-expanded :deep(.song-row) {
  min-height: 66px;
  padding-block: 10px;
}
.song-group.is-expanded > :deep(.song-row) {
  border-start-start-radius: 6px;
  border-start-end-radius: 6px;
}
.versions-toggle {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 5px;
  width: 100%;
  margin: 0;
  padding: 8px 0;
  border: 0;
  background: transparent;
  color: var(--app-text-muted);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
}
.versions-toggle svg {
  width: 16px;
  height: 16px;
}
.versions-toggle:hover {
  color: var(--app-link);
}
.versions-expand-enter-active,
.versions-expand-leave-active {
  transition:
    opacity 0.14s,
    transform 0.14s;
}
.versions-expand-enter-from,
.versions-expand-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
@media (prefers-reduced-motion: reduce) {
  .versions-expand-enter-active,
  .versions-expand-leave-active {
    transition: none;
  }
  .versions-expand-enter-from,
  .versions-expand-leave-to {
    transform: none;
  }
}
</style>
