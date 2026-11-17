import test from 'node:test';
import assert from 'node:assert/strict';
import {downloadStatus,downloadPercent,formatDownloadBytes,downloadError} from '../src/utils/download-display.ts';

test('转换失败与源校验失败独立，保底不冒充MP3完成',()=>{
 assert.equal(downloadStatus({status:'failed',sourcePreserved:true,errorCode:'conversion_failed'}),'转换失败');
 assert.equal(downloadStatus({status:'failed',errorCode:'conversion_failed'}),'转换失败');
 assert.equal(downloadStatus({status:'failed',errorCode:'source_verification_failed'}),'源文件校验失败');
 for(const phase of ['source_verifying','transcoding','output_verifying','publishing'])assert.equal(downloadPercent({status:'downloading',phase,receivedBytes:100,totalBytes:100}),null);
});
test('解析不显示下载百分比，未知总长不伪造百分比，收完不提前宣称完成',()=>{
 assert.equal(downloadPercent({status:'resolving',receivedBytes:0,totalBytes:100}),null);
 assert.equal(downloadPercent({status:'downloading',receivedBytes:42,totalBytes:null}),null);
 const task={status:'downloading',receivedBytes:100,totalBytes:100};assert.equal(downloadPercent(task),100);assert.equal(downloadStatus(task),'正在校验文件…');
 assert.equal(downloadStatus({...task,status:'completed'}),'已完成');assert.equal(formatDownloadBytes(1048576),'1.0 MB');
});
test('失败类别明确区分访问拒绝、超时、校验及保存失败',()=>{
 const messages=['access_denied','upstream_timeout','upstream_invalid_response','file_io_error'].map(downloadError);
 assert.equal(new Set(messages).size,4);assert.equal(downloadStatus({status:'cancelled'}),'已取消');
});

test('转换和验证保持活跃但不显示虚假的下载百分比',()=>{
 const task={status:'downloading',receivedBytes:100,totalBytes:100};
 assert.equal(downloadStatus({...task,phase:'transcoding'}),'转换中');
 assert.equal(downloadStatus({...task,phase:'verifying'}),'正在验证最终文件');
 assert.equal(downloadPercent({...task,phase:'transcoding'}),null);
 assert.equal(downloadPercent({...task,phase:'verifying'}),null);
});
