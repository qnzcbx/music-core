import type {LyricDocument,LyricLine,TrackIdentity} from '../types/core';

/** 二分定位；同时间戳的多行以最后一行为索引，展示时整组高亮。 */
export function currentLyricIndex(lines:readonly LyricLine[],seconds:number){
 if(!Number.isFinite(seconds))return -1;
 let low=0,high=lines.length-1,result=-1;const ms=seconds*1000;
 while(low<=high){const mid=(low+high)>>>1;if(lines[mid]!.startMs<=ms){result=mid;low=mid+1;}else high=mid-1;}
 const line=lines[result];return line&&line.endMs!=null&&ms>=line.endMs?-1:result;
}
export interface LyricsState {document:LyricDocument|null;loading:boolean;error:string}
/** 歌词仅按稳定身份换代，独立于媒体租约和模板生命周期。 */
export function createLyricsLoader(fetcher:(identity:TrackIdentity,signal:AbortSignal)=>Promise<LyricDocument>,notify:(state:LyricsState)=>void){
 let generation=0,key='',controller:AbortController|undefined;
 async function select(identity:TrackIdentity|null,force=false){
  const next=identity?JSON.stringify([identity.providerId,identity.platformId]):'';
  if(next===key&&!force)return;
  key=next;const token=++generation;controller?.abort();notify({document:null,loading:!!identity,error:''});
  if(!identity)return;
  const request=controller=new AbortController();
  try{const document=await fetcher({...identity},request.signal);
   if(token!==generation)return;
   if(document.identity.providerId!==identity.providerId||document.identity.platformId!==identity.platformId)throw new Error('歌词与当前歌曲不匹配');
   notify({document,loading:false,error:''});
  }catch(error){if(token===generation&&!request.signal.aborted)notify({document:null,loading:false,error:error instanceof Error?error.message:'歌词加载失败，请重试'});}
 }
 return {select,dispose(){generation++;controller?.abort();}};
}
