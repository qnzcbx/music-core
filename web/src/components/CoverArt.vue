<script setup lang="ts">
import { ref, watch } from "vue";
const props = defineProps<{ src?: string | null; alt?: string; loading?: "lazy" | "eager" }>();
const failed = ref(false),
  loaded = ref(false);
watch(
  () => props.src,
  () => {
    failed.value = false;
    loaded.value = false;
  },
);
</script>
<template>
  <span class="cover-art">
    <span class="cover-fallback" aria-hidden="true"><span>♫</span></span>
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
img.cover-loaded {
  opacity: 1;
}
</style>
