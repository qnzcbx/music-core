"""配置及 HTTP 测试只访问进程内 ASGI 应用。"""
import json
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from app.main import create_app
from app.config import SourcePolicy, load_policy
from app.core.errors import CoreError, ErrorCode


@pytest.mark.parametrize('data',[{}, {'sourceOrder':['kuwo']}, {'sourceOrder':['kuwo','qq','netease','qq']},
    {'defaultSelectedSources':[]},{'defaultSelectedSources':['unknown']},{'defaultSelectedSources':['qq','qq']},
    {'unexpected':'synthetic-secret'}, None, []])
def test_config_validation_or_fallback(tmp_path, data):
    path = tmp_path/'config.json'
    path.write_text(json.dumps(data),encoding='utf8')
    policy, fallback = load_policy(path)
    assert policy.defaultSelectedSources == ('kuwo',)
    assert fallback


def test_missing_and_invalid_config(tmp_path):
    path = tmp_path/'missing.json'
    assert load_policy(path)[1]
    path.write_text('{broken',encoding='utf8')
    assert load_policy(path)[1]


def test_custom_order_api(tmp_path):
    path = tmp_path/'sources.json'
    path.write_text(json.dumps({'sourceOrder':['migu','qq','kuwo','netease'],'defaultSelectedSources':['qq']}))
    with TestClient(create_app(path)) as client:
        rows = client.get('/api/providers').json()
        assert [r['id'] for r in rows] == ['migu','qq','kuwo','netease']
        assert [r['id'] for r in rows if r['defaultSelected']] == ['qq']


def test_live_contract_and_openapi():
    with TestClient(create_app()) as client:
        assert client.get('/api/health').json() == {'status':'ok','version':'0.1.0','configurationFallback':False}
        rows = client.get('/api/providers').json()
        assert [r['id'] for r in rows] == ['kuwo','qq','netease','migu']
        assert all(r['implementationStatus']=='not_integrated' and not any(r['capabilities'].values()) for r in rows)
        schema = client.get('/openapi.json').json()
        assert set(schema['paths']) == {'/api/health','/api/providers'}
        assert 'upstreamUrl' not in json.dumps(schema)
        assert client.get('/docs').status_code == 200
        assert client.get('/api/search').status_code == 404
        assert client.post('/api/health').status_code == 405


def test_degraded_health(tmp_path):
    with TestClient(create_app(tmp_path/'missing')) as client:
        assert client.get('/api/health').json()['status'] == 'degraded'


@pytest.mark.parametrize('code,status',[(ErrorCode.INVALID_INPUT,422),(ErrorCode.UNSUPPORTED_PROVIDER,400),
    (ErrorCode.TRACK_NOT_FOUND,404),(ErrorCode.MEDIA_UNAVAILABLE,409),(ErrorCode.UPSTREAM_FAILURE,502),
    (ErrorCode.MEDIA_EXPIRED,410),(ErrorCode.INTERNAL_ERROR,500)])
def test_error_contract(code, status):
    app = create_app()

    @app.get('/test-only')
    async def failing():
        raise CoreError(code)

    with TestClient(app,raise_server_exceptions=False) as client:
        response = client.get('/test-only')
        assert response.status_code == status
        assert response.json()['error']['code'] == code.value


def test_validation_and_unexpected_errors_are_sanitized():
    app = create_app()

    @app.get('/test-only')
    async def failing(value: int):
        raise RuntimeError('synthetic-private-marker')

    with TestClient(app,raise_server_exceptions=False) as client:
        for value,status in [('synthetic-private-marker',422),('1',500)]:
            response = client.get('/test-only',params={'value':value})
            assert response.status_code == status
            assert 'synthetic-private-marker' not in response.text
