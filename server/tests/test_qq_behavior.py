"""行为兼容回归：允许的协议会实际执行，缺少可选回显不是解析异常。"""
import asyncio
import httpx
import pytest
from app.providers.qq import QQProvider
from app.providers.qq_resolvers import vkeys,qqovo,media,result,RouteResult
from app.models import TrackIdentity
from test_media_lifecycle import media as fixture_media

TRACK=TrackIdentity(providerId='qq',platformId='ABC')
URL='https://aqqmusic.tc.qq.com/synthetic'

def test_identity_evidence_cannot_contradict_response():
    from pydantic import SecretStr
    bound=RouteResult('vkeys',SecretStr(URL))
    echoed=RouteResult('vkeys',SecretStr(URL),response_mid='ABC')
    assert bound.evidence=='request_bound' and bound.response_mid is None
    assert echoed.evidence=='confirmed' and echoed.response_mid=='ABC'
    with pytest.raises(TypeError):RouteResult('vkeys',SecretStr(URL),evidence='confirmed')

def test_approved_url_only_executes_then_official(monkeypatch):
    calls=[]
    async def external(client,mid):
        calls.append(('vkeys',mid));return result('vkeys',mid,{'url':URL})
    async def official(identity):
        calls.append(('official',identity.platformId));return fixture_media().model_copy(update={'identity':identity})
    monkeypatch.setattr(vkeys,'resolve',external)
    p=QQProvider(None,route_order=('vkeys','official'),enabled_external_routes=('vkeys',))
    monkeypatch.setattr(p,'_resolve_official',official)
    value=asyncio.run(p.resolve(TRACK))
    assert value.identity==TRACK and calls==[('vkeys','ABC'),('official','ABC')]

def test_approved_echo_stops_without_duplicate_probe(monkeypatch):
    calls=[]
    async def external(client,mid):
        calls.append('vkeys');return result('vkeys',mid,{'url':URL,'mid':mid})
    async def probe(client,url):calls.append('probe')
    async def official(identity):pytest.fail('成功后不应继续官方')
    monkeypatch.setattr(vkeys,'resolve',external);monkeypatch.setattr(media,'verify_media',probe)
    p=QQProvider(None,route_order=('vkeys','official'),enabled_external_routes=('vkeys',))
    monkeypatch.setattr(p,'_resolve_official',official)
    value=asyncio.run(p.resolve(TRACK))
    assert value.identity==TRACK and calls==['vkeys','probe']

def test_qqovo_minimal_bootstrap_uses_one_scoped_cookie_jar():
    requests=[];sessions=[]
    def handler(r):
        requests.append(r)
        if len(requests)==1:return httpx.Response(200,json={'apiSignKey':'synthetic'},headers={'set-cookie':'local=synthetic; Secure; Path=/'})
        assert r.headers['cookie']=='local=synthetic' and 'authorization' not in r.headers
        return httpx.Response(200,json={'url':URL})
    def factory(**options):
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler),**options);sessions.append(client);return client
    value=asyncio.run(qqovo.resolve(None,'ABC',session_factory=factory))
    assert value.evidence=='request_bound' and value.response_mid is None
    assert len(requests)==2 and sessions[0].is_closed
