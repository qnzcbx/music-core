"""发布前的有界媒体检查，按来源使用现有目标规则。"""
from urllib.parse import urljoin,urlsplit
import re
import httpx
from app.media_stream import validate_target
from app.core.errors import CoreError, ErrorCode, UnsupportedRouteFormat
from app.models import MediaRepresentation

QQ_ENCRYPTED_SUFFIXES=('.mgg','.mflac')


def inspect_audio(raw):
    """只读取有界前缀，未出现可靠结构的字段保持未知。"""
    result={}
    if raw.startswith(b'fLaC'):
        result['container']='flac'
        if len(raw)>=42 and raw[4]&127==0 and int.from_bytes(raw[5:8],'big')==34:
            bits=int.from_bytes(raw[18:26],'big');rate=bits>>44
            if rate>0:
                result['codec']='flac';result['lossless']=True;result['sampleRateHz']=rate
        return MediaRepresentation(**result)
    if len(raw)>=12 and raw[4:8]==b'ftyp':
        result['container']='mp4'
        def boxes(start,end,depth=0):
            if depth>8:return
            pos=start
            while pos+8<=end:
                size=int.from_bytes(raw[pos:pos+4],'big');kind=raw[pos+4:pos+8]
                if size<8 or pos+size>end:break
                if kind in (b'moov',b'trak',b'mdia',b'minf',b'stbl'):boxes(pos+8,pos+size,depth+1)
                if kind==b'stsd' and size>=16:boxes(pos+16,pos+size,depth+1)
                if kind in (b'mp4a',b'alac') and size>=36:
                    result['codec']='aac' if kind==b'mp4a' else 'alac';result['lossless']=kind==b'alac'
                    rate=int.from_bytes(raw[pos+32:pos+36],'big')>>16
                    result['sampleRateHz']=rate or None
                    # esds 的 DecoderConfigDescriptor 保存实际 AAC 平均码率；仅在音频样本框内读取。
                    child=pos+36
                    while child+8<=pos+size:
                        length=int.from_bytes(raw[child:child+4],'big');name=raw[child+4:child+8]
                        if length<8 or child+length>pos+size:break
                        if name==b'esds':
                            for marker in range(child+12,child+length-14):
                                if raw[marker]!=4:continue
                                cursor=marker+1;count=0
                                for _ in range(4):
                                    byte=raw[cursor];cursor+=1;count=(count<<7)|(byte&127)
                                    if not byte&128:break
                                if count>=13 and cursor+count<=child+length and raw[cursor] in (64,102,103,104):
                                    bitrate=int.from_bytes(raw[cursor+9:cursor+13],'big')
                                    if bitrate>0:result['bitrateBps']=bitrate
                        child+=length

                pos+=size
        boxes(0,len(raw))
        return MediaRepresentation(**result)
    offset=0
    if raw.startswith(b'ID3') and len(raw)>=10:
        if any(v&128 for v in raw[6:10]):return MediaRepresentation(**result)
        offset=10+sum(v<<(7*(3-i)) for i,v in enumerate(raw[6:10]))+(10 if raw[5]&16 else 0)
    # 两个连续合法 MPEG Layer III 帧才提供码率，避免将标签内偶然同步字当成音频。
    def frame(pos):
        if pos+4>len(raw):return None
        h=int.from_bytes(raw[pos:pos+4],'big');version=(h>>19)&3;layer=(h>>17)&3;index=(h>>12)&15;sr=(h>>10)&3
        if h>>21!=2047 or version==1 or layer!=1 or index in (0,15) or sr==3:return None
        kbps=([0,32,40,48,56,64,80,96,112,128,160,192,224,256,320] if version==3 else [0,8,16,24,32,40,48,56,64,80,96,112,128,144,160])[index]
        rate=[44100,48000,32000][sr]//(1 if version==3 else 2 if version==2 else 4)
        length=(144 if version==3 else 72)*kbps*1000//rate+((h>>9)&1)
        return kbps*1000,rate,length
    for pos in range(offset,min(len(raw)-4,offset+4096)):
        first=frame(pos)
        if first and frame(pos+first[2]):
            result['container']='mpeg-audio';result['codec']='mp3';result['lossless']=False;result['sampleRateHz']=first[1]
            # VBR 头不能把第一帧瞬时码率当平均值。
            if not any(tag in raw[pos:pos+first[2]] for tag in (b'Xing',b'VBRI')):result['bitrateBps']=first[0]
            return MediaRepresentation(**result)
    return MediaRepresentation(**result)

