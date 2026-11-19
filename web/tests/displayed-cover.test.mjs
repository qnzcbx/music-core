import test from 'node:test';
import assert from 'node:assert/strict';
import { displayedCover, CLOVER_COVER } from '../src/utils/displayed-cover.ts';

test('effects follow the final displayed cover, including a failed nonempty address', () => {
  const remote = 'https://example.test/cover.jpg';
  assert.equal(displayedCover(remote, 'pending', true, true), null);
  assert.equal(displayedCover(remote, 'loaded', true, true), remote);
  assert.equal(displayedCover(null, 'pending', true, false), null);
  assert.equal(displayedCover(null, 'pending', true, true), CLOVER_COVER);
  assert.equal(displayedCover(remote, 'failed', true, true), CLOVER_COVER);
  assert.equal(displayedCover(remote, 'failed', false, true), null);
});
