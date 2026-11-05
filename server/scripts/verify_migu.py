"""咪咕有限真实验收，最多四个录音及4096字节前缀，不输出临时媒体地址。"""
import asyncio
import json
from time import perf_counter
import httpx
from app.providers.migu import MiguProvider
from app.core.errors import CoreError
from scripts.verify_qq import probe


async def main():
    result={'searches':[],'resolves':[],'credentialConfigured':False}
    async with httpx.AsyncClient(timeout=httpx.Timeout(12,connect=5),follow_redirects=False) as client:
        provider=MiguProvider(client);selected=[]
        for query in ['银临','许嵩']:
            start=perf_counter()
            try:
                page=await provider.search(query,10)
                result['searches'].append({'query':query,'count':len(page.items),'validIdCount':len(page.items),
                    'elapsedMs':round((perf_counter()-start)*1000),'withArtists':sum(bool(i.artists) for i in page.items),
                    'withAlbum':sum(i.album is not None for i in page.items),'withCover':sum(i.cover is not None for i in page.items),
                    'withDuration':sum(i.durationSeconds is not None for i in page.items),
                    'selected':[i.identity.platformId for i in page.items[:2]]})
                selected.extend(page.items[:2])
            except CoreError as error:result['searches'].append({'query':query,'error':error.code.value})
        for item in selected[:4]:
            row={'platformId':item.identity.platformId}
            try:
                # 每个样本使用新Provider，证明没有搜索缓存前提。
                media=await MiguProvider(client).resolve(item.identity)
                row.update({'outcome':'resolved','route':'native_resourceinfo_listen_h5_v2.4',
                    'mediaHost':httpx.URL(media.upstreamUrl.get_secret_value()).host,'representation':media.representation.model_dump()})
                row['probe']=await asyncio.wait_for(probe(client,media,'migu'),20)
            except CoreError as error:row['error']=error.code.value
            except (httpx.HTTPError,asyncio.TimeoutError) as error:row['errorType']=type(error).__name__
            result['resolves'].append(row)
    print(json.dumps(result,ensure_ascii=True,indent=2))


if __name__=='__main__':asyncio.run(main())
