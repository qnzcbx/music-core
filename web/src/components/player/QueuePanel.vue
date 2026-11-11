<script setup lang="ts">
import { ref, watch } from "vue";
import { useMediaQuery } from "@vueuse/core";
import { Popover, PopoverTrigger, PopoverContent } from "../ui/popover";
import { Drawer, DrawerTrigger, DrawerContent, DrawerTitle } from "../ui/drawer";
import QueueList from "./QueueList.vue";
import QueueIcon from "~icons/lucide/list-music";
import { useCoreClient } from "../../composables/useCoreClient";
const { player } = useCoreClient();
const props = defineProps<{ immersive?: boolean; compact?: boolean }>();
const emit = defineEmits<{ openChange: [open: boolean] }>();
const mobile = useMediaQuery("(max-width:760px)"),
  opened = ref(false);
watch(opened, (value) => emit("openChange", value));
</script>
<template>
  <Drawer v-if="mobile" v-model:open="opened">
    <DrawerTrigger as-child>
      <button aria-label="播放队列">
        <QueueIcon />
        <span v-if="!props.compact">{{ player.queue.entries.value.length }}</span>
      </button>
    </DrawerTrigger>

    <DrawerContent
      :class="{ 'immersive-layer': props.immersive }"
      class="music-layer queue-drawer"
      :aria-describedby="undefined"
    >
      <DrawerTitle class="sr-only">播放队列</DrawerTitle>
      <QueueList />
    </DrawerContent>
  </Drawer>

  <Popover v-else v-model:open="opened">
    <PopoverTrigger as-child>
      <button aria-label="播放队列">
        <QueueIcon />
        <span v-if="!props.compact">{{ player.queue.entries.value.length }}</span>
      </button>
    </PopoverTrigger>
    
    <PopoverContent
      :class="{ 'immersive-layer': props.immersive }"
      class="music-layer queue-panel"
      side="top"
      align="end"
      :side-offset="12"
      aria-label="播放队列"
    >
      <QueueList />
    </PopoverContent>
  </Popover>
</template>
