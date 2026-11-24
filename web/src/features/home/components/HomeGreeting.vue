<script setup lang="ts">
import { homeGreeting } from "../greeting";
const greeting = homeGreeting();
</script>

<template>
  <h1 class="home-greeting">{{ greeting }}</h1>
</template>

<style scoped>
.home-greeting {
  margin: 0 0 32px;
  font:
    400 clamp(30px, 3vw, 40px)/1.5 "Songti SC",
    "STSong",
    "SimSun",
    serif;
  letter-spacing: 0.04em;
  color: var(--app-text);
  text-wrap: balance;
}
@media (max-width: 600px) {
  .home-greeting {
    margin-bottom: 24px;
    font-size: 28px;
  }
}
</style>
