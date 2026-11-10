import {requestJson} from './http';
import type {TrackIdentity,OpenResponse} from '../types/core';
export const openPlayback=(identity:TrackIdentity,signal?:AbortSignal)=>requestJson<OpenResponse>('/api/playback/open',{method:'POST',body:JSON.stringify({identity}),signal});
/** close/renew为204响应，接线阶段直接检查HTTP状态，不解析JSON。 */
export async function updateLease(id:string,operation:'close'|'renew',signal?:AbortSignal){
 const response=await fetch(`/api/playback/${encodeURIComponent(id)}/${operation}`,{method:'POST',signal});
 if(!response.ok)throw new Error('播放会话操作失败');
}
