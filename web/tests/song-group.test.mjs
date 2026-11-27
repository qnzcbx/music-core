import test from 'node:test';
import assert from 'node:assert/strict';
import { effectScope, ref } from 'vue';
import { createSongGroupState } from '../src/utils/song-group.ts';
import { useSongGroups } from '../src/composables/useSongGroups.ts';
import { queueKey } from '../src/utils/player-queue.ts';

function song(providerId, platformId = '123') {
  const identity = { providerId, platformId };
  return { identity, id: queueKey(identity), title: '晴天', artist: '歌手' };
}
const [kuwo, qq, netease] = ['kuwo', 'qq', 'netease'].map(source => song(source));
const order = ['kuwo', 'qq', 'netease'];

test('主版本按规范身份更新，保留组内版本、展开和分页状态', () => {
  const state = createSongGroupState();
  let [group] = state.update([qq, kuwo], order);
  assert.equal(group.representative, kuwo);
  state.toggle(group.key);
  [group] = state.update([qq, kuwo], order, qq.identity);
  assert.equal(group.expanded, true);
  assert.equal(group.representative, qq);
  state.toggle(group.key);
  state.lockRepresentatives();
  [group] = state.update([qq, kuwo, netease], order, netease.identity);
  assert.equal(group.expanded, false);
  assert.equal(group.representative, netease);
  assert.deepEqual(group.versions, [kuwo, qq, netease]);
  assert.equal(state.update([qq, kuwo, netease], order, song('qq', '456').identity)[0].representative, netease);
  state.reset();
  [group] = state.update([qq, kuwo, netease], order, song('migu').identity);
  assert.equal(group.representative, kuwo);
});

test('播放器选择独立驱动计算，重新挂载后按当前选择恢复', () => {
  const songs = ref([kuwo, qq, netease]);
  const providers = ref(order.map(id => ({ id })));
  const selected = ref(null);
  const mount = () => {
    const scope = effectScope();
    return { scope, ...scope.run(() => useSongGroups(songs, providers, selected)) };
  };
  let view = mount();
  try {
    assert.equal(view.groups.value[0].representative.id, kuwo.id);
    selected.value = qq.identity;
    assert.equal(view.groups.value[0].representative.id, qq.id);
    view.scope.stop();
    view = mount();
    assert.equal(view.groups.value[0].representative.id, qq.id);
    selected.value = null;
    assert.equal(view.groups.value[0].representative.id, qq.id);
    songs.value = [kuwo, qq];
    assert.equal(view.groups.value[0].representative.id, kuwo.id);
  } finally {
    view.scope.stop();
  }
});
