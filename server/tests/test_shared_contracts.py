"""双端固定样本通过正式数据模型、回退判定和 ASGI 流入口。"""
import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.errors import ErrorCode, may_try_another_route
from app.main import create_app
from app.models import TrackIdentity
from test_media_lifecycle import media
from test_media_stream import allow_test_target

FIXTURES = Path(__file__).resolve().parents[2] / 'tests' / 'fixtures' / 'contracts'


def rows(name):
    return json.loads((FIXTURES / f'{name}.json').read_text(encoding='utf8'))


@pytest.mark.parametrize('case', rows('identity'))
def test_shared_identity(case):
    if case['valid']:
        assert TrackIdentity.model_validate(case['identity']).model_dump() == case['identity']
    else:
        with pytest.raises(ValidationError):
            TrackIdentity.model_validate(case['identity'])


@pytest.mark.parametrize('case', rows('resolution'))
def test_shared_resolution_policy(case):
    assert may_try_another_route(ErrorCode(case['python'])) is case['continues']


@pytest.mark.parametrize('case', rows('playback-stream'))
def test_shared_range_and_failure_status(case):
    body = case['body'].encode()

    def upstream(request):
        assert request.headers.get('range') == case['range']
        return httpx.Response(case['upstream'], headers=case['headers'], stream=httpx.ByteStream(body))

    app = create_app(transport=httpx.MockTransport(upstream), target_check=allow_test_target)
    with TestClient(app) as client:
        item = app.state.media_store.put(media())
        lease = app.state.playback_leases.create(item.id)
        url = f'/api/playback/{lease}/stream'
        headers = {'Range': case['range']} if case.get('range') else {}
        for method in ('HEAD', 'GET'):
            response = client.request(method, url, headers=headers)
            assert response.status_code == case['status']
            if method == 'GET' and (response.status_code < 400 or response.status_code == 416):
                assert response.content == body
            if response.status_code == 200:
                assert 'content-range' not in response.headers
            assert not app.state.media_store.records[item.id].streams
