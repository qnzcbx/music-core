// 从 smoky-vinyl-v2 原型提取的静态材质，不包含播放器、封面或动画循环。
export const WIDE_COVER_RATIO = 0.604;
export const VINYL_PRESETS = {
  smoky: {
    name: '烟灰流纹胶圈 · 理想态',
    baseRGB: [122, 122, 127],
    collarRGB: [119, 119, 125],
    rimRGB: [115, 115, 121],
    alphaOuter: 0.81,
    alphaCollar: 0.91,
  },
  frost: {
    name: '冰透雾银胶圈 · 半透',
    baseRGB: [176, 184, 192],
    collarRGB: [132, 144, 158],
    rimRGB: [138, 146, 156],
    alphaOuter: 0.84,
    alphaCollar: 0.78,
  },
  amber: {
    name: '琥珀流金胶圈 · 玳瑁',
    baseRGB: [152, 132, 108],
    collarRGB: [112, 94, 76],
    rimRGB: [104, 86, 68],
    alphaOuter: 0.93,
    alphaCollar: 0.88,
  },
  obsidian: {
    name: '曜石黑胶 · 180g 母带',
    baseRGB: [52, 55, 60],
    collarRGB: [36, 40, 46],
    rimRGB: [28, 30, 34],
    alphaOuter: 0.98,
    alphaCollar: 0.95,
  },
  glacier: {
    name: '冰川蓝',
    baseRGB: [120, 166, 190],
    collarRGB: [92, 131, 151],
    rimRGB: [85, 129, 159],
    alphaOuter: 0.82,
    alphaCollar: 0.9,
  },
  turquoise: {
    name: '松石绿',
    baseRGB: [74, 151, 137],
    collarRGB: [57, 112, 105],
    rimRGB: [47, 111, 100],
    alphaOuter: 0.87,
    alphaCollar: 0.9,
  },
  violet: {
    name: '烟紫',
    baseRGB: [143, 129, 158],
    collarRGB: [114, 101, 132],
    rimRGB: [104, 91, 125],
    alphaOuter: 0.84,
    alphaCollar: 0.91,
  },
  lemon: {
    name: '柠黄',
    baseRGB: [209, 198, 93],
    collarRGB: [169, 158, 65],
    rimRGB: [153, 141, 53],
    alphaOuter: 0.83,
    alphaCollar: 0.9,
  },
  rose: {
    name: '玫瑰红',
    baseRGB: [187, 104, 130],
    collarRGB: [146, 78, 100],
    rimRGB: [135, 68, 91],
    alphaOuter: 0.87,
    alphaCollar: 0.92,
  },
};

const PERM = new Uint8Array(512);
(() => {
  const p = new Uint8Array(256);
  for (let i = 0; i < 256; i++) p[i] = i;
  let seed = 1337;
  for (let i = 255; i > 0; i--) {
    seed = (seed * 16807) % 2147483647;
    const j = seed % (i + 1);
    const tmp = p[i];
    p[i] = p[j];
    p[j] = tmp;
  }
  for (let i = 0; i < 512; i++) PERM[i] = p[i & 255];
})();

function fade(t) {
  return t * t * t * (t * (t * 6 - 15) + 10);
}
function lerp(a, b, t) {
  return a + t * (b - a);
}
function grad2(hash, x, y) {
  const h = hash & 7;
  const u = h < 4 ? x : y;
  const v = h < 4 ? y : x;
  return (h & 1 ? -u : u) + (h & 2 ? -2.0 * v : 2.0 * v);
}

function noise2D(x, y) {
  const X = Math.floor(x) & 255;
  const Y = Math.floor(y) & 255;
  const xf = x - Math.floor(x);
  const yf = y - Math.floor(y);
  const u = fade(xf);
  const v = fade(yf);
  const aa = PERM[PERM[X] + Y];
  const ab = PERM[PERM[X] + Y + 1];
  const ba = PERM[PERM[X + 1] + Y];
  const bb = PERM[PERM[X + 1] + Y + 1];
  const x1 = lerp(grad2(aa, xf, yf), grad2(ba, xf - 1, yf), u);
  const x2 = lerp(grad2(ab, xf, yf - 1), grad2(bb, xf - 1, yf - 1), u);
  return 0.5 + 0.35 * lerp(x1, x2, v);
}

// 预计算同心沟槽。每一道压痕都有暗肩和细亮边，深浅、间距不做等比重复。
const clamp01 = (x) => Math.max(0, Math.min(1, x));
const gauss = (x) => Math.exp(-x * x);
function smooth(lo, hi, x) {
  const k = clamp01((x - lo) / (hi - lo));
  return k * k * (3 - 2 * k);
}
function rnd(n) {
  n = Math.imul(n ^ (n >>> 16), 0x45d9f3b);
  n = Math.imul(n ^ (n >>> 16), 0x45d9f3b);
  return ((n ^ (n >>> 16)) >>> 0) / 4294967296;
}

