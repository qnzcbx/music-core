"""40-D.3 真实沉浸播放器及受控歌词、清空竞争验收。"""
import argparse
import asyncio
import json
import io
import os
import subprocess
import threading
import time
import wave
from types import SimpleNamespace
import httpx
import uvicorn
from playwright.sync_api import sync_playwright
from verify_vue_player import ROOT,FaultUpstream,allow_fixture_target
from app.main import create_app
from app.models import SearchPage,SongCandidate,TrackIdentity
from app.lyrics import LyricDocument,LyricLine
from app.core.media_store import MediaSettings

OUT=ROOT/'docs/migration/40-D-3'

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--controlled',action='store_true');args=parser.parse_args()
    url='http://127.0.0.1:5174';server=None;vite=None;thread=None;app=None;upstream=None
    held_lyrics=set()
    if args.controlled:
        upstream=FaultUpstream()
        output=io.BytesIO()
        with wave.open(output,'wb') as audio:
            audio.setparams((1,2,8000,0,'NONE','not compressed'));audio.writeframes(upstream.audio[44:]*4)
        upstream.audio=output.getvalue()
        async def resolve(identity,options=None):return await upstream.resolve(identity)
        async def search(*args):return SearchPage(items=tuple(SongCandidate(identity=TrackIdentity(providerId='kuwo',platformId=str(i)),title=f'人工歌曲{i}',artists=('人工',)) for i in range(1,31)))
        async def lyrics(identity):
            while identity.platformId in held_lyrics:await asyncio.sleep(.01)
            if identity.platformId=='4':return LyricDocument(identity=identity,status='plain',plainText='人工纯文本\n第二段')
            if identity.platformId=='5':return LyricDocument(identity=identity,status='instrumental')
            if identity.platformId=='6':return LyricDocument(identity=identity,status='unavailable')
            return LyricDocument(identity=identity,status='synced',lines=tuple(LyricLine(startMs=i*1000,endMs=(i+1)*1000,text=f'人工{identity.platformId}第{i}行',translation=f'译文{i}') for i in range(48)))
        app=create_app(transport=httpx.MockTransport(upstream.handle),target_check=allow_fixture_target,media_settings=MediaSettings(media_ttl=.3,lease_ttl=30,sweep_interval=.1))
        server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=8002,log_level='critical',access_log=False))
        thread=threading.Thread(target=server.run,daemon=True);thread.start()
        for _ in range(100):
            if server.started or not thread.is_alive():break
            time.sleep(.05)
        if not server.started:raise RuntimeError('受控8002未启动，验收脚本需串行运行')
        app.state.kuwo=SimpleNamespace(resolve=resolve,search=search,get_lyrics=lyrics)
        vite=subprocess.Popen(['cmd','/c','pnpm dev --port 5175'],cwd=ROOT/'web',env={**os.environ,'MUSIC_CORE_API_TARGET':'http://127.0.0.1:8002'},stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        url='http://127.0.0.1:5175'
        for _ in range(100):
            try:
                if httpx.get(url).status_code==200:break
            except httpx.HTTPError:pass
            time.sleep(.1)
    screenshots=OUT/'screenshots';screenshots.mkdir(parents=True,exist_ok=True)
    try:
        with sync_playwright() as pw:
            browser=pw.chromium.launch(headless=True,executable_path='C:/Users/86151/AppData/Local/ms-playwright/chromium-1243/chrome-win64/chrome.exe',args=['--autoplay-policy=no-user-gesture-required'])
            page=browser.new_page(viewport={'width':1440,'height':1000},has_touch=True)
            errors=[];console=[];opened=[];lyric_requests=[];renew=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.on('console',lambda m:console.append(m.text) if m.type=='error' else None)
            page.on('response',lambda r:opened.append(r.json()) if r.url.endswith('/api/playback/open') and r.status==200 else None)
            page.on('response',lambda r:renew.append(r.status) if r.url.endswith('/renew') else None)
            page.on('request',lambda r:lyric_requests.append(r.url.split('?')[-1]) if '/api/lyrics?' in r.url else None)
            page.goto(url);page.wait_for_load_state('networkidle')
            page.locator('#query').fill('人工' if args.controlled else '银临');page.locator('#query').press('Enter')
            mid='1' if args.controlled else '7075956'
            row=page.locator(f'.song-row[data-provider="kuwo"][data-platform-id="{mid}"]').first
            row.locator('.action-play').click(timeout=30000)
            page.wait_for_function("document.querySelector('audio').currentTime>1",timeout=45000)
            page.evaluate('window.firstAudio=document.querySelector("audio")')
            page.get_by_role('button',name='打开沉浸式播放器',exact=True).click()
            room=page.get_by_role('region',name='沉浸式播放器',exact=True)
            room.wait_for();page.locator('.lyric-line').first.wait_for(timeout=30000);page.wait_for_timeout(900)
            assert page.locator('[data-audio-host] audio').count()==1 and page.locator('audio').count()==1
            assert page.locator('.workspace-player').is_hidden()
            controls=room.locator('.player')
            def screenshot(name):
                if not args.controlled:page.screenshot(path=str(screenshots/name))
            def seek(value):
                controls.get_by_label('播放进度',exact=True).evaluate('(el,value)=>{el.value=String(value);el.dispatchEvent(new Event("change",{bubbles:true}));}',value)
                page.wait_for_function('target=>Math.abs(firstAudio.currentTime-target)<1&&!firstAudio.seeking',arg=value)
            def sync_line():
                page.wait_for_function("()=>{const a=document.querySelector('audio');const rows=[...document.querySelectorAll('.lyric-line')];const active=document.querySelector('.lyric-current .lyric-line');const eligible=rows.filter(r=>Number(r.dataset.time)<=a.currentTime);return active&&eligible.length&&Number(active.dataset.time)===Number(eligible.at(-1).dataset.time)}")
            seek(12 if args.controlled else 50);sync_line()
            controls.get_by_role('button',name='暂停',exact=True).click();active=page.locator('.lyric-current').inner_text();page.wait_for_timeout(600);assert page.locator('.lyric-current').inner_text()==active
            for value in ((5,24,11) if args.controlled else (70,140,100)):seek(value)
            sync_line();controls.get_by_role('button',name='播放',exact=True).click()
            before=page.locator('audio').evaluate('a=>a.currentTime');page.wait_for_timeout(1200);assert page.locator('audio').evaluate('a=>a.currentTime')>before+.5
            if args.controlled:assert page.locator('.lyric-current .lyric-translation').inner_text().startswith('译文')
            lyric_count=len(lyric_requests);open_count=len(opened)
            def layout(name):
                room.get_by_label('播放器样式',exact=True).click();room.get_by_role('button',name=name,exact=True).click();page.wait_for_timeout(700)
            def align(name):
                room.get_by_label('播放器样式',exact=True).click();room.get_by_role('radio',name=name,exact=True).check();page.keyboard.press('Escape');page.wait_for_timeout(100)
            for template,name in [('classic','经典唱片机'),('vinyl-wide','沉浸大唱片'),('square-cover','方形封面'),('lyrics-only','纯净歌词')]:
                layout(name);assert room.get_attribute('data-player-layout')==template
                assert page.locator('audio').evaluate('a=>a===firstAudio&&!a.paused')
                assert page.locator('audio').count()==1
                if template!='lyrics-only':
                    align('居左');assert page.locator('.lyric-line').first.evaluate('el=>getComputedStyle(el).textAlign')=='left';screenshot(f'{template}-left.png')
                    align('居中');assert page.locator('.lyric-line').first.evaluate('el=>getComputedStyle(el).textAlign')=='center'
                screenshot(f'template-{template}.png')
            assert len(opened)==open_count and len(lyric_requests)==lyric_count
            # 人工滚动暂停，程序居中保持跟随；恢复按钮和定时恢复均有效。
            scroll=page.get_by_label('可滚动歌词',exact=True);scroll.hover();page.mouse.wheel(0,200);page.get_by_role('button',name='立即恢复',exact=True).wait_for()
            page.get_by_role('button',name='立即恢复',exact=True).click();assert page.get_by_role('button',name='立即恢复',exact=True).count()==0
            scroll.focus();scroll.press('PageUp');page.get_by_role('button',name='立即恢复',exact=True).wait_for();page.wait_for_timeout(3400);assert page.get_by_role('button',name='立即恢复',exact=True).count()==0
            layout('经典唱片机')
            for width in (768,390):
                page.set_viewport_size({'width':width,'height':1000 if width==768 else 844});page.wait_for_timeout(200)
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                current=page.locator('.lyric-current').bounding_box();assert current and current['y']<page.locator('.immersive-controls').bounding_box()['y']
                if width==390:screenshot('mobile-immersive-lyrics.png')
            page.set_viewport_size({'width':1440,'height':1000})
            # 本地主题切换不改变媒体，降低动态效果也不暂停音频。
            room.get_by_label('外观设置',exact=True).click();room.get_by_role('radio',name='深色',exact=False).check();page.keyboard.press('Escape');screenshot('immersive-dark.png')
            room.get_by_label('外观设置',exact=True).click();room.get_by_role('radio',name='跟随系统',exact=False).check();page.keyboard.press('Escape')
            page.emulate_media(color_scheme='dark');page.wait_for_function("document.documentElement.dataset.theme==='dark'")
            page.emulate_media(color_scheme='light');page.wait_for_function("document.documentElement.dataset.theme==='light'")
            page.emulate_media(reduced_motion='reduce');assert page.locator('audio').evaluate('a=>!a.paused');page.emulate_media(reduced_motion='no-preference')
            assert len(opened)==open_count and len(lyric_requests)==lyric_count
            room.get_by_role('button',name='收起歌曲详情页',exact=True).click();page.wait_for_url('**/search?*');page.wait_for_timeout(800)
            assert page.locator('audio').evaluate('a=>a===firstAudio&&!a.paused')
            assert page.locator('.immersive-player').count()==0 and page.locator('.shared-cover-flight').count()==0
            # 固定面板在同窗口下0/1/多曲保持一致，列表独立滚动。
            page.get_by_role('button',name='播放队列',exact=True).click();panel=page.locator('.queue-panel');height=panel.bounding_box()['height'];assert panel.bounding_box()['y']>=0
            mode_button=page.locator('.queue-actions button').first
            for label in ('列表循环','单曲循环','随机播放','顺序播放'):
                mode_button.click();assert label in mode_button.get_attribute('aria-label')
                assert page.locator('.workspace-player button[aria-label="播放模式"]').get_attribute('title')==label
            page.keyboard.press('Escape')
            page.set_viewport_size({'width':390,'height':844});page.get_by_role('button',name='播放队列',exact=True).click();mobile_one_height=page.locator('.queue-drawer').bounding_box()['height'];page.keyboard.press('Escape');page.set_viewport_size({'width':1440,'height':1000})
            rows=page.locator('.song-row[data-provider="kuwo"]')
            for index in range(30 if args.controlled else 3):
                candidate=rows.nth(index);candidate.hover();candidate.locator('.action-play-next').click();page.get_by_role('menuitem',name='添加到播放队列',exact=True).click()
            page.get_by_role('button',name='播放队列',exact=True).click();assert abs(panel.bounding_box()['height']-height)<1
            header_y=page.locator('.queue-header').bounding_box()['y']
            content=page.locator('.queue-content');content.evaluate('el=>el.scrollTop=el.scrollHeight')
            assert page.locator('.queue-header').bounding_box()['y']==header_y
            if args.controlled:assert content.evaluate('el=>el.scrollTop>0&&el.scrollHeight>el.clientHeight')
            screenshot('desktop-queue-fixed.png');page.keyboard.press('Escape')
            page.set_viewport_size({'width':1440,'height':500});page.get_by_role('button',name='播放队列',exact=True).click();small=page.locator('.queue-panel').bounding_box();assert small['y']>=0 and small['height']<=280;page.mouse.click(200,120);assert page.locator('.queue-panel').count()==0;page.set_viewport_size({'width':1440,'height':1000})
            if args.controlled:
                # 媒体重开时只保留当前稳定身份歌词，不发新歌词请求。
                count=len(opened);lyric_count=len(lyric_requests)
                page.evaluate("async id=>fetch('/api/playback/'+id+'/close',{method:'POST'})",opened[-1]['playbackId'])
                page.wait_for_function("document.querySelector('.player').dataset.phase==='ready'")
                for _ in range(220):
                    if len(opened)>count:break
                    page.wait_for_timeout(100)
                assert len(opened)==count+1 and len(lyric_requests)==lyric_count,{'before':count,'after':len(opened),'lyricsBefore':lyric_count,'lyricsAfter':len(lyric_requests),'renew':renew,'phase':page.locator('.player').get_attribute('data-phase')}
                # B媒体和歌词挂起，C先就绪，晚到B不能覆盖。
                held_lyrics.add('2');upstream.hold_next=True
                page.locator('.song-row[data-platform-id="2"] .action-play').click()
                for _ in range(100):
                    if upstream.held:break
                    page.wait_for_timeout(20)
                page.locator('.song-row[data-platform-id="3"] .action-play').click();page.wait_for_function("document.querySelector('audio').currentTime>.1")
                upstream.held.clear();held_lyrics.clear();page.wait_for_timeout(700)
                assert '人工歌曲3' in page.locator('.track-title').inner_text()
                page.get_by_role('button',name='打开沉浸式播放器',exact=True).click();page.locator('.lyric-line').first.wait_for();assert '人工3' in page.locator('.lyric-line').first.inner_text()
                page.get_by_role('button',name='收起歌曲详情页',exact=True).click();page.wait_for_timeout(800)
            for width in (390,):
                page.set_viewport_size({'width':width,'height':844});page.get_by_role('button',name='播放队列',exact=True).click();drawer=page.locator('.queue-drawer');drawer.wait_for();mobile_height=drawer.bounding_box()['height'];assert abs(mobile_height-mobile_one_height)<1;screenshot('mobile-queue-fixed.png')
                cdp=page.context.new_cdp_session(page)
                def swipe(x,y,dy):
                    cdp.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[{'x':x,'y':y}]})
                    for i in range(1,9):
                        cdp.send('Input.dispatchTouchEvent',{'type':'touchMove','touchPoints':[{'x':x,'y':y+dy*i/8}]});page.wait_for_timeout(25)
                    cdp.send('Input.dispatchTouchEvent',{'type':'touchEnd','touchPoints':[]});page.wait_for_timeout(600)
                box=page.locator('.queue-content').bounding_box();swipe(180,box['y']+200,-150);assert drawer.is_visible()
                handle=page.locator('[data-slot=drawer-handle]').bounding_box();assert handle and handle['height']>0
                swipe(195,handle['y']+2,400);assert page.locator('.queue-drawer').count()==0
                page.get_by_role('button',name='播放队列',exact=True).click();page.wait_for_timeout(600);page.touchscreen.tap(195,100);page.locator('.queue-drawer').wait_for(state='hidden')
                page.get_by_role('button',name='播放队列',exact=True).click()
                page.get_by_role('button',name='清空队列',exact=True).click();page.get_by_text('空空如也',exact=True).wait_for();assert abs(drawer.bounding_box()['height']-mobile_height)<1;screenshot('mobile-queue-empty.png')
                assert page.locator('audio').evaluate('a=>a.paused&&!a.getAttribute("src")');page.keyboard.press('Escape')
            page.set_viewport_size({'width':1440,'height':1000});page.get_by_role('button',name='播放队列',exact=True).click();assert abs(panel.bounding_box()['height']-height)<1;screenshot('desktop-queue-empty.png');page.keyboard.press('Escape')
            if args.controlled:
                upstream.hold_next=True;page.locator('.song-row[data-platform-id="4"] .action-play').click()
                for _ in range(100):
                    if upstream.held:break
                    page.wait_for_timeout(20)
                page.get_by_role('button',name='播放队列',exact=True).click();page.get_by_role('button',name='清空队列',exact=True).click();upstream.held.clear();page.wait_for_timeout(700)
                assert page.locator('audio').evaluate('a=>a.paused&&!a.getAttribute("src")') and page.locator('.queue-list article').count()==0
                page.keyboard.press('Escape')
                # 纯文本、纯音乐、无歌词和网络失败各自展示，音频仍继续。
                for pid,expected in [('4','人工纯文本'),('5','纯音乐'),('6','暂无歌词'),('7','歌词加载失败')]:
                    if pid=='7':page.route('**/api/lyrics?*',lambda route:route.fulfill(status=503,json={'error':{'message':'受控歌词网络失败'}}))
                    page.locator(f'.song-row[data-platform-id="{pid}"] .action-play').click();page.wait_for_function('document.querySelector("audio").currentTime>.1')
                    page.get_by_role('button',name='打开沉浸式播放器',exact=True).click();page.locator('#lyric-panel').get_by_text(expected,exact=False).wait_for()
                    assert page.locator('audio').evaluate('a=>!a.paused')
                    page.get_by_role('button',name='收起歌曲详情页',exact=True).click();page.wait_for_timeout(800)
                # 恢复过程中清空，晚到恢复Lease同样必须回收。
                upstream.hold_next=True;page.get_by_role('button',name='重试播放',exact=True).click()
                for _ in range(100):
                    if upstream.held:break
                    page.wait_for_timeout(20)
                assert upstream.held
                page.get_by_role('button',name='播放队列',exact=True).click();page.get_by_role('button',name='清空队列',exact=True).click();upstream.held.clear();page.keyboard.press('Escape')
            page.wait_for_timeout(700)
            statuses=[page.request.head(url+s['streamUrl']).status for s in opened];assert all(s==410 for s in statuses),statuses
            assert not errors,errors
            if app:assert not app.state.media_store.records and not any(l.state=='active' for l in app.state.playback_leases.entries.values())
            stored=page.evaluate("JSON.parse(localStorage.getItem('music-core.queue.v1'))");assert stored['queue']==[] and stored['currentQueueKey'] is None
            count=len(opened);lyric_count=len(lyric_requests)
            page.goto(url+'/player');page.wait_for_load_state('networkidle');page.get_by_text('还没有正在播放的歌曲',exact=True).wait_for()
            layout('方形封面');align('居左');page.reload();page.wait_for_load_state('networkidle')
            assert room.get_attribute('data-player-layout')=='square-cover' and room.get_attribute('data-lyric-alignment')=='left'
            assert len(opened)==count and len(lyric_requests)==lyric_count and page.locator('audio').count()==1
            result={'controlled':args.controlled,'opens':len(opened),'lyricsRequests':len(lyric_requests),'renewStatuses':renew,'closedStatuses':statuses,'desktopHeight':height,'mobileHeight':mobile_height,'pageErrors':errors,'consoleErrors':console,'singleRootAudio':True,'templatesNoOpen':True,'sameIdentityLyricsRetained':True}
            (OUT/('controlled-result.json' if args.controlled else 'real-result.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result));browser.close()
    finally:
        if server:server.should_exit=True;thread.join(10)
        if vite:subprocess.run(['taskkill','/PID',str(vite.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)

if __name__=='__main__':main()
