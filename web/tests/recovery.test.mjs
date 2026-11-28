// 合成audio与HTTP替身只验证状态机，不冒充浏览器解码或平台成功。
import test from 'node:test';
import assert from 'node:assert/strict';
import {RecoveryPlayer} from '../src/player/recovery-player.mjs';

const identity={providerId:'kuwo',platformId:'1'};
test('QQ 备用解析晚到时保持切回的原生曲目并释放迟到会话', async () => {
  const s=setup();
  await s.player.select(identity);
  const release=s.delay();
  const pending=s.player.select({providerId:'qq',platformId:'0027oMO61wWi55'});
  await tick();
  await s.player.select(identity);
  const active=s.player.session.playbackId;
  release(); await pending;
  assert.deepEqual(s.player.identity,identity);
  assert.equal(s.player.session.playbackId,active);
  assert.equal(s.audio.src,`/api/playback/${active}/stream`);
  assert(s.closed.includes('lease1'));
  await s.player.dispose();
});
test('跨来源同数字 ID 与快速切歌晚到会话隔离', async () => {
  const s=setup();
  await s.player.select(identity);
  const release=s.delay();
  const pending=s.player.select({providerId:'netease',platformId:'1'});
  await tick();
  await s.player.select({providerId:'qq',platformId:'1'});
  await s.player.select({providerId:'migu',platformId:'1'});
  release(); await pending;
  assert.deepEqual(s.player.identity,{providerId:'migu',platformId:'1'});
  assert.equal(s.audio.src,'/api/playback/lease3/stream');
  for(const id of ['lease0','lease1','lease2']) assert(s.closed.includes(id));
  await s.player.select(identity);
  assert.deepEqual(s.player.identity,identity);
  assert(s.closed.includes('lease3'));
  await s.player.dispose();
});
const tick=()=>new Promise(resolve=>setTimeout(resolve,0));
class Audio extends EventTarget {
  constructor(){super();this.currentTime=0;this.duration=120;this.readyState=1;this.volume=1;this.muted=false;this.playbackRate=1;this.paused=true;this.seeking=false;this.error=null;}
  pause(){this.paused=true;this.dispatchEvent(new Event('pause'));}
  async play(){if(this.blocked)throw new DOMException('浏览器拒绝','NotAllowedError');this.paused=false;this.dispatchEvent(new Event('playing'));}
  load(){this.error=null;this.currentTime=0;this.readyState=1;this.duration=120;}
  removeAttribute(){this.src='';}
}
function setup(){
  const audio=new Audio(),closed=[],opened=[];
  let gate=null,fail=false,headStatus=410;
  const operations = {
    async close(id) { closed.push(id); },
    async probe() { return { ok: headStatus === 200, status: headStatus }; },
    async renew() { throw Object.assign(new Error('会话已过期'), { code: 'playback_expired', status: 410 }); },
    async open(track) {
      const key = 'lease' + opened.length;
      opened.push(track);
      if (gate) { const pending = gate; gate = null; await pending; }
      if (fail) throw new Error('重新打开失败');
      return { playbackId: key, streamUrl: '/api/playback/' + key + '/stream', identity: track };
    },
  };
  const player = new RecoveryPlayer(audio, { operations });
  return {audio,player,opened,closed,delay(){let release;gate=new Promise(r=>release=r);return release;},
    fail(value){fail=value;},head(value){headStatus=value;}};
}

test('首次打开先定位再出声，非法进度归零、越界按实际时长截断',async()=>{
 for(const [saved,expected] of [[42,42],[999,119.9],[-1,0],[NaN,0]]){
   const s=setup(),heard=[];s.audio.play=async()=>{heard.push(s.audio.currentTime);s.audio.paused=false;};
   await s.player.select(identity,saved);assert.deepEqual(heard,[expected]);await s.player.dispose();
 }
});

test('刷新恢复的 Open 晚到不能把旧进度套到新曲，旧 Lease 关闭',async()=>{
 const s=setup(),release=s.delay();const pending=s.player.select(identity,70);
 await tick();await s.player.select({...identity,platformId:'2'});release();await pending;
 assert.equal(s.player.identity.platformId,'2');assert.equal(s.audio.currentTime,0);
 assert.equal(s.player.session.playbackId,'lease1');assert(s.closed.includes('lease0'));
 await s.player.dispose();
});

