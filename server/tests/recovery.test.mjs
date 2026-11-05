// 合成audio与HTTP替身只验证状态机，不冒充浏览器解码或平台成功。
import test from 'node:test';
import assert from 'node:assert/strict';
import {RecoveryPlayer} from '../app/player-controller.mjs';

const identity={providerId:'kuwo',platformId:'1'};
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
  const request=async(url,options)=>{
    if(url.endsWith('/close')){closed.push(url.split('/')[3]);return {ok:true,status:204};}
    if(options.method==='HEAD')return {ok:headStatus===200,status:headStatus};
    if(url.endsWith('/renew'))return {ok:false,status:410};
    const track=JSON.parse(options.body).identity,key=`lease${opened.length}`;
    opened.push(track);
    if(gate){const pending=gate;gate=null;await pending;}
    return {ok:!fail,status:fail?502:200,json:async()=>fail?{error:{code:'upstream_failure'}}:
      {playbackId:key,streamUrl:`/api/playback/${key}/stream`,media:{identity:track}}};
  };
  const player=new RecoveryPlayer(audio,{request});
  return {audio,player,opened,closed,delay(){let release;gate=new Promise(r=>release=r);return release;},
    fail(value){fail=value;},head(value){headStatus=value;}};
}

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
