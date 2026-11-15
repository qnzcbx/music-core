"""只处理下载任务私有 FLAC 临时文件，不接受前端路径或任意参数。"""
import asyncio
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import logging
from app.core.errors import CoreError, ErrorCode
from app.models import MediaRepresentation

logger = logging.getLogger(__name__)


class ConversionError(CoreError):
    def __init__(self, phase, cause):
        self.phase = phase
        self.cause = cause
        super().__init__(ErrorCode.UPSTREAM_INVALID_RESPONSE)


def tools():
    configured=os.environ.get('MUSIC_CORE_FFMPEG')
    executable=shutil.which(configured or 'ffmpeg')
    if not executable:return None,None
    executable=str(Path(executable).resolve())
    sibling=Path(executable).with_name('ffprobe.exe' if os.name=='nt' else 'ffprobe')
    probe=str(sibling) if sibling.is_file() else shutil.which('ffprobe')
    return executable,probe


async def reap(process, *, drain_stderr=True):
    if process.returncode is None:
        try:process.kill()
        except ProcessLookupError:pass
    # Windows管道也需读到EOF，单等进程退出会留下Proactor传输对象。
    if process.stdout:
        while await process.stdout.read(8192):pass
    if drain_stderr and process.stderr:
        while await process.stderr.read(8192): pass
    await process.wait()
    await asyncio.sleep(0)


async def owned_process(args,*,timeout=15,output=None,max_bytes=None):
    """直接拥有子进程；取消、超时和输出超限都等待进程退出。"""
    spawning=asyncio.create_task(asyncio.create_subprocess_exec(*args,stdin=asyncio.subprocess.DEVNULL,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0))
    try:process=await asyncio.shield(spawning)
    except asyncio.CancelledError:
        process=await spawning
        await asyncio.shield(reap(process))
        raise
    async def drain_errors():
        tail = bytearray()
        while chunk := await process.stderr.read(8192):
            tail.extend(chunk)
            del tail[:-8192]
        return bytes(tail)
    errors = asyncio.create_task(drain_errors())
    async def collect():
        data=bytearray()
        while True:
            chunk=await process.stdout.read(8192)
            if not chunk:break
            data.extend(chunk)
            if len(data)>131072:raise CoreError(ErrorCode.MEDIA_CAPACITY)
        code=await process.wait()
        if code:
            tail = (await errors).decode(errors='replace')
            # 仅记录固定诊断短语，避免路径、签名地址或标签泄露。
            reasons = [reason for reason in ('invalid sync code','invalid frame header','Invalid data found','Unknown encoder','Permission denied','No space left') if reason in tail]
            logger.warning('media_process_failed exit=%s reasons=%s', code, reasons)
            raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
        return bytes(data)
    reader=asyncio.create_task(collect())
    async def monitor():
        while not reader.done():
            if output is not None and output.exists() and output.stat().st_size>max_bytes:raise CoreError(ErrorCode.MEDIA_CAPACITY)
            await asyncio.sleep(.1)
        return await reader
    try:return await asyncio.wait_for(monitor(),timeout)
    finally:
        if not reader.done():reader.cancel()
        await asyncio.gather(reader,return_exceptions=True)
        await asyncio.shield(reap(process, drain_stderr=False))
        await asyncio.shield(errors)


async def encoder_capability():
    executable,probe=tools()
    if not executable or not probe:return {'available':False,'reason':'本机未安装完整 FFmpeg 工具，保留原格式'}
    try:
        output=await owned_process([executable,'-hide_banner','-encoders'])
        available=re.search(rb'\bA\S*\s+libmp3lame\s',output) is not None
        return {'available':available,'reason':'' if available else '本机暂不支持 MP3 转换，保留原格式'}
    except NotImplementedError:
        # Windows reload 的 Selector 循环不支持子进程；只降级可选转换能力。
        return {'available':False,'reason':'当前运行环境不支持音频转换，保留原格式'}
    except (OSError,CoreError,asyncio.TimeoutError):return {'available':False,'reason':'转换工具暂不可用，保留原格式'}


