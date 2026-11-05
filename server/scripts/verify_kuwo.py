"""显式手动在线验收：两个关键词、每词最多十条、合计最多两次取链，不获取音频。"""
import asyncio
import json
import socket
import subprocess
import sys
from pathlib import Path
import httpx
from app.providers.kuwo import KuwoProvider
from app.models import TrackIdentity
from app.core.errors import CoreError


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
                    selected.append(TrackIdentity.model_validate(data['items'][0]['identity']))
            async with httpx.AsyncClient(timeout=httpx.Timeout(12,connect=5),follow_redirects=False) as upstream:
                provider=KuwoProvider(upstream)
                for identity in selected[:2]:
                    try:
                        media=await provider.resolve(identity)
                        public=media.public_view()
                        result['resolves'].append({'identity':identity.model_dump(),'outcome':'resolved',
                            'representation':public.representation.model_dump(),'validUntil':public.validUntil,
                            'mediaAccessChecked':False})
                    except CoreError as error:
                        result['resolves'].append({'identity':identity.model_dump(),'outcome':'failed','code':error.code.value})
        print(json.dumps(result,ensure_ascii=True,indent=2))
    finally:
        process.terminate()
        process.wait(timeout=10)


if __name__=='__main__':
    asyncio.run(main())
