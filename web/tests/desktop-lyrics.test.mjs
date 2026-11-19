import test from 'node:test';
import assert from 'node:assert/strict';
import { lyricSnapshot, acceptSnapshot, dispatchDesktopPlayback } from '../src/player/desktop-lyrics.ts';

test('uses actual time for initial snapshot and seeks in either direction', () => {
  const identity = {providerId:'netease', platformId:'123'};
  const doc = {identity,status:'synced',lines:[{startMs:1000,text:'one'},{startMs:4000,text:'two'},{startMs:9000,text:'three'}]};
  assert.deepEqual(lyricSnapshot(identity, doc, 5), {identity,current:'two',next:'three',available:true});
  assert.equal(lyricSnapshot(identity, doc, 1).current, 'one');
  assert.equal(lyricSnapshot(identity, doc, 0).next, 'one');
  assert.equal(lyricSnapshot(identity, doc, 10).next, '');
  assert.equal(lyricSnapshot({...identity,platformId:'456'},doc,5).available,false);
  assert.equal(lyricSnapshot(identity,{...doc,status:'plain'},5).available,false);
});
test('late snapshots cannot overwrite a newer track', () => {
  const current = {sequence:8, snapshot:lyricSnapshot(null,null,0)};
  assert.equal(acceptSnapshot(current,{sequence:7,snapshot:{...current.snapshot,current:'stale'}}),current);
  const next = {...current,sequence:9};
  assert.equal(acceptSnapshot(current,next),next);
});

test('desktop controls dispatch only enabled actions to the main player', () => {
  const calls = [];
  const state = { canPrevious:false, canToggle:true, canNext:true };
  const actions = { previous:()=>calls.push('previous'), toggle:()=>calls.push('toggle'), next:()=>calls.push('next') };
  for (const action of ['previous', 'toggle', 'next', 'lock']) dispatchDesktopPlayback(action, state, actions);
  assert.deepEqual(calls, ['toggle', 'next']);
});