async def probe_file(probe,path):
    try:
        data=json.loads(await owned_process([probe,'-v','error','-protocol_whitelist','file,pipe','-select_streams','a','-show_entries','stream=codec_name,sample_rate,channels,bit_rate:format=duration,size','-of','json',str(path)]))
        streams=data.get('streams',[])
        if len(streams)!=1:raise ValueError()
        stream=streams[0];duration=float(data['format']['duration'])
        if duration<=0 or int(data['format']['size'])!=path.stat().st_size:raise ValueError()
        return {**stream,'duration':duration}
    except (ValueError,KeyError,TypeError):raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE) from None


async def validate_flac(source, *, timeout=300):
    executable, probe = tools()
    if not executable or not probe: raise CoreError(ErrorCode.CAPABILITY_UNSUPPORTED)
    original = await probe_file(probe, source)
    if original['codec_name'] != 'flac': raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
    decoded = await owned_process([executable,'-nostdin','-v','error','-xerror','-protocol_whitelist','file,pipe','-threads','1','-i',str(source),'-map','0:a:0','-progress','pipe:1','-nostats','-f','null','-'],timeout=timeout)
    times = re.findall(rb'^out_time_us=(\d+)\r?$', decoded, re.M)
    if not times or b'progress=end' not in decoded or abs(int(times[-1])/1000000-original['duration']) > max(.15, original['duration']*.001):
        raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
    return original


async def convert_flac(source,output,bitrate,*,timeout,max_bytes,phase_changed=None):
    phase = 'transcoding'
    def change(value):
        nonlocal phase
        phase = value
        if phase_changed: phase_changed(value)
    try:
        return await _convert_flac(source,output,bitrate,timeout=timeout,max_bytes=max_bytes,change=change)
    except (CoreError, OSError, asyncio.TimeoutError) as error:
        raise ConversionError(phase, error) from None


async def _convert_flac(source,output,bitrate,*,timeout,max_bytes,change):
    if bitrate not in (192000,320000):raise CoreError(ErrorCode.INVALID_INPUT)
    capability=await encoder_capability()
    if not capability['available']:raise CoreError(ErrorCode.CAPABILITY_UNSUPPORTED)
    executable,probe=tools();original=await probe_file(probe,source)
    if original['codec_name']!='flac':raise CoreError(ErrorCode.CAPABILITY_UNSUPPORTED)
    rate=int(original['sample_rate']);channels=int(original['channels'])
    if channels not in (1,2):raise CoreError(ErrorCode.CAPABILITY_UNSUPPORTED)
    # MP3不能表示任意FLAC采样率，仅编码器不支持时降至48kHz，不做上采样。
    target_rate=rate if rate in (32000,44100,48000) else min(rate,48000)
    command=[executable,'-nostdin','-hide_banner','-v','error','-xerror','-n','-protocol_whitelist','file,pipe','-threads','1','-i',str(source),'-map','0:a:0','-vn','-map_metadata','-1',
        '-c:a','libmp3lame','-b:a',str(bitrate),'-ar',str(target_rate),'-threads','1','-fs',str(max_bytes),'-f','mp3',str(output)]
    await owned_process(command,timeout=timeout,output=output,max_bytes=max_bytes)
    change('output_verifying')
    actual=await probe_file(probe,output)
    size=output.stat().st_size
    if actual['codec_name']!='mp3' or abs(int(actual.get('bit_rate',0))-bitrate)>1000 or int(actual.get('channels',0))!=channels or int(actual.get('sample_rate',0))!=target_rate or abs(actual['duration']-original['duration'])>max(.3,original['duration']*.002):
        raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
    expected=original['duration']*bitrate/8
    if not 0<size<=max_bytes or size<expected*.9 or size>expected*1.1+65536:raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
    decoded=await owned_process([executable,'-nostdin','-v','error','-xerror','-protocol_whitelist','file,pipe','-threads','1','-i',str(output),'-map','0:a:0','-threads','1','-progress','pipe:1','-nostats','-f','null','-'],timeout=timeout)
    times=re.findall(rb'^out_time_us=(\d+)\r?$',decoded,re.M)
    if not times or b'progress=end' not in decoded or abs(int(times[-1])/1000000-original['duration'])>max(.15,original['duration']*.001):raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
    return MediaRepresentation(container='mpeg-audio',codec='mp3',bitrateBps=bitrate,sampleRateHz=int(actual['sample_rate']),sizeBytes=size,lossless=False)
