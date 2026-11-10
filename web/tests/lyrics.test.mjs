import test from 'node:test';
import assert from 'node:assert/strict';
import {createLyricsLoader,currentLyricIndex} from '../src/player/lyrics-state.ts';
import {createPlayerLayoutSelection} from '../src/appearance/player-layout.ts';
const identity=id=>({providerId:'kuwo',platformId:id});
const document=id=>({identity:identity(id),status:'synced',lines:[{startMs:1000,text:'人工原文',translation:'人工翻译'}]});
test('歌词时间线处理首行之前、边界、结束、重复时间和连续Seek',()=>{
 const lines=[{startMs:1000,text:'甲'},{startMs:2000,endMs:3000,text:'乙'},{startMs:2000,endMs:3000,text:'丙'},{startMs:4000,text:'丁'}];
 assert.deepEqual([0,1,2,2.9,3,4,1.5,4.5].map(t=>currentLyricIndex(lines,t)),[-1,0,2,2,-1,3,0,3]);
 assert.equal(currentLyricIndex([],10),-1);assert.equal(currentLyricIndex(lines,NaN),-1);
});
test('歌词旧请求晚到不能覆盖新曲；同身份恢复和换模板不重新获取',async()=>{
 let release,oldSignal;const states=[],requests=[];
 const loader=createLyricsLoader((id,signal)=>{requests.push(id.platformId);if(id.platformId==='1'){oldSignal=signal;return new Promise(resolve=>{release=resolve;});}return Promise.resolve(document(id.platformId));},s=>states.push(s));
 const old=loader.select(identity('1'));await loader.select(identity('2'));assert.ok(oldSignal.aborted);release(document('1'));await old;
 assert.equal(states.at(-1).document.identity.platformId,'2');await loader.select(identity('2'));assert.deepEqual(requests,['1','2']);loader.dispose();
});
test('无歌词、纯文本、网络错误分开呈现；错误重试及销毁清理',async()=>{
 const states=[];let fail=true,release;
 const loader=createLyricsLoader(async id=>{if(id.platformId==='1')return {identity:id,status:'unavailable',lines:[]};if(id.platformId==='2')return {identity:id,status:'plain',plainText:'人工纯文本'};if(id.platformId==='4')return new Promise(resolve=>{release=resolve;});if(fail)throw Error('网络中断');return document('3');},s=>states.push(s));
 await loader.select(identity('1'));assert.equal(states.at(-1).document.status,'unavailable');
 await loader.select(identity('2'));assert.equal(states.at(-1).document.plainText,'人工纯文本');
 await loader.select(identity('3'));assert.equal(states.at(-1).error,'网络中断');assert.equal(states.at(-1).document,null);
 fail=false;await loader.select(identity('3'),true);assert.equal(states.at(-1).document.lines[0].translation,'人工翻译');
 const pending=loader.select(identity('4'));loader.dispose();const count=states.length;release(document('4'));await pending;assert.equal(states.length,count);
});
test('拒绝歌词身份不匹配；清空当前歌曲取消歌词',async()=>{
 const states=[];const loader=createLyricsLoader(async()=>document('2'),s=>states.push(s));await loader.select(identity('1'));assert.match(states.at(-1).error,/不匹配/);
 await loader.select(null);assert.deepEqual(states.at(-1),{document:null,loading:false,error:''});loader.dispose();
});
test('四套模板默认对齐与独立偏好持久化',()=>{
 let raw=null;const storage={getItem:()=>raw,setItem:(_key,value)=>{raw=value;}};const s=createPlayerLayoutSelection(undefined,storage);
 assert.equal(s.lyricAlignment.value,'center');s.selectLyricAlignment('left');s.selectLayout('vinyl-wide');assert.equal(s.lyricAlignment.value,'left');s.selectLyricAlignment('center');s.selectLayout('square-cover');assert.equal(s.lyricAlignment.value,'center');
 const restored=createPlayerLayoutSelection(undefined,storage);restored.selectLayout('classic');assert.equal(restored.lyricAlignment.value,'left');restored.selectLayout('vinyl-wide');assert.equal(restored.lyricAlignment.value,'center');assert.ok(!raw.includes('playbackId'));
});
