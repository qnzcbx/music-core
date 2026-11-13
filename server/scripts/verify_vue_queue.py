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

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--controlled',action='store_true');parser.add_argument('--resume',action='store_true');parser.add_argument('--url',default=os.environ.get('MUSIC_CORE_WEB_URL','http://127.0.0.1:5174'),help='未启动受控客户端时使用的 Vue 地址');args=parser.parse_args()
    server=None;vite=None;thread=None;app=None;upstream=None;url=args.url.rstrip('/')
    if args.controlled:
        upstream=FaultUpstream()
        output=io.BytesIO()
        with wave.open(output,'wb') as audio:
            audio.setparams((1,2,8000,0,'NONE','not compressed'));audio.writeframes(upstream.audio[44:44+8000*2*8])
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
        vite=subprocess.Popen(['cmd','/c',f'pnpm dev --host 127.0.0.1 --port {web_port} --strictPort'],cwd=ROOT/'web',env={**os.environ,'MUSIC_CORE_API_TARGET':f'http://127.0.0.1:{api_port}'},stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        url=f'http://127.0.0.1:{web_port}'
        for _ in range(100):
            try:
                if httpx.get(url).status_code==200:break
            except httpx.HTTPError:pass
            time.sleep(.1)
    screenshots=OUT/'screenshots';screenshots.mkdir(parents=True,exist_ok=True)
    try:
        with sync_playwright() as pw:
            browser=pw.chromium.launch(headless=True,executable_path=os.environ.get('CHROMIUM_PATH'),args=['--autoplay-policy=no-user-gesture-required'])
            page=browser.new_page(viewport={'width':1440,'height':1000},has_touch=True);errors=[];console=[];opened=[];requests=[]
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
