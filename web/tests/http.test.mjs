import test from 'node:test';
import assert from 'node:assert/strict';
import { requestJson } from '../src/api/http.ts';

test('HTTP 区分空响应、JSON null、业务拒绝和未确认的变更结果', async (context) => {
  const outcomes = [
    new Response(null, { status: 204 }),
    Response.json(null),
    new Response('invalid', { status: 200 }),
    Response.json({ error: { code: 'upstream_failure', message: '来源暂不可用', retryable: true } }, { status: 502 }),
    new Response('invalid', { status: 502 }),
    new TypeError('connection lost'),
  ];
  const fetch = context.mock.method(globalThis, 'fetch', async () => {
    const result = outcomes.shift();
    if (result instanceof Error) throw result;
    return result;
  });
  assert.equal(await requestJson('/api/close', { method: 'POST' }), undefined);
  assert.equal(await requestJson('/api/query'), null);
  await assert.rejects(requestJson('/api/query'), { code: 'invalid_response', status: 502 });
  await assert.rejects(requestJson('/api/query'), { code: 'upstream_failure', retryable: true });
  await assert.rejects(requestJson('/api/write', { method: 'POST', mutation: true }), { code: 'outcome_unknown' });
  await assert.rejects(requestJson('/api/write', { method: 'POST', mutation: true }), { code: 'outcome_unknown' });
  assert.equal(fetch.mock.callCount(), 6);
});
