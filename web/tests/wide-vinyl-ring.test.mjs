import test from 'node:test';
import assert from 'node:assert/strict';
import { buildRingField, paintRing, VINYL_PRESETS } from '../src/components/wide-vinyl/ring-field.js';

test('胶圈保持透明内孔和半透材质，预设换色复用同一纹理场', () => {
  const previous = globalThis.ImageData;
  globalThis.ImageData = class {
    constructor(width, height) {
      this.data = new Uint8ClampedArray(width * height * 4);
    }
  };
  try {
    const field = buildRingField(128, 0.604);
    const flow = field.flow.slice();
    const colors = new Set();
    let draws = 0;
    const context = { putImageData() { draws++; } };
    for (const preset of Object.keys(VINYL_PRESETS)) {
      paintRing(context, field, preset);
      const center = (64 * 128 + 64) * 4;
      const ring = (64 * 128 + 120) * 4;
      assert.equal(field.pixels.data[center + 3], 0);
      assert(field.pixels.data[ring + 3] > 0 && field.pixels.data[ring + 3] < 255);
      colors.add([...field.pixels.data.slice(ring, ring + 4)].join(','));
      assert.deepEqual(field.flow, flow);
    }
    assert.equal(colors.size, 9);
    assert.equal(draws, 9);
    assert(field.flow.some(value => value < -1) && field.flow.some(value => value > 1));
  } finally {
    globalThis.ImageData = previous;
  }
});
