"""固定单曲真实协议实验，分离API结果与正式发布；不落盘URL或会话材料。"""
import asyncio
import json
from time import perf_counter
import httpx
from app.providers.qq import QQProvider
from app.providers.qq_resolvers import vkeys,tang
from app.models import TrackIdentity
from app.core.errors import CoreError,ErrorCode
from scripts.verify_qq import probe

MID='001e7VNQ43nv4W'


async def main():
    report=[]
    for route in ('official','vkeys','tang'):
        events=[]
        class Observer(httpx.AsyncBaseTransport):
            def __init__(self):self.transport=httpx.AsyncHTTPTransport()
            async def handle_async_request(self,request):
                event={'method':request.method,'host':request.url.host,
                    'path':request.url.path if request.url.host in ('u.y.qq.com','api.vkeys.cn','tang.api.s01s.cn') else '[media]'}
                events.append(event)
                response=await self.transport.handle_async_request(request)
                event['httpStatus']=response.status_code
                upstream=response.stream
                class Stream(httpx.AsyncByteStream):
                    async def __aiter__(self):
                        prefix=bytearray()
                        try:
                            async for chunk in upstream:
                                prefix.extend(chunk[:max(0,2048-len(prefix))]);yield chunk
                        finally:
                            try:
                                data=json.loads(prefix)
                                if isinstance(data,dict):
                                    event['responseKeys']=list(data)
                                    if type(data.get('code')) in (int,str):event['businessCode']=data['code']
                                    for key in ('authenticated','loginRequired'):
                                        if type(data.get(key))is bool:event[key]=data[key]
                            except (ValueError,UnicodeError):pass
                    async def aclose(self):await upstream.aclose()
                response.stream=Stream()
                return response
            async def aclose(self):await self.transport.aclose()
        def factory(**options):return httpx.AsyncClient(transport=Observer(),**options)
        start=perf_counter();row={'route':route,'songmid':MID,'events':events,'browserPlayed':False,'seekTested':False}
        async with factory(timeout=httpx.Timeout(10,connect=5),follow_redirects=False) as client:
            try:
                if route=='official':
                    media=await QQProvider(client).resolve(TrackIdentity(providerId='qq',platformId=MID))
                    row.update({'urlObtained':True,'identity':'official_mid_matched'})
                else:
                    adapter={'vkeys':vkeys,'tang':tang}[route]
                    value=await asyncio.wait_for(adapter.resolve(client,MID),25)
                    row.update({'urlObtained':True,'identity':value.evidence,'mediaHost':httpx.URL(value.url.get_secret_value()).host})
                    from app.models import ResolvedMedia,MediaRepresentation
                    media=ResolvedMedia(id='isolated-experiment',identity=TrackIdentity(providerId='qq',platformId=MID),
                        representation=MediaRepresentation(),resolvedAt=0,upstreamUrl=value.url)
                row['resolveMs']=round((perf_counter()-start)*1000)
                row['probe']=await asyncio.wait_for(probe(client,media),20)
            except CoreError as error:row['error']=error.code.value
            except (httpx.HTTPError,asyncio.TimeoutError) as error:row['errorType']=type(error).__name__
        row['elapsedMs']=round((perf_counter()-start)*1000);report.append(row)
    print(json.dumps(report,ensure_ascii=True,indent=2))


def chain_browser(browser_path,mid):
    """仅当前实验进程预览请求绑定资源，不改变正式Provider发布条件。"""
    import sys
    from time import time
    from uuid import uuid4
    from app.models import ResolvedMedia,MediaRepresentation
    import app.main as core
    original=core.QQProvider
    class ExperimentQQProvider(original):
        async def resolve(self,identity,options=None):
            async def execute():
                failures=[]
                for route,adapter in [('vkeys',vkeys),('tang',tang),('official',None)]:
                    try:
                        if adapter is None:return await super(ExperimentQQProvider,self).resolve(identity,options)
                        value=await adapter.resolve(self.client,identity.platformId)
                        media=ResolvedMedia(id=uuid4().hex,identity=identity,representation=MediaRepresentation(),
                            resolvedAt=int(time()*1000),upstreamUrl=value.url)
                        checked=await probe(self.client,media)
                        if not checked['passed']:
                            failures.append({'route':route,'error':'probe_failed'});continue
                        print(json.dumps({'isolatedChainHit':route,'identity':value.evidence,
                            'previousFailures':failures,'laterRoutesCalled':False,'probe':checked}),flush=True)
                        return media
                    except CoreError as error:
                        if error.code.value=='access_denied':raise
                        failures.append({'route':route,'error':error.code.value})
                    except httpx.HTTPError as error:
                        failures.append({'route':route,'errorType':type(error).__name__})
                raise CoreError(ErrorCode.MEDIA_UNAVAILABLE)
            return await asyncio.wait_for(execute(),25)
    core.QQProvider=ExperimentQQProvider
    previous=sys.argv
    try:
        from scripts.verify_playback_browser import main as play
        sys.argv=['isolated-chain','--browser',browser_path,'--provider','qq','--track',mid,'--recover']
        play()
    finally:
        core.QQProvider=original;sys.argv=previous


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description='QQ单路协议或隔离串行预览实验')
    parser.add_argument('--chain-browser',help='使用已有Chromium进行隔离串行播放')
    parser.add_argument('--mid',default='004Yi5BD3ksoAN',help='固定实验songmid')
    args=parser.parse_args()
    if args.chain_browser:chain_browser(args.chain_browser,args.mid)
    else:asyncio.run(main())