const SAMPLES = 2048;
const SEAT = 0.153;
const mainZones = [0.268, 0.344, 0.472, 0.577, 0.643, 0.748, 0.827, 0.902];
const fineCuts = [];
for (let i = 0, t = 0.186; t < 0.943; i++) {
  fineCuts.push([t, 0.0009 + rnd(i + 310) * 0.0014, 0.9 + rnd(i + 900) * 2.4]);
  t += 0.008 + rnd(i + 71) * 0.013;
}
const profile = Array.from({ length: SAMPLES }, (_, i) => {
  const t = i / (SAMPLES - 1);
  const seat = 1 - smooth(SEAT - 0.008, SEAT + 0.009, t);
  const lip = smooth(0.943, 0.962, t);
  const shoulder = gauss((t - 0.937) / 0.023);
  const bevel = lip * (14 - 5 * smooth(0.984, 0.999, t)) + 7 * gauss((t - 0.994) / 0.008);
  let cut = 0;
  for (const [at, w, d] of fineCuts) {
    if (Math.abs(at - t) < 0.013)
      cut += d * (0.7 * gauss((t - at - w) / w) - gauss((t - at + w * 0.6) / (w * 1.4)));
  }
  for (let j = 0; j < mainZones.length; j++) {
    const at = mainZones[j];
    const width = 0.0042 + rnd(j + 15) * 0.0031;
    cut +=
      (5.5 + rnd(j + 35) * 5.7) *
      (gauss((t - at) / width) - 0.63 * gauss((t - at + width * 1.35) / (width * 1.3)));
  }
  for (const at of [0.024, 0.047, 0.077, 0.108, 0.137]) {
    cut += 1.65 * (gauss((t - at) / 0.0032) - 0.72 * gauss((t - at - 0.004) / 0.0034));
  }
  const shaping =
    1.5 * gauss((t - 0.52) / 0.31) +
    5 * shoulder -
    bevel -
    4 * gauss((t - 0.01) / 0.012) +
    2.7 * gauss((t - SEAT + 0.02) / 0.01);
  return { seat, lip, cut, shaping };
});

// 流纹用整圆连续的域变形和几组局部流路。特征位置从参考图取样，
// 纹理本身为程序生成，不拼接截图。只在分辨率、环宽变更时重建纹理场。

