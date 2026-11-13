import test from 'node:test';
import assert from 'node:assert/strict';
import {
  createPlayerLayoutSelection,
  PLAYER_RING_PRESETS,
} from '../src/appearance/player-layout.ts';

test('九款胶圈均可保存恢复，换色不改变背景', () => {
  const { state, restore } = fixture(null);
  state.selectLayout('vinyl-wide');
  state.selectBackground('dark');
  for (const preset of PLAYER_RING_PRESETS) {
    state.selectRingPreset(preset.id);
    assert.equal(restore().ringPreset.value, preset.id);
    assert.equal(state.backgroundMode.value, 'dark');
  }
});

function fixture(saved) {
  let raw = JSON.stringify(saved);
  const storage = {
    getItem: () => raw,
    setItem: (_key, value) => {
      raw = value;
    },
  };
  return {
    state: createPlayerLayoutSelection(undefined, storage),
    restore: () => createPlayerLayoutSelection(undefined, storage),
  };
}

test('旧样式与对齐迁移后保留，缺少的新偏好使用默认值', () => {
  const { state } = fixture({
    version: 2,
    layout: 'square-cover',
    lyricAlignments: { 'square-cover': 'left' },
  });
  assert.equal(state.layout.value, 'square-cover');
  assert.equal(state.lyricAlignment.value, 'left');
  assert.equal(state.backgroundMode.value, 'cover');
  assert.equal(state.ringPreset.value, 'smoky');
});

test('背景和歌词按样式保存，颜色和背景互不重置，刷新恢复', () => {
  const { state, restore } = fixture(null);
  state.selectLayout('vinyl-wide');
  state.selectBackground('dark');
  state.selectLyricAlignment('center');
  state.selectRingPreset('amber');
  state.selectLayout('square-cover');
  assert.equal(state.backgroundMode.value, 'cover');
  state.selectBackground('light');
  state.selectLyricAlignment('left');
  const restored = restore();
  assert.equal(restored.backgroundMode.value, 'light');
  restored.selectLayout('vinyl-wide');
  assert.equal(restored.backgroundMode.value, 'dark');
  assert.equal(restored.lyricAlignment.value, 'center');
  assert.equal(restored.ringPreset.value, 'amber');
  restored.selectBackground('cover');
  assert.equal(restored.ringPreset.value, 'amber');
});

test('无效字段和拒绝存储不妨碍当前会话设置', () => {
  const { state } = fixture({
    version: 3,
    layout: 'unknown',
    backgrounds: { classic: 'invalid' },
    ringPreset: 'unknown',
  });
  assert.equal(state.layout.value, 'classic');
  assert.equal(state.backgroundMode.value, 'cover');
  const unavailable = createPlayerLayoutSelection(undefined, {
    getItem() {
      throw Error();
    },
    setItem() {
      throw Error();
    },
  });
  unavailable.selectBackground('dark');
  assert.equal(unavailable.backgroundMode.value, 'dark');
});
