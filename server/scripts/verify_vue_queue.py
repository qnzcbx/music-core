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
from types import SimpleNamespace
import httpx
import uvicorn
from playwright.sync_api import sync_playwright
from verify_vue_player import ROOT,FaultUpstream,allow_fixture_target
from app.main import create_app
from app.models import SearchPage,SongCandidate,TrackIdentity
from app.core.media_store import MediaSettings
from app.lyrics import LyricDocument

OUT=Path(os.environ.get('MUSIC_CORE_VERIFY_OUT',ROOT/'docs/archive/14-播放器与歌词/screenshots'))

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

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--controlled',action='store_true');args=parser.parse_args()
    server=None;vite=None;thread=None;app=None;upstream=None;url='http://127.0.0.1:5174'
    if args.controlled:
        upstream=FaultUpstream()
        output=io.BytesIO()
        with wave.open(output,'wb') as audio:
            audio.setparams((1,2,8000,0,'NONE','not compressed'));audio.writeframes(upstream.audio[44:44+8000*2*8])
        upstream.audio=output.getvalue()
        async def resolve(identity,options=None):return await upstream.resolve(identity)
        async def search(*args):return SearchPage(items=tuple(SongCandidate(identity=TrackIdentity(providerId='kuwo',platformId=str(i)),title=f'人工测试{i}',artists=('人工',)) for i in (1,2,3)))
        async def get_lyrics(identity):return LyricDocument(identity=identity,status='unavailable')
        app=create_app(transport=httpx.MockTransport(upstream.handle),target_check=allow_fixture_target,media_settings=MediaSettings(media_ttl=.3,lease_ttl=30,sweep_interval=.1))
        server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=8002,log_level='critical',access_log=False))
        thread=threading.Thread(target=server.run,daemon=True);thread.start()
        for _ in range(100):
            if server.started or not thread.is_alive():break
            time.sleep(.05)
        if not server.started:raise RuntimeError('受控服务8002启动失败；两个受控验收脚本应串行运行')
        app.state.kuwo=SimpleNamespace(resolve=resolve,search=search,get_lyrics=get_lyrics)
        vite=subprocess.Popen(['cmd','/c','pnpm dev --port 5175'],cwd=ROOT/'web',env={**os.environ,'MUSIC_CORE_API_TARGET':'http://127.0.0.1:8002'},stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        url='http://127.0.0.1:5175'
        for _ in range(100):
            try:
                if httpx.get(url).status_code==200:break
            except httpx.HTTPError:pass
            time.sleep(.1)
    OUT.mkdir(parents=True,exist_ok=True)
    try:
        with sync_playwright() as pw:
            browser=pw.chromium.launch(headless=True,executable_path='C:/Users/86151/AppData/Local/ms-playwright/chromium-1243/chrome-win64/chrome.exe',args=['--autoplay-policy=no-user-gesture-required'])
            page=browser.new_page(viewport={'width':1440,'height':1000},has_touch=True);errors=[];console=[];opened=[];requests=[]
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
            if not args.controlled:page.screenshot(path=str(OUT/'queue-desktop-queue.png'))
            page.locator('.queue-choose').nth(1).click();ready(page,titles[1]);page.keyboard.press('Escape')
            page.get_by_role('button',name='上一首',exact=True).click();ready(page,titles[0])
            page.get_by_role('button',name='下一首',exact=True).click();ready(page,titles[1])
            count=len(requests)
            for label in ('随机播放','单曲循环','列表循环','顺序播放'):mode(page,label)
            assert len(requests)==count
            page.get_by_role('button',name='播放模式',exact=True).click()
            if not args.controlled:page.screenshot(path=str(OUT/'queue-playback-mode-menu.png'))
            page.keyboard.press('Escape');assert page.get_by_role('button',name='播放模式',exact=True).evaluate('el=>el===document.activeElement')
            page.get_by_role('button',name='音量设置',exact=True).click();slider=page.locator('.volume-layer [role=slider]');slider.press('Home')
            for _ in range(30):slider.press('ArrowUp')
            page.get_by_role('button',name='静音',exact=True).click();assert page.locator('audio').evaluate('a=>a.muted&&a.volume===.3')
            slider.press('ArrowUp');assert page.locator('audio').evaluate('a=>!a.muted&&a.volume===.31')
            if not args.controlled:page.screenshot(path=str(OUT/'queue-volume-popover.png'))
            page.keyboard.press('Escape');assert page.locator('.volume-layer').count()==0
            page.get_by_role('button',name='音量设置',exact=True).click();page.locator('.track-title').click();assert page.locator('.volume-layer').count()==0
            for path in ('/','/settings','/search'):
                page.evaluate("path=>{history.pushState({},'',path);dispatchEvent(new PopStateEvent('popstate'))}",path);page.wait_for_timeout(200)
                assert page.locator('audio').evaluate('a=>a===window.firstAudio')
                if path=='/settings':
                    session=len(requests);page.get_by_role('radio',name='深色',exact=True).check();assert len(requests)==session
                    queue(page)
                    if not args.controlled:page.screenshot(path=str(OUT/'queue-desktop-dark-queue.png'))
                    page.keyboard.press('Escape');page.get_by_role('radio',name='浅色',exact=True).check()
            for width in (768,390):
                page.set_viewport_size({'width':width,'height':844});queue(page)
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                assert page.locator('audio').count()==1
                if width==390:
                    assert page.locator('.queue-drawer').is_visible()
                    if not args.controlled:page.screenshot(path=str(OUT/'queue-mobile-queue-drawer.png'))
                page.keyboard.press('Escape')
                if width==390:
                    button=page.get_by_role('button',name='音量设置',exact=True).bounding_box();page.touchscreen.tap(button['x']+button['width']/2,button['y']+button['height']/2)
                    track=page.locator('.volume-layer [data-slot=slider]').bounding_box();page.touchscreen.tap(track['x']+track['width']/2,track['y']+track['height']*.25)
                    assert page.locator('audio').evaluate('a=>a.volume>.6&&a.volume<.9&&!a.muted')
                    page.keyboard.press('Escape')
            page.set_viewport_size({'width':1440,'height':1000})
            if not args.controlled:page.screenshot(path=str(OUT/'queue-real-playing-footer.png'))
            if args.controlled:
                # 顺序末尾真正ended后停止，不发新open。
                queue(page);page.locator('.queue-choose').nth(2).click();ready(page,titles[2]);page.keyboard.press('Escape')
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
                assert titles[2] in page.locator('.track-title').inner_text()
            # 收敛后的界面逐个移除待播，验证保留当前曲与刷新仅恢复安全展示。
            queue(page)
            while page.locator('.queue-list article[data-current=false] button[aria-label]').count():
                page.locator('.queue-list article[data-current=false] button[aria-label]').first.click()
            assert page.locator('.queue-list article').count()==1
            assert page.locator('audio').evaluate('a=>a===window.firstAudio')
            page.keyboard.press('Escape')
            page.get_by_role('button',name='关闭播放',exact=True).click();page.wait_for_timeout(700)
            closed=[page.request.head(url+s['streamUrl']).status for s in opened];assert all(status==410 for status in closed),closed
            count=len(requests);page.reload();page.wait_for_load_state('networkidle');assert len(requests)==count
            queue(page);assert page.locator('.queue-list article').count()==1;page.keyboard.press('Escape')
            assert page.locator('audio').evaluate('a=>a.paused&&!a.getAttribute("src")')
            queue(page);page.locator('.queue-list article button[aria-label^="移除 "]').click();assert page.locator('.queue-list article').count()==0
            page.keyboard.press('Escape');assert len(requests)==count
            assert not errors,errors
            if app:assert not app.state.media_store.records and not any(l.state=='active' for l in app.state.playback_leases.entries.values())
            result={'controlled':args.controlled,'titles':titles,'ids':ids,'opens':len(opened),'allClosed410':closed,'noAutoOpenAfterReload':True,'singleAudio':True,'naturalModes':args.controlled,'pageErrors':errors,'consoleErrors':console}
            (OUT.parent/('queue-controlled-result.json' if args.controlled else 'queue-real-result.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps(result,ensure_ascii=False));browser.close()
    finally:
        if server:server.should_exit=True;thread.join(10)
        if vite:subprocess.run(['taskkill','/PID',str(vite.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)

if __name__=='__main__':main()
