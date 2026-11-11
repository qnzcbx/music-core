"""四来源真实封面链路验收；不替换搜索、解析或播放响应。"""
import json
import argparse
import os
from pathlib import Path
import subprocess
import threading
import time
from urllib.parse import urlsplit
import httpx
import uvicorn
from playwright.sync_api import sync_playwright
from app.main import create_app

ROOT=Path(__file__).resolve().parents[2]
CHROME='C:/Users/86151/AppData/Local/ms-playwright/chromium-1243/chrome-win64/chrome.exe'
SAMPLES=[('kuwo','银临 东风志','东风志'),('netease','齐豫 飞鸟与鱼','飞鸟与鱼'),('qq','许嵩 幻听','幻听'),('qq','许嵩 灰色头像','灰色头像'),('migu','许嵩 庐州月','庐州月'),('migu','周杰伦 我落泪情绪零碎','我落泪情绪零碎')]


def verify_overlay(page,shots):
    """使用正常网易云歌曲检查透明表面、卡片和进出行为，不注入媒体响应。"""
    events=[]
    page.on('response',lambda response:events.append(response.status) if response.url.endswith('/api/playback/open') else None)
    if page.locator('.immersive-player').count():page.locator('.collapse-player').click();page.wait_for_timeout(700)
    page.locator('a[href="/"]').first.click();page.locator('.primary-sources input[value="netease"]').check()
    for provider in ('kuwo','qq','migu'):page.locator(f'.primary-sources input[value="{provider}"]').uncheck()
    page.locator('#query').fill('齐豫 飞鸟与鱼');page.locator('#query').press('Enter')
    row=page.locator('.song-row[data-platform-id="284617"]').first
    try:row.wait_for(timeout=15000)
    except Exception:
        for button in page.locator('.versions-toggle').all():button.click()
    row.locator('.action-play').click();page.wait_for_function('!document.querySelector("audio").paused&&document.querySelector("audio").currentTime>.2',timeout=45000)
    mini=page.locator('.player-cover');page.mouse.move(10,10);page.wait_for_timeout(150)
    assert mini.locator('.cover-expand').evaluate('el=>getComputedStyle(el).opacity')=='0'
    mini.hover();page.wait_for_timeout(180);assert mini.locator('.cover-expand').evaluate('el=>getComputedStyle(el).opacity')=='1'
    assert mini.locator('.cover-expand svg').evaluate('el=>getComputedStyle(el).width')=='24px'
    page.screenshot(path=str(shots/'visual-patch-expand-hover.png'))
    page.mouse.move(10,10);mini.focus();page.keyboard.press('Tab');page.keyboard.press('Shift+Tab');page.wait_for_timeout(180)
    assert mini.locator('.cover-expand').evaluate('el=>getComputedStyle(el).opacity')=='1'
    count=len(events);before=page.locator('audio').evaluate('a=>a.currentTime');mini.click();page.locator('.immersive-player').wait_for();page.wait_for_timeout(900)
    room=page.locator('.immersive-player');controls=room.locator('.immersive-controls')
    assert page.locator('audio').evaluate('a=>a===firstAudio&&!a.paused') and len(events)==count
    assert page.locator('audio').evaluate('a=>a.currentTime')>=before
    def surfaces():
        return controls.evaluate('el=>[el,el.parentElement].flatMap(node=>[null,"::before","::after"].map(pseudo=>{const s=getComputedStyle(node,pseudo);return {pseudo,background:s.backgroundColor,image:s.backgroundImage,border:[s.borderTopWidth,s.borderRightWidth,s.borderBottomWidth,s.borderLeftWidth],shadow:s.boxShadow,blur:s.backdropFilter,content:s.content}}))')
    def transparent():
        result=surfaces()
        for item in result:
            assert item['background']=='rgba(0, 0, 0, 0)' and item['image']=='none' and item['shadow']=='none' and item['blur']=='none',item
            assert all(value=='0px' for value in item['border']),item
        return result
    def wake():page.mouse.move(10,80);page.wait_for_timeout(150)
    def idle():page.locator('.collapse-player').focus();page.mouse.move(11,81);page.wait_for_timeout(4500)
    def layout(name):
        if page.viewport_size['width']<=600:
            wake();page.locator('.collapse-player').click();page.wait_for_timeout(700)
            page.locator('a[href="/settings"]:visible').first.click();page.get_by_role('button',name=name,exact=True).click()
            page.locator('.player-cover').tap();page.wait_for_timeout(800);return
        wake();controls.get_by_label('播放器样式',exact=True).click();cards=room.locator('.layout-card');assert cards.count()==4
        for preview in room.locator('.layout-preview').all():assert preview.bounding_box()['height']>=76
        for card in cards.all():assert card.bounding_box()['height']>120
        assert room.locator('.preview-classic .preview-machine').bounding_box()['width']>30
        page.get_by_role('button',name=name,exact=True).click();page.wait_for_timeout(700)
    visible_styles=transparent();assert page.locator('.immersive-control-layer').evaluate('el=>el.getBoundingClientRect().height')==0
    original=page.locator('.ambient-active').evaluate('el=>getComputedStyle(el).backgroundImage')
    for theme in ('dark','light'):
        page.emulate_media(color_scheme=theme);page.wait_for_function('theme=>document.documentElement.dataset.theme===theme',arg=theme,timeout=5000)
        assert page.locator('.ambient-active').evaluate('el=>getComputedStyle(el).backgroundImage')==original;transparent()
    templates=[('classic','经典唱片机'),('vinyl-wide','沉浸大唱片'),('square-cover','方形封面'),('lyrics-only','纯净歌词')]
    for width in (1440,768,390):
        page.set_viewport_size({'width':width,'height':844 if width==390 else 1000});page.wait_for_timeout(200)
        for identifier,name in templates:
            layout(name);assert room.get_attribute('data-player-layout')==identifier
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth');transparent()
            assert page.locator('audio').evaluate('a=>a===firstAudio&&!a.paused') and len(events)==count
            page.screenshot(path=str(shots/f'visual-patch-{width}-{identifier}.png'))
        if width>600:
            wake();controls.get_by_label('播放器样式',exact=True).click();page.mouse.move(10,80);page.wait_for_timeout(4500)
            assert room.get_attribute('data-controls-hidden')=='false';transparent()
            panel=room.locator('.layout-panel').bounding_box();assert panel['y']>=0 and panel['y']+panel['height']<=page.viewport_size['height']
            assert room.locator('.layout-panel').evaluate('el=>getComputedStyle(el).scrollbarWidth')=='none'
            page.screenshot(path=str(shots/f'visual-patch-style-cards-{width}.png'));page.keyboard.press('Escape')
        else:
            assert controls.locator('.player-info,.player-tools,.immersive-back').count()==0
            assert controls.get_by_role('button',name='音量设置').count()==0 and controls.get_by_label('播放器样式',exact=True).count()==0
            assert controls.locator('.transport-buttons button').count()==5
            progress=controls.locator('.progress-row').bounding_box();buttons=controls.locator('.transport-buttons').bounding_box()
            assert progress['y']+progress['height']<=buttons['y']
    # 短桌面视口验证滚动条隐藏后仍可滚动。
    page.set_viewport_size({'width':1440,'height':640});wake();controls.get_by_label('播放器样式',exact=True).click()
    scroll=room.locator('.layout-panel');assert scroll.evaluate('el=>getComputedStyle(el).scrollbarWidth')=='none'
    assert scroll.evaluate('el=>getComputedStyle(el,"::-webkit-scrollbar").display')=='none'
    assert scroll.evaluate('el=>{el.scrollTop=100;return el.scrollTop}')>0
    page.screenshot(path=str(shots/'visual-patch-style-scrollbar-hidden.png'));page.keyboard.press('Escape');page.set_viewport_size({'width':1440,'height':1000})
    # 设置页与弹层使用同一组件、同一选中状态和歌词对齐偏好。
    before=page.locator('audio').evaluate('a=>a.currentTime');controls.locator('.immersive-back').click();page.wait_for_timeout(700)
    assert page.locator('audio').evaluate('a=>a===firstAudio&&!a.paused&&a.currentTime>='+str(before)) and len(events)==count
    page.locator('a[href="/settings"]:visible').first.click();page.get_by_role('button',name='纯净歌词',exact=True).wait_for()
    assert page.get_by_role('button',name='纯净歌词',exact=True).get_attribute('aria-pressed')=='true'
    page.get_by_role('button',name='经典唱片机',exact=True).click();page.get_by_role('radio',name='居左',exact=True).check()
    page.locator('.player-cover').click();page.wait_for_timeout(800);assert room.get_attribute('data-player-layout')=='classic' and room.get_attribute('data-lyric-alignment')=='left'
    # 真实暂停、Seek、音量及菜单不重开媒体。
    controls.get_by_role('button',name='暂停',exact=True).click();idle();assert room.get_attribute('data-controls-hidden')=='false'
    controls.get_by_role('slider',name='播放进度').evaluate('el=>{el.value=30;el.dispatchEvent(new Event("change",{bubbles:true}))}')
    page.wait_for_function('Math.abs(document.querySelector("audio").currentTime-30)<1')
    controls.get_by_role('button',name='播放',exact=True).click();idle();assert room.get_attribute('data-controls-hidden')=='true';hidden_styles=transparent()
    page.screenshot(path=str(shots/'visual-patch-transparent-hidden.png'));wake();assert room.get_attribute('data-controls-hidden')=='false'
    controls.get_by_role('button',name='音量设置',exact=True).click();page.mouse.move(10,80);page.wait_for_timeout(4500);assert room.get_attribute('data-controls-hidden')=='false';page.keyboard.press('Escape')
    controls.get_by_role('button',name='播放队列',exact=True).click();page.mouse.move(10,80);page.wait_for_timeout(4500);assert room.get_attribute('data-controls-hidden')=='false';page.keyboard.press('Escape')
    page.set_viewport_size({'width':390,'height':844});page.wait_for_timeout(250)
    controls.get_by_role('button',name='播放队列').tap();page.mouse.move(10,80);page.wait_for_timeout(4500);assert room.get_attribute('data-controls-hidden')=='false';page.keyboard.press('Escape')
    idle();assert room.get_attribute('data-controls-hidden')=='true';page.touchscreen.tap(10,90);page.wait_for_timeout(200);assert room.get_attribute('data-controls-hidden')=='false'
    page.emulate_media(reduced_motion='reduce');assert page.locator('.immersive-control-layer').evaluate('el=>getComputedStyle(el).transitionDuration')=='0s'
    assert len(events)==count and page.locator('audio').evaluate('a=>a===firstAudio&&!a.paused')
    page.locator('.collapse-player').click();page.wait_for_timeout(700);page.locator('.player-cover').tap();page.wait_for_timeout(700)
    assert page.locator('audio').evaluate('a=>a===firstAudio&&!a.paused') and len(events)==count
    result={'realIdentity':{'providerId':'netease','platformId':'284617'},'visibleSurfaces':visible_styles,'hiddenSurfaces':hidden_styles,'expandFocusAndHover':True,'shrinkKeepsPlayback':True,'cardsAndSettingsSync':True,'fourTemplatesThreeWidths':True,'noVisualPlaybackOpen':True,'audioUnchanged':True,'menusHoldVisible':True,'idleAndTouchWake':True,'pauseSeek':True,'mobileCompactFiveButtons':True,'mobileProgressAbove':True,'styleScrollbarHiddenAndScrollable':True}
    (ROOT/'.runtime/e1-overlay-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'overlay':result},ensure_ascii=True),flush=True)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--overlay-only',action='store_true');parser.add_argument('--mobile-retry-only',action='store_true');args=parser.parse_args()
    server=uvicorn.Server(uvicorn.Config(create_app(),host='127.0.0.1',port=8009,log_level='critical',access_log=False))
    thread=threading.Thread(target=server.run,daemon=True);thread.start()
    for _ in range(100):
        if server.started:break
        time.sleep(.05)
    assert server.started
    vite=subprocess.Popen(['cmd','/c','pnpm dev --port 5187 --strictPort'],cwd=ROOT/'web',env={**os.environ,'MUSIC_CORE_API_TARGET':'http://127.0.0.1:8009'},stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    url='http://127.0.0.1:5187';shots=ROOT/'docs/archive/17-沉浸视觉/screenshots';shots.mkdir(parents=True,exist_ok=True)
    results=[];errors=[]
    try:
        for _ in range(100):
            try:
                if httpx.get(url).status_code==200:break
            except httpx.HTTPError:pass
            time.sleep(.1)
        with sync_playwright() as pw:
            browser=pw.chromium.launch(headless=True,executable_path=CHROME,args=['--autoplay-policy=no-user-gesture-required'])
            page=browser.new_page(viewport={'width':1440,'height':1000},has_touch=True);page.on('pageerror',lambda error:errors.append(str(error)))
            playback_faults=[]
            def playback_response(response):
                if '/api/playback/' not in response.url or response.status<400 or not (response.url.endswith('/open') or '/stream' in response.url):return
                try:code=response.json().get('error',{}).get('code')
                except Exception:code=None
                playback_faults.append({'operation':'open' if response.url.endswith('/open') else 'stream','status':response.status,'code':code})
            page.on('response',playback_response)
            page.goto(url);page.wait_for_load_state('networkidle')
            page.evaluate('window.firstAudio=document.querySelector("audio")')
            for provider,query,title in ([] if args.overlay_only else [SAMPLES[2]] if args.mobile_retry_only else SAMPLES):
                response=page.request.post(url+'/api/search',data={'providerId':provider,'query':query,'limit':8})
                data=response.json();songs=data.get('items',[])
                song=next((song for song in songs if song['title']==title and song.get('cover')),None)
                if song is None:song=next((song for song in songs if title in song['title'] and song.get('cover')),None)
                if provider=='netease':song=next((item for item in songs if item['identity']['platformId']=='284617'),song)
                if not song:
                    results.append({'provider':provider,'query':query,'status':'no-cover-candidate','httpStatus':response.status});continue
                if page.locator('.immersive-player').count():page.locator('.collapse-player').click();page.wait_for_timeout(700)
                page.locator('a[href="/"]').first.click()
                page.locator(f'.primary-sources input[value="{provider}"]').check()
                for other in ('kuwo','qq','netease','migu'):
                    if other!=provider:page.locator(f'.primary-sources input[value="{other}"]').uncheck()
                page.locator('#query').fill(query);page.locator('#query').press('Enter')
                selector=f'.song-row[data-provider="{provider}"][data-platform-id="{song["identity"]["platformId"]}"]'
                row=page.locator(selector).first
                try:row.wait_for(timeout=15000)
                except Exception:
                    for button in page.locator('.versions-toggle').all():button.click()
                    row.wait_for(timeout=5000)
                selected_cover=row.locator('.cover img').first.get_attribute('src') or song['cover']
                faults_before=len(playback_faults)
                row.locator('.action-play').click()
                page.get_by_role('button',name='打开沉浸式播放器',exact=True).click();page.locator('.immersive-player').wait_for()
                try:page.wait_for_function('url=>{const data=document.querySelector(".ambient-background").dataset;return data.paletteStatus==="success"&&data.paletteKey===url}',arg=selected_cover,timeout=20000)
                except Exception:pass
                page.wait_for_timeout(1000)
                observation=page.locator('.ambient-background').evaluate('el=>({status:el.dataset.paletteStatus,via:el.dataset.paletteVia,initialFailure:el.dataset.paletteReason,evidence:el.dataset.paletteEvidence,key:el.dataset.paletteKey,colors:["--ambient-left","--ambient-center","--ambient-right"].map(name=>getComputedStyle(el.querySelector(".ambient-active")).getPropertyValue(name).trim()),background:getComputedStyle(el.querySelector(".ambient-active")).backgroundImage})')
                observation['sameCover']=observation.pop('key')==selected_cover
                observation['displayCover']=page.locator('.record-column img').first.get_attribute('src') if page.locator('.record-column img').count() else None
                observation['expectedCover']=selected_cover
                assert page.locator('audio').evaluate('(a)=>a===firstAudio')
                # 正常媒体请求可能受平台访问条件限制，照实记录，不以人工音频替换。
                try:page.wait_for_function('(!document.querySelector("audio").paused&&document.querySelector("audio").currentTime>.2)||["error","blocked","network"].includes(document.querySelector(".immersive-controls").dataset.phase)',timeout=35000)
                except Exception:pass
                page.wait_for_timeout(300);observation['playing']=page.locator('audio').evaluate('(a)=>!a.paused&&a.currentTime>0')
                observation['playbackErrors']=playback_faults[faults_before:]
                observation['phase']=page.locator('.immersive-controls').get_attribute('data-phase')
                observation['playbackMessage']=page.locator('.immersive-controls .playback-status').inner_text()
                observation.update({'provider':provider,'identity':song['identity'],'title':song['title'],'cover':selected_cover,'coverHost':urlsplit(selected_cover).hostname})
                if args.mobile_retry_only:
                    assert observation['phase']=='error' and not observation['playing']
                    page.set_viewport_size({'width':390,'height':844});page.wait_for_timeout(200)
                    retry=page.locator('.immersive-controls').get_by_role('button',name='重试播放',exact=True)
                    with page.expect_request(lambda request:request.url.endswith('/api/playback/open')):retry.tap()
                    page.wait_for_function('["ready","error","blocked"].includes(document.querySelector(".immersive-controls").dataset.phase)')
                    observation['mobileCentralRetryRequested']=True
                    page.screenshot(path=str(shots/'visual-patch-mobile-retry.png'));page.set_viewport_size({'width':1440,'height':1000})
                else:page.screenshot(path=str(shots/f'visual-real-{provider}-{song["identity"]["platformId"]}.png'))
                results.append(observation);(ROOT/('.runtime/e1-mobile-retry-result.json' if args.mobile_retry_only else '.runtime/e1-real-results.json')).write_text(json.dumps({'samples':results,'pageErrors':errors},ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(observation,ensure_ascii=True),flush=True)
            if args.overlay_only:verify_overlay(page,shots)
            if page.locator('.immersive-player').count():page.locator('.collapse-player').click();page.wait_for_timeout(700)
            stop=page.get_by_role('button',name='关闭播放',exact=True)
            if stop.count():stop.click()
            browser.close()
        if not args.overlay_only:
            path=ROOT/('.runtime/e1-mobile-retry-result.json' if args.mobile_retry_only else '.runtime/e1-real-results.json');path.parent.mkdir(exist_ok=True);path.write_text(json.dumps({'samples':results,'pageErrors':errors},ensure_ascii=False,indent=2),encoding='utf-8')
            assert len(results)==(1 if args.mobile_retry_only else 6) and all(row.get('status')=='success' and row.get('sameCover') and row.get('displayCover')==row.get('cover') and row.get('evidence')!='fallback' and row.get('background')!='none' for row in results),results
        assert not errors,errors
    finally:
        server.should_exit=True;thread.join(timeout=5)
        subprocess.run(['taskkill','/PID',str(vite.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)


if __name__=='__main__':main()
