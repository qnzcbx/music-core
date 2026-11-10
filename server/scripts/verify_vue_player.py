"""新Vue真实播放及受控过期恢复验收，不保存上游地址。"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import threading
import time
from types import SimpleNamespace
import httpx
import uvicorn
from playwright.sync_api import sync_playwright
from app.main import create_app
from app.models import SearchPage,SongCandidate,TrackIdentity
from app.core.media_store import MediaSettings
from recovery_fixture import FaultUpstream,allow_fixture_target

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'docs/migration/40-D-1/screenshots'


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--controlled',action='store_true');args=parser.parse_args()
    server=None;vite=None;thread=None;upstream=None
    url='http://127.0.0.1:5174';mid='9942644';query='银临'
    if args.controlled:
        upstream=FaultUpstream()
        async def resolve(identity,options=None):return await upstream.resolve(identity)
        async def search(*args):return SearchPage(items=tuple(SongCandidate(identity=TrackIdentity(providerId='kuwo',platformId=str(i)),title=f'人工测试{i}',artists=('人工',)) for i in (1,2)))
        app=create_app(transport=httpx.MockTransport(upstream.handle),target_check=allow_fixture_target,media_settings=MediaSettings(media_ttl=.3,lease_ttl=30,sweep_interval=.1))
        server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=8002,log_level='critical',access_log=False))
        thread=threading.Thread(target=server.run,daemon=True);thread.start()
        for _ in range(100):
            if server.started or not thread.is_alive():break
            time.sleep(.05)
        if not server.started:raise RuntimeError('受控服务8002启动失败；两个受控验收脚本应串行运行')
        app.state.kuwo=SimpleNamespace(resolve=resolve,search=search)
        vite=subprocess.Popen(['cmd','/c','pnpm dev --port 5175'],cwd=ROOT/'web',env={**os.environ,'MUSIC_CORE_API_TARGET':'http://127.0.0.1:8002'},stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        url='http://127.0.0.1:5175';mid='1';query='人工'
        for _ in range(100):
            try:
                if httpx.get(url).status_code==200:break
            except httpx.HTTPError:pass
            time.sleep(.1)
    OUT.mkdir(parents=True,exist_ok=True)
    try:
        with sync_playwright() as pw:
            browser=pw.chromium.launch(headless=True,executable_path='C:/Users/86151/AppData/Local/ms-playwright/chromium-1243/chrome-win64/chrome.exe',args=['--autoplay-policy=no-user-gesture-required'])
            page=browser.new_page(viewport={'width':1440,'height':1000});errors=[];opened=[];renew_status=[];console_errors=[];failed=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.on('console',lambda m:console_errors.append(m.text) if m.type=='error' else None)
            page.on('requestfailed',lambda r:failed.append(r.failure))
            page.on('response',lambda r:opened.append(r.json()) if r.url.endswith('/api/playback/open') and r.status==200 else None)
            page.on('response',lambda r:renew_status.append(r.status) if r.url.endswith('/renew') else None)
            page.goto(url);page.wait_for_load_state('networkidle')
            page.locator('#query').fill(query);page.locator('#query').press('Enter')
            row=page.locator(f'.song-row[data-platform-id="{mid}"]').first
            row.locator('.action-play').click(timeout=30000)
            page.wait_for_function("document.querySelector('audio')?.currentTime>2",timeout=30000)
            page.evaluate("window.firstAudio=document.querySelector('audio')")
            assert page.locator('audio').count()==1
            if not args.controlled:page.screenshot(path=str(OUT/'desktop-search-playing.png'))
            page.get_by_role('button',name='暂停',exact=True).click();before=page.locator('audio').evaluate('a=>a.currentTime');page.wait_for_timeout(600)
            assert abs(page.locator('audio').evaluate('a=>a.currentTime')-before)<.1
            page.get_by_role('button',name='播放',exact=True).click()
            page.get_by_role('button',name='音量设置',exact=True).click()
            page.locator('.volume-layer [role=slider]').press('Home')
            for _ in range(30):page.locator('.volume-layer [role=slider]').press('ArrowUp')
            page.get_by_role('button',name='静音',exact=True).click()
            page.keyboard.press('Escape')
            snapshot=page.locator('audio').evaluate('a=>({volume:a.volume,muted:a.muted})');assert snapshot=={'volume':.3,'muted':True},snapshot
            for ratio in (.5,.94):
                duration=page.locator('audio').evaluate('a=>a.duration');target=duration*ratio
                slider=page.get_by_label('播放进度',exact=True);slider.evaluate('(el,value)=>{el.value=String(value);el.dispatchEvent(new Event("input",{bubbles:true}));el.dispatchEvent(new Event("change",{bubbles:true}));}',target)
                page.wait_for_function("target=>{const a=document.querySelector('audio');return !a.seeking&&Math.abs(a.currentTime-target)<2}",arg=target)
            for path in ('/','/settings','/search'):
                page.evaluate("path=>history.pushState({},'',path)",path);page.evaluate("dispatchEvent(new PopStateEvent('popstate'))")
                page.wait_for_timeout(150)
                assert page.locator('audio').evaluate('a=>a===window.firstAudio&&!a.paused')
                if path=='/' and not args.controlled:page.screenshot(path=str(OUT/'desktop-home-playing.png'))
            if args.controlled:
                for _ in range(250):
                    if 204 in renew_status:break
                    page.wait_for_timeout(100)
                assert 204 in renew_status, {'renew':renew_status,'opened':len(opened),'fixtureOpens':len(upstream.opens),'leases':[(l.state,round(l.expires_at-app.state.media_store.clock(),2)) for l in app.state.playback_leases.entries.values()],'phase':page.locator('.player').get_attribute('data-phase')}
                # 主动关闭当前租约，下次定时renew触发真实410并自动重开。
                count=len(opened);old=opened[-1]['playbackId']
                page.evaluate("async id=>fetch('/api/playback/'+id+'/close',{method:'POST'})",old)
                for _ in range(200):
                    if len(opened)>count:break
                    page.wait_for_timeout(100)
                assert len(opened)==count+1, {'before':count,'after':len(opened),'phase':page.locator('.player').get_attribute('data-phase'),'fixtureOpens':len(upstream.opens),'leases':[l.state for l in app.state.playback_leases.entries.values()]}
                page.wait_for_function("document.querySelector('.player').dataset.phase==='ready'")
                assert page.locator('audio').evaluate('a=>a===window.firstAudio&&a.volume===.3&&a.muted')
                upstream.hold_next=True
                page.locator('.song-row[data-platform-id="2"] .action-play').click()
                for _ in range(50):
                    if upstream.held:break
                    page.wait_for_timeout(50)
                assert upstream.held
                page.locator('.song-row[data-platform-id="1"] .action-play').click()
                page.wait_for_function("document.querySelector('.player').dataset.phase==='ready'")
                upstream.held.clear();page.wait_for_timeout(400)
                assert '人工测试1' in page.locator('.player .track-title').inner_text()
                assert sum(l.state=='active' for l in app.state.playback_leases.entries.values())==1
                page.route('**/api/playback/open',lambda route:route.fulfill(status=503,json={'error':{'message':'人工受控失败'}}))
                page.get_by_role('button',name='重试播放').click()
                page.wait_for_function("document.querySelector('.player').dataset.phase==='error'")
                page.screenshot(path=str(OUT/'controlled-error.png'))
            else:
                page.set_viewport_size({'width':390,'height':844});page.screenshot(path=str(OUT/'mobile-player.png'))
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            page.get_by_role('button',name='关闭播放').click();page.wait_for_timeout(700)
            assert not page.locator('audio').get_attribute('src')
            closed_status=[page.request.head(url+session['streamUrl']).status for session in opened]
            assert all(status==410 for status in closed_status),closed_status
            assert not errors,errors
            if args.controlled:assert not app.state.media_store.records and not any(l.state=='active' for l in app.state.playback_leases.entries.values())
            print(json.dumps({'controlled':args.controlled,'opened':len(opened),'pause':True,'seek':True,'volumeMute':snapshot,'renewStatuses':renew_status,'closedStatuses':closed_status,'routeContinuity':True,'singleAudio':True,'errors':errors,'consoleErrors':console_errors,'failedRequestReasons':failed}))
            browser.close()
    finally:
        if server:server.should_exit=True;thread.join(10)
        if vite:subprocess.run(['taskkill','/PID',str(vite.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)


if __name__=='__main__':main()
