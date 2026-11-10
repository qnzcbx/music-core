import test from 'node:test';
import assert from 'node:assert/strict';
import {downloadStatus,downloadPercent,formatDownloadBytes,downloadError} from '../src/utils/download-display.ts';
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
