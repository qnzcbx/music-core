"""本地播放与文件操作浏览器验收；历史音频只读，写操作隔离于临时目录。"""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import threading
import time
from types import SimpleNamespace
import httpx
import uvicorn
from playwright.sync_api import sync_playwright
from app.main import create_app
from app.downloads import DownloadManager, DownloadSettings, DownloadTask, Job
from app.models import TrackIdentity, SearchPage, SongCandidate
from app.lyrics import LyricDocument
from app.core.media_store import MediaSettings
from recovery_fixture import FaultUpstream, allow_fixture_target

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(os.environ.get('MUSIC_CORE_VERIFY_OUT', ROOT / '.runtime/verify-local-files'))
CHROME = os.environ.get('CHROMIUM_PATH')


def free_port(excluded=()):
    for _ in range(20):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
        if port not in excluded: return port
    raise RuntimeError('无法分配未占用的本地端口')


def main():
    OUT.mkdir(parents=True, exist_ok=True); (OUT / 'screenshots').mkdir(exist_ok=True)
    api_port = free_port(); web_port = free_port({api_port})
    root = ROOT / 'downloads'
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in root.iterdir() if p.suffix in ('.mp3', '.m4a', '.flac')}
    upstream = FaultUpstream(); resolves = []
    async def resolve(identity, options=None):
        resolves.append(identity.platformId)
        if identity.platformId == '2': await asyncio.sleep(1)
        return await upstream.resolve(identity)
    async def search(*args):
        return SearchPage(items=tuple(SongCandidate(identity=TrackIdentity(providerId='kuwo', platformId=str(i)), title=f'在线验收{i}', artists=('人工',), cover='https://fixture.test/cover.svg') for i in (1, 2)))
    async def lyrics(identity): return LyricDocument(identity=identity, status='unavailable')
    app = create_app(transport=httpx.MockTransport(upstream.handle), target_check=allow_fixture_target,
                     download_settings=DownloadSettings(directory=root), media_settings=MediaSettings(lease_ttl=2, media_ttl=.3, sweep_interval=.1))
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=api_port, access_log=False, log_level='critical'))
    thread = threading.Thread(target=server.run, daemon=True); thread.start()
    for _ in range(100):
        if server.started: break
        time.sleep(.05)
    assert server.started
    app.state.kuwo = SimpleNamespace(resolve=resolve, search=search, get_lyrics=lyrics)
    vite = subprocess.Popen(['cmd', '/c', f'pnpm dev --host 127.0.0.1 --port {web_port} --strictPort'], cwd=ROOT / 'web', env={**os.environ, 'MUSIC_CORE_API_TARGET': f'http://127.0.0.1:{api_port}'}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f'http://127.0.0.1:{web_port}'; result = {}; errors = []
    try:
        for _ in range(100):
            try:
                if httpx.get(url).status_code == 200: break
            except httpx.HTTPError: pass
            time.sleep(.1)
        with tempfile.TemporaryDirectory(prefix='music-core-local-acceptance-') as directory, sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, executable_path=CHROME, args=['--autoplay-policy=no-user-gesture-required'])
            context = browser.new_context(viewport={'width': 1440, 'height': 1000}, permissions=['clipboard-read', 'clipboard-write'])
            page = context.new_page(); page.route('https://fixture.test/cover.svg',lambda route:route.fulfill(content_type='image/svg+xml',body='<svg xmlns="http://www.w3.org/2000/svg" width="44" height="44"><rect width="44" height="44" fill="#879ba5"/></svg>')); page.on('pageerror', lambda e: errors.append(str(e)))
            requests = []; leases = []; closed = []
            page.on('request', lambda r: requests.append(r.url.split('/api/', 1)[1]) if '/api/' in r.url else None)
            page.on('response', lambda r: leases.append(r.json()['playbackId']) if r.url.endswith('/api/playback/open') and r.status == 200 else None)
            page.on('response', lambda r: closed.append(r.status) if r.url.endswith('/close') else None)
            page.goto(url + '/downloads'); page.wait_for_load_state('networkidle')
            page.evaluate('window.originalAudio=document.querySelector("audio")')
            files = page.request.get(url + '/api/downloads/files').json()
            assert len(files) == len(before)
            def row(file): return page.locator(f'.saved-row[data-filename="{file["filename"]}"]')
            def play(file):
                if row(file).get_attribute('data-playback')!='playing': row(file).locator('.download-identity').click()
                page.wait_for_function('!document.querySelector("audio").paused&&document.querySelector("audio").currentTime>0')
                page.wait_for_function('Number.isFinite(document.querySelector("audio").duration)&&document.querySelector("audio").duration>1')
            def seek(fraction):
                page.get_by_role('slider', name='播放进度').evaluate('(el,f)=>{el.value=Number(el.max)*f;el.dispatchEvent(new Event("input",{bubbles:true}));el.dispatchEvent(new Event("change",{bubbles:true}));}', fraction)
                page.wait_for_function('(f)=>Math.abs(document.querySelector("audio").currentTime/document.querySelector("audio").duration-f)<.02', arg=fraction)
            samples = []
            for pattern in ['东风志', '牵丝戏', '飞鸟与鱼', '一场雨', '天龙八部']:
                file = next(f for f in files if pattern in f['filename']); play(file)
                seek(.5); seek(.96)
                samples.append({'format': file['format'], 'durationSeconds': page.locator('audio').evaluate('(a)=>a.duration'), 'middleAndEndSeek': True})
            assert not resolves and not leases
            result['realSamples'] = samples
            mp3 = next(f for f in files if '东风志' in f['filename']); play(mp3)
            other=next(f for f in files if f['fileId']!=mp3['fileId'])
            row(other).hover(); page.wait_for_timeout(180)
            assert row(other).locator('.download-cover-play').evaluate('(el)=>getComputedStyle(el).opacity')=='1'
            assert row(other).locator('.download-cover-play').get_attribute('data-icon')=='play'
            assert row(mp3).locator('.download-cover-play').get_attribute('data-icon')=='pause'
            assert page.locator('.saved-row.is-current').count()==1
            assert row(other).evaluate("el=>{const probe=document.createElement('i');probe.style.background='var(--app-hover)';el.append(probe);const equal=getComputedStyle(el).backgroundColor===getComputedStyle(probe).backgroundColor;probe.remove();return equal}")
            row(mp3).locator('.download-cover').click(); page.wait_for_function('document.querySelector(".saved-row.is-current").dataset.playback==="paused"')
            assert row(mp3).get_attribute('data-playback')=='paused' and row(mp3).locator('.download-cover-play').get_attribute('data-icon')=='play'
            assert row(mp3).get_by_role('status').inner_text()=='已暂停'
            row(other).click(position={'x':row(other).bounding_box()['width']/2,'y':10}); page.wait_for_timeout(300)
            assert row(other).get_attribute('data-playback')=='playing' and row(mp3).get_attribute('data-playback') is None
            row(mp3).locator('.download-identity').focus(); page.wait_for_timeout(180)
            assert row(mp3).locator('.download-cover-play').evaluate('(el)=>getComputedStyle(el).opacity')=='1'
            held=[];pattern='**/api/downloads/files/'+mp3['fileId']+'/stream'
            page.route(pattern,lambda route:held.append(route))
            row(mp3).locator('.download-identity').click(); page.wait_for_function('document.querySelector(".saved-row.is-current").dataset.playback==="loading"')
            assert row(mp3).locator('.download-cover-play').get_attribute('data-icon')=='loading'
            page.screenshot(path=str(OUT/'screenshots/feedbackPatch-patch-loading.png'))
            page.get_by_role('button',name='暂停',exact=True).click(); page.unroute(pattern)
            for pending_route in held: pending_route.continue_()
            page.wait_for_timeout(350); assert page.locator('audio').evaluate('(a)=>a.paused') and row(mp3).get_attribute('data-playback')=='paused'
            play(mp3)
            result['feedbackPatch']={'hoverMatchesSearch':True,'defaultCoverOverlay':True,'coverToggle':True,'wholeRowPlay':True,'pauseKeepsSelection':True,'focusFeedback':True}

            page.get_by_role('button', name='暂停', exact=True).click(); assert page.locator('audio').evaluate('(a)=>a.paused')
            page.get_by_role('button', name='播放', exact=True).click(); page.wait_for_timeout(300)
            row(mp3).get_by_role('button', name='复制名称', exact=True).click()
            assert page.evaluate('navigator.clipboard.readText()') == mp3['filename']
            page.locator('a[href="/settings"]').first.click(); page.wait_for_timeout(200)
            assert not page.locator('audio').evaluate('(a)=>a.paused')
            page.get_by_role('button', name='打开沉浸式播放器').first.click(); page.get_by_role('region', name='沉浸式播放器').wait_for()
            assert page.evaluate('document.querySelector("audio")===window.originalAudio&&document.querySelectorAll("audio").length===1')
            page.get_by_role('button', name='收起歌曲详情页').click(); page.wait_for_timeout(500)
            page.locator('a[href="/downloads"]').first.click(); page.wait_for_timeout(300)
            for width in (1440, 768, 390):
                page.set_viewport_size({'width': width, 'height': 1000})
                for theme in ('light', 'dark'):
                    page.evaluate('(theme)=>{document.documentElement.classList.toggle("dark",theme==="dark");document.documentElement.dataset.theme=theme}', theme)
                    page.wait_for_timeout(150)
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                    page.screenshot(path=str(OUT / f'screenshots/feedbackPatch-files-{width}-{theme}.png'))
            page.set_viewport_size({'width': 1440, 'height': 1000})
            operation_x=page.locator('.download-columns span').last.bounding_box()['x']
            for icon in page.get_by_role('button',name='复制名称',exact=True).all(): assert abs(icon.bounding_box()['x']-operation_x)<2
            result['desktopColumnsAligned']=True
            page.evaluate('document.documentElement.classList.remove("dark");document.documentElement.dataset.theme="light"')
            # 相同 Audio 在线、本地双向切换；在线使用明确标识的受控可播放 WAV。
            page.locator('a[href="/"]').first.click(); page.locator('#query').fill('在线验收'); page.locator('#query').press('Enter')
            online = page.locator('.song-row[data-platform-id="1"]').first
            online.locator('.action-play').click(); page.wait_for_function('document.querySelector("audio").currentTime>0&&!document.querySelector("audio").paused')
            page.wait_for_timeout(1400); assert leases and resolves
            page.locator('a[href="/downloads"]').first.click(); page.wait_for_timeout(100); assert page.locator('.saved-row.is-current').count()==0; play(mp3)
            page.wait_for_timeout(300); assert 204 in closed
            count = len([r for r in requests if r.endswith('/renew')]); page.wait_for_timeout(2300)
            assert len([r for r in requests if r.endswith('/renew')]) == count
            page.locator('a[href="/"]').first.click(); page.locator('#query').fill('在线验收'); page.locator('#query').press('Enter')
            page.locator('.song-row[data-platform-id="2"]').first.locator('.action-play').click(); page.wait_for_timeout(100)
            page.locator('a[href="/downloads"]').first.click(); play(mp3); page.wait_for_timeout(1600)
            assert '/api/downloads/files/' in page.locator('audio').get_attribute('src')
            assert page.evaluate('document.querySelector("audio")===window.originalAudio')
            result['remoteSwitch'] = {'controlled': True, 'opens': len(leases), 'closeStatuses': closed, 'noLocalRenew': True, 'lateRemoteIsolated': True}
            page.get_by_role('button', name='关闭播放').click(); page.wait_for_timeout(300)
            # 从此刻起仅操作临时副本，真实目录只读验收结束。
            temporary = Path(directory)
            for name in ('保留.mp3', '删除.mp3', '其他.mp3', '失败.mp3'):
                shutil.copyfile(root / mp3['filename'], temporary / name)
            app.state.downloads = DownloadManager(app.state, DownloadSettings(directory=temporary))
            saved = app.state.downloads.files(); metadata = next(f for f in saved if f.filename == '保留.mp3')
            now = int(time.time() * 1000)
            app.state.downloads.jobs['metadata'] = Job(DownloadTask(id='metadata', identity=TrackIdentity(providerId='kuwo', platformId='1'), title='真实任务标题', artist='任务歌手', status='completed', filename=metadata.filename, fileId=metadata.fileId, receivedBytes=metadata.sizeBytes, createdAt=now, updatedAt=now))
            # 封面视觉夹具经原搜索下载入口进入 covers，不写入历史歌曲或改播放器。
            page.route('**/api/downloads',lambda route:route.fulfill(status=202,json=app.state.downloads.jobs['metadata'].public.model_dump()) if route.request.method=='POST' else route.continue_())
            page.locator('a[href="/"]').first.click(); page.locator('#query').fill('在线验收'); page.locator('#query').press('Enter')
            page.locator('.song-row[data-platform-id="1"]').first.locator('.action-download').click()
            page.wait_for_timeout(300); page.unroute('**/api/downloads')
            page.locator('a[href="/downloads"]').first.click(); page.get_by_role('button', name='刷新下载列表').click(); page.get_by_text('真实任务标题', exact=True).wait_for()
            keep = page.locator('.saved-row[data-filename="保留.mp3"]')
            keep.locator('img.cover-loaded').wait_for(); keep.hover(); page.wait_for_timeout(180)
            assert keep.locator('.download-cover-play').evaluate('(el)=>getComputedStyle(el).opacity')=='1'
            page.screenshot(path=str(OUT/'screenshots/feedbackPatch-patch-image-cover-hover.png'))
            result['feedbackPatch']['imageCoverOverlay']=True
            keep.get_by_role('button', name='复制名称').click(); assert page.evaluate('navigator.clipboard.readText()') == '真实任务标题'
            keep.get_by_role('button', name='删除下载记录').click(); dialog = page.get_by_role('alertdialog')
            assert not dialog.get_by_role('checkbox').is_checked(); dialog.get_by_role('button', name='取消', exact=True).click()
            assert (temporary / '保留.mp3').exists() and keep.count() == 1
            # 删除其他文件不影响当前歌曲。
            page.locator('.saved-row[data-filename="其他.mp3"] .download-identity').click(); page.wait_for_timeout(500)
            keep.get_by_role('button', name='删除下载记录').click(); dialog.get_by_role('button', name='确认删除').click(); dialog.wait_for(state='hidden')
            assert keep.count() == 0 and (temporary / '保留.mp3').exists()
            assert not page.locator('audio').evaluate('(a)=>a.paused')
            # 新建 Manager 模拟 Core 生命周期重启；随后页面刷新仍隐藏。
            page.get_by_role('button', name='关闭播放').click(); page.wait_for_timeout(200)
            server.should_exit = True; thread.join(timeout=5); assert not thread.is_alive()
            app = create_app(download_settings=DownloadSettings(directory=temporary))
            server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=api_port, access_log=False, log_level='critical'))
            thread = threading.Thread(target=server.run, daemon=True); thread.start()
            for _ in range(100):
                if server.started: break
                time.sleep(.05)
            assert server.started
            page.reload(); page.wait_for_load_state('networkidle'); assert keep.count() == 0
            assert (temporary / '保留.mp3').exists()
            # 后端拒绝时弹窗及列表保留。
            failure = page.locator('.saved-row[data-filename="失败.mp3"]')
            failure.get_by_role('button', name='删除下载记录').click()
            page.route('**/api/downloads/files/*/remove', lambda route: route.fulfill(status=503, json={'error': {'message': '人工占用，删除失败'}}))
            dialog.get_by_role('button', name='确认删除').click(); dialog.get_by_role('alert').wait_for()
            assert failure.count() == 1 and (temporary / '失败.mp3').exists()
            page.screenshot(path=str(OUT / 'screenshots/feedbackPatch-delete-failure.png')); dialog.get_by_role('button', name='取消', exact=True).click(); page.unroute('**/api/downloads/files/*/remove')
            # 当前本地文件必须先停止并清除队列，再真实删除。
            delete = page.locator('.saved-row[data-filename="删除.mp3"]')
            delete.locator('.download-identity').click(); page.wait_for_function('document.querySelector("audio").currentTime>0')
            delete.get_by_role('button', name='删除下载记录').click(); dialog.get_by_role('checkbox').check()
            page.screenshot(path=str(OUT / 'screenshots/feedbackPatch-delete-confirm.png')); dialog.get_by_role('button', name='确认删除').click(); dialog.wait_for(state='hidden')
            assert not (temporary / '删除.mp3').exists() and delete.count() == 0
            assert page.locator('audio').evaluate('(a)=>a.paused&&!a.getAttribute("src")'); assert page.locator('.saved-row.is-current').count()==0
            page.get_by_role('button', name='播放队列').click(); assert page.locator('.queue-body').get_by_text('删除.mp3', exact=True).count() == 0
            page.keyboard.press('Escape')
            for index in range(10):
                scrolling=temporary/f'滚动验收{index}.mp3'; shutil.copyfile(root/mp3['filename'],scrolling); os.utime(scrolling,(1,1))
            # 真触摸 CDP：短按、长按、滑动取消；不是仅派发 DOM click。
            mobile = browser.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True, permissions=['clipboard-read','clipboard-write'])
            touch = mobile.new_page(); touch.on('pageerror', lambda e: errors.append(str(e))); touch.goto(url + '/downloads'); touch.wait_for_load_state('networkidle')
            target = touch.locator('.saved-row[data-filename="其他.mp3"]'); assert target.evaluate('(el)=>getComputedStyle(el).webkitTapHighlightColor')=='rgba(0, 0, 0, 0)'; box = target.bounding_box(); x, y = box['x'] + 80, box['y'] + 20
            cdp = mobile.new_cdp_session(touch)
            def dispatch(kind, points): cdp.send('Input.dispatchTouchEvent', {'type': kind, 'touchPoints': points})
            dispatch('touchStart', [{'x': x, 'y': y}]); touch.wait_for_timeout(850); touch.get_by_role('menu').wait_for(); dispatch('touchEnd', [])
            assert touch.locator('audio').evaluate('(a)=>a.paused&&!a.getAttribute("src")')
            touch.screenshot(path=str(OUT / 'screenshots/feedbackPatch-mobile-context-menu.png')); touch.get_by_role('menuitem',name='复制名称').click(); touch.get_by_role('menu').wait_for(state='hidden')
            assert touch.evaluate('navigator.clipboard.readText()')=='其他.mp3'
            dispatch('touchStart', [{'x': x, 'y': y}]); dispatch('touchMove', [{'x': x, 'y': y - 60}]); touch.wait_for_timeout(850); dispatch('touchEnd', [])
            assert touch.get_by_role('menu').count() == 0 and touch.locator('audio').evaluate('(a)=>a.paused')
            touch.evaluate('document.querySelector("#app-content").scrollTop=0'); touch.wait_for_timeout(250)
            box=target.bounding_box(); x,y=box['x']+80,box['y']+20
            touch.touchscreen.tap(x, y); touch.wait_for_function('document.querySelector("audio").currentTime>0&&!document.querySelector("audio").paused')
            assert target.locator('.local-playback-status').inner_text()=='正在播放' and not target.locator('.download-cover').is_visible()
            touch.touchscreen.tap(x,y); touch.wait_for_function('document.querySelector(".saved-row.is-current").dataset.playback==="paused"'); assert target.locator('.local-playback-status').inner_text()=='已暂停'
            assert target.get_attribute('class').find('is-current')>=0
            touch.screenshot(path=str(OUT/'screenshots/feedbackPatch-patch-mobile-paused.png'))
            target.locator('.download-identity').focus(); touch.keyboard.press('Shift+F10'); touch.get_by_role('menu').wait_for(); touch.get_by_role('menuitem',name='删除',exact=True).click()
            assert not touch.get_by_role('alertdialog').get_by_role('checkbox').is_checked()
            touch.get_by_role('button',name='取消',exact=True).click()
            target.get_by_role('button',name='文件操作',exact=True).focus(); target.get_by_role('button',name='文件操作',exact=True).press('Enter'); touch.get_by_role('menu').wait_for(); touch.keyboard.press('Escape')
            target.click(button='right'); touch.get_by_role('menu').wait_for(); touch.mouse.click(350, 10); touch.get_by_role('menu').wait_for(state='hidden')
            assert touch.evaluate('document.documentElement.scrollWidth<=innerWidth')
            mobile.close(); context.close(); browser.close()
            result['temporaryOperations'] = {'hideSurvivesRestart': True, 'originalCopyPreserved': True, 'physicalDelete': True, 'failureRetainsRow': True, 'currentStoppedAndRemovedFromQueue': True, 'otherSongContinues': True}
            result['gestures'] = {'shortTap': True, 'longPressNoPlay': True, 'movingCancels': True, 'keyboard': True, 'rightClick': True, 'outsideCloses': True}
            result['pageErrors'] = errors
            assert errors == []
        assert before == {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in root.iterdir() if p.suffix in ('.mp3', '.m4a', '.flac')}
        result['historicalFilesUnchanged'] = True
        (OUT / 'browser-result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(result, ensure_ascii=False))
    finally:
        server.should_exit = True; thread.join(timeout=5)
        subprocess.run(['taskkill', '/PID', str(vite.pid), '/T', '/F'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == '__main__': main()
