"""显式在线验收：两词各十条、最多四次取链，每条媒体至多读取4096字节。"""
import asyncio
import json
import socket
import subprocess
import sys
import re
from pathlib import Path
import httpx
from app.providers.kuwo import KuwoProvider
from app.models import TrackIdentity
from app.core.errors import CoreError


async def probe_media(client, media):
    """只检查有限前缀，不把取得URL等同于浏览器播放或完整下载。"""
    headers={k:v.get_secret_value() for k,v in media.headers.items()}
    headers.update({'Range':'bytes=0-4095','Accept-Encoding':'identity'})
    try:
        async with client.stream('GET',media.upstreamUrl.get_secret_value(),headers=headers,
                follow_redirects=True) as response:
            mime=response.headers.get('content-type','').split(';')[0].lower()
            prefix=bytearray()
            if response.status_code not in (200,206):
                return {'passed':False,'status':response.status_code,'bytesRead':0}
            async for chunk in response.aiter_raw(chunk_size=4096):
                prefix.extend(chunk[:4096-len(prefix)])
                if len(prefix)>=4096:
                    break
            data=bytes(prefix)
            kind='flac' if data.startswith(b'fLaC') else 'ogg' if data.startswith(b'OggS') else 'mp3' if data.startswith(b'ID3') or len(data)>1 and data[0]==255 and data[1]&224==224 else None
            bad=(mime in ('text/html','application/json') or data.lstrip().startswith((b'<',b'{',b'['))
                 or response.headers.get('content-encoding','identity')!='identity')
            total=None
            if response.status_code==206:
                match=re.fullmatch(r'bytes 0-(\d+)/(\d+)',response.headers.get('content-range',''))
                if match and len(data)==min(4096,int(match[1])+1) and int(match[2])>int(match[1]):
                    total=int(match[2])
                else:
                    bad=True
            elif response.headers.get('content-length','').isdigit():
                total=int(response.headers['content-length'])
            return {'passed':bool(kind) and not bad,'status':response.status_code,'bytesRead':len(data),
                    'contentType':mime,'prefixFormat':kind,'sizeBytes':total}
    except httpx.HTTPError as error:
        return {'passed':False,'errorType':type(error).__name__}


async def main():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0))
        port=sock.getsockname()[1]
    process=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port',str(port)],
        cwd=Path(__file__).resolve().parents[1],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    result={'port':port,'searches':[],'resolves':[]}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            base=f'http://127.0.0.1:{port}'
            for _ in range(100):
                try:
                    response=await client.get(base+'/api/health')
                    if response.status_code==200:
                        break
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(.1)
            else:
                raise RuntimeError('本地服务未启动')
            result['health']=response.json()
            result['providers']=(await client.get(base+'/api/providers')).json()
            result['openapiStatus']=(await client.get(base+'/openapi.json')).status_code
            result['docsStatus']=(await client.get(base+'/docs')).status_code
            selected=[]
            for query in ['银临','许嵩']:
                response=await client.post(base+'/api/search',json={'providerId':'kuwo','query':query,'limit':10})
                data=response.json()
                result['searches'].append({'query':query,'status':response.status_code,
                    'count':len(data.get('items',[])),'error':data.get('error')})
                if data.get('items'):
                    selected.extend(TrackIdentity.model_validate(item['identity']) for item in data['items'][:2])
            paths=[]
            async def record_route(response):
                paths.append(response.request.url.path)
            async with httpx.AsyncClient(timeout=httpx.Timeout(12,connect=5),follow_redirects=False,
                    max_redirects=3,event_hooks={'response':[record_route]}) as upstream:
                provider=KuwoProvider(upstream)
                for identity in selected[:4]:
                    paths.clear()
                    try:
                        media=await provider.resolve(identity)
                        public=media.public_view()
                        routes=list(paths)
                        probe=await asyncio.wait_for(probe_media(upstream,media),timeout=20)
                        result['resolves'].append({'identity':identity.model_dump(),'outcome':'resolved',
                            'routes':routes,'probe':probe,
                            'representation':public.representation.model_dump(),'validUntil':public.validUntil,
                            'mediaAccessChecked':True})
                    except CoreError as error:
                        result['resolves'].append({'identity':identity.model_dump(),'outcome':'failed','code':error.code.value,'routes':list(paths)})
                    except asyncio.TimeoutError:
                        result['resolves'].append({'identity':identity.model_dump(),'outcome':'probe_timeout'})
        print(json.dumps(result,ensure_ascii=True,indent=2))
    finally:
        process.terminate()
        process.wait(timeout=10)


if __name__=='__main__':
    asyncio.run(main())
