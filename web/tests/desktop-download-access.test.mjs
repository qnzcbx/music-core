import test from 'node:test';
import assert from 'node:assert/strict';
import { downloadBlockReason } from '../src/utils/track-access.ts';
test('桌面两个入口共享未知可探查、明确拒绝不可放行的规则', () => {
  for (const downloadAllowed of [undefined, null, true, false]) {
    assert.equal(!!downloadBlockReason({ downloadAllowed }), downloadAllowed === false);
  }
  assert.equal(downloadBlockReason({}), '');
});
