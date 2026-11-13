"""独立的进程内下载消费者：解析、限流、临时文件和原子发布。"""
import asyncio
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
import os
import re
import stat
import hashlib
import ipaddress
import json
import logging
import threading
import unicodedata
from time import time
from typing import Literal
from urllib.parse import urljoin, urlsplit
from uuid import uuid4

import anyio
import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import Field
from app.models import DTO, TrackIdentity, ResolveOptions, MediaRepresentation
from app.download_quality import inspect_audio, satisfies
from app.providers import provider_for
from app.core.errors import CoreError, ErrorCode
from app.media_stream import validate_target, range_header, OwnedStream

TERMINAL = {'completed', 'failed', 'cancelled'}
ROOT = Path(__file__).resolve().parents[2] / 'downloads'


OutputMode=Literal['original','mp3_320','mp3_192']


DownloadQuality=Literal['auto','standard','high','lossless']


class DownloadRequest(DTO):
    outputMode: OutputMode = 'original'
    expectedSourceCodec: Literal['flac'] | None = None
    quality: DownloadQuality = 'auto'
    identity: TrackIdentity
    # 名称仅用于文件展示，不参与身份解析；缺省按稳定身份命名。
    title: str | None = Field(default=None, max_length=500)
    artist: str | None = Field(default=None, max_length=500)


class DownloadTask(DTO):
    outputMode: OutputMode = 'original'
    expectedSourceCodec: Literal['flac'] | None = None
    phase: Literal['downloading','source_verifying','transcoding','output_verifying','publishing','verifying','completed'] | None = None
    sourceMedia: MediaRepresentation | None = None
    sourcePreserved: bool = False
    transcoded: bool = False
    finalSizeBytes: int | None = None
    quality: DownloadQuality = 'auto'
    actualMedia: MediaRepresentation | None = None
    id: str
    identity: TrackIdentity
    title: str | None
    artist: str | None
    status: Literal['queued', 'resolving', 'downloading', 'completed', 'failed', 'cancelled']
    receivedBytes: int = 0
    totalBytes: int | None = None
    progress: float | None = None
    filename: str | None = None
    fileId: str | None = None
    format: str | None = None
    errorCode: str | None = None
    createdAt: int
    updatedAt: int


class SavedDownloadFile(DTO):
    fileId: str
    filename: str
    sizeBytes: int
    format: str
    modifiedAt: int


class RemoveDownloadFile(DTO):
    deleteFile: bool = False


def file_error(status, message):
    return JSONResponse(status_code=status, content={'error': {'code': 'local_file_error', 'message': message, 'retryable': status >= 500}})


def trusted_local(request):
    """文件能力只向回环客户端开放；拒绝跨站及恶意 Host 请求。"""
    def loopback(host):
        if host == 'localhost': return True
        try: return ipaddress.ip_address(host or '').is_loopback
        except ValueError: return False
    try:
        origin = request.headers.get('origin')
        return (request.client is not None and loopback(request.client.host)
                and loopback(urlsplit('http://' + request.headers.get('host', '')).hostname)
                and (not origin or urlsplit(origin).scheme in ('http', 'https') and loopback(urlsplit(origin).hostname))
                and request.headers.get('sec-fetch-site', 'same-origin') in ('same-origin', 'none'))
    except ValueError: return False


@dataclass(frozen=True)
class DownloadSettings:
    directory: Path = ROOT
    concurrency: int = 2
    capacity: int = 100
    max_pending: int = 20
    max_bytes: int = 1024 * 1024 * 1024
    timeout: float = 1800
    conversion_timeout: float = 300

    def __post_init__(self):
        if min(self.concurrency, self.capacity, self.max_pending, self.max_bytes, self.timeout, self.conversion_timeout) <= 0:
            raise ValueError('下载限制必须为正数')


@dataclass
class Job:
    public: DownloadTask
    worker: asyncio.Task | None = field(default=None, repr=False)


def safe_stem(value):
    value = ''.join('_' if unicodedata.category(c) in ('Cc','Cs') else c for c in value)
    value = re.sub(r'[\\/:*?"<>|\x00-\x1f\x7f]', '_', value).strip(' .')
    # 按UTF-16长度约束，保留补码字符；避免Windows路径及保留设备名。
    value = value.encode('utf-16-le', errors='replace')[:240].decode('utf-16-le', errors='ignore').rstrip(' .')
    if not value:
        value = '未命名'
    if re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])(?:\..*)?', value, re.I):
        value = '_' + value
    return value


