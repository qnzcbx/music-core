"""有限读取服务公开入口，不请求歌曲或输出页面中的签名材料。"""
import asyncio
import json
from time import perf_counter
import httpx


async def main():
    rows=[]
    async with httpx.AsyncClient(timeout=httpx.Timeout(8,connect=5),follow_redirects=False) as client:
        for route,url in [('vkeys','https://api.vkeys.cn/'),('tang','https://tang.api.s01s.cn/')]:
            start=perf_counter();row={'route':route,'implemented':True,'enabled':False,'songRequests':0}
            response=None
            try:
                response=await client.send(httpx.Request('GET',url,headers={'User-Agent':'Mozilla/5.0'}),stream=True)
                size=0
                async for chunk in response.aiter_raw(chunk_size=4096):
                    size+=len(chunk)
                    if size>=65536:break
                row.update({'status':response.status_code,'publicBytesRead':size,'contentType':response.headers.get('content-type'),
                    'condition':'public_entry_only_service_permission_and_recording_evidence_unconfirmed'})
            except httpx.HTTPError as error:row.update({'errorType':type(error).__name__,'condition':'public_entry_request_failed_permission_unconfirmed'})
            finally:
                if response is not None:await response.aclose()
            row['elapsedMs']=round((perf_counter()-start)*1000);rows.append(row)
    print(json.dumps(rows,ensure_ascii=True,indent=2))


if __name__=='__main__':asyncio.run(main())
