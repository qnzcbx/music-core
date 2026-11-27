<script setup lang="ts">
import SongItem from "./SongItem.vue";
import SongVersionList from "./SongVersionList.vue";
import type { SongGroup } from "../utils/song-group";
import type { SearchEntry as Song } from "../types/music";
import { computed, onUnmounted, ref, watch } from "vue";
import DownIcon from "~icons/lucide/chevron-down";
import UpIcon from "~icons/lucide/chevron-up";
import { useProviders, providerFor } from "../composables/useProviders";

const props = defineProps<{
  group: SongGroup;
  now: number;
  index: number;
  activeId?: string;
  submitting: boolean;
  preResolveEnabled: boolean;
}>();
const emit = defineEmits<{
  play: [song: Song];
  download: [song: Song];
  playNext: [song: Song, origin: HTMLElement];
  toggle: [key: string];
  eligible: [key: string, eligible: boolean, visible: boolean];
}>();
const container = ref<HTMLElement>();
const { providers } = useProviders();

const otherVersions = computed(() =>
  props.group.versions
    .filter((song) => song.id !== props.group.representative.id)
    .sort((a, b) => {
      const rank = (song: Song) => {
        const index = providers.value.findIndex(
          (p) =>
            p.id ===
            (providerFor(("providerId" in song && song.providerId) || song.source)?.id ??
              song.source),
        );
        return index < 0 ? providers.value.length : index;
      };
      return rank(a) - rank(b);
    }),
);

let observer: IntersectionObserver | undefined;
watch(
  [container, () => props.preResolveEnabled],
  () => {
    observer?.disconnect();
    emit("eligible", props.group.key, false, false);
    if (!props.preResolveEnabled || !container.value || !("IntersectionObserver" in window)) return;
    const root = container.value.closest<HTMLElement>(".app-content");
    const row = container.value.querySelector<HTMLElement>(":scope > .song-row");
    if (!row) return;
    observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          const bounds = root?.getBoundingClientRect() ?? { top: 0, bottom: window.innerHeight };
          // 仅观测主行；展开版本没有新的 observer/budget。
          emit(
            "eligible",
            props.group.key,
            entry.isIntersecting,
            entry.boundingClientRect.top < bounds.bottom &&
              entry.boundingClientRect.bottom > bounds.top,
          );
        }
      },
      { root, rootMargin: "300px 0px", threshold: 0 },
    );
    observer.observe(row);
  },
  { flush: "post" },
);
onUnmounted(() => {
  observer?.disconnect();
  emit("eligible", props.group.key, false, false);
});
</script>

<template>
  <div
    ref="container"
    class="song-group"
    :class="{ 'is-expanded': group.expanded }"
    :data-group-key="group.key"
  >
    <SongItem
      :song="group.representative"
      :now="now"
      :index="index"
      :selected="
        activeId === group.representative.id ||
        (!!activeId &&
          'resolveState' in group.representative &&
          activeId === group.representative.resolvedId)
      "
      :submitting="submitting"
      :group-expanded="group.expanded"
      @play="emit('play', $event)"
      @download="emit('download', $event)"
      @play-next="(song, origin) => emit('playNext', song, origin)"
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
        :now="now"
        :versions="otherVersions"
        :active-id="activeId"
        :submitting="submitting"
        @play="emit('play', $event)"
        @download="emit('download', $event)"
        @play-next="(song, origin) => emit('playNext', song, origin)"
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
