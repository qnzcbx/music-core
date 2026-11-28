import test from 'node:test';
import assert from 'node:assert/strict';

test('续租失效、查询取消及迟到结果经显式桌面命令处理', async () => {
  const calls = [];
  let finish;
  const mediaPort = 43210;
  const playbackId = '0123456789abcdef0123456789abcdef';
  let returnedPort = mediaPort;
  const identity = { providerId: 'kuwo', platformId: '123' };
  globalThis.window = { __TAURI__: { core: { invoke: async (command, args) => {
    calls.push([command, args?.request]);
    if (command === 'desktop_platform') return { mediaPort };
    if (args.request.op === 'playbackOpen') {
      return {
        playbackId, identity, expiresInSeconds: 120,
        streamUrl: 'http://127.0.0.1:' + returnedPort + '/api/playback/' + playbackId + '/stream',
      };
    }
    if (args.request.op === 'playbackClose') return null;
    if (args.request.op === 'downloadCreate') throw new Error('host disconnected');
    if (args.request.op === 'playbackRenew') {
      throw { code: 'playback_expired', status: 410, message: '播放会话已过期', retryable: false };
    }
    return new Promise(resolve => { finish = resolve; });
  } } } };
  try {
    const { invokeCore } = await import('../src/api/transport.ts');
    await assert.rejects(
      invokeCore({ op: 'playbackRenew', payload: { playbackId } }),
      { code: 'playback_expired', status: 410, retryable: false },
    );
    assert.deepEqual(calls[0], ['core_request', { op: 'playbackRenew', payload: { playbackId } }]);
    const controller = new AbortController();
    const reading = invokeCore({ op: 'lyricsGet', payload: { providerId: 'kuwo', platformId: '123' } }, { signal: controller.signal });
    controller.abort();
    await assert.rejects(reading, { name: 'AbortError' });
    finish({ status: 'unavailable' });
    assert.equal(calls.length, 2);
    const { playbackOperations } = await import('../src/api/playback.ts');
    assert.equal((await playbackOperations.open(identity)).playbackId, playbackId);
    returnedPort++;
    await assert.rejects(playbackOperations.open(identity), { code: 'invalid_response' });
    assert.deepEqual(calls.at(-1), ['core_request', { op: 'playbackClose', payload: { playbackId } }]);

    await assert.rejects(invokeCore({ op: 'downloadCreate', payload: { identity } }, { mutation: true }),
      { code: 'outcome_unknown', retryable: false });
    assert.equal(calls.filter(([, request]) => request?.op === 'downloadCreate').length, 1);

  } finally {
    delete globalThis.window;
  }
});
