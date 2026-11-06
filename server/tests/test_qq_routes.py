"""路线编排使用人工路由，不能作为外部服务已经接入的证据。"""
import asyncio
import httpx
import pytest
from app.providers.qq import QQProvider
from app.models import TrackIdentity
from app.core.errors import CoreError,ErrorCode
from test_media_lifecycle import media

TRACK=TrackIdentity(providerId='qq',platformId='ABC')

@pytest.mark.parametrize('order',[(),('official','official'),('unknown',), 'official',('official',1)])
def test_invalid_order(order):
    with pytest.raises(ValueError):QQProvider(None,route_order=order)

@pytest.mark.parametrize('timeout',[0,-1,61,True,float('nan')])
def test_invalid_timeout(timeout):
    with pytest.raises(ValueError):QQProvider(None,resolve_timeout=timeout)

def test_disabled_external_cannot_make_requests():
    async def execute():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:pytest.fail('禁止外部请求'))) as client:
            p=QQProvider(client,route_order=('vkeys','tang'))
            with pytest.raises(CoreError) as error:await p.resolve(TRACK)
            assert error.value.code==ErrorCode.CAPABILITY_UNSUPPORTED
    asyncio.run(execute())

@pytest.mark.parametrize('code,continues',[(ErrorCode.UPSTREAM_FAILURE,True),(ErrorCode.UPSTREAM_TIMEOUT,True),
    (ErrorCode.MEDIA_UNAVAILABLE,True),(ErrorCode.ACCESS_DENIED,False),(ErrorCode.UPSTREAM_INVALID_RESPONSE,False)])
def test_order_and_failure_boundary(code,continues):
    async def execute():
        calls=[]
        class Fixture(QQProvider):
            available_routes=('vkeys','official')
            async def _resolve_route(self,route,identity,options):
                calls.append(route)
                if route=='vkeys':raise CoreError(code)
                return media().model_copy(update={'identity':identity})
        p=Fixture(None,route_order=('vkeys','official'))
        if continues:assert (await p.resolve(TRACK)).identity==TRACK
        else:
            with pytest.raises(CoreError):await p.resolve(TRACK)
        assert calls==(['vkeys','official'] if continues else ['vkeys'])
    asyncio.run(execute())

def test_stop_success_identity_and_all_failed():
    async def execute():
        calls=[]
        class Fixture(QQProvider):
            available_routes=('vkeys','official')
            async def _resolve_route(self,route,identity,options):
                calls.append(route);return media().model_copy(update={'identity':identity})
        p=Fixture(None,route_order=('official','vkeys'))
        await p.resolve(TRACK);assert calls==['official']
        async def wrong(*args):return media()
        p._resolve_route=wrong
        with pytest.raises(CoreError) as error:await p.resolve(TRACK)
        assert error.value.code==ErrorCode.UPSTREAM_INVALID_RESPONSE
        async def failed(*args):raise CoreError(ErrorCode.MEDIA_UNAVAILABLE)
        p._resolve_route=failed
        with pytest.raises(CoreError) as error:await p.resolve(TRACK)
        assert error.value.code==ErrorCode.MEDIA_UNAVAILABLE
    asyncio.run(execute())

def test_total_budget_cancel_and_no_continuation():
    async def execute():
        calls=[];closed=[];entered=asyncio.Event()
        class Fixture(QQProvider):
            available_routes=('vkeys','official')
            async def _resolve_route(self,route,identity,options):
                calls.append(route);entered.set()
                try:await asyncio.Event().wait()
                finally:closed.append(True)
        p=Fixture(None,route_order=('vkeys','official'),resolve_timeout=.02)
        with pytest.raises(CoreError) as error:await p.resolve(TRACK)
        assert error.value.code==ErrorCode.UPSTREAM_TIMEOUT and calls==['vkeys'] and closed==[True]
        calls.clear();closed.clear();entered.clear()
        task=asyncio.create_task(p.resolve(TRACK));await entered.wait();task.cancel()
        with pytest.raises(asyncio.CancelledError):await task
        assert calls==['vkeys'] and closed==[True]
        p.continue_on_transient=False
        async def failed(route,*args):calls.append(route);raise CoreError(ErrorCode.UPSTREAM_FAILURE)
        p._resolve_route=failed;calls.clear()
        with pytest.raises(CoreError):await p.resolve(TRACK)
        assert calls==['vkeys']
    asyncio.run(execute())
