"""网易云有限在线验收：两词各十条、最多四次取链、每次最多4096字节。"""
import asyncio
import json
from time import perf_counter
import httpx
from app.providers.netease import NeteaseProvider
from app.core.errors import CoreError
from scripts.verify_qq import probe


async def main():
    result={'searches':[],'resolves':[],'credentialConfigured':False}
    async with httpx.AsyncClient(timeout=httpx.Timeout(12,connect=5),follow_redirects=False) as client:
        provider=NeteaseProvider(client);selected=[]
        for query in ['银临','许嵩']:
            start=perf_counter()
            try:
                page=await provider.search(query,10)
                result['searches'].append({'query':query,'count':len(page.items),
                    'elapsedMs':round((perf_counter()-start)*1000),'validIdCount':len(page.items),
                    'withArtists':sum(bool(i.artists) for i in page.items),'withAlbum':sum(i.album is not None for i in page.items),
                    'withCover':sum(i.cover is not None for i in page.items),'withDuration':sum(i.durationSeconds is not None for i in page.items),
                    'selected':[i.identity.platformId for i in page.items[:2]]})
                selected.extend(page.items[:2])
            except CoreError as error:result['searches'].append({'query':query,'error':error.code.value})
        for item in selected[:4]:
            row={'platformId':item.identity.platformId}
            try:
                media=await provider.resolve(item.identity)
                row.update({'outcome':'resolved','route':'native_player_url','mediaHost':httpx.URL(media.upstreamUrl.get_secret_value()).host,
                    'representation':media.representation.model_dump(),'expiryKnown':media.validUntil is not None})
                row['probe']=await asyncio.wait_for(probe(client,media,'netease'),20)
            except CoreError as error:
                row['error']=error.code.value
                row['platformCode']=getattr(error,'platform_code',None)
            except (httpx.HTTPError,asyncio.TimeoutError) as error:row['errorType']=type(error).__name__
            result['resolves'].append(row)
    print(json.dumps(result,ensure_ascii=True,indent=2))


if __name__=='__main__':asyncio.run(main())
