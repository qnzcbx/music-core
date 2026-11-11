import test from 'node:test';
import assert from 'node:assert/strict';
import {createPaletteLoader,createPaletteSelection,CoverPaletteError} from '../src/utils/ambient-palette.ts';

test('真实采样成功、灰度采样与无封面诊断互不混淆',async()=>{
 const load=createPaletteLoader(async url=>({colors:url==='gray'?[[100,100,100]]:[[180,50,40]],diagnostic:{status:'success',via:'relay',initialFailure:'canvas-cors-denied'}}));
 const color=await load('color'),gray=await load('gray'),none=await load(null);
 assert.equal(color.evidence,'cover');assert.equal(color.diagnostic.via,'relay');
 assert.equal(gray.evidence,'neutral');assert.equal(gray.diagnostic.status,'success');
 assert.equal(none.evidence,'fallback');assert.equal(none.diagnostic.status,'no-cover');
});

test('同封面并发共享缓存，失败保留具体阶段并在三十秒后允许重试',async()=>{
 let count=0,now=0;
 const load=createPaletteLoader(async()=>{count++;throw new CoverPaletteError('canvas-cors-denied')},()=>now);
 const [a,b]=await Promise.all([load('same'),load('same')]);
 assert.equal(count,1);assert.equal(a,b);assert.equal(a.diagnostic.status,'canvas-cors-denied');assert.equal(a.evidence,'fallback');
 now=29999;await load('same');assert.equal(count,1);now=30001;await load('same');assert.equal(count,2);
});

test('空像素不能宣称调色成功，旧取色晚到不能覆盖新封面',async()=>{
 const empty=await createPaletteLoader(async()=>[])('empty');assert.equal(empty.diagnostic.status,'palette-failed');
 const pending=new Map(),commits=[];
 const selection=createPaletteSelection(url=>new Promise(resolve=>pending.set(url,resolve)),value=>commits.push(value.key));
 const a=selection.select('A'),b=selection.select('B');pending.get('B')({key:'B'});await b;pending.get('A')({key:'A'});await a;
 assert.deepEqual(commits,['B']);selection.dispose();
});
