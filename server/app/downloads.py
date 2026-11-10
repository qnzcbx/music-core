"""独立的进程内下载消费者：解析、限流、临时文件和原子发布。"""
import asyncio
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
import os
import re
import stat
import unicodedata
from time import time
from typing import Literal
from urllib.parse import urljoin
from uuid import uuid4

import anyio
import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import Field
from app.models import DTO, TrackIdentity, ResolveOptions
from app.providers import provider_for
from app.core.errors import CoreError, ErrorCode
from app.media_stream import validate_target

TERMINAL = {'completed', 'failed', 'cancelled'}
ROOT = Path(__file__).resolve().parents[2] / 'downloads'


class DownloadRequest(DTO):
    identity: TrackIdentity
    # 名称仅用于文件展示，不参与身份解析；缺省按稳定身份命名。
    title: str | None = Field(default=None, max_length=500)
    artist: str | None = Field(default=None, max_length=500)


class DownloadTask(DTO):
    id: str
    identity: TrackIdentity
    title: str | None
    artist: str | None
    status: Literal['queued', 'resolving', 'downloading', 'completed', 'failed', 'cancelled']
    receivedBytes: int = 0
    totalBytes: int | None = None
    progress: float | None = None
    filename: str | None = None
    format: str | None = None
    errorCode: str | None = None
    createdAt: int
    updatedAt: int


class SavedDownloadFile(DTO):
    filename: str
    sizeBytes: int
    format: str
    modifiedAt: int


@dataclass(frozen=True)
class DownloadSettings:
    directory: Path = ROOT
    concurrency: int = 2
    capacity: int = 100
    max_pending: int = 20
    max_bytes: int = 1024 * 1024 * 1024
    timeout: float = 1800

    def __post_init__(self):
        if min(self.concurrency, self.capacity, self.max_pending, self.max_bytes, self.timeout) <= 0:
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
        self.closed = False

    def prepare(self):
        # 只清理本实现自己创建的任务临时文件，不触碰其他文件及子目录。
        try:
            if self.root.exists():
                for path in self.root.glob('.music-core-*.part'):
                    match = re.fullmatch(r'\.music-core-([1-9][0-9]{0,9})-[0-9a-f]{32}\.part', path.name)
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
        return p.model_copy(update={'progress': p.receivedBytes / p.totalBytes if p.totalBytes else None})

    def get(self, identifier):
        if identifier not in self.jobs: raise HTTPException(404)
        return self.jobs[identifier]

    def files(self):
        """只读列出受限目录内的音频，不推断已丢失的任务身份。"""
        if not self.root.exists(): return []
        output = []
        try:
            for path in self.root.iterdir():
                if path.name.startswith('.') or path.suffix.lower() not in ('.mp3','.m4a','.flac','.ogg'): continue
                info = path.lstat()
                if not stat.S_ISREG(info.st_mode) or path.is_symlink() or getattr(info,'st_file_attributes',0) & 0x400: continue
                try:
                    with path.open('rb') as stream: kind = audio_format(stream.read(16))
                except (CoreError,FileNotFoundError): continue
                output.append(SavedDownloadFile(filename=path.name,sizeBytes=info.st_size,format=kind,modifiedAt=int(info.st_mtime*1000)))
            return sorted(output,key=lambda row:(-row.modifiedAt,row.filename))
        except OSError: raise HTTPException(503,detail='无法读取下载目录') from None

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
                              status='queued', createdAt=now, updatedAt=now))
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
            if job.public.status not in TERMINAL: self.update(job, status='failed', errorCode=error.code.value)
        except (asyncio.TimeoutError, httpx.TimeoutException):
            if job.public.status not in TERMINAL: self.update(job, status='failed', errorCode='upstream_timeout')
        except httpx.HTTPError:
            if job.public.status not in TERMINAL: self.update(job, status='failed', errorCode='upstream_failure')
        except OSError:
            if job.public.status not in TERMINAL: self.update(job, status='failed', errorCode='file_io_error')
        except Exception:
            if job.public.status not in TERMINAL: self.update(job, status='failed', errorCode='internal_error')
        finally:
            try: part.unlink(missing_ok=True)
            except OSError:
                # 清理失败明确可见，下次启动仍只识别为未完成文件。
                self.update(job, errorCode='temporary_cleanup_failed')

    async def transfer(self, job, part):
        if job.public.status in TERMINAL: raise asyncio.CancelledError()
        self.update(job, status='resolving')
        media = await provider_for(self.state, job.public.identity.providerId).resolve(
            job.public.identity, ResolveOptions(purpose='download'))
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
            self.update(job, status='downloading', totalBytes=total)
            prefix = bytearray()
            # 同步有界文件写入不会留下取消后仍写盘的线程；每块让出事件循环。
            with part.open('xb') as output:
                async for chunk in response.aiter_raw(chunk_size=65536):
                    received = job.public.receivedBytes + len(chunk)
                    if received > self.settings.max_bytes: raise CoreError(ErrorCode.MEDIA_CAPACITY)
                    if total is not None and received > total: raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
                    prefix.extend(chunk[:max(0,4096-len(prefix))])
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
            kind = audio_format(bytes(prefix))
            expected = media.representation.container
            if expected in ('flac','mpeg-audio','mp4','ogg') and kind != {'mpeg-audio':'mp3','mp4':'m4a'}.get(expected,expected):
                raise CoreError(ErrorCode.UPSTREAM_INVALID_RESPONSE)
            # 最后一次可取消点在发布前；原子发布与终态更新之间没有await。
            await asyncio.sleep(0)
            if job.public.status in TERMINAL: raise asyncio.CancelledError()
            p = job.public
            stem = safe_stem(' - '.join(s.strip() for s in (p.artist,p.title) if s and s.strip())
                             or f'{p.identity.providerId}-{p.identity.platformId}')
            for index in range(1,10001):
                target = self.root / (stem + (f' ({index})' if index > 1 else '') + '.' + kind)
                try:
                    # 同文件系统硬链接是原子的“不存在才发布”，跨进程也绝不覆盖。
                    os.link(part,target)
                    break
                except FileExistsError: continue
            else: raise OSError('无可用文件名')
            self.update(job, status='completed', filename=target.name, format=kind)
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

    @router.get('/files', response_model=list[SavedDownloadFile])
    async def files(request: Request):
        try: return manager(request).files()
        except HTTPException:
            return JSONResponse(status_code=503,content={'error':{'code':'file_io_error','message':'无法读取下载目录','retryable':True}})

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
        return m.view(m.create(DownloadRequest(identity=p.identity,title=p.title,artist=p.artist)))

    return router
