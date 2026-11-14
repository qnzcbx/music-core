<script setup lang="ts">
import { inject, onMounted, onBeforeUnmount, ref } from 'vue';
import { APPEARANCE, type Appearance } from '../appearance/theme';
import { drawDeadAirCover } from '../utils/dead-air-cover';

const appearance = inject<Appearance>(APPEARANCE);
const canvas = ref<HTMLCanvasElement>();
let observer: ResizeObserver | undefined;
let unsubscribe: (() => void) | undefined;

function render() {
  const element = canvas.value;
  const context = element?.getContext('2d');
  if (!element || !context) return;
  const { width, height } = element.getBoundingClientRect();
  if (!width || !height) return;
  const ratio = Math.min(2, window.devicePixelRatio || 1);
  element.width = Math.round(width * ratio);
  element.height = Math.round(height * ratio);
  context.setTransform(element.width / width, 0, 0, element.height / height, 0, 0);
  drawDeadAirCover(context, width, height, appearance?.effective === 'dark');
}

onMounted(() => {
  observer = new ResizeObserver(render);
  if (canvas.value) observer.observe(canvas.value);
  unsubscribe = appearance?.subscribe(render);
  render();
});
onBeforeUnmount(() => {
  observer?.disconnect();
  unsubscribe?.();
});
</script>
<template>
  <figure
    class="sleeve"
    aria-label="Dead Air 试压盘封套"
  >
    <div
      class="art"
      aria-hidden="true"
    >
      <canvas
        class="record"
        ref="canvas"
      ></canvas>
      <div class="sticker">
        AFTERTONE ARCHIVE <em>AT-404</em><span>TEST PRESSING · NO SIGNAL</span>
      </div>
      <div class="rpm">33⅓ RPM<br />MONO</div>
      <div class="matrix">MATRIX // AT-000-404-NULL</div>
      <svg
        class="signature"
        viewBox="0 0 386 113"
      >
        <title>Dead Air</title>
        <path
          stroke-width="4.1"
          d="
              M15 89 C24 78 36 61 47 39 C56 22 69 9 74 15 C81 26 56 68 44 78
              C36 84 27 88 20 85 C27 79 42 76 56 80 C82 88 106 67 100 45
              C97 31 79 32 65 43
              M55 81 C76 80 98 80 111 71 C119 66 116 59 110 61 C101 64 94 77 101 82
              C108 88 121 80 134 68
              M147 66 C142 56 127 63 122 76 C117 88 130 89 143 75 L152 62 C145 73 142 81 147 83 C153 86 167 74 175 66
              M189 66 C181 57 167 65 162 77 C157 87 169 88 181 77 C192 65 211 32 217 20
              C222 11 221 10 217 14 C205 25 187 59 182 77 C179 88 191 87 205 75
              M220 85 C234 71 258 35 281 17 C291 9 294 12 290 23 C286 37 272 57 263 73
              C257 83 257 88 264 85 C274 81 282 73 289 67
              M226 65 C239 60 260 58 278 58
              M302 62 C296 70 287 82 292 86 C297 91 311 78 322 68
              M312 47 L314 44
              M310 85 C321 75 324 65 328 62 C330 61 329 69 333 70 C339 72 343 64 348 63
              C347 68 337 82 345 84 C354 86 368 77 381 69
              M21 108 C31 100 36 105 43 107 C48 109 53 105 60 101"
        />
        <path
          stroke-width="1.7"
          opacity=".75"
          d="M16 90 C41 87 47 85 58 82 M218 87 C224 84 226 81 228 76 M268 84 C272 82 277 78 280 76"
        />
      </svg>
      <svg
        class="flourish"
        viewBox="0 0 300 25"
        preserveAspectRatio="none"
      >
        <path d="M2 21 C90 11 203 9 296 4 C252 8 192 14 137 19" />
      </svg>
      <div class="caption">FREQUENCY NOT FOUND · 04:04</div>
      <div class="seal">VOID<br />404</div>
    </div>
    <figcaption class="catalog">
      <span>ARCHIVE / 000</span><span>04:04 · NO SIGNAL</span>
    </figcaption>
  </figure>