def audio_format(raw):
    if raw.startswith(b'fLaC'): return 'flac'
    if raw.startswith(b'ID3') or len(raw) >= 2 and raw[0] == 255 and raw[1] & 224 == 224: return 'mp3'
    if len(raw) >= 12 and raw[4:8] == b'ftyp': return 'm4a'
    if raw.startswith(b'OggS'): return 'ogg'
    raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)


def process_exists(pid):
    if os.name == 'nt':
        import ctypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if handle:
            kernel.CloseHandle(handle)
            return True
        # 无权限或未知错误都按仍在运行处理，只清理明确不存在的进程。
        return ctypes.get_last_error() != 87
    try: os.kill(pid, 0)
    except ProcessLookupError: return False
    except PermissionError: pass
    return True


class DownloadManager:
    def __init__(self, state, settings):
        self.state, self.settings = state, settings
        self.root = Path(settings.directory).resolve()
        self.jobs = {}
        self.slots = asyncio.Semaphore(settings.concurrency)
        self.conversion_slots = asyncio.Semaphore(1)
        self.closed = False
        self.file_lock = threading.RLock()
        self.readers = {}

    def prepare(self):
        # 只清理本实现自己创建的任务临时文件，不触碰其他文件及子目录。
        try:
            if self.root.exists():
                for path in self.root.glob('.music-core-*.part'):
                    match = re.fullmatch(r'\.music-core-([1-9][0-9]{0,9})-[0-9a-f]{32}(?:-output)?\.part', path.name)
                    if match and not process_exists(int(match[1])):
                        with suppress(OSError): path.unlink()
        except OSError:
            # 目录不可读写由下载任务报告，不能妨碍播放服务启动。
            pass

    def update(self, job, **values):
        if job.public.status in TERMINAL and 'status' in values and values['status'] != job.public.status:
            return
        job.public = job.public.model_copy(update={**values, 'updatedAt': int(time()*1000)})

    def view(self, job):
        p = job.public
        return p.model_copy(update={'progress': p.receivedBytes / p.totalBytes if p.totalBytes and p.phase in (None,'downloading','completed') else None})

    def get(self, identifier):
        if identifier not in self.jobs: raise HTTPException(404)
        return self.jobs[identifier]

    def fingerprint(self, path, info):
        value = (str(self.root), path.name, info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
        return hashlib.sha256(repr(value).encode('utf-8')).hexdigest()

    def hidden(self):
        path = self.root / '.music-core-hidden.json'
        if not path.exists(): return set()
        info = path.lstat()
        if path.is_symlink() or getattr(info, 'st_file_attributes', 0) & 0x400 or not stat.S_ISREG(info.st_mode) or info.st_size > 1048576:
            raise OSError('隐藏索引不可读')
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
            if data.get('version') != 1 or not isinstance(data.get('hidden'), list): raise ValueError()
            if any(not isinstance(x, str) or not re.fullmatch('[0-9a-f]{64}', x) for x in data['hidden']): raise ValueError()
            return set(data['hidden'])
        except (ValueError, AttributeError): raise OSError('隐藏索引损坏') from None

    def write_hidden(self, identifiers):
        temporary = self.root / ('.music-core-hidden-' + uuid4().hex + '.tmp')
        content = json.dumps({'version': 1, 'hidden': sorted(identifiers)})
        if len(content.encode('utf-8')) > 1048576: raise OSError('隐藏索引容量已满')
        try:
            with temporary.open('x', encoding='utf-8') as output:
                output.write(content)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, self.root / '.music-core-hidden.json')
        finally:
            temporary.unlink(missing_ok=True)

    def snapshots(self):
        if not self.root.exists(): return
        for path in self.root.iterdir():
            if path.name.startswith('.') or path.suffix.lower() not in ('.mp3', '.m4a', '.flac', '.ogg'): continue
            try:
                info = path.lstat()
                if not stat.S_ISREG(info.st_mode) or path.is_symlink() or getattr(info, 'st_file_attributes', 0) & 0x400: continue
                with path.open('rb') as stream:
                    if self.fingerprint(path, os.fstat(stream.fileno())) != self.fingerprint(path, info): continue
                    kind = audio_format(stream.read(16))
                yield path, info, kind
            except (CoreError, FileNotFoundError): continue

    def find_file(self, identifier):
        if not re.fullmatch('[0-9a-f]{64}', identifier): raise FileNotFoundError()
        for path, info, kind in self.snapshots():
            if self.fingerprint(path, info) == identifier: return path, info, kind
        raise FileNotFoundError()

    def files(self):
        """只读列出受限目录内的音频，不推断已丢失的任务身份。"""
        if not self.root.exists(): return []
        output = []
        try:
            with self.file_lock:
                hidden = self.hidden()
                for path, info, kind in self.snapshots():
                    identifier = self.fingerprint(path, info)
                    if identifier not in hidden:
                        output.append(SavedDownloadFile(fileId=identifier,filename=path.name,sizeBytes=info.st_size,format=kind,modifiedAt=int(info.st_mtime*1000)))
            return sorted(output,key=lambda row:(-row.modifiedAt,row.filename))
        except OSError: raise HTTPException(503,detail='无法读取下载目录') from None

    def remove_file(self, identifier, delete_file):
        with self.file_lock:
            path, info, _ = self.find_file(identifier)
            if delete_file:
                if self.readers.get(identifier): raise BlockingIOError()
                # 删除前再次验证实例；无 await，其他 Core 请求不能在检查与删除之间插入。
                if self.fingerprint(path, path.lstat()) != identifier: raise FileNotFoundError()
                self.unlink_file(path, identifier)
            else:
                hidden = self.hidden()
                hidden.add(identifier)
                self.write_hidden(hidden)

    def unlink_file(self, path, identifier):
        """Windows 在经过验证的句柄上删除，避免检查后同名替换的竞态。"""
        if os.name != 'nt':
            path.unlink()
            return
        import ctypes
        import msvcrt
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        kernel.CreateFileW.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.SetFileInformationByHandle.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        # 读取、删除权限；不跟随重解析点，允许其他只读者及时关闭。
        handle = kernel.CreateFileW(str(path), 0x80010000, 7, None, 3, 0x00200000, None)
        if handle == wintypes.HANDLE(-1).value: raise ctypes.WinError(ctypes.get_last_error())
        try: descriptor = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
        except BaseException:
            kernel.CloseHandle(handle)
            raise
        with os.fdopen(descriptor, 'rb') as stream:
            if self.fingerprint(path, os.fstat(stream.fileno())) != identifier: raise FileNotFoundError()
            disposition = wintypes.BOOL(True)
            if not kernel.SetFileInformationByHandle(handle, 4, ctypes.byref(disposition), ctypes.sizeof(disposition)):
                raise ctypes.WinError(ctypes.get_last_error())

    def stream_file(self, request, identifier):
        stream = None
        try:
            with self.file_lock:
                path, info, kind = self.find_file(identifier)
                stream = path.open('rb')
                if self.fingerprint(path, os.fstat(stream.fileno())) != identifier:
                    raise FileNotFoundError()
                self.readers[identifier] = self.readers.get(identifier, 0) + 1
        except BaseException:
            if stream: stream.close()
            raise
        closed = False
        async def cleanup():
            nonlocal closed
            if not closed:
                closed = True
                stream.close()
                with self.file_lock:
                    self.readers[identifier] -= 1
                    if not self.readers[identifier]: del self.readers[identifier]
        size = info.st_size
        headers = {'Accept-Ranges': 'bytes', 'ETag': '"' + identifier + '"', 'Cache-Control': 'no-store'}
        start, end, status = 0, size - 1, 200
        try:
            requested = range_header(request.headers.get('range'))
            if requested:
                left, right = requested[6:].split('-')
                start = int(left) if left else max(0, size - int(right))
                end = min(int(right), size - 1) if left and right else size - 1
                if start >= size or start > end: raise CoreError(ErrorCode.INVALID_RANGE)
                status = 206
                headers['Content-Range'] = f'bytes {start}-{end}/{size}'
        except CoreError:
            stream.close()
            self.readers[identifier] -= 1
            if not self.readers[identifier]: del self.readers[identifier]
            return Response(status_code=416, headers={**headers, 'Content-Range': f'bytes */{size}'})
        headers['Content-Length'] = str(end - start + 1)
        media_type = {'mp3': 'audio/mpeg', 'm4a': 'audio/mp4', 'flac': 'audio/flac', 'ogg': 'audio/ogg'}[kind]
        async def chunks():
            stream.seek(start)
            remaining = end - start + 1
            while remaining > 0:
                chunk = stream.read(min(65536, remaining))
                if not chunk: break
                remaining -= len(chunk)
                yield chunk
                await asyncio.sleep(0)
        if request.method == 'HEAD':
            stream.close()
            self.readers[identifier] -= 1
            if not self.readers[identifier]: del self.readers[identifier]
            return Response(status_code=status, headers=headers, media_type=media_type)
        return OwnedStream(chunks(), status_code=status, headers=headers, media_type=media_type, cleanup=cleanup)

    def create(self, body):
        provider_for(self.state, body.identity.providerId)
        if self.closed or sum(j.public.status not in TERMINAL for j in self.jobs.values()) >= self.settings.max_pending:
            raise HTTPException(429)
        while len(self.jobs) >= self.settings.capacity:
            old = next((k for k,j in self.jobs.items() if j.public.status in TERMINAL and j.worker is None), None)
            if old is None: raise HTTPException(429)
            del self.jobs[old]
        now = int(time()*1000)
        job = Job(DownloadTask(id=uuid4().hex, identity=body.identity, title=body.title, artist=body.artist,
                              quality=body.quality, outputMode=body.outputMode, expectedSourceCodec=body.expectedSourceCodec, status='queued', createdAt=now, updatedAt=now))
        self.jobs[job.public.id] = job
        job.worker = asyncio.create_task(self.run(job))
        # queued阶段即取消时协程可能尚未启动，回调仍负责去除Task引用。
        job.worker.add_done_callback(lambda task: setattr(job, 'worker', None))
        return job

    async def cancel(self, job):
        if job.public.status in TERMINAL: return
        self.update(job, status='cancelled', errorCode=None)
        worker = job.worker
        if worker:
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)

    async def close(self):
        self.closed = True
        workers = [j.worker for j in self.jobs.values() if j.worker is not None]
        await asyncio.gather(*(self.cancel(j) for j in list(self.jobs.values())))
        await asyncio.gather(*workers, return_exceptions=True)

    async def run(self, job):
        part = self.root / (f'.music-core-{os.getpid()}-' + job.public.id + '.part')
        try:
            async with self.slots:
                await asyncio.wait_for(self.transfer(job, part), self.settings.timeout)
        except asyncio.CancelledError:
            if job.public.status not in TERMINAL: self.update(job, status='cancelled')
        except CoreError as error:
            logging.getLogger(__name__).warning('download_failed task=%s phase=%s code=%s', job.public.id, job.public.phase, error.code.value)
            if job.public.status not in TERMINAL:
                code = ('conversion_failed' if error.code == ErrorCode.CAPABILITY_UNSUPPORTED and job.public.outputMode != 'original'
                        else 'source_verification_failed' if job.public.phase == 'source_verifying' else error.code.value)
                self.update(job, status='failed', errorCode=code)
        except (asyncio.TimeoutError, httpx.TimeoutException):
            if job.public.status not in TERMINAL: self.update(job, status='failed', errorCode='upstream_timeout')
        except httpx.HTTPError:
            if job.public.status not in TERMINAL: self.update(job, status='failed', errorCode='upstream_failure')
        except OSError:
            if job.public.status not in TERMINAL: self.update(job, status='failed', errorCode='file_io_error')
        except Exception:
            if job.public.status not in TERMINAL: self.update(job, status='failed', errorCode='internal_error')
        finally:
            for owned in (part,part.with_name(part.stem+'-output.part')):
                try:owned.unlink(missing_ok=True)
                except OSError:
                    # 每份任务文件独立清理，不因一个删除失败跳过另一份。
                    self.update(job, errorCode='temporary_cleanup_failed')

    def publish(self, job, publish_part, actual, kind, *, preserved=False):
        p = job.public
        stem = safe_stem(' - '.join(s.strip() for s in (p.artist,p.title) if s and s.strip())
                     or f'{p.identity.providerId}-{p.identity.platformId}')
        for index in range(1,10001):
            target = self.root / (stem + (f' ({index})' if index > 1 else '') + '.' + kind)
            try:
                # 同文件系统硬链接是原子的“不存在才发布”，跨进程也绝不覆盖。
                os.link(publish_part,target)
                break
            except FileExistsError: continue
        else: raise OSError('无可用文件名')
        self.update(job, status='failed' if preserved else 'completed', phase=job.public.phase if preserved else 'completed', filename=target.name, fileId=self.fingerprint(target, target.stat()), format=kind, actualMedia=actual, finalSizeBytes=actual.sizeBytes, sourcePreserved=preserved)

    async def convert_and_save(self, job, part, source, existing=None):
        from app.transcode import validate_flac, convert_flac, ConversionError
        output = part.with_name(part.stem+'-output.part')
        async with self.conversion_slots:
            self.update(job, phase='source_verifying', sourceMedia=source)
            await validate_flac(part, timeout=self.settings.conversion_timeout)
            self.update(job, phase='transcoding')
            try:
                actual = await asyncio.wait_for(convert_flac(part, output, 320000 if job.public.outputMode=='mp3_320' else 192000,
                    timeout=self.settings.conversion_timeout, max_bytes=self.settings.max_bytes,
                    phase_changed=lambda phase: self.update(job, phase=phase)), self.settings.conversion_timeout)
            except (CoreError, asyncio.TimeoutError) as error:
                cause = error.cause if isinstance(error, ConversionError) else error
                if isinstance(error, ConversionError): self.update(job, phase=error.phase)
                logging.getLogger(__name__).warning('download_conversion_failed task=%s phase=%s error=%s', job.public.id, job.public.phase, type(cause).__name__)
                if isinstance(cause, OSError) and not isinstance(cause, FileNotFoundError): raise cause
                output.unlink(missing_ok=True)
                # 保底前再次完整验证，不把截断或损坏源文件发布为成果。
                await validate_flac(part, timeout=self.settings.conversion_timeout)
                self.update(job, errorCode='conversion_failed')
                if not existing:
                    for previous in self.jobs.values():
                        saved = previous.public
                        if saved.identity != job.public.identity or saved.format != 'flac' or not saved.fileId:
                            continue
                        try:
                            path, info, _ = self.find_file(saved.fileId)
                            if info.st_size != part.stat().st_size: continue
                            with path.open('rb') as left, part.open('rb') as right:
                                while True:
                                    chunk = left.read(65536)
                                    if chunk != right.read(65536): break
                                    if not chunk:
                                        if self.fingerprint(path, path.stat()) == saved.fileId:
                                            existing = saved.fileId
                                        break
                        except FileNotFoundError:
                            continue
                        if existing: break
                if existing:
                    path, info, kind = self.find_file(existing)
                    self.update(job, status='failed', sourcePreserved=True, fileId=existing, filename=path.name,
                        format=kind, actualMedia=source, finalSizeBytes=info.st_size)
                else:
                    self.publish(job, part, source, 'flac', preserved=True)
                return
            self.update(job, phase='publishing', transcoded=True)
            await asyncio.sleep(0)
            self.publish(job, output, actual, 'mp3')

    async def transfer(self, job, part):
        if job.public.status in TERMINAL: raise asyncio.CancelledError()
        self.update(job, status='resolving')
        if job.public.outputMode != 'original':
            # 只复用仍有稳定来源身份和文件指纹的当前进程任务，不按标题猜测。
            for previous in reversed(list(self.jobs.values())):
                saved = previous.public
                if saved.id == job.public.id or saved.identity != job.public.identity or saved.format != 'flac' or not saved.fileId:
                    continue
                try:
                    path, info, _ = self.find_file(saved.fileId)
                except FileNotFoundError:
                    continue
                if info.st_size > self.settings.max_bytes: continue
                self.root.mkdir(parents=True, exist_ok=True)
                with path.open('rb') as source_file, part.open('xb') as target:
                    copied = 0
                    while chunk := source_file.read(65536):
                        copied += len(chunk)
                        if copied > self.settings.max_bytes: raise CoreError(ErrorCode.MEDIA_CAPACITY)
                        target.write(chunk)
                        await asyncio.sleep(0)
                    target.flush()
                    os.fsync(target.fileno())
                if self.fingerprint(path, path.stat()) != saved.fileId:
                    raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
                with part.open('rb') as source_file:
                    actual = inspect_audio(source_file.read(65536)).model_copy(update={'sizeBytes':info.st_size})
                await self.convert_and_save(job, part, actual, existing=saved.fileId)
                return
        async def resolve_source():
            provider=provider_for(self.state,job.public.identity.providerId)
            if job.public.outputMode!='original':
                bitrate=320000 if job.public.outputMode=='mp3_320' else 192000
                cached=getattr(self.state,'download_quality_cache',{})
                # 只利用同身份、仍有效的已确认MP3摘要，不扫描其他来源或所有路线。
                for quality in ('high','standard','auto'):
                    value=cached.get((job.public.identity.providerId,job.public.identity.platformId,quality))
                    rep=value[1].get('representation') if value and value[0]>time() else None
                    if not rep or rep.get('codec')!='mp3' or abs((rep.get('bitrateBps') or 0)-bitrate)>1000:continue
                    try:
                        candidate=await asyncio.wait_for(provider.resolve(job.public.identity,ResolveOptions(purpose='download',providerQualityId=None if quality=='auto' else quality)),8)
                        if candidate.identity!=job.public.identity:raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
                        rep=candidate.representation
                        if not (rep.codec and rep.bitrateBps):
                            from app.core.media_probe import verify_media
                            rep=await verify_media(self.state.http_client,candidate.upstreamUrl.get_secret_value(),candidate.identity.providerId,detail=True,
                                headers={k:v.get_secret_value() for k,v in candidate.headers.items()})
                        if rep.codec=='mp3' and abs((rep.bitrateBps or 0)-bitrate)<=1000:return candidate.model_copy(update={'representation':rep})
                    except CoreError as error:
                        if error.code not in (ErrorCode.MEDIA_UNAVAILABLE,ErrorCode.UPSTREAM_TIMEOUT,ErrorCode.UPSTREAM_FAILURE):raise
                    except asyncio.TimeoutError:pass
                    break
            return await provider.resolve(job.public.identity,ResolveOptions(purpose='download',providerQualityId=None if job.public.quality=='auto' else job.public.quality))
        media=await asyncio.wait_for(resolve_source(),25) if job.public.outputMode!='original' else await resolve_source()
        if media.identity != job.public.identity: raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
        if media.validUntil is not None and media.validUntil <= int(time()*1000):
            raise CoreError(ErrorCode.UPSTREAM_MEDIA_EXPIRED)
        url = media.upstreamUrl.get_secret_value()
        headers = {k:v.get_secret_value() for k,v in media.headers.items() if k.lower() in ('user-agent','referer')}
        headers['Accept-Encoding'] = 'identity'
        response = None
        try:
            for hop in range(4):
                check = self.state.target_check
                if check is validate_target: await check(url, media.identity.providerId)
                else: await check(url)
                response = await self.state.http_client.send(httpx.Request('GET', url, headers=headers),
                                                             stream=True, follow_redirects=False, auth=None)
                if response.status_code not in (301,302,303,307,308): break
                location = response.headers.get('location')
                await response.aclose()
                if not location or hop == 3: raise CoreError(ErrorCode.UPSTREAM_FAILURE)
                url = urljoin(url, location)
                headers = {'Accept-Encoding':'identity'}
            if response.status_code in (401,403): raise CoreError(ErrorCode.ACCESS_DENIED)
            if response.status_code in (404,410): raise CoreError(ErrorCode.UPSTREAM_MEDIA_EXPIRED)
            if response.status_code not in (200,206): raise CoreError(ErrorCode.UPSTREAM_FAILURE)
            if response.headers.get('content-encoding','identity').lower() != 'identity':
                raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
            total = None
            length = response.headers.get('content-length')
            if length is not None:
                if not re.fullmatch(r'[0-9]{1,20}',length) or int(length) <= 0:
                    raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
                total = int(length)
            content_range = response.headers.get('content-range')
            if response.status_code == 206 or content_range is not None:
                match = re.fullmatch(r'bytes 0-([0-9]{1,20})/([0-9]{1,20})',content_range or '')
                if not match or int(match[1])+1 != int(match[2]) or int(match[2]) <= 0:
                    raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
                if total is not None and total != int(match[2]): raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
                total = int(match[2])
            if total is not None and total > self.settings.max_bytes: raise CoreError(ErrorCode.MEDIA_CAPACITY)
            self.root.mkdir(parents=True, exist_ok=True)
            self.update(job, status='downloading', phase='downloading', totalBytes=total)
            prefix = bytearray()
            # 同步有界文件写入不会留下取消后仍写盘的线程；每块让出事件循环。
            with part.open('xb') as output:
                async for chunk in response.aiter_raw(chunk_size=65536):
                    received = job.public.receivedBytes + len(chunk)
                    if received > self.settings.max_bytes: raise CoreError(ErrorCode.MEDIA_CAPACITY)
                    if total is not None and received > total: raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
                    prefix.extend(chunk[:max(0,65536-len(prefix))])
                    output.write(chunk)
                    self.update(job, receivedBytes=received)
                    await asyncio.sleep(0)
                output.flush()
                os.fsync(output.fileno())
            size = part.stat().st_size
            if not size or size != job.public.receivedBytes or total is not None and size != total:
                raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
            if media.representation.sizeBytes is not None and size != media.representation.sizeBytes:
                raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
            actual=inspect_audio(bytes(prefix)).model_copy(update={'sizeBytes':size})
            direct=job.public.outputMode!='original' and actual.codec=='mp3' and abs((actual.bitrateBps or 0)-(320000 if job.public.outputMode=='mp3_320' else 192000))<=1000
            if not direct and not satisfies(actual,job.public.quality):raise CoreError(ErrorCode.MEDIA_UNAVAILABLE)
            if job.public.expectedSourceCodec and job.public.outputMode=='original' and actual.codec!=job.public.expectedSourceCodec:raise CoreError(ErrorCode.MEDIA_UNAVAILABLE)
            kind = audio_format(bytes(prefix))
            expected = media.representation.container
            if expected in ('flac','mpeg-audio','mp4','ogg') and kind != {'mpeg-audio':'mp3','mp4':'m4a'}.get(expected,expected):
                raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
            self.update(job,sourceMedia=actual)
            publish_part=part
            if job.public.outputMode!='original' and not direct:
                if actual.codec!='flac' or actual.lossless is not True:raise CoreError(ErrorCode.CAPABILITY_UNSUPPORTED)
                await self.convert_and_save(job, part, actual)
                return
            self.update(job,phase='verifying',actualMedia=actual,finalSizeBytes=actual.sizeBytes)
            # 最后一次可取消点在发布前；原子发布与终态更新之间没有await。
            await asyncio.sleep(0)
            if job.public.status in TERMINAL: raise asyncio.CancelledError()
            self.publish(job, publish_part, actual, kind)
        finally:
            if response is not None:
                with anyio.CancelScope(shield=True): await response.aclose()


