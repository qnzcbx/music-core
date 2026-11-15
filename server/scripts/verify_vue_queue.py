"""14 播放器与歌词 浏览器验收：真实媒体与受控短音频分别执行。"""
import argparse
import io
import json
import os
import subprocess
import threading
import time
import wave
from pathlib import Path
import socket
import shutil
import uuid
from types import SimpleNamespace
import httpx
import uvicorn
from playwright.sync_api import sync_playwright
from verify_vue_player import ROOT,FaultUpstream,allow_fixture_target
from app.main import create_app
from app.models import SearchPage,SongCandidate,TrackIdentity
from app.core.media_store import MediaSettings
from app.lyrics import LyricDocument

OUT=Path(os.environ.get('MUSIC_CORE_VERIFY_OUT',ROOT/'.runtime/verify-vue-queue'))

def free_port(excluded=()):
    for _ in range(20):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        if port not in excluded:return port
    raise RuntimeError('无法分配未占用的本地端口')

def mode(page,label):
    page.get_by_role('button',name='播放模式',exact=True).click()
    page.get_by_role('menuitem',name=label,exact=True).click()

def add(page,row):
    row.hover();row.locator('.action-play-next').click()
    page.get_by_role('menuitem',name='添加到播放队列',exact=True).click()

def ready(page,title=None):
    page.wait_for_function("title=>document.querySelector('.player').dataset.phase==='ready' && !document.querySelector('audio').paused && (!title||document.querySelector('.player .track-title').textContent.includes(title))",arg=title,timeout=45000)
    if title:assert title in page.locator('.player .track-title').inner_text()

def queue(page):page.get_by_role('button',name='播放队列',exact=True).click()

def seek_end(page):
    page.get_by_label('播放进度',exact=True).evaluate('el=>{el.value=String(Number(el.max)-.25);el.dispatchEvent(new Event("change",{bubbles:true}));}')


