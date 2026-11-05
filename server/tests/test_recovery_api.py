"""恢复复用open接口：只用自有音频上游，不访问酷我。"""
import time
import httpx
from fastapi.testclient import TestClient
from app.main import create_app
from app.core.media_store import MediaSettings
from scripts.recovery_fixture import FaultUpstream,allow_fixture_target


def setup():
    fixture=FaultUpstream()
    app=create_app(transport=httpx.MockTransport(fixture.handle),target_check=allow_fixture_target,
        media_settings=MediaSettings(media_ttl=.01,lease_ttl=10,sweep_interval=.01))
    return fixture,app


def test_reopen_uses_stable_identity_and_new_lease():
    fixture,app=setup()
    with TestClient(app) as client:
        app.state.kuwo=fixture
        body={'identity':{'providerId':'kuwo','platformId':'1'}}
        first=client.post('/api/playback/open',json=body).json()
        second=client.post('/api/playback/open',json=body).json()
        assert first['playbackId']!=second['playbackId'] and first['media']['id']!=second['media']['id']
        assert len(fixture.opens)==2 and fixture.opens[0]==fixture.opens[1]
        client.post(f"/api/playback/{first['playbackId']}/close")
        assert client.get(first['streamUrl']).status_code==410
        assert client.head(second['streamUrl']).status_code==200
        client.post(f"/api/playback/{second['playbackId']}/close")
        time.sleep(.03);app.state.playback_leases.sweep()
        assert not app.state.media_store.records


def test_failed_reopen_creates_no_orphan_record():
    fixture,app=setup()
    with TestClient(app) as client:
        app.state.kuwo=fixture;fixture.fail_open=True
        result=client.post('/api/playback/open',json={'identity':{'providerId':'kuwo','platformId':'1'}})
        assert result.status_code==502 and not app.state.media_store.records and not app.state.playback_leases.entries


def test_upstream_expired_then_new_resource_accessible():
    fixture,app=setup()
    with TestClient(app) as client:
        app.state.kuwo=fixture
        body={'identity':{'providerId':'kuwo','platformId':'1'}}
        first=client.post('/api/playback/open',json=body).json();fixture.invalid.add(1)
        response=client.head(first['streamUrl'])
        assert response.status_code==410
        second=client.post('/api/playback/open',json=body).json()
        assert client.head(second['streamUrl']).status_code==200
        assert not any(r.streams for r in app.state.media_store.records.values())
