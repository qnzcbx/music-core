"""目录管理能力只授予持有本机授权文件的操作者，不以代理后的 IP 作为授权。"""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import secrets
import getpass
import subprocess
from time import time
from uuid import UUID, uuid4


def system_folder(name):
    if os.name != 'nt':
        return Path.home() / ('Music' if name == 'music' else 'Downloads')
    from ctypes import wintypes
    class GUID(ctypes.Structure):
        _fields_ = [('a', wintypes.DWORD), ('b', wintypes.WORD), ('c', wintypes.WORD), ('d', ctypes.c_ubyte * 8)]
    value = UUID('4bd8d571-6d19-48d3-be97-422220080e43' if name == 'music' else '374de290-123f-4565-9164-39c4925e467b')
    guid = GUID.from_buffer_copy(value.bytes_le)
    result = ctypes.c_wchar_p()
    shell = ctypes.windll.shell32
    code = shell.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(result))
    if code:
        raise OSError('无法读取系统目录')
    try:
        return Path(result.value)
    finally:
        ctypes.windll.ole32.CoTaskMemFree(result)


def initial_directory(data, default_directory, override=None):
    from app.download_index import DownloadIndex
    if override is not None and not override.strip():
        raise ValueError('音乐库目录不能为空')
    index = DownloadIndex(data)
    saved = index.setting('directory')
    if override is not None:
        selected = Path(override)
    elif saved:
        selected = Path(saved)
    else:
        selected = system_folder('music') if os.name == 'nt' else default_directory
    if override is not None or not saved:
        index.setting('directory', str(selected.resolve()))
    return selected


def protect_local_file(path):
    if os.name == 'nt':
        identity = os.environ.get('USERDOMAIN', '') + '\\' + getpass.getuser()
        subprocess.run(['icacls', str(path), '/inheritance:r', '/grant:r', identity + ':(F)'],
                       check=True, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    else:
        path.chmod(0o600)


class LibraryManager:
    def __init__(self, manager):
        self.manager = manager
        self.locked = manager.settings.deployment_locked
        directory = manager.index.path.parent
        self.token_file = directory / 'library-admin.html'
        secret_file = directory / '.library-admin-token'
        if not secret_file.exists():
            with secret_file.open('x', encoding='utf-8') as output:
                output.write(secrets.token_urlsafe(32))
            protect_local_file(secret_file)
        self.token = secret_file.read_text(encoding='utf-8').strip()
        protect_local_file(secret_file)
        self.tickets = {}
        self.sessions = {}

    def issue_ticket(self):
        now = time()
        self.tickets = {key: expiry for key, expiry in self.tickets.items() if expiry > now}
        if len(self.tickets) >= 32:
            raise ValueError('本机启动请求过多，请稍后重试')
        ticket = secrets.token_urlsafe(32)
        self.tickets[ticket] = now + 60
        return ticket

    def redeem(self, ticket):
        expiry = self.tickets.pop(ticket, 0)
        if expiry <= time():
            raise ValueError('本机启动授权已失效，请重新打开客户端')
        now = time()
        self.sessions = {key: expiry for key, expiry in self.sessions.items() if expiry > now}
        if len(self.sessions) >= 128:
            raise ValueError('管理会话过多，请稍后重试')
        session = secrets.token_urlsafe(32)
        self.sessions[session] = now + 12 * 3600
        return session

    def launcher_authorized(self, request):
        if any(key in request.headers for key in ('forwarded', 'x-forwarded-for', 'x-real-ip')):
            return False
        supplied = request.headers.get('x-library-admin', '')
        return bool(supplied) and secrets.compare_digest(supplied, self.token)

    def authorized(self, request):
        if any(key in request.headers for key in ('forwarded', 'x-forwarded-for', 'x-real-ip')):
            return False
        session = request.cookies.get('music-core-library-session', '')
        # 私有能力仍供本机工具使用，普通页面只收到 HttpOnly 管理会话。
        return self.sessions.get(session, 0) > time() or self.launcher_authorized(request)

    def target(self, location, path):
        if self.locked:
            raise ValueError('由部署配置管理，不能在网页更改目录')
        target = system_folder(location) if location in ('music', 'downloads') else Path(path or '')
        if location == 'custom' and (not path or not target.is_absolute()):
            raise ValueError('请输入后端机器上的绝对目录路径')
        target = target.resolve()
        target.mkdir(parents=True, exist_ok=True)
        probe = target / ('.music-core-check-' + uuid4().hex)
        with probe.open('xb') as output:
            output.write(b'check')
            output.flush()
            os.fsync(output.fileno())
        probe.unlink()
        return target

    def candidates(self):
        m = self.manager
        published = m.index.published()
        if not published:
            return []
        successors, _ = m.index.aliases()
        eligible = {identifier: (raw, hidden) for identifier, _, raw, hidden in published
                    if identifier not in successors}
        if not eligible:
            return []
        paths = {identifier: path for path, info, _ in m.snapshots()
                 if (identifier := m.fingerprint(path, info)) in eligible}
        return [(identifier, paths[identifier], json.loads(raw), hidden)
                for identifier, (raw, hidden) in eligible.items() if identifier in paths]

    def change(self, target, migrate):
        m = self.manager
        if migrate and (m.readers or any(j.public.status not in ('completed', 'failed', 'cancelled') for j in m.jobs.values())):
            raise ValueError('有文件正在播放或下载，请停止后再迁移')
        results = []
        if migrate:
            for identifier, source, metadata, hidden in self.candidates():
                if source.parent == target:
                    continue
                temporary = target / ('.music-core-migrate-' + uuid4().hex + '.part')
                destination = None
                try:
                    digest = hashlib.sha256()
                    with source.open('rb') as original, temporary.open('xb') as output:
                        if m.fingerprint(source, os.fstat(original.fileno())) != identifier:
                            raise OSError('源文件已变化')
                        while chunk := original.read(65536):
                            digest.update(chunk)
                            output.write(chunk)
                        output.flush()
                        os.fsync(output.fileno())
                    with temporary.open('rb') as copied:
                        verify = hashlib.sha256()
                        while chunk := copied.read(65536):
                            verify.update(chunk)
                    if verify.digest() != digest.digest() or m.fingerprint(source, source.stat()) != identifier:
                        raise OSError('文件完整性验证失败')
                    from app.downloads import safe_stem
                    for number in range(1, 10001):
                        destination = target / (safe_stem(source.stem) + (f' ({number})' if number > 1 else '') + source.suffix)
                        try:
                            os.link(temporary, destination)
                            break
                        except FileExistsError:
                            continue
                    else:
                        raise OSError('没有可用的目标名称')
                    temporary.unlink()
                    new = m.fingerprint(destination, destination.stat())
                    m.index.libraries(target)
                    m.index.relocated(identifier, new, destination, metadata, hidden)
                    # 先让旧 ID 能定位完整副本，再删除经过指纹验证的源文件。
                    m.unlink_file(source, identifier)
                    results.append({'file': source.name, 'status': 'moved'})
                except OSError as reason:
                    results.append({'file': source.name, 'status': 'failed', 'error': str(reason)})
                finally:
                    temporary.unlink(missing_ok=True)
        m.index.setting('directory', str(target))
        m.index.libraries(target)
        m.root = target
        return {'directory': str(target), 'results': results}
