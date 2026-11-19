import test from 'node:test';
import assert from 'node:assert/strict';
import {effectScope} from 'vue';
import {useQueue} from '../src/player/useQueue.ts';
import {decodePlayer} from '../src/player/player-persistence.ts';
const song=(id,source='kuwo')=>({id,source,platformId:id,mid:id,name:'同名歌曲',title:'同名歌曲',artist:'歌手',album:'专辑',duration:10,resolveState:'idle'});
const local=fileId=>({kind:'local',fileId,id:JSON.stringify(['local',fileId]),source:'local',name:'历史.mp3',title:'历史.mp3',artist:'',album:'',cover:null,duration:null});
function fixture(storage,open=async()=>{}) {
 const scope=effectScope(),calls=[],stops=[];
 const queue=scope.run(()=>useQueue(async row=>{calls.push(row.platformId);await open(row);},async()=>{stops.push(true);},()=>true,()=>0,storage));
 return {queue,calls,stops,close:()=>scope.stop()};
}

test('本地身份与在线不碰撞，同文件去重，队列直接交还本地条目',async()=>{
 const scope=effectScope(),opened=[];
 const q=scope.run(()=>useQueue(async row=>opened.push(row),async()=>{},()=>true,()=>0));
 q.add(song('same'));q.add(local('same'));q.add(local('same'));assert.equal(q.entries.value.length,2);
 await q.select(local('same'));assert.equal(opened[0].kind,'local');assert.equal(opened[0].fileId,'same');assert.equal(opened[0].artist,'');
 assert.equal('identity' in opened[0],false);scope.stop();
});

test('混合队列复用四种模式与历史，删除其他文件不中断，删除当前文件停止',async()=>{
 const scope=effectScope(),opened=[],stopped=[];
 const q=scope.run(()=>useQueue(async row=>opened.push(row.id),async()=>{stopped.push(true)},()=>true,()=>0));
 await q.select(local('a'));q.add(song('r'));q.add(local('b'));
 await q.next();assert.equal(q.current.value,JSON.stringify(['kuwo','r']));await q.previous();assert.equal(q.current.value,JSON.stringify(['local','a']));
 for(const mode of ['repeat_all','repeat_one','shuffle','order']){q.setMode(mode);await q.next();assert.ok(q.entries.value.some(e=>e.key===q.current.value));}
 await q.select(local('a'));await q.remove(JSON.stringify(['local','b']));assert.equal(stopped.length,0);
 await q.remove(JSON.stringify(['local','a']));assert.equal(q.current.value,null);assert.equal(stopped.length,1);scope.stop();
});

test('无效本地文件 ID 不写入快照，在线队列重载兼容',async()=>{
 let value=null;const storage={getItem:()=>value,setItem:(_key,text)=>{value=text}};
 const f=fixture(storage);f.queue.add(song('11'));await f.queue.select(local('file-id'));
 assert.ok(value);assert.equal(value.includes('file-id'),false);assert.equal(value.includes('/stream'),false);
 const next=fixture(storage);assert.equal(next.queue.entries.value.length,1);assert.equal(next.queue.entries.value[0].track.platformId,'11');assert.equal(next.queue.current.value,null);
 f.close();next.close();
});

test('稳定本地文件 ID、混合队列、模式和进度恢复但不打开媒体，清空后不复活',async()=>{
 let raw=null;const storage={getItem:()=>raw,setItem:(_key,value)=>{raw=value;}};
 const f=fixture(storage),fileId='a'.repeat(64);
 f.queue.add(song('11'));await f.queue.select({...local(fileId),duration:123});
 f.queue.position.value=37.5;f.queue.setMode('repeat_all');
 const restored=fixture(storage);
 assert.equal(restored.queue.currentSong.value.fileId,fileId);
 assert.equal(restored.queue.currentSong.value.duration,123);
 assert.equal(restored.queue.position.value,37.5);
 assert.equal(restored.queue.navigation.mode,'repeat_all');
 assert.equal(restored.queue.entries.value.length,2);assert.deepEqual(restored.calls,[]);
 await restored.queue.select(song('11'));assert.equal(restored.queue.position.value,0);
 await restored.queue.clear();const empty=fixture(storage);
 assert.equal(empty.queue.currentSong.value,null);assert.deepEqual(empty.queue.entries.value,[]);
 f.close();restored.close();empty.close();
});

test('旧快照兼容，非法进度归零，恢复身份与元数据显式投影',()=>{
 for(const version of [1,2,3]){
   const value=decodePlayer(JSON.stringify({schemaVersion:version,queue:[],position:-10}));
   assert.equal(value.kind,'valid');assert.equal(value.value.position,0);
 }
 for(const position of ['60',null,-1,86401]){
   const value=decodePlayer(JSON.stringify({schemaVersion:3,position}));
   assert.equal(value.value.position,0);
 }
 for(const query of ['token=secret','Authorization=secret','signature=secret']){
   let raw;const f=fixture({getItem:()=>null,setItem:(_key,value)=>{raw=value;}});
   f.queue.add({...song('12'),cover:`https://example.test/a.jpg?${query}`,streamUrl:'secret',lease:'secret'});
   assert.equal(raw.includes('secret'),false);f.close();
 }
});
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

test('online queue discards expired desktop relay URLs but preserves the track and stable cover',()=>{
 let raw;const f=fixture({getItem:()=>null,setItem:(_key,value)=>{raw=value;}});
 const stale='http://127.0.0.1:4321/covers/0123456789abcdef0123456789abcdef';
 const stable='https://y.gtimg.cn/music/photo_new/T002R500x500M000000lqMaM0HR7AF.jpg';
 f.queue.add({...song('12'),cover:stale});f.queue.add({...song('13'),cover:stable});
 assert.equal(raw.includes(stale),false);
 const old=JSON.parse(raw);old.queue[0].metadata.cover=stale;
 const restored=decodePlayer(JSON.stringify(old)).value.queue;
 assert.deepEqual(restored.map(row=>[row.track.platformId,row.metadata.cover]),[['12',null],['13',stable]]);
 f.close();
});
