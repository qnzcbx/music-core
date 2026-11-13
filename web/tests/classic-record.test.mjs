import test from 'node:test';
import assert from 'node:assert/strict';
import { paintRecord, neutralMaterial } from '../src/components/classic-turntable/record-material.js';

function render(colors) {
  let pixels;
  const context = {
    createImageData: (w, h) => ({ data: new Uint8ClampedArray(w * h * 4) }),
    putImageData: (image) => { pixels = image.data; },
  };
  paintRecord(context, 128, neutralMaterial, { opacity: .97, blur: 8 }, colors);
  return pixels;
}

test('经典材质保留透明标签孔、边缘及径向层次，颜色由角向样本决定', () => {
  const neutral = Array.from({ length: 16 }, () => neutralMaterial.neutral);
  const pixels = render(neutral);
  assert.equal(pixels[(64 * 128 + 64) * 4 + 3], 0);
  assert.equal(pixels[3], 0);
  assert.equal(pixels[(64 * 128 + 110) * 4 + 3], 255);
  assert.notEqual(pixels[(64 * 128 + 110) * 4], pixels[(64 * 128 + 125) * 4]);
  assert.deepEqual(render(neutral), pixels);
  const varied = render(neutral.map((_, i) => i < 8 ? [180, 70, 80] : [60, 110, 170]));
  assert.notDeepEqual(varied, pixels);
  assert.notEqual(varied[(64 * 128 + 110) * 4], varied[(64 * 128 + 18) * 4]);
});