test('恢复中Seek采用最新目标并保持暂停',async()=>{
 const s=setup();await s.player.select(identity);const release=s.delay();const pending=s.player.recover(true);
 s.player.seek(70);await s.player.setPlaying(false);release();await pending;
 assert.equal(s.audio.currentTime,70);assert.equal(s.audio.paused,true);
});
test('销毁后移除持久监听且关闭会话',async()=>{
 const s=setup();await s.player.select(identity);await s.player.dispose();
 assert.equal(s.player.listeners.length,0);assert.equal(s.player.session,null);assert(s.closed.includes('lease0'));
});
test('旧续期晚到不能覆盖新歌曲',async()=>{
 const s=setup();await s.player.select(identity);let release;
 s.player.operations.renew = () => new Promise((_, reject) => { release = reject; });
 const renewal=s.player.renew();await s.player.select({...identity,platformId:'2'});
 release({code:'playback_expired', status:410});await renewal;
 assert.equal(s.player.identity.platformId,'2');assert.equal(s.opened.length,2);assert.equal(s.player.phase,'ready');
});
test('同源stream地址保留服务端查询参数',async()=>{
 const s=setup();const original=s.player.operations.open;
 s.player.operations.open = async (identity) => {
   const session = await original(identity);
   return { ...session, streamUrl: session.streamUrl + '?test=1' };
 };
 await s.player.select(identity);assert.equal(s.audio.src,'/api/playback/lease0/stream?test=1');
});

