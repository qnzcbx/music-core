import test from 'node:test';
import assert from 'node:assert/strict';

test('桌面 IPC 保留会话 URL 白名单，未迁移操作不落到 HTTP', async () => {
  const calls = [];
  let mediaUrl = 'http://127.0.0.1:43210/api/playback/0123456789abcdef0123456789abcdef/stream';
  globalThis.window = { __TAURI__: { core: { invoke: async (command, args) => {
    calls.push({ command, ...args });
    if (args.path === '/api/playback/open') return { streamUrl: mediaUrl };
    if (args.path.endsWith('/close')) return null;
    if (args.path === '/api/lyrics') return {identity:args.body,status:'unavailable',lines:[]};
    throw '此功能尚未迁移到桌面版';
  } } } };
  const { apiFetch, isPlaybackUrl } = await import('../src/api/transport.ts');
  const opened = await apiFetch('/api/playback/open', { body: JSON.stringify({ identity: { providerId: 'kuwo', platformId: '123' } }) });
  assert.equal(opened.status, 200);
  assert.equal(isPlaybackUrl(mediaUrl), true);
  assert.equal(isPlaybackUrl('http://127.0.0.1:9999/arbitrary'), false);
  assert.equal((await apiFetch('/api/downloads')).status, 503);
  assert.equal(calls[1].command, 'desktop_request');
  assert.equal((await apiFetch('/api/playback/0123456789abcdef0123456789abcdef/close')).status, 204);
  assert.equal(isPlaybackUrl(mediaUrl), false);
  mediaUrl = 'https://private.invalid/song';
  assert.equal((await apiFetch('/api/playback/open')).status, 503);
  const lyric = await apiFetch('/api/lyrics?providerId=qq&platformId=0027oMO61wWi55');
  assert.deepEqual((await lyric.json()).identity,{providerId:'qq',platformId:'0027oMO61wWi55'});
  assert.equal(calls.at(-1).path,'/api/lyrics');
  delete globalThis.window;
});