def verify_resume(page, url, upstream, app):
    """复用本脚本的 Chromium、受控上游及动态端口，验收刷新恢复。"""
    controlled = upstream is not None
    requests, errors = [], []
    page.on('request', lambda r: requests.append(r.url) if r.url.endswith('/api/playback/open') else None)
    page.on('pageerror', lambda e: errors.append(str(e)))
    target = 2 if controlled else 60
    page.goto(url + '/search?q=' + ('人工' if controlled else '莉莉安'))
    a = page.locator('.song-row[data-provider="kuwo"][data-platform-id="' + ('1' if controlled else '3453735') + '"]').first
    a.wait_for(timeout=30000)
    a_id = a.get_attribute('data-platform-id')
    b = page.locator('.song-row[data-provider="kuwo"]:not([data-platform-id="' + a_id + '"])').first
    title_a, title_b = a.locator('h3').inner_text(), b.locator('h3').inner_text()
    a.locator('.action-play').click()
    ready(page, title_a)
    add(page, b)
    mode(page, '列表循环')

    def snapshot():
        return page.evaluate('JSON.parse(localStorage.getItem("music-core.queue.v1"))')

    def seek(seconds):
        page.get_by_label('播放进度', exact=True).evaluate(
            '(el,n)=>{el.value=String(n);el.dispatchEvent(new Event("change",{bubbles:true}));}', seconds)
        page.wait_for_function('!document.querySelector("audio").seeking')

    def reload_paused(expected):
        count = len(requests)
        page.reload()
        page.wait_for_load_state('networkidle')
        assert len(requests) == count, '刷新不应 Open'
        assert page.locator('audio').evaluate('a=>a.paused&&!a.getAttribute("src")')
        assert page.locator('.player .play-toggle').get_attribute('aria-label') == '播放'
        assert abs(float(page.get_by_label('播放进度', exact=True).input_value()) - expected) < 1
        return count

    def resume(expected):
        page.evaluate('window.heardFrom=null;document.querySelector("audio").addEventListener("playing",()=>window.heardFrom=document.querySelector("audio").currentTime,{once:true})')
        page.locator('.player .play-toggle').click()
        page.wait_for_function('n=>!document.querySelector("audio").paused&&document.querySelector("audio").currentTime>=n-.5', arg=expected, timeout=45000)
        page.wait_for_function('window.heardFrom!==null')
        assert abs(page.evaluate('window.heardFrom') - expected) < .6
        page.wait_for_function('document.querySelector("audio").currentTime>window.heardFrom+.1')
        return page.locator('audio').evaluate('a=>a.currentTime')

    seek(target)
    before = page.locator('audio').evaluate('a=>a.currentTime')
    saved = snapshot()
    count = reload_paused(before)
    assert title_a in page.locator('.track-title').inner_text()
    assert snapshot()['currentQueueKey'] == saved['currentQueueKey']
    assert snapshot()['queue'] == saved['queue']
    assert snapshot()['navigation']['mode'] == 'repeat_all'
    OUT.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(OUT / 'resume-online-paused.png'))
    after = resume(before)
    assert len(requests) == count + 1
    page.locator('.player .play-toggle').click()
    assert page.locator('audio').evaluate('a=>a.paused')
    paused = snapshot()['position']
    reload_paused(paused)
    resume(paused)
    seek(target + 1)
    reload_paused(target + 1)

    # 恢复后直接选择另一首，起点不能沿用上一首位置。
    b.locator('.action-play').click()
    ready(page, title_b)
    assert page.locator('audio').evaluate('a=>a.currentTime<1.5')
    page.get_by_role('button', name='上一首', exact=True).click()
    ready(page, title_a)
    page.get_by_role('button', name='下一首', exact=True).click()
    ready(page, title_b)
    local_result = None

    if controlled:
        # 恢复 Open 被受控上游挂起，用户立即切下一首；晚到结果须被关闭。
        seek(3)
        reload_paused(3)
        upstream.hold_next = True
        page.locator('.player .play-toggle').click()
        for _ in range(100):
            if upstream.held: break
            page.wait_for_timeout(20)
        assert upstream.held
        page.get_by_role('button', name='下一首', exact=True).click()
        ready(page, title_a)
        upstream.held.clear()
        page.wait_for_timeout(500)
        assert title_a in page.locator('.track-title').inner_text()
        assert page.locator('audio').evaluate('a=>a.currentTime<2')
        assert sum(lease.state == 'active' for lease in app.state.playback_leases.entries.values()) == 1
        # 在线临时失败保留曲目、位置及重试入口。
        seek(2)
        reload_paused(2)
        upstream.fail_open = True
        page.locator('.player .play-toggle').click()
        page.wait_for_function('document.querySelector(".player").dataset.phase==="error"')
        assert len(snapshot()['queue']) == 2
        upstream.fail_open = False
        resumed_retry = resume(2)
        assert resumed_retry >= 1.5
        mode(page, '顺序播放')
        page.get_by_role('button', name='下一首', exact=True).click()
        ready(page, title_b)
        seek_end(page)
        page.wait_for_function('document.querySelector("audio").ended', timeout=10000)
        assert snapshot()['position'] == 0
        reload_paused(0)
    else:
        # 只复制并删除本验收自己创建的文件，不修改已有下载。
        owned = ROOT / 'downloads' / ('resume-verification-' + uuid.uuid4().hex + '.mp3')
        source = next((ROOT / 'downloads').glob('*.mp3'))
        try:
            shutil.copyfile(source, owned)
            page.goto(url + '/downloads')
            row = page.locator('.download-row[data-filename="' + owned.name + '"]')
            row.locator('.download-identity').click(timeout=20000)
            ready(page, owned.name)
            seek(30)
            local_before = page.locator('audio').evaluate('a=>a.currentTime')
            file_id = snapshot()['queue'][-1]['fileId']
            count = reload_paused(local_before)
            assert any(f['fileId'] == file_id for f in page.request.get(url + '/api/downloads/files').json())
            local_after = resume(local_before)
            assert len(requests) == count, '本地恢复不应创建在线 Lease'
            page.locator('.player .play-toggle').click()
            reload_paused(snapshot()['position'])
            owned.unlink()
            page.locator('.player .play-toggle').click()
            page.wait_for_function('document.querySelector(".player").dataset.phase==="error"')
            assert '本地文件已不存在' in page.locator('.client-notice').inner_text()
            page.screenshot(path=str(OUT / 'resume-local-missing.png'))
            local_result = {'before': local_before, 'after': local_after, 'refreshOpens': 0, 'clickOpens': 0, 'stableFileId': True, 'missingFileMessage': True}
            queue(page)
            page.locator('.queue-choose').first.click()
            ready(page, title_a)
            page.keyboard.press('Escape')
        finally:
            owned.unlink(missing_ok=True)

    # 沉浸地址刷新退回底栏，仍然不发 Open。
    page.get_by_role('button', name='打开沉浸式播放器', exact=True).click()
    page.wait_for_url('**/player/**')
    count = len(requests)
    page.reload()
    page.wait_for_url(url + '/')
    assert len(requests) == count
    queue(page)
    page.get_by_role('button', name='清空队列', exact=True).click()
    page.keyboard.press('Escape')
    page.reload()
    page.wait_for_load_state('networkidle')
    assert page.locator('.player .play-toggle').is_disabled()
    assert snapshot()['queue'] == []
    for raw in ['{broken', '{"schemaVersion":999}']:
        page.evaluate('(raw)=>localStorage.setItem("music-core.queue.v1",raw)', raw)
        page.reload()
        page.wait_for_load_state('networkidle')
        assert page.locator('.player .play-toggle').is_disabled()
    assert not errors, errors
    result = {'controlled': controlled, 'before': before, 'after': after, 'refreshOpens': 0, 'clickOpens': 1, 'pausedReload': True, 'seekReload': True, 'directOtherStartsZero': True, 'queueModeRestored': True, 'raceAndFailure': controlled, 'endedPositionZero': controlled, 'local': local_result, 'clearAndInvalid': True, 'immersiveClosed': True, 'pageErrors': errors}
    (OUT / ('resume-controlled.json' if controlled else 'resume-real.json')).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))

