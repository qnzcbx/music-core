<script setup lang="ts">
import { computed } from "vue";
import { useCoreClient } from "../../composables/useCoreClient";
import CoverArt from "../CoverArt.vue";
import TrashIcon from "~icons/lucide/trash-2";
import OrderIcon from "~icons/lucide/list-ordered";
import RepeatIcon from "~icons/lucide/repeat";
import RepeatOneIcon from "~icons/lucide/repeat-1";
import ShuffleIcon from "~icons/lucide/shuffle";
const { player } = useCoreClient();
const { entries, current, navigation } = player.queue;
const modes = [
  { id: "order", label: "顺序播放", icon: OrderIcon },
  { id: "repeat_all", label: "列表循环", icon: RepeatIcon },
  { id: "repeat_one", label: "单曲循环", icon: RepeatOneIcon },
  { id: "shuffle", label: "随机播放", icon: ShuffleIcon },
] as const;
const mode = computed(() => modes.find((m) => m.id === navigation.mode)!);
function cycle() {
  player.queue.setMode(
    modes[(modes.findIndex((m) => m.id === navigation.mode) + 1) % modes.length]!.id,
  );
}
</script>
<template>
  <div class="queue-body">
    <header class="queue-header">
      <div>
        <h2>播放队列</h2>
        <span>{{ entries.length }} 首歌曲</span>
      </div>
      <div class="queue-actions">
        <button 
          :title="mode.label" 
          :aria-label="`当前${mode.label}，切换播放模式`" 
          @click="cycle"
        >
          <component :is="mode.icon" />
        </button>
        <button
          title="清空队列"
          aria-label="清空队列"
          :disabled="!entries.length"
          @click="player.queue.clear"
        >
          <TrashIcon />
        </button>
      </div>
    </header>
    <div 
      class="queue-content" 
      data-reka-swipe-ignore 
      tabindex="0" 
      aria-label="队列歌曲列表"
    >
      <p v-if="!entries.length" class="queue-empty">空空如也</p>
      <div v-else class="queue-list">
        <article v-for="entry in entries" :key="entry.key" :data-current="entry.key === current">
          <div class="queue-cover"><CoverArt :src="entry.metadata.cover" /></div>
          <button
            class="queue-choose"
            :aria-current="entry.key === current ? 'true' : undefined"
            @click="
              entry.key === current && player.selected.value
                ? player.toggle()
                : player.queue.choose(entry)
            "
          >
            <strong>{{ entry.metadata.title }}</strong
            ><small>{{ entry.metadata.artist }}</small></button
          ><button
            :aria-label="`移除 ${entry.metadata.title}`"
            @click="player.queue.remove(entry.key)"
          >
            ×
          </button>
        </article>
      </div>
    </div>
  </div>
</template>