</template>
<style scoped>
.sleeve {
  width: min(100%, 550px, max(280px, calc(100cqh - 110px)));
  margin: 0;
  justify-self: center;
  padding: 11px;
  border-radius: 16px;
  border: 1px solid var(--frame-edge);
  background: linear-gradient(135deg, var(--surface), var(--frame));
  box-shadow:
    inset 0 0 0 3px var(--paper),
    0 24px 44px -19px var(--shadow);
}
.art {
  container-type: inline-size;
  position: relative;
  isolation: isolate;
  aspect-ratio: 1;
  border-radius: 8px;
  overflow: hidden;
  background: radial-gradient(ellipse at 30% 20%, #b29c7b, #545449 75%, #3e443e);
}
.record {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  display: block;
}
.sticker,
.rpm,
.matrix,
.caption,
.seal,
.catalog,
.eyebrow {
  font-family: ui-monospace, Consolas, 'Liberation Mono', monospace;
}
.sticker {
  position: absolute;
  top: 8%;
  left: 7.6%;
  padding: 1.35cqw 2cqw 1.15cqw;
  background: #f1e7d4;
  color: #30362e;
  border-radius: 2px;
  font-size: 2cqw;
  font-weight: 700;
  line-height: 1.44;
  letter-spacing: 0.13em;
  transform: rotate(-1.4deg);
  box-shadow:
    0 2px 6px #221b1452,
    inset 0 0 0 1px #6f625235;
}
.sticker em {
  font-style: normal;
  color: #8a492a;
}
.sticker span {
  display: block;
  margin-top: 0.55cqw;
  padding-top: 0.65cqw;
  border-top: 1px solid #4c3b2933;
}
.rpm {
  position: absolute;
  top: 8.5%;
  right: 7.5%;
  color: #f3e8d3d9;
  text-align: right;
  font-size: 2.15cqw;
  font-weight: 700;
  line-height: 1.45;
  letter-spacing: 0.16em;
}
.matrix {
  position: absolute;
  right: 6%;
  top: 27%;
  writing-mode: vertical-rl;
  color: #f8e6cf9e;
  font-size: 1.9cqw;
  letter-spacing: 0.23em;
}
.signature {
  position: absolute;
  left: 5.5%;
  bottom: 24%;
  width: 77%;
  overflow: visible;
  transform: rotate(-3.6deg);
  color: #fff0d6;
  filter: drop-shadow(0 2px 2px #1a1e17aa);
}
.signature path {
  fill: none;
  stroke: currentColor;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.flourish {
  position: absolute;
  bottom: 11%;
  left: 6%;
  width: 80%;
  height: 8%;
  overflow: visible;
}
.flourish path {
  fill: none;
  stroke: #edbd8bab;
  stroke-width: 1.35;
  stroke-linecap: round;
}
.caption {
  position: absolute;
  bottom: 9.1%;
  left: 7.6%;
  font-size: 1.95cqw;
  font-weight: 700;
  color: #f4e8d4d9;
  letter-spacing: 0.17em;
}
.seal {
  position: absolute;
  right: 7.3%;
  bottom: 6.6%;
  width: 10.4%;
  aspect-ratio: 1;
  display: grid;
  place-content: center;
  border-radius: 50%;
  text-align: center;
  border: 1px solid #fbe9cd70;
  color: #f4e8d4e0;
  transform: rotate(8deg);
  font-size: 2.45cqw;
  font-weight: 700;
  line-height: 1.07;
}
.catalog {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  padding: 14px 6px 4px;
  color: var(--muted);
  font-size: 10px;
  letter-spacing: 0.14em;
}
.catalog span:last-child {
  color: var(--accent);
}

@media (max-width: 760px) {
  .sleeve {
    width: min(100%, 330px);
    padding: 8px;
    border-radius: 12px;
  }
  .catalog {
    padding: 9px 3px 2px;
    font-size: 8px;
  }
}
</style>
