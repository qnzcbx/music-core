"""下载品质的字节核对；不保存媒体地址，也不调度解析路线。"""
from app.models import MediaRepresentation
from app.core.errors import CoreError, ErrorCode

QUALITIES=('auto','standard','high','lossless')

def requested(options):
    value=options.providerQualityId
    if value is not None and (options.purpose!='download' or value not in QUALITIES):
        raise CoreError(ErrorCode.CAPABILITY_UNSUPPORTED)
    return None if value in (None,'auto') else value

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

def satisfies(rep,quality):
    if quality in (None,'auto'):return True
    if quality=='lossless':return rep.lossless is True and rep.codec in ('flac','alac')
    if quality=='high':return rep.lossless is True or rep.bitrateBps is not None and rep.bitrateBps>=188160
    return rep.lossless is False and rep.bitrateBps is not None and rep.bitrateBps<=160000

async def qualify(client,media,quality):
    if quality is None:return media
    from app.core.media_probe import verify_media
    rep=media.representation
    if not (rep.codec and rep.sampleRateHz):
        rep=await verify_media(client,media.upstreamUrl.get_secret_value(),media.identity.providerId,detail=True,headers={k:v.get_secret_value() for k,v in media.headers.items()})
    if not satisfies(rep,quality):raise CoreError(ErrorCode.MEDIA_UNAVAILABLE)
    return media.model_copy(update={'representation':rep.model_copy(update={'providerQualityId':quality})})