test('书签、稳定身份、新会话和音量速率恢复',async()=>{
  const s=setup();await s.player.select(identity);const old=s.player.session.playbackId;
  s.audio.currentTime=32;s.audio.volume=.3;s.audio.muted=true;s.audio.playbackRate=1.25;
  await s.player.recover(true);
  assert.equal(s.audio.currentTime,32);assert.equal(s.audio.volume,.3);assert.equal(s.audio.muted,true);assert.equal(s.audio.playbackRate,1.25);
  assert.equal(s.audio.paused,false);assert.notEqual(old,s.player.session.playbackId);
  assert.deepEqual(s.opened,[identity,identity]);assert(s.closed.includes(old));
});
test('原本暂停仍保持暂停',async()=>{
  const s=setup();await s.player.select(identity);await s.player.setPlaying(false);s.audio.currentTime=20;
  await s.player.recover(true);assert.equal(s.audio.paused,true);assert.equal(s.audio.currentTime,20);
});
test('自动最多一次，显式手动可以再试',async()=>{
  const s=setup();await s.player.select(identity);await s.player.recover(true);await s.player.recover(true);
  assert.equal(s.opened.length,2);await s.player.recover(false);assert.equal(s.opened.length,3);
});
test('重复恢复共享同一在途工作',async()=>{
  const s=setup();await s.player.select(identity);const release=s.delay();
  const a=s.player.recover(true),b=s.player.recover(false);assert.equal(a,b);release();await a;assert.equal(s.opened.length,2);
});
for(const action of ['stop','switch','pause'])test(`恢复中${action}不被旧结果覆盖`,async()=>{
  const s=setup();await s.player.select(identity);const release=s.delay();const pending=s.player.recover(true);
  if(action==='stop')await s.player.stop();
  if(action==='switch')await s.player.select({...identity,platformId:'2'});
  if(action==='pause')await s.player.setPlaying(false);
  release();await pending;
  if(action==='stop'){assert.equal(s.player.session,null);assert.equal(s.audio.paused,true);assert(s.closed.includes('lease1'));}
  if(action==='switch'){assert.equal(s.player.identity.platformId,'2');assert.equal(s.player.session.playbackId,'lease2');assert(s.closed.includes('lease1'));}
  if(action==='pause')assert.equal(s.audio.paused,true);
});
test('失败清理旧会话，保留书签供手动恢复',async()=>{
  const s=setup();await s.player.select(identity);s.audio.currentTime=50;s.fail(true);await s.player.recover(true);
  assert.equal(s.player.phase,'error');assert.equal(s.player.session,null);assert(s.closed.includes('lease0'));
  s.fail(false);await s.player.recover(false);assert.equal(s.audio.currentTime,50);
});
test('自动播放策略失败保留已恢复资源和位置',async()=>{
  const s=setup();await s.player.select(identity);s.audio.currentTime=10;s.audio.blocked=true;
  await s.player.recover(true);assert.equal(s.player.phase,'blocked');assert(s.player.session);assert.equal(s.audio.currentTime,10);
  assert(!s.closed.includes(s.player.session.playbackId));
});
for(const code of [1,3])test(`MediaError ${code}不自动重解析`,async()=>{
  const s=setup();await s.player.select(identity);s.audio.error={code};await s.player.mediaError();assert.equal(s.opened.length,1);
});
test('权限拒绝不自动恢复',async()=>{
  const s=setup();await s.player.select(identity);s.head(403);s.audio.error={code:2};await s.player.mediaError();assert.equal(s.opened.length,1);
});
test('waiting和stalled不是永久故障',async()=>{
  const s=setup();await s.player.select(identity);s.audio.dispatchEvent(new Event('waiting'));s.audio.dispatchEvent(new Event('stalled'));await tick();assert.equal(s.opened.length,1);
});
test('会话过期续租失败通过稳定身份恢复',async()=>{
  const s=setup();await s.player.select(identity);await s.player.renew();assert.equal(s.opened.length,2);assert.equal(s.player.phase,'ready');
});
test('连续错误不重复取链',async()=>{
  const s=setup();await s.player.select(identity);s.audio.error={code:2};await Promise.all([s.player.mediaError(),s.player.mediaError()]);
  assert.equal(s.opened.length,2);s.audio.error={code:2};await s.player.mediaError();assert.equal(s.opened.length,2);
});
test('新媒体加载失败关闭新旧Lease，不产生递归恢复',async()=>{
  const s=setup();await s.player.select(identity);s.audio.currentTime=25;
  s.audio.load=function(){this.currentTime=0;this.readyState=0;queueMicrotask(()=>{this.error={code:2};this.dispatchEvent(new Event('error'))});};
  await s.player.recover(true);assert.equal(s.player.phase,'error');assert.equal(s.player.session,null);
  assert(s.closed.includes('lease0')&&s.closed.includes('lease1'));assert.equal(s.opened.length,2);
});
test('恢复到合法时长内，未完成seek不覆盖旧书签',async()=>{
  const s=setup();await s.player.select(identity);s.audio.currentTime=140;s.player.capture();
  s.audio.seeking=true;s.audio.currentTime=80;s.player.capture();assert.equal(s.player.bookmark,140);
  s.audio.seeking=false;s.audio.currentTime=140;await s.player.recover(false);assert.equal(s.audio.currentTime,119.9);
});


test('首次打开失败后主动Play新建会话且合并重复请求',async()=>{
 const s=setup();s.fail(true);await s.player.select(identity);assert.equal(s.player.phase,'error');
 s.fail(false);const release=s.delay();const a=s.player.setPlaying(true),b=s.player.setPlaying(true);
 assert.equal(s.opened.length,2);release();await Promise.all([a,b]);
 assert.equal(s.player.phase,'ready');assert.equal(s.audio.paused,false);assert.equal(s.player.automaticUsed,true);
});
test('自动恢复失败后Play保留书签，手动失败与成功不重置自动预算',async()=>{
 const s=setup();await s.player.select(identity);s.audio.currentTime=37;s.fail(true);await s.player.recover(true);
 await s.player.setPlaying(true);assert.equal(s.player.phase,'error');s.fail(false);await s.player.setPlaying(true);
 assert.equal(s.audio.currentTime,37);assert.equal(s.audio.paused,false);
 const count=s.opened.length;await s.player.recover(true);assert.equal(s.opened.length,count);
});
test('主动Play重试晚到被切歌或停止隔离并关闭会话',async()=>{
 for(const stop of [false,true]){const s=setup();s.fail(true);await s.player.select(identity);s.fail(false);
 const release=s.delay();const pending=s.player.setPlaying(true);
 if(stop)await s.player.stop();else await s.player.select({...identity,platformId:'2'});
 release();await pending;assert.equal(s.player.identity?.platformId,stop?undefined:'2');assert(s.closed.includes('lease1'));
 }
});
