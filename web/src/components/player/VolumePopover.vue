<script setup lang="ts">
import { ref, watch } from 'vue';
import { Popover, PopoverTrigger, PopoverContent } from '../ui/popover';
import { Slider } from '../ui/slider';
import { useCoreClient } from '../../composables/useCoreClient';
import VolumeIcon from '~icons/lucide/volume-2';
import MuteIcon from '~icons/lucide/volume-x';

const { player } = useCoreClient();
const props = defineProps<{ immersive?: boolean }>();
const emit = defineEmits<{ openChange: [open: boolean] }>();
const opened = ref(false);
watch(opened, (value) => emit('openChange', value));
</script>

<template>
  <Popover v-model:open="opened">
    <PopoverTrigger as-child>
      <button
        aria-label="音量设置"
        :title="`音量 ${Math.round(player.volume.value * 100)}%`"
      >
        <MuteIcon v-if="player.muted.value || !player.volume.value" />
        <VolumeIcon v-else />
      </button>
    </PopoverTrigger>

    <PopoverContent
      :class="{ 'immersive-layer': props.immersive }"
      class="music-layer volume-layer"
      side="top"
      :side-offset="12"
      aria-label="音量设置"
    >
      <Slider
        orientation="vertical"
        :min="0"
        :max="100"
        :step="1"
        :model-value="[Math.round(player.volume.value * 100)]"
        @update:model-value="(value) => player.setVolume((value?.[0] ?? 0) / 100)"
        aria-label="音量"
      />
      <span>{{ Math.round(player.volume.value * 100) }}%</span>
      <button
        @click="player.mute"
        :aria-label="player.muted.value ? '取消静音' : '静音'"
      >
        {{ player.muted.value ? '取消静音' : '静音' }}
      </button>
    </PopoverContent>
  </Popover>
</template>