def download_router():
    router = APIRouter(prefix='/api/downloads')

    def manager(request): return request.app.state.downloads

    @router.post('', response_model=DownloadTask, status_code=202)
    async def create(body: DownloadRequest, request: Request):
        m = manager(request)
        return m.view(m.create(body))

    @router.get('', response_model=list[DownloadTask])
    async def listing(request: Request):
        m = manager(request)
        return [m.view(j) for j in m.jobs.values()]

    @router.post('/options')
    async def options(body: DownloadRequest, request: Request):
        # 只缓存短期公开检测信息；确认下载必须重新解析，不保存签名媒体URL。
        from collections import OrderedDict
        from app.core.media_probe import verify_media
        cache=getattr(request.app.state,'download_quality_cache',None)
        if cache is None:cache=request.app.state.download_quality_cache=OrderedDict()
        key=(body.identity.providerId,body.identity.platformId,body.quality)
        cached=cache.get(key)
        if cached and cached[0]>time():return cached[1]
        cache_until=[time()+30]
        async def detect():
            media=await provider_for(request.app.state,body.identity.providerId).resolve(body.identity,
                ResolveOptions(purpose='download',providerQualityId=None if body.quality=='auto' else body.quality))
            if media.identity!=body.identity:raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
            if media.validUntil is not None:
                if media.validUntil<=int(time()*1000):raise CoreError(ErrorCode.UPSTREAM_MEDIA_EXPIRED)
                cache_until[0]=min(cache_until[0],media.validUntil/1000)
            rep=media.representation
            if not (rep.codec and rep.sampleRateHz):
                rep=await verify_media(request.app.state.http_client,media.upstreamUrl.get_secret_value(),body.identity.providerId,detail=True,
                    headers={k:v.get_secret_value() for k,v in media.headers.items()})
            if not satisfies(rep,body.quality):raise CoreError(ErrorCode.MEDIA_UNAVAILABLE)
            from app.transcode import encoder_capability
            conversion=await encoder_capability() if rep.codec=='flac' and rep.lossless is True else None
            return {'quality':body.quality,'availability':'available','representation':rep.model_dump(),'errorCode':None,'conversion':conversion}
        operation=asyncio.create_task(asyncio.wait_for(detect(),27))
        async def disconnected():
            while not operation.done():
                if await request.is_disconnected():operation.cancel();return
                await asyncio.sleep(.1)
        monitor=asyncio.create_task(disconnected())
        try:
            try:value=await operation
            except CoreError as error:value={'quality':body.quality,'availability':'unavailable','representation':None,'errorCode':error.code.value}
            except (asyncio.TimeoutError,httpx.TimeoutException):value={'quality':body.quality,'availability':'unavailable','representation':None,'errorCode':'upstream_timeout'}
            cache[key]=(cache_until[0],value);cache.move_to_end(key)
            while len(cache)>32:cache.popitem(last=False)
            return value
        finally:
            monitor.cancel();await asyncio.gather(monitor,return_exceptions=True)

    @router.get('/files', response_model=list[SavedDownloadFile])
    async def files(request: Request):
        try: return manager(request).files()
        except HTTPException:
            return JSONResponse(status_code=503,content={'error':{'code':'file_io_error','message':'无法读取下载目录','retryable':True}})

    @router.post('/files/{identifier}/remove')
    async def remove_file(identifier: str, body: RemoveDownloadFile, request: Request):
        if not trusted_local(request): return file_error(403, '只允许本机页面管理下载文件')
        m = manager(request)
        # 等待播放器停止后正在取消的媒体响应释放句柄；超时明确返回失败。
        for attempt in range(21):
            try:
                m.remove_file(identifier, body.deleteFile)
                return {'removed': True, 'fileDeleted': body.deleteFile}
            except BlockingIOError:
                if attempt == 20: return file_error(409, '文件仍在播放，请停止后重试')
                await asyncio.sleep(.05)
            except FileNotFoundError: return file_error(404, '文件已变化或不存在，请刷新列表')
            except OSError: return file_error(503, '无法修改本地文件，请检查占用及目录权限')

    @router.get('/files/{identifier}/stream')
    @router.head('/files/{identifier}/stream', include_in_schema=False)
    async def stream_file(identifier: str, request: Request):
        if not trusted_local(request): return file_error(403, '只允许本机页面读取下载文件')
        try: return manager(request).stream_file(request, identifier)
        except FileNotFoundError: return file_error(404, '文件已变化或不存在，请刷新列表')
        except OSError: return file_error(503, '无法读取本地音频文件')

    @router.get('/{identifier}', response_model=DownloadTask)
    async def get(identifier: str, request: Request):
        m = manager(request)
        return m.view(m.get(identifier))

    @router.post('/{identifier}/cancel', response_model=DownloadTask)
    async def cancel(identifier: str, request: Request):
        m = manager(request)
        job = m.get(identifier)
        await m.cancel(job)
        return m.view(job)

    @router.post('/{identifier}/retry', response_model=DownloadTask, status_code=202)
    async def retry(identifier: str, request: Request):
        m = manager(request)
        p = m.get(identifier).public
        if p.status not in ('failed','cancelled'): raise HTTPException(409)
        return m.view(m.create(DownloadRequest(identity=p.identity,title=p.title,artist=p.artist,quality=p.quality,outputMode=p.outputMode,expectedSourceCodec=p.expectedSourceCodec)))

    return router
