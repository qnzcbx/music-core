"""自有媒体验证直接下载和播放使用同一串行编排，不访问公网。"""
import asyncio
import httpx
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.downloads import DownloadSettings
from app.models import ResolvedMedia,MediaRepresentation
from app.core.errors import CoreError,ErrorCode

@pytest.mark.parametrize('hit',['official','vkeys','xunhuisi','denied'])
def test_direct_download_and_playback_order(tmp_path,monkeypatch,hit):
    monkeypatch.setenv('MUSIC_CORE_QQ_RESOLVER_ORDER','official,vkeys,tang,xunhuisi')
    async def allow(*args):pass
    body=b'ID3'+b'x'*100
    app=create_app(target_check=allow,download_settings=DownloadSettings(directory=tmp_path),
        transport=httpx.MockTransport(lambda r:httpx.Response(200,headers={'content-length':str(len(body))},stream=httpx.ByteStream(body))))
    calls=[]
    async def route(name,identity,options):
        calls.append((options.purpose,name))
        if hit=='denied':raise CoreError(ErrorCode.ACCESS_DENIED)
        if name!=hit:raise CoreError(ErrorCode.MEDIA_UNAVAILABLE if name=='official' else ErrorCode.UPSTREAM_FAILURE)
        return ResolvedMedia(id='fixture',identity=identity,representation=MediaRepresentation(),resolvedAt=1,upstreamUrl='https://aqqmusic.tc.qq.com/sample')
    with TestClient(app) as client:
        app.state.qq._resolve_route=route
        created=client.post('/api/downloads',json={'identity':{'providerId':'qq','platformId':'ABC'}}).json()
        import time
        for _ in range(200):
            job=client.get('/api/downloads/'+created['id']).json()
            if job['status'] in ('completed','failed'):break
            time.sleep(.005)
        assert job['status']==('failed' if hit=='denied' else 'completed')
        assert not app.state.media_store.records and not app.state.playback_leases.entries
        if hit!='denied':assert (tmp_path/job['filename']).read_bytes()==body
        opened=client.post('/api/playback/open',json={'identity':{'providerId':'qq','platformId':'ABC'}})
        assert opened.status_code==(403 if hit=='denied' else 200)
        expected=['official'] if hit=='denied' else ['official','vkeys','tang','xunhuisi'][:['official','vkeys','tang','xunhuisi'].index(hit)+1]
        assert calls==[(purpose,name) for purpose in ('download','playback') for name in expected]
        if opened.status_code==200:client.post(opened.json()['streamUrl'].replace('/stream','/close'))


def test_removed_route_is_configuration_error():
    from app.providers.qq import QQProvider
    with pytest.raises(ValueError,match='qqovo'):QQProvider(None,route_order=('official','qqovo'))
