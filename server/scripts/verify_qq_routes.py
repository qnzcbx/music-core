"""固定样本比较官方基线与当前审核后的策略；不调用未准入的外部服务。"""
import asyncio
import json
import math
from time import perf_counter
import httpx
from app.providers.qq import QQProvider
from app.models import TrackIdentity
from app.core.errors import CoreError
from scripts.verify_qq import probe

async def main():
    result={}
    async with httpx.AsyncClient(timeout=httpx.Timeout(12,connect=5),follow_redirects=False) as client:
        for name,order in [('baseline',('official',)),('reviewed',('vkeys','tang','official'))]:
            rows=[];times=[];resolve_times=[];count=[0]
            async def count_request(request):count[0]+=1
            client.event_hooks={'request':[count_request]}
            provider=QQProvider(client,route_order=order)
            for mid in ['001e7VNQ43nv4W','0012mUEO3j7Xwj']:
                start=perf_counter();row={'songmid':mid}
                try:
                    m=await provider.resolve(TrackIdentity(providerId='qq',platformId=mid))
                    row['resolveMs']=round((perf_counter()-start)*1000)
                    row.update({'resolved':True,'identityConfirmed':True,'route':'official','probe':await asyncio.wait_for(probe(client,m),20)})
                except CoreError as error:row['error']=error.code.value
                except httpx.HTTPError as error:row['errorType']=type(error).__name__
                except asyncio.TimeoutError:row['error']='probe_timeout'
                resolve_times.append(row.get('resolveMs',round((perf_counter()-start)*1000)))
                row['elapsedMs']=round((perf_counter()-start)*1000);times.append(row['elapsedMs']);rows.append(row)
            result[name]={'order':order,'eligible':provider.available_routes,'rows':rows,'requestsIncludingProbe':count[0],
                'meanResolveMs':round(sum(resolve_times)/len(resolve_times)),'p95ResolveMs':sorted(resolve_times)[math.ceil(.95*len(resolve_times))-1],
                'meanEndToEndMs':round(sum(times)/len(times)),'p95EndToEndMs':sorted(times)[math.ceil(.95*len(times))-1]}
    print(json.dumps(result,ensure_ascii=True,indent=2))

if __name__=='__main__':asyncio.run(main())
