"""仅测试使用的自生成WAV与可中断上游，绝不注册到正式配置。"""
import asyncio
import io
import math
import struct
import wave
from time import time
import httpx
from app.models import ResolvedMedia,MediaRepresentation
from app.core.errors import CoreError,ErrorCode


def own_audio():
    output=io.BytesIO()
    with wave.open(output,'wb') as audio:
        audio.setparams((1,2,8000,0,'NONE','not compressed'))
        audio.writeframes(b''.join(struct.pack('<h',int(1200*math.sin(i*2*math.pi*330/8000))) for i in range(8000*48)))
    return output.getvalue()


class FaultUpstream:
    def __init__(self):
        self.audio=own_audio();self.opens=[];self.closed=0;self.interruptions=0
        self.invalid=set();self.broken=set();self.denied=set();self.hold_next=False;self.held=set()
        self.fail_open=False;self.requests=0;self.closed_versions=set()

    async def resolve(self,identity):
        version=len(self.opens)+1;self.opens.append(identity)
        if self.hold_next:
            self.hold_next=False;self.held.add(version)
            while version in self.held:await asyncio.sleep(.01)
        if self.fail_open:raise CoreError(ErrorCode.UPSTREAM_FAILURE)
        return ResolvedMedia(id=f'fixture-{version}',identity=identity,representation=MediaRepresentation(container='wav'),
            resolvedAt=int(time()*1000),upstreamUrl=f'https://fixture.kuwo.cn/audio/{version}')

    async def handle(self,request):
        self.requests+=1
        version=int(request.url.path.rsplit('/',1)[1])
        if version in self.denied:return httpx.Response(403)
        if version in self.invalid:return httpx.Response(410)
        start,end=0,len(self.audio)-1
        value=request.headers.get('range')
        if value:
            first,last=value[6:].split('-')
            start=int(first) if first else max(0,len(self.audio)-int(last))
            if first and last:end=min(end,int(last))
        if start>=len(self.audio):return httpx.Response(416,headers={'Content-Range':f'bytes */{len(self.audio)}'})
        headers={'Content-Type':'audio/wav','Content-Length':str(end-start+1),'Accept-Ranges':'bytes'}
        if value:headers['Content-Range']=f'bytes {start}-{end}/{len(self.audio)}'
        owner=self
        class AudioStream(httpx.AsyncByteStream):
            async def __aiter__(self):
                if request.method=='HEAD':return
                for offset in range(start,end+1,4096):
                    if version in owner.broken:
                        owner.interruptions+=1;owner.invalid.add(version)
                        raise httpx.ReadError('受控测试中途断流')
                    yield owner.audio[offset:min(offset+4096,end+1)]
                    await asyncio.sleep(.025)
            async def aclose(self):owner.closed+=1;owner.closed_versions.add(version)
        return httpx.Response(206 if value else 200,headers=headers,stream=AudioStream())


async def allow_fixture_target(url):
    """仅应用工厂注入，生产域名和DNS检查不变。"""
