import test from 'node:test';
import assert from 'node:assert/strict';
import {effectScope} from 'vue';
import {useQueue} from '../src/player/useQueue.ts';
const song=(id,source='kuwo')=>({id,source,platformId:id,mid:id,name:'同名歌曲',title:'同名歌曲',artist:'歌手',album:'专辑',duration:10,resolveState:'idle'});
function fixture(storage,open=async()=>{}) {
 const scope=effectScope(),calls=[],stops=[];
 const queue=scope.run(()=>useQueue(async row=>{calls.push(row.platformId);await open(row);},async()=>{stops.push(true);},()=>true,()=>0,storage));
 return {queue,calls,stops,close:()=>scope.stop()};
}
test('稳定身份去重、同名不同版本保留，添加不解析',()=>{
 const f=fixture();f.queue.add(song('1'));f.queue.add(song('1'));f.queue.add(song('2'));f.queue.add(song('1','netease'));
 assert.equal(f.queue.entries.value.length,3);assert.deepEqual(f.calls,[]);f.close();
});
test('顺序、实际历史上一首、下一首、末尾停止，模式切换不解析',async()=>{
 const f=fixture(),q=f.queue;q.add(song('2'));await q.select(song('1'));q.add(song('3'));
 await q.next();assert.equal(f.calls.at(-1),'3');await q.previous();assert.equal(f.calls.at(-1),'1');await q.next();assert.equal(f.calls.at(-1),'3');
 await q.advance(true);assert.equal(f.calls.length,4);assert.equal(q.hasNext.value,false);
 q.setMode('repeat_all');assert.equal(f.calls.length,4);await q.advance(true);assert.equal(f.calls.at(-1),'2');
 q.setMode('repeat_one');await q.next();assert.equal(f.calls.at(-1),'1');f.close();
});
test('可注入随机源、不立即重复、上一首沿实际随机历史返回',async()=>{
 const f=fixture(),q=f.queue;await q.select(song('1'));q.add(song('2'));q.add(song('3'));q.setMode('shuffle');
 await q.next();const second=q.current.value;assert.notEqual(second,q.entries.value[0].key);
 await q.next();assert.notEqual(q.current.value,second);await q.previous();assert.equal(q.current.value,second);
 await q.next();assert.deepEqual(f.calls,['1','3','2','3','2']);f.close();
});
test('清空待播保持当前音频；移除非当前不停止，移除当前停止',async()=>{
 const f=fixture(),q=f.queue;await q.select(song('1'));q.add(song('2'));await q.remove(q.key(song('2')));assert.equal(f.stops.length,0);
 q.add(song('3'));q.clearPending();assert.equal(q.entries.value.length,1);assert.equal(f.stops.length,0);
 await q.remove(q.current.value);assert.equal(q.current.value,null);assert.equal(f.stops.length,1);f.close();
});
test('安全持久化、刷新仅恢复展示，损坏及未知版本存储忽略',async()=>{
 let raw=null;const storage={getItem:()=>raw,setItem:(_key,value)=>{raw=value;}};
 const f=fixture(storage);await f.queue.select({...song('1'),streamUrl:'secret',token:'secret',cover:'https://x.test/a.jpg?access_token=secret'});f.queue.setMode('shuffle');
 f.queue.entries.value[0].resolved={playbackId:'secret',streamUrl:'secret',lease:'secret'};
 assert.ok(!raw.includes('secret'));f.close();const restored=fixture(storage);
 assert.equal(restored.queue.entries.value.length,1);assert.equal(restored.queue.navigation.mode,'shuffle');assert.deepEqual(restored.calls,[]);restored.close();
 for(raw of ['{bad','{"schemaVersion":999}',null]){const invalid=fixture(storage);assert.equal(invalid.queue.entries.value.length,0);invalid.close();}
});
test('快速切歌和旧打开晚到不提交错误历史',async()=>{
 let finish;const f=fixture(undefined,row=>row.platformId==='2'?new Promise(resolve=>{finish=resolve;}):Promise.resolve());const q=f.queue;
 await q.select(song('1'));q.add(song('2'));q.add(song('3'));const late=q.next();await q.next();finish();await late;
 assert.equal(q.current.value,q.key(song('3')));assert.deepEqual(q.navigation.history,[q.key(song('1')),q.key(song('3'))]);f.close();
});
test('清空整个队列在打开中停止，旧请求晚到不能恢复队列或历史',async()=>{
 let release,raw;const storage={getItem:()=>null,setItem:(_key,value)=>{raw=value;}};
 const f=fixture(storage,()=>new Promise(resolve=>{release=resolve;}));const opening=f.queue.select(song('1'));
 await f.queue.clear();assert.equal(f.stops.length,1);assert.equal(f.queue.current.value,null);assert.deepEqual(f.queue.entries.value,[]);
 release();await opening;assert.deepEqual(f.queue.navigation.history,[]);assert.deepEqual(JSON.parse(raw).queue,[]);f.close();
});
