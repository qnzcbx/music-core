<script setup lang="ts">
import { ref } from "vue";
import HomeInkBackground from "../features/home/components/HomeInkBackground.vue";
import HomeGreeting from "../features/home/components/HomeGreeting.vue";
import HomeSearch from "../features/home/components/HomeSearch.vue";
const inkText = ref("");
</script>
<template>
  <section class="home-view" aria-label="首页">
    <HomeInkBackground :text="inkText" />
    <div class="home-main"><HomeGreeting /><HomeSearch @draft-change="inkText = $event" /></div>
  </section>
</template>
<style scoped>
.home-view {
  position: relative;
  height: 100%;
  min-height: 0;
  width: 100%;
  display: grid;
  place-items: center;
  overflow: hidden;
  isolation: isolate;
  background: var(--app-bg);
}
.home-main {
  pointer-events: none;
  position: relative;
  z-index: 1;
  width: min(600px, calc(100% - 64px));
  text-align: center;
  transform: translateY(-24px);
}
.home-main :deep(.home-search) {
  pointer-events: auto;
}
@media (max-width: 600px) {
  .home-main {
    width: calc(100% - 36px);
    transform: translateY(-12px);
  }
  .home-main::before {
    inset: -40px -25px;
  }
}
@media (max-height: 440px) {
  .home-main {
    transform: none;
  }
  .home-main :deep(.home-greeting) {
    margin-bottom: 16px;
    font-size: 26px;
  }
  .home-main :deep(.search-hero) {
    height: 50px;
  }
}
</style>
