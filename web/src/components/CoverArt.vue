<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { CLOVER_COVER, displayedCover } from '../utils/displayed-cover';
const emit = defineEmits<{ displayed: [url: string | null] }>();
const props = defineProps<{ src?: string | null; cloverFallback?: boolean; alt?: string; loading?: "lazy" | "eager" }>();
const fallbackLoaded = ref(false);
const failed = ref(false),
  loaded = ref(false);
watch(
  () => props.src,
  () => {
    failed.value = false;
    loaded.value = false;
  },
  { flush: "sync" },
);
const displayed = computed(() => displayedCover(props.src, loaded.value ? 'loaded' : failed.value ? 'failed' : 'pending',
  !!props.cloverFallback, fallbackLoaded.value));
watch(displayed, url => emit('displayed', url), { immediate: true });
</script>
<template>
  <span class="cover-art">
    <span class="cover-fallback" aria-hidden="true">
      <img v-if="cloverFallback && !loaded" class="clover-placeholder"
        :src="CLOVER_COVER" alt="" :loading="loading" @load="fallbackLoaded = true" />
      <span v-else>♫</span>
    </span>
    <img
      :key="src ?? ''"
      v-if="src && !failed"
      :src="src"
      :alt="alt ?? ''"
      :loading="loading"
      :class="{ 'cover-loaded': loaded }"
      referrerpolicy="no-referrer"
      @load="loaded = true"
      @error="failed = true"
    />
  </span>
</template>
<style scoped>
.cover-art {
  position: relative;
  display: block;
  width: 100%;
  height: 100%;
  overflow: hidden;
  border-radius: inherit;
}
.cover-fallback {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  background: repeating-radial-gradient(circle at 50% 50%, var(--app-cover-base) 0 5px, var(--app-cover-line) 6px 9px);
  color: var(--app-text-muted);
}
.cover-fallback span {
  font-size: clamp(28px, 3vw, 30px);
}
img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  opacity: 0;
}
img.cover-loaded, img.clover-placeholder {
  opacity: 1;
}
</style>
