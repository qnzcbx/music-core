"""行为兼容回归：允许的协议会实际执行，缺少可选回显不是解析异常。"""
import asyncio
import httpx
import pytest
from app.providers.qq import QQProvider
from app.providers.qq_resolvers import vkeys,media,result,RouteResult
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
    async def probe(client,url):
        calls.append('probe')
        from app.models import MediaRepresentation
        return MediaRepresentation()
    async def official(identity):pytest.fail('成功后不应继续官方')
    monkeypatch.setattr(vkeys,'resolve',external);monkeypatch.setattr(media,'verify_media',probe)
    p=QQProvider(None,route_order=('vkeys','official'),enabled_external_routes=('vkeys',))
    monkeypatch.setattr(p,'_resolve_official',official)
    value=asyncio.run(p.resolve(TRACK))
    assert value.identity==TRACK and calls==['vkeys','probe']
