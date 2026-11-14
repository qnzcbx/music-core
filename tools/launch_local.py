"""可信本机入口：启动或复用服务，通过私有能力换取一次性票据后打开网页。"""
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
        return subprocess.Popen(args, cwd=cwd, stdin=subprocess.DEVNULL, stdout=output, stderr=output,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)


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
        for process in started:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=15)
        raise


if __name__ == '__main__':
    try:
        launch()
    except Exception as reason:
        # 不把授权 URL 或私有能力写入日志、剪贴板和错误弹窗。
        import tkinter.messagebox
        tkinter.messagebox.showerror('音乐客户端启动失败', str(reason))
