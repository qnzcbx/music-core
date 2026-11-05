"""有限真实QQ验收：两个关键词各十条、最多四次取链，不记录媒体能力值。"""
import asyncio
import json
import os
import re
from time import perf_counter
from urllib.parse import urljoin
import httpx
from app.providers.qq import QQProvider
from app.core.errors import CoreError
from app.media_stream import validate_target


async def probe(client,media):
    url=media.upstreamUrl.get_secret_value()
    headers={'User-Agent':'Mozilla/5.0','Range':'bytes=0-4095','Accept-Encoding':'identity'}
    for redirect in range(4):
        await validate_target(url,'qq')
        response=await client.send(httpx.Request('GET',url,headers=headers),stream=True)
        try:
            if response.status_code in (301,302,303,307,308):
                location=response.headers.get('location')
                if not location or redirect==3:return {'passed':False,'status':response.status_code}
                url=urljoin(url,location);continue
            prefix=bytearray()
            async for chunk in response.aiter_raw(chunk_size=4096):
                prefix.extend(chunk[:4096-len(prefix)])
                if len(prefix)>=4096:break
            raw=bytes(prefix);mime=response.headers.get('content-type','')
            kind='mp4' if raw[4:8]==b'ftyp' else 'mp3' if raw.startswith(b'ID3') else 'ogg' if raw.startswith(b'OggS') else None
            size=None;match=re.fullmatch(r'bytes 0-\d+/(\d+)',response.headers.get('content-range',''))
            if match:size=int(match[1])
            return {'passed':response.status_code in (200,206) and kind is not None and not any(t in mime for t in ('html','json')),
                'status':response.status_code,'bytesRead':len(raw),'prefixFormat':kind,'contentType':mime,
                'sizeBytes':size,'redirects':redirect,'mediaHost':httpx.URL(url).host}
        finally:await response.aclose()


async def main():
    result={'searches':[],'resolves':[],'credentialConfigured':bool(os.environ.get('MUSIC_CORE_QQ_COOKIE'))}
    async with httpx.AsyncClient(timeout=httpx.Timeout(12,connect=5),max_redirects=3) as client:
        provider=QQProvider(client,cookie=os.environ.get('MUSIC_CORE_QQ_COOKIE',''))
        selected=[]
        for query in ['许嵩','银临']:
            start=perf_counter()
            try:
                page=await provider.search(query,10)
                result['searches'].append({'query':query,'count':len(page.items),'validMidCount':len(page.items),
                    'elapsedMs':round((perf_counter()-start)*1000),'selected':[i.identity.platformId for i in page.items[:2]]})
                selected.extend(page.items[:2])
            except CoreError as error:result['searches'].append({'query':query,'error':error.code.value})
        for item in selected[:4]:
            try:
                media=await provider.resolve(item.identity)
                await validate_target(media.upstreamUrl.get_secret_value(),'qq')
                checked=await asyncio.wait_for(probe(client,media),20)
                result['resolves'].append({'songmid':item.identity.platformId,'outcome':'resolved',
                    'route':'music.vkey.GetVkey.UrlGetVkey','probe':checked,'validUntil':media.validUntil})
            except CoreError as error:result['resolves'].append({'songmid':item.identity.platformId,'error':error.code.value,
                'platformCode':getattr(error,'platform_code',None)})
            except httpx.HTTPError as error:result['resolves'].append({'songmid':item.identity.platformId,'errorType':type(error).__name__})
            except asyncio.TimeoutError:result['resolves'].append({'songmid':item.identity.platformId,'error':'probe_timeout'})
    print(json.dumps(result,ensure_ascii=True,indent=2))


if __name__=='__main__':asyncio.run(main())