export function buildRingField(size, ratio) {
  const half = size / 2;
  const inner = half * ratio;
  const span = half - inner;
  const len = size * size;
  const radiusIdx = new Uint16Array(len);
  const flow = new Float32Array(len);
  const grooveLight = new Float32Array(len);
  const edge = new Uint8Array(len);
  const TAU = Math.PI * 2;
  function delta(a, b) {
    let d = a - b;
    if (d > Math.PI) d -= TAU;
    if (d < -Math.PI) d += TAU;
    return d;
  }
  for (let y = 0; y < size; y++) {
    const dy = y + 0.5 - half;
    for (let x = 0; x < size; x++) {
      const dx = x + 0.5 - half;
      const r = Math.sqrt(dx * dx + dy * dy);
      if (r < inner - 2 || r > half + 1) continue;
      const i = y * size + x;
      const t = clamp01((r - inner) / span);
      edge[i] = 255 * clamp01(half - r + 0.5) * clamp01(r - inner + 1.7);
      const k = Math.round(t * (SAMPLES - 1));
      radiusIdx[i] = k;
      const { seat, lip } = profile[k];
      const a = Math.atan2(dy, dx);
      const c = dx / r,
        s = dy / r;
      const slow = noise2D(c * 2.15 + t * 0.38 + 8.7, s * 2.15 - t * 0.57 + 1.2) - 0.5;
      const swell =
        noise2D(c * 5.3 + t * 1.2 + slow * 1.1 + 3.5, s * 5.3 - t * 1.6 + slow * 1.9 + 6.1) - 0.5;
      const draw = a + 0.084 * t + slow * 0.15;
      const u = Math.cos(draw),
        v = Math.sin(draw);
      const wisps = noise2D(u * 16.5 + t * 0.91 + 4.2, v * 16.5 - t * 1.2 + 3.6) - 0.5;
      const strands = noise2D(u * 49 + slow * 2.0 + t * 0.75, v * 49 + swell * 2.1 - t * 1.6) - 0.5;
      const grain = (rnd(i + 127) - 0.5) * 0.95;
      const mist = noise2D(c * 10.2 + t * 6.2 + swell * 2.6, s * 10.2 - t * 3.9 + slow * 2.1) - 0.5;
      let body =
        slow * 11 +
        swell * 12 +
        mist * 16 +
        wisps * (6 + 8 * smooth(0.61, 0.98, t)) +
        strands * (3 + 10 * smooth(0.66, 0.96, t));

      // 左上拖痕的尾部逐渐化开，水平细纹在左缘不完全连续。
      const upper = delta(a, -2.795 + 0.32 * t + 0.01 * Math.sin(t * 19));
      body -=
        (19 * gauss(upper / (0.006 + 0.008 * t)) + 7 * gauss((upper - 0.013) / 0.026)) *
        smooth(0.273, 0.327, t) *
        (1 - smooth(0.91, 1.02, t)) *
        (0.93 + mist * 1.25);
      const left = delta(a, -3.127 - 0.023 * Math.sin(t * 3.2) + 0.007 * Math.sin(t * 10));
      body -=
        (11 * gauss(left / 0.0085) + 4.1 * gauss((left + 0.008) / 0.024)) *
        smooth(0.25, 0.46, t) *
        (0.88 + wisps * 0.85);

      // 下方的压制褶皱要有聚有散，细条跨过唱片声槽，而不是再叠一圈粗环。
      const fan = delta(a, 1.53 + 0.08 * t + 0.023 * Math.sin(t * 10.3 + 0.85) + 0.04 * slow);
      const folds = fan * (112 + t * 70) + swell * 9 + mist * 2;
      const foldEnvelope =
        gauss(fan / 0.119) * smooth(0.23, 0.49, t) * (1 - 0.33 * smooth(0.91, 1, t));
      body +=
        (Math.sin(folds) * 3.8 +
          Math.sin(folds * 0.51 + 1.4) * 3 -
          15 * gauss((fan + 0.022) / 0.066) -
          16 * gauss((fan + 0.023) / 0.013) * smooth(0.66, 0.97, t)) *
        foldEnvelope;
      const lower = delta(a, 1.92 - 0.105 * t);
      body -= 12 * gauss(lower / 0.105) * gauss((t - 0.46) / 0.13);
      const bend = delta(a, 2.56 + 0.36 * (t - 0.48));
      body -=
        (12 * gauss(bend / 0.05) + 5 * gauss((bend - 0.08) / 0.035)) * gauss((t - 0.48) / 0.31);
      body += gauss((t - 0.67) / 0.12) * gauss(delta(a, 1.7) / 0.28) * 8;

      flow[i] = body * (1 - 0.88 * seat) * (1 - 0.34 * lip) + grain;
      grooveLight[i] = 1.04 + 0.68 * mist + 0.42 * swell;
    }
  }
  return { size, ratio, radiusIdx, flow, grooveLight, edge, pixels: new ImageData(size, size) };
}

export function paintRing(ctx, field, preset) {
  const { radiusIdx, flow, grooveLight, edge, pixels } = field;
  const out = pixels.data;
  const p = VINYL_PRESETS[preset];
  const tint = p.collarRGB;
  const colors = profile.map(({ seat, lip, shaping, cut }) => ({
    r:
      lerp(
        lerp(p.baseRGB[0], p.rimRGB[0], lip * 0.28),
        lerp(p.collarRGB[0], tint[0], 0.024),
        seat,
      ) + shaping,
    g:
      lerp(
        lerp(p.baseRGB[1], p.rimRGB[1], lip * 0.28),
        lerp(p.collarRGB[1], tint[1], 0.024),
        seat,
      ) + shaping,
    b:
      lerp(
        lerp(p.baseRGB[2], p.rimRGB[2], lip * 0.28),
        lerp(p.collarRGB[2], tint[2], 0.024),
        seat,
      ) + shaping,
    opacity: lerp(p.alphaOuter, p.alphaCollar, seat) + (1 - p.alphaOuter) * lip * 0.55,
    cut: cut * 0.76,
  }));
  const materialScale = preset === 'obsidian' ? 0.68 : 1;
  for (let i = 0; i < edge.length; i++) {
    if (!edge[i]) continue;
    const p = colors[radiusIdx[i]];
    const f = flow[i] * 0.82 * materialScale;
    const d = f + p.cut * grooveLight[i];
    const j = i * 4;
    out[j] = p.r + d;
    out[j + 1] = p.g + d;
    out[j + 2] = p.b + d;
    out[j + 3] = Math.min(1, Math.max(0.55, p.opacity - f * 0.002)) * edge[i];
  }
  ctx.putImageData(pixels, 0, 0);
}
