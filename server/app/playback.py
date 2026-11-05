"""播放API只发本地能力地址，私有媒体始终由Store持有。"""
from pathlib import Path
from fastapi import APIRouter,Request,Response
from fastapi.responses import HTMLResponse
from app.models import DTO,TrackIdentity,PublicMedia
from app.core.errors import CoreError,ErrorCode
from app.media_stream import proxy,validate_target


class OpenRequest(DTO):
    identity: TrackIdentity


class OpenResponse(DTO):
    playbackId: str
    streamUrl: str
    media: PublicMedia
    expiresInSeconds: float


def playback_router(*, dev_player=False):
    router=APIRouter()

    @router.post('/api/playback/open',response_model=OpenResponse)
    async def open_playback(body: OpenRequest,request: Request,response: Response):
        if body.identity.providerId!='kuwo':
            raise CoreError(ErrorCode.PROVIDER_NOT_INTEGRATED)
        media=await request.app.state.kuwo.resolve(body.identity)
        await request.app.state.target_check(media.upstreamUrl.get_secret_value())
        store,leases=request.app.state.media_store,request.app.state.playback_leases
        stored=store.put(media)
        try:
            key=leases.create(stored.id)
        except BaseException:
            with store.lock:
                store.records.pop(stored.id,None)
            raise
        response.headers['Cache-Control']='no-store'
        return OpenResponse(playbackId=key,streamUrl=f'/api/playback/{key}/stream',
            media=stored.public_view(),expiresInSeconds=store.settings.lease_ttl)

    @router.get('/api/playback/{key}/stream')
    @router.head('/api/playback/{key}/stream')
    async def stream(key: str,request: Request):
        leases,store=request.app.state.playback_leases,request.app.state.media_store
        media,ticket=leases.use(key,stream=True)
        return await proxy(request,media,request.app.state.http_client,
            lambda:store.release(media.id,ticket),request.app.state.target_check)

    @router.post('/api/playback/{key}/renew')
    async def renew(key: str,request: Request):
        request.app.state.playback_leases.use(key)
        return Response(status_code=204,headers={'Cache-Control':'no-store'})

    @router.post('/api/playback/{key}/close')
    async def close(key: str,request: Request):
        request.app.state.playback_leases.close(key)
        return Response(status_code=204,headers={'Cache-Control':'no-store'})

    if dev_player:
        @router.get('/dev/player-controller.mjs',include_in_schema=False)
        async def controller():
            return Response(Path(__file__).with_name('player-controller.mjs').read_text(encoding='utf8'),
                media_type='text/javascript',headers={'Cache-Control':'no-store'})

        @router.get('/dev/player',include_in_schema=False,response_class=HTMLResponse)
        async def player():
            return HTMLResponse(Path(__file__).with_name('player.html').read_text(encoding='utf8'),
                headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer'})

    return router
