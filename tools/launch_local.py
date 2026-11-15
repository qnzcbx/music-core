"""可信本机入口：启动或复用服务，通过私有能力换取一次性票据后打开网页。"""
import argparse
import ctypes
from contextlib import contextmanager
from ctypes import wintypes
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from urllib.error import URLError
from urllib.parse import urlsplit, quote
from urllib.request import Request, urlopen
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / '.runtime' / 'local-launch' / 'processes.json'


def kernel_api():
    kernel = ctypes.windll.kernel32
    signatures = {
        'OpenProcess': ([wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
        'GetProcessTimes': ([wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4, wintypes.BOOL),
        'CloseHandle': ([wintypes.HANDLE], wintypes.BOOL),
        'WaitForSingleObject': ([wintypes.HANDLE, wintypes.DWORD], wintypes.DWORD),
        'TerminateProcess': ([wintypes.HANDLE, wintypes.UINT], wintypes.BOOL),
        'AttachConsole': ([wintypes.DWORD], wintypes.BOOL),
        'GetConsoleProcessList': ([ctypes.POINTER(wintypes.DWORD), wintypes.DWORD], wintypes.DWORD),
        'GenerateConsoleCtrlEvent': ([wintypes.DWORD, wintypes.DWORD], wintypes.BOOL),
    }
    for name, (arguments, result) in signatures.items():
        function = getattr(kernel, name)
        function.argtypes = arguments
        function.restype = result
    return kernel


def snapshot():
    command = (
        "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(); "
        "$ErrorActionPreference='Stop'; "
        "@(Get-CimInstance Win32_Process | ForEach-Object { [pscustomobject]@{"
        "pid=$_.ProcessId; parent=$_.ParentProcessId; "
        "created=$_.CreationDate.ToFileTimeUtc().ToString(); "
        "exe=$_.ExecutablePath; command=$_.CommandLine} }) | ConvertTo-Json -Compress"
    )
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', command],
                            capture_output=True, check=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
    rows = json.loads(result.stdout.decode('utf-8-sig'))
    for row in rows:
        # CIM 只保留微秒，句柄上的 FILETIME 则精确到 100 纳秒。
        row['created'] = str(int(row['created']) // 10)
    return {int(row['pid']): row for row in rows}


def creation_time(handle):
    values = [wintypes.FILETIME() for _ in range(4)]
    if not kernel_api().GetProcessTimes(handle, *(ctypes.byref(v) for v in values)):
        raise OSError('无法核验进程创建时间')
    return str(((values[0].dwHighDateTime << 32) | values[0].dwLowDateTime) // 10)


def verified_handle(identity, processes):
    current = processes.get(identity.get('pid'))
    fields = ('pid', 'created', 'exe', 'command')
    if not current or not all(identity.get(k) and current.get(k) == identity[k] for k in fields):
        return None
    kernel = kernel_api()
    handle = kernel.OpenProcess(0x100000 | 0x1000 | 1, False, identity['pid'])
    if not handle:
        return None
    try:
        if creation_time(handle) == identity['created']:
            return handle
    except OSError:
        pass
    kernel.CloseHandle(handle)
    return None


def load_state():
    if not STATE.exists():
        return {'project': str(ROOT.resolve()), 'services': {}}
    state = json.loads(STATE.read_text(encoding='utf-8'))
    if state.get('project') != str(ROOT.resolve()):
        raise RuntimeError('启动记录不属于当前项目，不执行进程操作')
    return state


def save_state(state):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATE.with_suffix('.tmp')
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(STATE)


@contextmanager
def launcher_lock():
    import msvcrt
    STATE.parent.mkdir(parents=True, exist_ok=True)
    with STATE.with_suffix('.lock').open('a+b') as lock:
        if lock.tell() == 0:
            lock.write(b'0')
            lock.flush()
        deadline = time.monotonic() + 90
        while True:
            lock.seek(0)
            try:
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError:
                if time.monotonic() > deadline:
                    raise RuntimeError('启动或关闭仍在进行，请稍后再试')
                time.sleep(.1)
        try:
            yield
        finally:
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)


def remember_process(process, cwd, label):
    processes = snapshot()
    identity = processes.get(process.pid)
    if process.poll() is not None:
        raise RuntimeError('服务启动后已退出，请检查启动日志')
    if (not identity or not identity['exe'] or not identity['command']
            or creation_time(int(process._handle)) != identity['created']):
        raise RuntimeError('无法核验新服务身份，不登记所有权')
    state = load_state()
    entry = {'owned': True, 'cwd': str(cwd.resolve()), 'root': identity}
    entry['members'] = collect_members(entry, processes)
    state['services'][label] = entry
    save_state(state)


def collect_members(entry, processes):
    """只有已记录且身份仍匹配的父进程，才可用于发现新的后代。"""
    members = list(entry.get('members', [entry['root']]))
    known = {(item['pid'], item['created']) for item in members}
    for parent in members:
        handle = verified_handle(parent, processes)
        if not handle:
            continue
        try:
            for child in processes.values():
                key = (child['pid'], child['created'])
                if (child['parent'] == parent['pid']
                        and int(child['created']) >= int(parent['created']) and key not in known):
                    members.append(child)
                    known.add(key)
        finally:
            kernel_api().CloseHandle(handle)
    return members


def refresh_members(label):
    state = load_state()
    entry = state['services'].get(label, {})
    if entry.get('owned'):
        entry['members'] = collect_members(entry, snapshot())
        save_state(state)


def remember_reused(label):
    state = load_state()
    entry = state['services'].get(label, {})
    if entry.get('owned'):
        processes = snapshot()
        # 先前由本入口启动且仍存活的成员继续保留所有权；不接管新服务。
        for member in entry.get('members', [entry['root']]):
            handle = verified_handle(member, processes)
            if handle:
                kernel_api().CloseHandle(handle)
                refresh_members(label)
                return
    state['services'][label] = {'owned': False}
    save_state(state)


def request_shutdown(pid, owned_pids):
    kernel = kernel_api()
    # 每个自启服务有独立隐藏控制台，信号只发往该控制台。
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.DWORD)
    callback = callback_type(lambda event: True)
    kernel.FreeConsole()
    if kernel.AttachConsole(pid):
        kernel.SetConsoleCtrlHandler(callback, True)
        try:
            console_pids = (wintypes.DWORD * 1024)()
            count = kernel.GetConsoleProcessList(console_pids, len(console_pids))
            # 控制台若混入身份未核验的进程，放弃广播，仅使用后续的具体句柄兜底。
            verified_console = set(owned_pids) | {os.getpid()}
            if 0 < count <= len(console_pids) and set(console_pids[:count]) <= verified_console:
                kernel.GenerateConsoleCtrlEvent(1, 0)
                time.sleep(.3)
        finally:
            kernel.FreeConsole()
            kernel.SetConsoleCtrlHandler(callback, False)


def stop_owned(labels=('web', 'backend')):
    state = load_state()
    processes = snapshot() if any(entry.get('owned') for entry in state['services'].values()) else {}
    messages = []
    kernel = kernel_api()
    for label in labels:
        name = '前端' if label == 'web' else '后端'
        entry = state['services'].get(label)
        if entry and entry.get('stopped'):
            messages.append(name + '：已停止，无需重复关闭')
            continue
        if not entry or not entry.get('owned'):
            messages.append(name + '：未由本入口启动，保留（手动或旧服务）')
            continue
        members = collect_members(entry, processes)
        entry['members'] = members
        # 先保存后代身份，即使根进程先退出，下次仍可核验已登记的子进程。
        save_state(state)
        handles = []
        for member in members:
            handle = verified_handle(member, processes)
            if handle:
                handles.append((member, handle))
        if not handles:
            messages.append(name + '：已退出或身份无法核对，未操作')
            continue
        try:
            request_shutdown(handles[0][0]['pid'], {member['pid'] for member, _ in handles})
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline and any(kernel.WaitForSingleObject(h, 0) == 258 for _, h in handles):
                time.sleep(.1)
            # 正常停止超时，仅对持有的已核验句柄兜底，绝不按端口或名称结束。
            for _, handle in reversed(handles):
                if kernel.WaitForSingleObject(handle, 0) == 258:
                    kernel.TerminateProcess(handle, 1)
                    kernel.WaitForSingleObject(handle, 3000)
            remaining = any(kernel.WaitForSingleObject(h, 0) != 0 for _, h in handles)
            messages.append(name + ('：部分进程未退出，请检查' if remaining else '：已停止'))
            if not remaining:
                entry['owned'] = False
                entry['stopped'] = True
        finally:
            for _, handle in handles:
                kernel.CloseHandle(handle)
    save_state(state)
    return '\n'.join(messages)


def local_url(value):
    parsed = urlsplit(value)
    if parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost', '::1') or parsed.username or parsed.password:
        raise ValueError('本机启动入口只连接回环 HTTP 服务')
    return parsed


def ready(url):
    try:
        with urlopen(url, timeout=2) as response:
            return response.status == 200
    except (URLError, TimeoutError, OSError):
        return False


def wait_ready(url, timeout=60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if ready(url):
            return
        time.sleep(.2)
    raise RuntimeError('客户端服务未能启动，请检查 .runtime/local-launch 日志')


def start_service(args, cwd, label):
    logs = ROOT / '.runtime' / 'local-launch'
    logs.mkdir(parents=True, exist_ok=True)
    with (logs / (label + '.log')).open('ab') as output:
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = 0
        process = subprocess.Popen(args, cwd=cwd, stdin=subprocess.DEVNULL, stdout=output, stderr=output,
                                   creationflags=subprocess.CREATE_NEW_CONSOLE, startupinfo=startup)
    try:
        remember_process(process, cwd, label)
    except Exception:
        # Popen 持有刚创建进程的句柄；登记失败时不留下未管理的根进程。
        process.terminate()
        process.wait(timeout=15)
        raise
    return process


def _launch(started, open_browser):
    api = os.environ.get('MUSIC_CORE_API_TARGET', 'http://127.0.0.1:8001').rstrip('/')
    page = os.environ.get('MUSIC_CORE_ADMIN_WEB_URL', 'http://127.0.0.1:5174/settings')
    backend, frontend = local_url(api), local_url(page)
    os.environ['MUSIC_CORE_LOCAL_MODE'] = '1'
    if not ready(api + '/api/health'):
        python = ROOT / 'server' / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        if not python.is_file():
            raise RuntimeError('尚未安装后端依赖，请先按开发说明准备环境')
        started.append(start_service([str(python), '-m', 'uvicorn', 'app.main:app', '--host', backend.hostname,
                       '--port', str(backend.port or 80)], ROOT / 'server', 'backend'))
        wait_ready(api + '/api/health')
        refresh_members('backend')
    else:
        remember_reused('backend')
    web_origin = frontend.scheme + '://' + frontend.netloc
    if not ready(web_origin):
        node = shutil.which('node')
        vite = ROOT / 'web' / 'node_modules' / 'vite' / 'bin' / 'vite.js'
        if not node or not vite.is_file():
            raise RuntimeError('未找到 Node 或前端依赖，请先按开发说明安装环境')
        # 与 pnpm dev 相同的 Vite 入口，直接调用 Node，避开 Windows 批处理路径转义。
        command = [node, str(vite), '--host', frontend.hostname, '--port', str(frontend.port or 80), '--strictPort']
        started.append(start_service(command, ROOT / 'web', 'web'))
        wait_ready(web_origin)
        refresh_members('web')
    else:
        remember_reused('web')
    data = Path(os.environ.get('MUSIC_CORE_DATA_DIR', ROOT / '.runtime' / 'app-data'))
    with urlopen(api + '/api/downloads/settings', timeout=10) as response:
        if json.load(response).get('mode') != 'local':
            raise RuntimeError('此端口正在运行正式网页模式；请为本机模式配置独立端口，不会自动重启现有服务')
    # 私有能力只在本机进程读取，永远不传给浏览器或普通 HTTP 访问者。
    secret = (data / '.library-admin-token').read_text(encoding='utf-8').strip()
    request = Request(api + '/api/downloads/settings/local-launch', method='POST', data=b'',
                      headers={'X-Library-Admin': secret, 'Sec-Fetch-Site':'none'})
    with urlopen(request, timeout=10) as response:
        ticket = json.load(response)['ticket']
    target = page.split('#', 1)[0] + '#local-launch=' + quote(ticket)
    open_browser(target)
    return started


def launch(open_browser=webbrowser.open):
    started = []
    try:
        return _launch(started, open_browser)
    except Exception:
        # 失败时只清理本次入口创建的进程，绝不终止已存在的服务。
        labels = []
        state = load_state()
        for label, entry in state['services'].items():
            if entry.get('owned') and any(entry['root']['pid'] == process.pid for process in started):
                labels.append(label)
        if labels:
            stop_owned(labels)
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--stop', action='store_true')
    args = parser.parse_args()
    try:
        with launcher_lock():
            if args.stop:
                result = stop_owned()
            else:
                launch()
        if args.stop:
            import tkinter.messagebox
            tkinter.messagebox.showinfo('音乐客户端关闭结果', result)
    except Exception as reason:
        # 不把授权 URL 或私有能力写入日志、剪贴板和错误弹窗。
        import tkinter.messagebox
        tkinter.messagebox.showerror('音乐客户端操作失败', str(reason))
