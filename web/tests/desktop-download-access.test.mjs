import test from 'node:test';
import assert from 'node:assert/strict';
import { downloadBlockReason } from '../src/utils/track-access.ts';
test('桌面两个入口共享未知可探查、明确拒绝不可放行的规则', () => {
  for (const state of ['unknown','allowed','denied']) {
    const song={source:'kuwo',trackAccess:{download:{state,reason:'来源限制',evidence:'desktop-source-policy'}}};
    assert.equal(!!downloadBlockReason(song),state==='denied');
  }
  assert.ok(downloadBlockReason({source:'fma'}));
});