def verify_empty_queue_dismissal(page, url, app):
    """复用真实播放链路，验证首页队列清空时的 Portal 与焦点清理。"""
    page.set_default_timeout(10000)
    errors, opened, results = [], [], []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('response', lambda response: opened.append(response.json())
            if response.url.endswith('/api/playback/open') and response.status == 200 else None)
    screenshots = OUT / 'screenshots'
    screenshots.mkdir(parents=True, exist_ok=True)
    for width in (1440, 390):
        page.set_viewport_size({'width': width, 'height': 900 if width == 1440 else 844})
        for action in ('clear', 'remove-last'):
            print(f'CASE {width} {action}', flush=True)
            page.goto(url + '/search?q=人工')
            page.wait_for_load_state('networkidle')
            page.locator('.song-row[data-platform-id="1"] .action-play').click()
            ready(page)
            # 从通常的导航入口返回首页，保留正在播放的会话。
            page.locator('a[href="/"]:visible').first.click()
            page.wait_for_url(url + '/')
            queue(page)
            layer = '.queue-panel' if width == 1440 else '.queue-drawer'
            page.locator(layer).wait_for(state='visible')
            page.screenshot(path=str(screenshots / f'queue-{width}-{action}-before.png'))
            # 逐帧观察，不能在底栏隐藏后继续显示失去锚点的面板。
            page.evaluate("""() => {
              window.queueResidualFrames = [];
              window.observeQueueFrames = true;
              const frame = () => {
                const footer = document.querySelector('.workspace-player');
                const layers = [...document.querySelectorAll('.queue-panel,.queue-drawer,[data-slot=drawer-overlay]')];
                if (!footer?.getClientRects().length && layers.some(el => el.getClientRects().length))
                  window.queueResidualFrames.push(layers.map(el => ({x:el.getBoundingClientRect().x,y:el.getBoundingClientRect().y})));
                if (window.observeQueueFrames) requestAnimationFrame(frame);
              };
              requestAnimationFrame(frame);
            }""")
            if action == 'clear':
                page.get_by_role('button', name='清空队列', exact=True).click()
            else:
                page.locator('.queue-remove').click()
            page.wait_for_function("!document.querySelector('.workspace-player').getClientRects().length")
            # 无需等待动画或 Escape，搜索必须立即能获得焦点并编辑。
            search = page.locator('#query')
            assert page.locator('.queue-panel,.queue-drawer,[data-slot=drawer-overlay]').count() == 0
            search.click(timeout=5000)
            search.fill('test')
            assert search.input_value() == 'test'
            assert search.evaluate('el => el === document.activeElement')
            assert page.url == url + '/'
            assert page.locator('.queue-panel,.queue-drawer,[data-slot=drawer-overlay]').count() == 0
            assert page.locator('audio').evaluate('audio => audio.paused && !audio.getAttribute("src")')
            page.wait_for_timeout(650)
            assert search.evaluate('el => el === document.activeElement')
            assert page.evaluate('window.queueResidualFrames') == []
            page.evaluate('window.observeQueueFrames = false')
            page.screenshot(path=str(screenshots / f'queue-{width}-{action}-after.png'), timeout=10000)
            for session in opened:
                assert page.request.head(url + session['streamUrl']).status == 410
            if app:
                assert not any(lease.state == 'active' for lease in app.state.playback_leases.entries.values())
            before = len(opened)
            page.reload()
            page.wait_for_load_state('networkidle')
            assert page.url == url + '/'
            assert not page.locator('.workspace-player').is_visible()
            assert page.locator('.queue-panel,.queue-drawer,[data-slot=drawer-overlay]').count() == 0
            assert page.locator('audio').evaluate('audio => audio.paused && !audio.getAttribute("src")')
            assert len(opened) == before
            # 重新从首页搜索并播放，队列能够正常再次打开。
            page.locator('#query').fill('人工')
            page.locator('#query').press('Enter')
            page.locator('.song-row[data-platform-id="1"] .action-play').click()
            ready(page)
            page.locator('a[href="/"]:visible').first.click()
            queue(page)
            assert page.locator(layer).is_visible()
            assert page.locator('.queue-list article').count() == 1
            page.keyboard.press('Escape')
            page.wait_for_selector(layer, state='detached')
            results.append({'width': width, 'action': action, 'closedWithoutResidualFrames': True,
                            'searchImmediatelyUsable': True, 'sessionReleased': True,
                            'reloadStaysEmpty': True, 'replayQueueOpens': True})
            # 清理本轮重新播放的测试歌曲，避免下一轮沿用。
            queue(page)
            page.get_by_role('button', name='清空队列', exact=True).click()
            page.wait_for_function("!document.querySelector('.workspace-player').getClientRects().length")
    assert not errors, errors
    result = {'cases': results, 'pageErrors': errors}
    (OUT / 'empty-queue-result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))


def verify_not_found(page, url, app):
    """在生产构建预览中覆盖路由回退和持续播放，复用既有受控服务。"""
    errors, results = [], []
    page.on('pageerror', lambda error: errors.append(str(error)))
    screenshots = OUT / 'screenshots'
    screenshots.mkdir(parents=True, exist_ok=True)
    paths = ['/missing-page?probe=1#lost', '/unknown/deep/page?probe=2#lost']
    for width in (1440, 390):
        page.set_viewport_size({'width': width, 'height': 900 if width == 1440 else 844})
        for path in paths:
            for method in ('internal', 'direct', 'refresh'):
                status = None
                if method == 'internal':
                    page.goto(url + '/settings')
                    page.wait_for_load_state('networkidle')
                    page.evaluate('path => document.querySelector("#app").__vue_app__.config.globalProperties.$router.push(path)', path)
                else:
                    response = page.goto(url + path)
                    status = response.status
                page.wait_for_load_state('networkidle')
                if method == 'refresh':
                    assert page.url == url + path
                    response = page.reload()
                    status = response.status
                    page.wait_for_load_state('networkidle')
                assert page.url == url + path
                assert page.get_by_role('heading', name='页面未找到', exact=True).count() == 1
                assert page.locator('.home-view').count() == 0
                assert not page.locator('.workspace-player').is_visible()
                assert page.locator('audio').evaluate('audio => audio.paused && !audio.getAttribute("src")')
                assert page.locator('.signature path').count() == 2
                assert page.locator('iframe').count() == 0
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                results.append({'width': width, 'requested': path, 'method': method,
                                'finalUrl': page.url, 'documentStatus': status})
                page.get_by_role('link', name='回到首页', exact=True).click()
                page.wait_for_url(url + '/')
                assert page.locator('.home-view').is_visible()
        page.goto(url + paths[1])
        page.wait_for_load_state('networkidle')
        page.screenshot(path=str(screenshots / f'not-found-{width}-light.png'))
    # 在实际剩余内容区校验居中和滚动，不能只靠全屏截图判断。
    layout_results = []
    def check_layout(width, height, must_fit):
        page.set_viewport_size({'width': width, 'height': height})
        page.wait_for_timeout(100)
        assert page.locator('.app-topbar').count() == 0
        assert page.locator('.app-sidebar').is_visible() == (width > 760)
        metrics = page.evaluate("""() => {
          const main = document.querySelector('#app-content');
          const box = main.getBoundingClientRect();
          const composition = document.querySelector('.composition').getBoundingClientRect();
          const sleeve = document.querySelector('.sleeve').getBoundingClientRect();
          const button = document.querySelector('.home-action').getBoundingClientRect();
          return {top:box.top,height:main.clientHeight,scrollHeight:main.scrollHeight,
            centerOffset:Math.abs((composition.top+composition.bottom)/2-(box.top+main.clientHeight/2)),
            sleeveVisible:sleeve.top>=box.top && sleeve.bottom<=box.bottom,
            buttonVisible:button.top>=box.top && button.bottom<=box.bottom};
        }""")
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        assert abs(metrics['top']) < 1, metrics
        if must_fit:
            assert metrics['scrollHeight'] <= metrics['height'] + 1, metrics
            assert metrics['sleeveVisible'] and metrics['buttonVisible'], metrics
            assert metrics['centerOffset'] < 3, metrics
        else:
            page.locator('.home-action').scroll_into_view_if_needed()
            assert page.locator('.home-action').evaluate('el => { const a=el.getBoundingClientRect(), b=document.querySelector("#app-content").getBoundingClientRect(); return a.top>=b.top && a.bottom<=b.bottom; }')
            page.locator('.sleeve').scroll_into_view_if_needed()
            page.locator('#app-content').evaluate('el => el.scrollTop = 0')
        assert page.locator('.error-time').is_visible() == (width > 760)
        layout_results.append({'width':width,'viewportHeight':height,'mustFit':must_fit,**metrics})
    page.goto(url + '/missing-page')
    page.wait_for_load_state('networkidle')
    for width, height in [(1920,1080),(1440,900),(1366,768),(1280,720),(1024,768),
                          (679,912),(390,844),(375,667),(390,500),(900,400)]:
        check_layout(width, height, height >= 667)
        if (width,height) in [(1366,768),(390,844),(390,500)]:
            page.screenshot(path=str(screenshots / f'not-found-layout-{width}-{height}.png'))
    # 应用主题优先于系统；画布跟随现有主题服务重绘。
    page.goto(url + '/settings')
    page.get_by_role('radio', name='深色', exact=True).check()
    page.evaluate('document.querySelector("#app").__vue_app__.config.globalProperties.$router.push("/missing-page")')
    page.wait_for_selector('.not-found')
    assert page.locator('html').get_attribute('data-theme') == 'dark'
    page.screenshot(path=str(screenshots / 'not-found-390-dark.png'))
    page.goto(url + '/settings')
    page.get_by_role('radio', name='浅色', exact=True).check()
    assert page.locator('.app-topbar').is_visible()
    # 合法搜索深链接及首页旧查询链接继续有效。
    page.goto(url + '/search?q=人工')
    page.locator('.song-row[data-platform-id="1"]').wait_for()
    assert page.url == url + '/search?q=%E4%BA%BA%E5%B7%A5' or page.url == url + '/search?q=人工'
    page.goto(url + '/?q=人工')
    page.wait_for_url('**/search?q=*')
    page.locator('.song-row[data-platform-id="1"]').wait_for()
    # 有效播放器旧入口保留刷新时回首页的行为；未知多层路径不被此守卫吞掉。
    page.goto(url + '/player/legacy-id')
    page.wait_for_url(url + '/')
    page.goto(url + '/player/unknown/deep')
    page.wait_for_selector('.not-found')
    assert page.url == url + '/player/unknown/deep'
    # 页面请求由 SPA 回退返回 200；资源/API 缺失不能返回应用 HTML。
    http_results = []
    for path in ['/missing-page', '/unknown/deep/page', '/api/does-not-exist',
                 '/assets/missing-file.js', '/assets/missing-file.css', '/missing.svg']:
        response = page.request.get(url + path)
        html = response.headers.get('content-type', '').startswith('text/html')
        expected_page = path in ['/missing-page', '/unknown/deep/page']
        assert response.status == (200 if expected_page else 404)
        assert html == expected_page
        http_results.append({'path': path, 'status': response.status, 'contentType': response.headers.get('content-type')})
    # 导航进出 404 保留同一个 Audio、会话、队列及连续播放时间。
    for width in (1440, 390):
        page.set_viewport_size({'width': width, 'height': 900 if width == 1440 else 844})
        page.goto(url + '/search?q=人工')
        page.locator('.song-row[data-platform-id="1"] .action-play').click()
        ready(page)
        page.wait_for_function('document.querySelector("audio").currentTime > .2')
        page.evaluate('window.originalAudio = document.querySelector("audio")')
        before = page.locator('audio').evaluate('audio => ({src:audio.src,time:audio.currentTime})')
        # 等待现有播放器把真实解码时长写回元数据，避免与本次路由无关的自然补全竞争。
        page.wait_for_function('JSON.parse(localStorage.getItem("music-core.queue.v1")).queue[0].metadata.durationSeconds > 0')
        storage = page.evaluate('localStorage.getItem("music-core.queue.v1")')
        page.evaluate('document.querySelector("#app").__vue_app__.config.globalProperties.$router.push("/unknown/deep/page")')
        page.wait_for_selector('.not-found')
        assert page.locator('audio').evaluate('audio => audio === window.originalAudio && !audio.paused')
        assert page.locator('audio').evaluate('audio => audio.src') == before['src']
        assert page.locator('.workspace-player').is_visible()
        check_layout(1366 if width == 1440 else width, 768 if width == 1440 else 844, True)
        page.screenshot(path=str(screenshots / f'not-found-playing-{width}.png'))
        queue(page)
        assert page.locator('.queue-list article').count() == 1
        page.keyboard.press('Escape')
        page.get_by_role('link', name='回到首页', exact=True).click()
        page.wait_for_url(url + '/')
        assert page.locator('audio').evaluate('audio => audio === window.originalAudio && !audio.paused')
        after = page.locator('audio').evaluate('audio => ({src:audio.src,time:audio.currentTime})')
        assert after['src'] == before['src'] and after['time'] >= before['time']
        snapshot = json.loads(page.evaluate('localStorage.getItem("music-core.queue.v1")'))
        assert snapshot['queue'] == json.loads(storage)['queue'], (snapshot['queue'], json.loads(storage)['queue'])
        if app: assert sum(lease.state == 'active' for lease in app.state.playback_leases.entries.values()) == 1
        results.append({'width': width, 'playingAcrossNotFound': True, 'sameAudioAndSource': True, 'queueUnchanged': True})
    assert not errors, errors
    result = {'navigation': results, 'layout': layout_results, 'http': http_results, 'pageErrors': errors}
    (OUT / 'not-found-result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--controlled',action='store_true');parser.add_argument('--resume',action='store_true');parser.add_argument('--empty-queue',action='store_true');parser.add_argument('--not-found',action='store_true');parser.add_argument('--home-voice',action='store_true');parser.add_argument('--url',default=os.environ.get('MUSIC_CORE_WEB_URL','http://127.0.0.1:5174'),help='未启动受控客户端时使用的 Vue 地址');args=parser.parse_args()
    server=None;vite=None;thread=None;app=None;upstream=None;url=args.url.rstrip('/')
    if args.controlled:
        upstream=FaultUpstream()
        output=io.BytesIO()
        with wave.open(output,'wb') as audio:
            audio.setparams((1,2,8000,0,'NONE','not compressed'))
            if args.not_found or args.home_voice:
                seconds = 60 if args.home_voice else 30
                audio.writeframes(upstream.audio[44:44+8000*2] * seconds)
            else:
                audio.writeframes(upstream.audio[44:44+8000*2*8])
        upstream.audio=output.getvalue()
        async def resolve(identity,options=None):return await upstream.resolve(identity)
        async def search(*args):return SearchPage(items=tuple(SongCandidate(identity=TrackIdentity(providerId='kuwo',platformId=str(i)),title=f'人工测试{i}',artists=('人工',)) for i in (1,2,3)))
        async def get_lyrics(identity):return LyricDocument(identity=identity,status='unavailable')
        # 队列断言不与定时续租竞争；短 TTL 的自动恢复由 verify_vue_player 覆盖。
        app=create_app(transport=httpx.MockTransport(upstream.handle),target_check=allow_fixture_target,media_settings=MediaSettings(media_ttl=.3,lease_ttl=300,sweep_interval=.1))
        api_port=free_port();web_port=free_port({api_port})
        server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=api_port,log_level='critical',access_log=False))
        thread=threading.Thread(target=server.run,daemon=True);thread.start()
        for _ in range(100):
            if server.started or not thread.is_alive():break
            time.sleep(.05)
        if not server.started:raise RuntimeError('队列受控服务启动失败')
        app.state.kuwo=SimpleNamespace(resolve=resolve,search=search,get_lyrics=get_lyrics)
        if args.not_found or args.home_voice:
            command = ['node', str(ROOT/'web/node_modules/vite/bin/vite.js'), 'preview', '--host', '127.0.0.1', '--port', str(web_port), '--strictPort']
        else:
            command = ['cmd','/c',f'pnpm dev --host 127.0.0.1 --port {web_port} --strictPort']
        vite=subprocess.Popen(command,cwd=ROOT/'web',env={**os.environ,'MUSIC_CORE_API_TARGET':f'http://127.0.0.1:{api_port}'},stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        url=f'http://127.0.0.1:{web_port}'
        for _ in range(100):
            try:
                if httpx.get(url).status_code==200:break
            except httpx.HTTPError:pass
            time.sleep(.1)
    screenshots=OUT/'screenshots';screenshots.mkdir(parents=True,exist_ok=True)
    try:
        with sync_playwright() as pw:
            browser=pw.chromium.launch(headless=True,executable_path=os.environ.get('CHROMIUM_PATH'),args=['--autoplay-policy=document-user-activation-required'] if args.home_voice else ['--autoplay-policy=no-user-gesture-required'])
            page=browser.new_page(viewport={'width':1440,'height':1000},has_touch=True);errors=[];console=[];opened=[];requests=[]
            if args.home_voice:
                from verify_home_voice import verify_home_voice
                verify_home_voice(browser, url, app, OUT)
                browser.close()
                return
            if args.not_found:
                verify_not_found(page, url, app)
                browser.close()
                return
            if args.empty_queue:
                verify_empty_queue_dismissal(page, url, app)
                browser.close()
                return
            if args.resume:
                verify_resume(page, url, upstream, app)
                browser.close()
                return
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.on('console',lambda m:console.append(m.text) if m.type=='error' else None)
            page.on('response',lambda r:opened.append(r.json()) if r.url.endswith('/api/playback/open') and r.status==200 else None)
            page.on('request',lambda r:requests.append(r.url) if r.url.endswith('/api/playback/open') else None)
            page.goto(url);page.wait_for_load_state('networkidle')
            page.locator('#query').fill('人工' if args.controlled else '银临');page.locator('#query').press('Enter')
            a=page.locator('.song-row[data-provider="kuwo"][data-platform-id="'+('1' if args.controlled else '9942644')+'"]').first
            a.wait_for(timeout=30000)
            # 相同关键词再次提交也应刷新，无独立更新按钮。
            for action in ('enter','icon'):
                with page.expect_response(lambda r:'/api/search' in r.url and r.request.method=='POST'):
                    if action=='enter':page.locator('#query').press('Enter')
                    else:page.get_by_role('button',name='搜索',exact=True).click()
                a.wait_for()
            assert page.get_by_role('button',name='更新搜索',exact=True).count()==0
            if args.controlled:b=page.locator('.song-row[data-platform-id="2"]');c=page.locator('.song-row[data-platform-id="3"]')
            else:
                others=page.locator('.song-row[data-provider="kuwo"]:not([data-platform-id="9942644"])');b=others.nth(0);c=others.nth(1)
            titles=[row.locator('h3').inner_text() for row in (a,b,c)]
            ids=[row.get_attribute('data-platform-id') for row in (a,b,c)]
            a.locator('.action-play').click();ready(page,titles[0]);page.wait_for_function("document.querySelector('audio').currentTime>.2")
            page.evaluate("window.firstAudio=document.querySelector('audio');window.naturalEnds=0;firstAudio.addEventListener('ended',()=>naturalEnds++)")
            count=len(requests);a.locator('.action-play').click();assert page.locator('audio').evaluate('a=>a.paused')
            a.locator('.action-play').click();ready(page,titles[0]);assert len(requests)==count
            add(page,b);add(page,b);add(page,c);assert len(opened)==1
            queue(page);assert page.locator('.queue-list article').count()==3
            if not args.controlled:page.screenshot(path=str(screenshots/'queue-desktop-queue.png'))
            page.locator('.queue-choose').nth(1).click();ready(page,titles[1]);page.keyboard.press('Escape')
            page.get_by_role('button',name='上一首',exact=True).click();ready(page,titles[0])
            page.get_by_role('button',name='下一首',exact=True).click();ready(page,titles[1])
            count=len(requests)
            for label in ('随机播放','单曲循环','列表循环','顺序播放'):mode(page,label)
            assert len(requests)==count
            page.get_by_role('button',name='播放模式',exact=True).click()
            if not args.controlled:page.screenshot(path=str(screenshots/'queue-playback-mode-menu.png'))
            page.keyboard.press('Escape');page.wait_for_function('document.activeElement?.getAttribute("aria-label")==="播放模式"')
            page.get_by_role('button',name='音量设置',exact=True).click();slider=page.locator('.volume-layer [role=slider]');slider.press('Home')
            for _ in range(30):slider.press('ArrowUp')
            page.get_by_role('button',name='静音',exact=True).click();assert page.locator('audio').evaluate('a=>a.muted&&a.volume===.3')
            slider.press('ArrowUp');assert page.locator('audio').evaluate('a=>!a.muted&&a.volume===.31')
            if not args.controlled:page.screenshot(path=str(screenshots/'queue-volume-popover.png'))
            page.keyboard.press('Escape');assert page.locator('.volume-layer').count()==0
            page.get_by_role('button',name='音量设置',exact=True).click();page.locator('.track-title').click();assert page.locator('.volume-layer').count()==0
            for path in ('/','/settings','/search'):
                page.evaluate("path=>{history.pushState({},'',path);dispatchEvent(new PopStateEvent('popstate'))}",path);page.wait_for_timeout(200)
                assert page.locator('audio').evaluate('a=>a===window.firstAudio')
                if path=='/settings':
                    session=len(requests);page.get_by_role('radio',name='深色',exact=True).check();assert len(requests)==session
                    queue(page)
                    if not args.controlled:page.screenshot(path=str(screenshots/'queue-desktop-dark-queue.png'))
                    page.keyboard.press('Escape');page.get_by_role('radio',name='浅色',exact=True).check()
            for width in (768,390):
                page.set_viewport_size({'width':width,'height':844});queue(page)
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                assert page.locator('audio').count()==1
                if width==390:
                    assert page.locator('.queue-drawer').is_visible()
                    if not args.controlled:page.screenshot(path=str(screenshots/'queue-mobile-queue-drawer.png'))
                page.keyboard.press('Escape')
                if width==390:
                    # 当前迷你底栏仅保留播放与队列，音量在桌面已验证。
                    assert page.locator('.mini-play-toggle').is_visible()
            page.set_viewport_size({'width':1440,'height':1000})
            if not args.controlled:page.screenshot(path=str(screenshots/'queue-real-playing-footer.png'))
            if args.controlled:
                # 顺序末尾真正ended后停止，不发新open。
                queue(page)
                last=page.locator('.queue-list article').nth(2)
                if last.get_attribute('data-current')!='true' or page.locator('audio').evaluate('a=>a.paused'):
                    last.locator('.queue-choose').click()
                ready(page,titles[2]);page.keyboard.press('Escape')
                count=len(requests);ends=page.evaluate('naturalEnds');seek_end(page)
                page.wait_for_function('n=>naturalEnds>n',arg=ends);page.wait_for_timeout(250)
                assert len(requests)==count and page.locator('audio').evaluate('a=>a.ended')
                mode(page,'列表循环');page.get_by_role('button',name='播放',exact=True).click();seek_end(page);ready(page,titles[0])
                # 单曲循环复用已有会话；自然结束事件来自真实解码器。
                mode(page,'单曲循环');count=len(requests);ends=page.evaluate('naturalEnds');seek_end(page)
                page.wait_for_function('n=>naturalEnds>n',arg=ends);ready(page,titles[0]);assert len(requests)==count
                mode(page,'随机播放');page.get_by_role('button',name='下一首',exact=True).click();ready(page);shuffled=page.locator('.track-title').inner_text();assert shuffled!=titles[0]
                page.get_by_role('button',name='上一首',exact=True).click();ready(page,titles[0])
                mode(page,'顺序播放')
                # B的open挂起，用户继续next到C；旧B晚到不得改变UI或泄漏Lease。
                upstream.hold_next=True;page.get_by_role('button',name='下一首',exact=True).click()
                for _ in range(100):
                    if upstream.held:break
                    page.wait_for_timeout(20)
                assert upstream.held
                page.get_by_role('button',name='下一首',exact=True).click();ready(page,titles[2]);upstream.held.clear();page.wait_for_timeout(700)
                assert titles[2] in page.locator('.track-title').inner_text()
                assert sum(l.state=='active' for l in app.state.playback_leases.entries.values())==1
                # 媒体error不应触发队列下一首，仍由RecoveryPlayer处理。
                page.evaluate("firstAudio.dispatchEvent(new Event('error'))");page.wait_for_timeout(200)
                page.wait_for_function("!['opening','positioning'].includes(document.querySelector('.player').dataset.phase)")
                assert titles[2] in page.locator('.track-title').inner_text()
            # 收敛后的界面逐个移除待播，验证保留当前曲与刷新仅恢复安全展示。
            queue(page)
            while page.locator('.queue-list article[data-current=false] .queue-remove').count():
                page.locator('.queue-list article[data-current=false] .queue-remove').first.click()
            assert page.locator('.queue-list article').count()==1
            assert page.locator('audio').evaluate('a=>a===window.firstAudio')
            page.keyboard.press('Escape')
            count=len(requests);page.reload();page.wait_for_load_state('networkidle');page.wait_for_timeout(700)
            closed=[page.request.head(url+s['streamUrl']).status for s in opened];assert all(status==410 for status in closed),closed
            assert len(requests)==count
            queue(page);assert page.locator('.queue-list article').count()==1;page.keyboard.press('Escape')
            assert page.locator('audio').evaluate('a=>a.paused&&!a.getAttribute("src")')
            queue(page);page.locator('.queue-list article button[aria-label^="移除 "]').click();assert page.locator('.queue-list article').count()==0
            page.keyboard.press('Escape');assert len(requests)==count
            assert not errors,errors
            if app:assert not app.state.media_store.records and not any(l.state=='active' for l in app.state.playback_leases.entries.values())
            result={'controlled':args.controlled,'titles':titles,'ids':ids,'opens':len(opened),'allClosed410':closed,'noAutoOpenAfterReload':True,'singleAudio':True,'naturalModes':args.controlled,'pageErrors':errors,'consoleErrors':console}
            (OUT/('queue-controlled-result.json' if args.controlled else 'queue-real-result.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps(result,ensure_ascii=False));browser.close()
    finally:
        if server:server.should_exit=True;thread.join(10)
        if vite:subprocess.run(['taskkill','/PID',str(vite.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)

if __name__=='__main__':main()
