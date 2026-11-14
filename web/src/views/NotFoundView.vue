<script setup lang="ts">
import { RouterLink } from 'vue-router';
import DeadAirSleeve from '../components/DeadAirSleeve.vue';
</script>
<template>
  <section
    class="not-found stage"
    aria-label="页面未找到"
  >
    <div class="composition">
      <DeadAirSleeve />
      <section
        class="story"
        aria-labelledby="error-title"
      >
        <p
          class="eyebrow"
          aria-hidden="true"
        >
          NO SIGNAL · TRACK 404
        </p>
        <p
          class="error-time"
          aria-hidden="true"
        >
          4<span class="track-colon">:</span>0<span class="track-last">4</span>
        </p>
        <div
          class="track-rule"
          aria-hidden="true"
        ></div>
        <h1 id="error-title">页面未找到</h1>
        <p class="description">这条音轨已不在当前唱片上。</p>
        <RouterLink
          class="home-action"
          :to="{ name: 'home' }"
          >回到首页
          <svg
            viewBox="0 0 24 24"
            aria-hidden="true"
            fill="none"
            stroke="currentColor"
            stroke-width="1.7"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <path d="M4 12h15m-6-6 6 6-6 6" />
          </svg>
        </RouterLink>
      </section>
    </div>
  </section>
</template>
<style scoped>
.not-found {
  --paper: var(--app-bg);
  --ink: var(--app-text);
  --muted: var(--app-text-muted);
  --line: var(--app-border-soft);
  --grid: color-mix(in srgb, var(--app-text) 6%, transparent);
  --accent: #a55737;
  --surface: var(--app-surface-raised);
  --frame: var(--app-surface);
  --frame-edge: var(--app-border);
  --button: var(--app-text);
  --button-ink: var(--app-bg);
  --shadow: var(--app-shadow-color);
}
:global(:root[data-theme='dark']) .not-found {
  --accent: #e2a280;
}
.stage {
  position: relative;
  isolation: isolate;
  display: grid;
  align-items: center;
  min-height: 100%;
  padding: 24px clamp(12px, 3vw, 56px);
}
.stage::before {
  content: '';
  position: absolute;
  inset: 0;
  z-index: -1;
  pointer-events: none;
  background-image:
    linear-gradient(90deg, var(--grid) 1px, transparent 1px),
    linear-gradient(var(--grid) 1px, transparent 1px);
  background-size: 24px 24px;
  mask-image: radial-gradient(ellipse 76% 74% at 53% 48%, #000, transparent 92%);
}
.composition {
  width: min(100%, 1120px);
  margin-inline: auto;
  display: grid;
  grid-template-columns: minmax(0, 1.15fr) minmax(0, 0.85fr);
  align-items: center;
  gap: clamp(32px, 6vw, 100px);
}
.story {
  min-width: 0;
  width: 100%;
  justify-self: center;
  text-align: center;
}
.eyebrow {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 12px;
  margin: 0 0 17px;
  color: var(--accent);
  font-size: 11px;
  letter-spacing: 0.21em;
  font-weight: 700;
}
.eyebrow::before {
  content: '';
  width: 26px;
  height: 1px;
  background: currentColor;
}
.error-time {
  color: var(--ink);
  white-space: nowrap;
  margin: 0;
  font:
    400 clamp(96px, 10vw, 162px) / 0.93 Georgia,
    'Times New Roman',
    serif;
  font-variant-numeric: lining-nums;
  letter-spacing: -0.081em;
  padding-inline-end: 0.1em;
}
.track-colon {
  color: var(--accent);
  font-size: 0.72em;
  vertical-align: 10%;
  margin-inline: 0.04em;
}
.track-last {
  font-style: italic;
}
.track-rule {
  width: min(78%, 290px);
  height: 1px;
  margin: 27px auto 25px;
  background: linear-gradient(90deg, var(--accent) 0 24%, var(--line) 24% 100%);
}
.story h1 {
  font-size: clamp(22px, 2vw, 28px);
  line-height: 1.4;
  font-weight: 600;
  margin: 0 0 9px;
  letter-spacing: 0.055em;
}
.description {
  color: var(--muted);
  font-size: 14px;
  line-height: 1.8;
  margin: 0 0 27px;
}
.home-action {
  min-height: 48px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 13px;
  padding: 0 22px 0 25px;
  border-radius: 999px;
  background: var(--button);
  color: var(--button-ink);
  text-decoration: none;
  font-size: 14px;
  box-shadow: 0 8px 16px -8px var(--shadow);
}
.home-action:hover {
  filter: brightness(1.12);
}
.home-action svg {
  width: 17px;
  height: 17px;
}

@media (max-width: 900px) {
  .composition {
    gap: 32px;
  }
}
@media (max-width: 760px) {
  .stage {
    padding: 16px 4px;
  }
  .composition {
    grid-template-columns: 1fr;
    gap: 32px;
  }
  .eyebrow,
  .error-time,
  .track-rule {
    display: none;
  }
  .story h1 {
    font-size: 21px;
    margin-bottom: 3px;
  }
  .description {
    margin-bottom: 16px;
    font-size: 13px;
  }
  .home-action {
    min-height: 44px;
  }
}
</style>
