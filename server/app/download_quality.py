"""下载品质的字节核对；不保存媒体地址，也不调度解析路线。"""
from app.core.media_probe import verify_media
from app.core.errors import CoreError, ErrorCode

QUALITIES=('auto','standard','high','lossless')

def requested(options):
    value=options.providerQualityId
    if value is not None and (options.purpose!='download' or value not in QUALITIES):
        raise CoreError(ErrorCode.CAPABILITY_UNSUPPORTED)
    return None if value in (None,'auto') else value

def satisfies(rep,quality):
    if quality in (None,'auto'):return True
    if quality=='lossless':return rep.lossless is True and rep.codec in ('flac','alac')
    if quality=='high':return rep.lossless is True or rep.bitrateBps is not None and rep.bitrateBps>=188160
    return rep.lossless is False and rep.bitrateBps is not None and rep.bitrateBps>0

async def qualify(client,media,quality):
    if quality is None:return media
    rep=media.representation
    if not (rep.codec and rep.sampleRateHz):
        rep=await verify_media(client,media.upstreamUrl.get_secret_value(),media.identity.providerId,detail=True,headers={k:v.get_secret_value() for k,v in media.headers.items()})
    if not satisfies(rep,quality):raise CoreError(ErrorCode.MEDIA_UNAVAILABLE)
    return media.model_copy(update={'representation':rep.model_copy(update={'providerQualityId':quality})})
