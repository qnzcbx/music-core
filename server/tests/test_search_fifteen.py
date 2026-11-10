"""15条批次、绑定游标及酷我旧参数的离线契约回归。"""
import asyncio
from urllib.parse import parse_qs
import httpx
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.providers.kuwo import KuwoProvider
from app.providers.qq import QQProvider
from app.providers.netease import NeteaseProvider
from app.providers.migu import MiguProvider

@pytest.mark.parametrize('provider',[KuwoProvider,QQProvider,NeteaseProvider,MiguProvider])
def test_fifteen_roundtrip(provider):
    def handler(request):
        values=request.url.params
        if provider is NeteaseProvider:values={k:v[0] for k,v in parse_qs(request.content.decode()).items()}
        if provider is KuwoProvider:
            assert values['vipver']=='1' and values['rn']=='15';page=int(values['pn'])
        elif provider is QQProvider:assert values['n']=='15';page=int(values['p'])-1
        elif provider is NeteaseProvider:assert values['limit']=='15';page=int(values['offset'])//15
        else:assert values['pageSize']=='15';page=int(values['pageNo'])-1
        ids=range(page*15+1,min((page+1)*15,31)+1)
        if provider is KuwoProvider:data={'abslist':[{'MUSICRID':f'MUSIC_{i}','SONGNAME':'人工'} for i in ids],'TOTAL':'31'}
        elif provider is QQProvider:data={'code':0,'data':{'song':{'list':[{'mid':f'T{i}','title':'人工'} for i in ids],'totalnum':31}}}
        elif provider is NeteaseProvider:data={'code':200,'result':{'songs':[{'id':i,'name':'人工'} for i in ids],'songCount':31}}
        else:data={'code':'000000','songResultData':{'result':[{'contentId':str(i),'name':'人工'} for i in ids],'totalCount':31}}
        return httpx.Response(200,json=data)
    async def execute():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            p=provider(client);first=await p.search('人工',15);second=await p.search('人工',15,first.nextCursor);last=await p.search('人工',15,second.nextCursor)
            assert [len(page.items) for page in (first,second,last)]==[15,15,1]
            assert last.nextCursor is None
            assert len({item.identity.key for page in (first,second,last) for item in page.items})==31
    asyncio.run(execute())

def test_api_default_fifteen_and_reject_sixteen():
    def handler(request):
        assert request.url.params['rn']=='15'
        return httpx.Response(200,json={'abslist':[],'TOTAL':'0'})
    with TestClient(create_app(transport=httpx.MockTransport(handler))) as client:
        assert client.post('/api/search',json={'providerId':'kuwo','query':'人工'}).status_code==200
        assert client.post('/api/search',json={'providerId':'kuwo','query':'人工','limit':16}).status_code==422
