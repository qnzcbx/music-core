import { requestJson } from './http';
import type { ProviderId,SearchPage } from '../types/core';
export function searchSource(providerId:ProviderId,query:string,cursor:string|null,signal:AbortSignal){
 return requestJson<SearchPage>('/api/search',{method:'POST',body:JSON.stringify({providerId,query,limit:15,cursor}),signal});
}
