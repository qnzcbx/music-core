// V2 的角向颜色、径向沟槽和微颗粒；不携带示例曲目或预写色样。
const clamp = (v) => Math.max(0, Math.min(1, v));
const mix = (a, b, t) => a + (b - a) * t;
const smooth = (a, b, x) => {
  const t = clamp((x - a) / (b - a));
  return t * t * (3 - 2 * t);
};
function cubicColor(stops, a, channel) {
  const n = stops.length,
    i = Math.floor(a),
    x = a - i;
  const p = stops[(i + n - 1) % n][channel],
    q = stops[i % n][channel];
  const r = stops[(i + 1) % n][channel],
    s = stops[(i + 2) % n][channel];
  return q + 0.5 * x * (r - p + x * (2 * p - 5 * q + 4 * r - s + x * (3 * q - 3 * r + s - p)));
}
function grainAt(i) {
  i = Math.imul(i ^ (i >>> 16), 0x45d9f3b);
  i = Math.imul(i ^ (i >>> 16), 0x45d9f3b);
  return ((i ^ (i >>> 16)) >>> 0) / 4294967296;
}
const cuts = [];
for (let i = 0, pos = 0.06; pos < 0.95; i++) {
  cuts.push([pos, 0.0038 + grainAt(i + 46) * 0.0036, 0.6 + grainAt(i + 21) * 1.7]);
  pos += 0.014 + grainAt(i + 1) * 0.016;
}
for (const pos of [0.217, 0.335, 0.531, 0.662, 0.789, 0.884]) cuts.push([pos, 0.0065, 2.4]);
const ridge = (x) => Math.exp(-x * x);
const radial = Array.from({ length: 1024 }, (_, i) => {
  const t = i / 1023;
  let g = 0;
  for (const [p, w, d] of cuts) {
    if (Math.abs(t - p) < 0.024) g += d * (ridge((t - p) / w) - 0.76 * ridge((t - p + w) / w));
  }
  return {
    groove: g * smooth(0.016, 0.105, t) * (1 - smooth(0.912, 0.985, t)),
    edge:
      -14 * smooth(0.936, 0.982, t) +
      7 * ridge((t - 0.955) / 0.017) +
      3 * ridge((t - 0.991) / 0.008) -
      3.5 * ridge(t / 0.029),
  };
});

export function coverSamples(img, palette) {
  const scratch = document.createElement('canvas');
  scratch.width = scratch.height = 64;
  const c = scratch.getContext('2d', { willReadFrequently: true });
  const side = Math.min(img.naturalWidth, img.naturalHeight);
  c.drawImage(
    img,
    (img.naturalWidth - side) / 2,
    (img.naturalHeight - side) / 2,
    side,
    side,
    0,
    0,
    64,
    64,
  );
  const pixels = c.getImageData(0, 0, 64, 64).data;
  return Array.from({ length: 16 }, (_, i) => {
    const a = (i / 16) * Math.PI * 2,
      rgb = [0, 0, 0];
    let n = 0;
    for (let j = -3; j <= 3; j++)
      for (let k = 0; k < 5; k++) {
        const ang = a + j * 0.075,
          r = 11 + k * 3.7;
        const p =
          (Math.round(31.5 + r * Math.sin(ang)) * 64 + Math.round(31.5 + r * Math.cos(ang))) * 4;
        const weight = pixels[p + 3] / 255;
        for (let ch = 0; ch < 3; ch++) rgb[ch] += pixels[p + ch] * weight;
        n += weight;
      }
    if (!n) return palette.neutral.slice();
    const avg = rgb.map((v) => v / n);
    const l = 0.22 * avg[0] + 0.68 * avg[1] + 0.1 * avg[2];
    return avg.map((v, ch) => palette.neutral[ch] * 0.57 + l * 0.43 + (v - l) * 0.47);
  });
}

export function paintRecord(ctx, size, palette, settings, custom) {
  const image = ctx.createImageData(size, size),
    data = image.data,
    half = size / 2;
  const angleSteps = 384;
  const tone = Array.from({ length: angleSteps }, (_, i) => {
    const n = custom?.length || 12,
      a = (i * n) / angleSteps;
    const blur = clamp((settings.blur - 4) / 20);
    const spread = 0.13 + blur * 0.8;
    function soft(stops, ch) {
      return (
        0.56 * cubicColor(stops, a, ch) +
        0.22 * (cubicColor(stops, a + spread, ch) + cubicColor(stops, a - spread + n, ch))
      );
    }
    return [0, 1, 2].map((ch) => {
      const inner = soft(custom || palette.inside, ch);
      const outer = soft(custom || palette.outside, ch);
      return [
        mix(inner, mix(outer, palette.neutral[ch], 0.23), blur * 0.15),
        mix(outer, mix(inner, palette.neutral[ch], 0.3), blur * 0.18),
      ];
    });
  });
  for (let y = 0; y < size; y++) {
    const v = (y + 0.5 - half) / half;
    for (let x = 0; x < size; x++) {
      const u = (x + 0.5 - half) / half,
        r = Math.sqrt(u * u + v * v);
      if (r < 0.659 || r > 1 + 1 / half) continue;
      const t = clamp((r - 0.6656) / 0.3344);
      const a = Math.atan2(v, u),
        q = a + 0.06 * Math.sin(t * 3.3 + a * 2.0) + 0.016 * Math.sin(a * 5 + t * 5.8);
      const k = ((q / (2 * Math.PI) + 1) * angleSteps) % angleSteps;
      const ka = Math.floor(k),
        kb = (ka + 1) % angleSteps;
      const p = radial[Math.round(t * 1023)];
      const grain = (grainAt(y * size + x) - 0.5) * 1.65;
      const strata =
        1.15 * Math.sin(a * 5.0 + t * 4.3) +
        0.66 * Math.sin(a * 13.0 - t * 9.0) +
        0.32 * Math.sin(a * 27.0 + t * 14.1);
      const grooves = p.groove * (1.29 + 0.32 * Math.cos(a * 2 + 1.1));
      const edge = p.edge * (1 + 0.23 * Math.sin(a - 0.8));
      const blend = smooth(0.07, 0.94, t);
      const j = (y * size + x) * 4;
      for (let ch = 0; ch < 3; ch++) {
        const base = mix(
          mix(tone[ka][ch][0], tone[ka][ch][1], blend),
          mix(tone[kb][ch][0], tone[kb][ch][1], blend),
          k - ka,
        );
        data[j + ch] =
          mix(palette.neutral[ch], base, settings.opacity) + grooves + edge + grain + strata;
      }
      data[j + 3] = 255 * clamp((1 - r) * half + 0.65);
    }
  }
  ctx.putImageData(image, 0, 0);
}

export const neutralMaterial = { neutral: [115, 119, 126], inside: [], outside: [] };