async def verify_media(client,url,provider_id='qq',*,detail=False,headers=None):
    limit=65536 if detail else 4096
    try:
        for hop in range(4):
            await validate_target(url,provider_id,client)
            if provider_id in ('qq','netease'):
                path=urlsplit(url).path.lower()
                encrypted_suffixes=QQ_ENCRYPTED_SUFFIXES if provider_id=='qq' else ('.ncm',)
                if path.endswith(encrypted_suffixes):raise CoreError(ErrorCode.CAPABILITY_UNSUPPORTED)
                if path.endswith(('.m3u8','.mpd')):raise UnsupportedRouteFormat()
            response=await client.send(httpx.Request('GET',url,headers={**(headers or {}),'Range':f'bytes=0-{limit-1}',
                'Accept-Encoding':'identity','User-Agent':'Mozilla/5.0'}),stream=True,follow_redirects=False,auth=None)
            try:
                if response.status_code in (301,302,303,307,308):
                    location=response.headers.get('location')
                    if not location or hop==3:raise CoreError(ErrorCode.UPSTREAM_FAILURE)
                    url=urljoin(url,location);continue
                if response.status_code in (401,403):raise CoreError(ErrorCode.ACCESS_DENIED)
                if response.status_code not in (200,206):raise CoreError(ErrorCode.UPSTREAM_FAILURE)
                expected=None
                if response.status_code==206:
                    match=re.fullmatch(r'bytes 0-([0-9]{1,20})/([0-9]{1,20})',response.headers.get('content-range',''))
                    if not match or int(match[2])<=0 or int(match[1])!=min(limit-1,int(match[2])-1):
                        raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
                    expected=int(match[1])+1
                mime=response.headers.get('content-type','').lower()
                if any(t in mime for t in ('html','json')) or response.headers.get('content-encoding','identity')!='identity':
                    raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
                prefix=bytearray()
                async for chunk in response.aiter_raw(chunk_size=limit):
                    prefix.extend(chunk[:limit-len(prefix)])
                    if len(prefix)>=limit:break
                raw=bytes(prefix)
                if expected is not None and len(raw)!=expected:raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
                if not (raw.startswith((b'ID3',b'fLaC',b'OggS')) or raw[4:8]==b'ftyp' or len(raw)>1 and raw[0]==255 and raw[1]&224==224):
                    raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
                kind='flac' if raw.startswith(b'fLaC') else 'mpeg-audio' if raw.startswith(b'ID3') or len(raw)>1 and raw[0]==255 and raw[1]&224==224 else 'ogg' if raw.startswith(b'OggS') else 'mp4'
                size=int(match[2]) if expected is not None else None
                length=response.headers.get('content-length','')
                if size is None and re.fullmatch(r'[0-9]{1,20}',length) and int(length)>0:size=int(length)
                if detail:
                    return inspect_audio(raw).model_copy(update={'sizeBytes':size,'contentType':mime.split(';')[0] or None})
                return MediaRepresentation(container=kind,codec='flac' if kind=='flac' else 'mp3' if kind=='mpeg-audio' else None,
                    contentType=mime.split(';')[0] or None,sizeBytes=size,lossless=True if kind=='flac' else None)
            finally:await response.aclose()
    except httpx.TimeoutException:raise CoreError(ErrorCode.UPSTREAM_TIMEOUT) from None
    except httpx.HTTPError:raise CoreError(ErrorCode.UPSTREAM_FAILURE) from None
