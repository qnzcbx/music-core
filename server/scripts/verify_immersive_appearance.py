"""封面取色及操作层真实浏览器验收；媒体和封面均为明确标识的受控夹具。"""
import asyncio
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import threading
import time
from types import SimpleNamespace
import wave
import httpx
import uvicorn
from fastapi.responses import Response
from playwright.sync_api import sync_playwright
from app.main import create_app
from app.models import SearchPage, SongCandidate, TrackIdentity
from app.lyrics import LyricDocument, LyricLine
from app.core.media_store import MediaSettings
from recovery_fixture import FaultUpstream, allow_fixture_target

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(os.environ.get('MUSIC_CORE_VERIFY_OUT',ROOT/'.runtime/verify-immersive-appearance'))
CHROME=os.environ.get('CHROMIUM_PATH')

def free_port(excluded=()):
    for _ in range(20):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        if port not in excluded:return port
    raise RuntimeError('无法分配未占用的本地端口')


def main():
    api_port=free_port();web_port=free_port({api_port})
    upstream=FaultUpstream(); output=io.BytesIO()
    with wave.open(output,'wb') as audio:
        audio.setparams((1,2,8000,0,'NONE','not compressed'));audio.writeframes(upstream.audio[44:]*4)
    upstream.audio=output.getvalue()
    async def resolve(identity,options=None):return await upstream.resolve(identity)
    async def search(*args):
        return SearchPage(items=tuple(SongCandidate(identity=TrackIdentity(providerId='kuwo',platformId=str(i)),title=f'取色验收{i}',artists=('人工',),cover=None if i==3 else f'http://127.0.0.1:{api_port}/fixture/{"red" if i in (1,5) else "blue" if i==2 else "denied"}.svg') for i in range(1,6)))
    async def lyrics(identity):return LyricDocument(identity=identity,status='synced',lines=tuple(LyricLine(startMs=i*1000,endMs=(i+1)*1000,text=f'人工歌词 {i}') for i in range(190)))
    app=create_app(transport=httpx.MockTransport(upstream.handle),target_check=allow_fixture_target,media_settings=MediaSettings(lease_ttl=600,media_ttl=.3,sweep_interval=.1))
    @app.get('/fixture/{kind}.svg')
    async def cover(kind:str):
        colors=('#b84d40','#e4b359') if kind=='red' else ('#365cb0','#65c7d2')
        return Response(f'<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><rect width="75" height="100" fill="{colors[0]}"/><rect x="75" width="25" height="100" fill="{colors[1]}"/></svg>',media_type='image/svg+xml',headers={} if kind=='denied' else {'Access-Control-Allow-Origin':'*'})
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=api_port,access_log=False,log_level='critical'))
    thread=threading.Thread(target=server.run,daemon=True);thread.start()
    for _ in range(100):
        if server.started:break
        time.sleep(.05)
    assert server.started
    app.state.kuwo=SimpleNamespace(resolve=resolve,search=search,get_lyrics=lyrics)
    vite=subprocess.Popen(['cmd','/c',f'pnpm dev --host 127.0.0.1 --port {web_port} --strictPort'],cwd=ROOT/'web',env={**os.environ,'MUSIC_CORE_API_TARGET':f'http://127.0.0.1:{api_port}'},stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    url=f'http://127.0.0.1:{web_port}';shots=OUT/'screenshots';shots.mkdir(parents=True,exist_ok=True);result={};errors=[]
    try:
        for _ in range(100):
            try:
                if httpx.get(url).status_code==200:break
            except httpx.HTTPError:pass
            time.sleep(.1)
        with sync_playwright() as pw:
            browser=pw.chromium.launch(headless=True,executable_path=CHROME,args=['--autoplay-policy=no-user-gesture-required'])
            context=browser.new_context(viewport={'width':1440,'height':1000},has_touch=True)
            page=context.new_page();page.on('pageerror',lambda error:errors.append(str(error)))
            page.add_init_script('window.extractions=0;const original=CanvasRenderingContext2D.prototype.getImageData;CanvasRenderingContext2D.prototype.getImageData=function(...args){window.extractions++;return original.apply(this,args)}')
            page.goto(url);page.wait_for_load_state('networkidle');page.locator('#query').fill('取色');page.locator('#query').press('Enter')
            def choose(identifier):
                if page.locator('.immersive-player').count():page.get_by_role('button',name='收起歌曲详情页').click();page.wait_for_timeout(700)
                page.locator(f'.song-row[data-platform-id="{identifier}"] .action-play').first.click()
                page.wait_for_function('document.querySelector("audio").currentTime>0&&!document.querySelector("audio").paused')
                page.get_by_role('button',name='打开沉浸式播放器',exact=True).click();page.locator('.immersive-player').wait_for();page.wait_for_timeout(1100)
            choose(1);page.evaluate('window.firstAudio=document.querySelector("audio")')
            page.get_by_role('button',name='收起歌曲详情页').click();page.wait_for_timeout(700)
            page.locator('.song-row[data-platform-id="2"] .action-play-next').first.click();page.get_by_role('menuitem',name='添加到播放队列',exact=True).click()
            page.get_by_role('button',name='打开沉浸式播放器',exact=True).click();page.wait_for_timeout(700)
            room=page.locator('.immersive-player');controls=room.locator('.immersive-controls')
            def fingerprint():return page.locator('.ambient-active').evaluate('(el)=>[getComputedStyle(el).backgroundImage,getComputedStyle(document.querySelector(".ambient-background")).filter,getComputedStyle(document.querySelector(".immersive-player")).color]')
            def shot(name):page.screenshot(path=str(shots/f'visual-{name}'))
            def away():
                page.locator('.collapse-player').focus();page.mouse.move(700 if page.viewport_size['width']>760 else 10,80)
            assert page.locator('.ambient-background').get_attribute('data-palette-evidence')=='cover'
            palette_colors=lambda:page.locator('.ambient-active').evaluate('(el)=>["--ambient-left","--ambient-center","--ambient-right"].map(name=>getComputedStyle(el).getPropertyValue(name).trim())')
            red_colors=palette_colors();red=fingerprint();shot('red-controls-visible.png');first_count=page.evaluate('extractions')
            count=len(upstream.opens)
            controls.get_by_role('button',name='暂停',exact=True).click();page.wait_for_timeout(4400);assert room.get_attribute('data-controls-hidden')=='false'
            controls.get_by_role('slider',name='播放进度').evaluate('(el)=>{el.value=30;el.dispatchEvent(new Event("change",{bubbles:true}))}')
            controls.get_by_role('button',name='播放',exact=True).click()
            assert page.evaluate('extractions')==first_count
            for dark in (True,False):
                page.emulate_media(color_scheme='dark' if dark else 'light');page.wait_for_timeout(200);assert page.evaluate('document.documentElement.dataset.theme')==('dark' if dark else 'light')
                assert fingerprint()==red
            result['themeIndependent']=True
            for identifier,name in [('classic','经典唱片机'),('vinyl-wide','沉浸大唱片'),('square-cover','方形封面'),('lyrics-only','纯净歌词')]:
                controls.get_by_label('播放器样式',exact=True).click();page.get_by_role('button',name=name,exact=True).click();page.wait_for_timeout(700)
                assert room.get_attribute('data-player-layout')==identifier
                shot(f'template-{identifier}.png')
            assert len(upstream.opens)==count and page.evaluate('extractions')==first_count
            # 自动隐藏与鼠标、键盘唤醒；原生焦点需离开控制栏。
            away();page.wait_for_timeout(4450);assert room.get_attribute('data-controls-hidden')=='true';shot('controls-hidden.png')
            page.mouse.move(705,85);page.wait_for_timeout(100);assert room.get_attribute('data-controls-hidden')=='false'
            away();page.wait_for_timeout(4450);assert room.get_attribute('data-controls-hidden')=='true'
            page.keyboard.press('Tab');page.wait_for_timeout(100);assert room.get_attribute('data-controls-hidden')=='false'
            controls.get_by_role('button',name='播放队列').click();page.mouse.move(10,80);page.wait_for_timeout(4450);assert room.get_attribute('data-controls-hidden')=='false';page.keyboard.press('Escape')
            controls.get_by_label('播放器样式',exact=True).click();away();page.wait_for_timeout(4450);assert room.get_attribute('data-controls-hidden')=='false';page.keyboard.press('Escape')
            controls.hover();page.wait_for_timeout(4450);assert room.get_attribute('data-controls-hidden')=='false'
            controls.get_by_role('button',name='查看歌词',exact=True).click();assert page.locator('.lyric-scroll').is_visible();assert len(upstream.opens)==count
            result['idle']={'fourSeconds':True,'mouseWake':True,'tabWake':True,'queueLock':True,'styleLock':True,'hoverLock':True,'pauseVisible':True}
            shot('red-before-next.png');controls.get_by_role('button',name='下一首',exact=True).click()
            page.wait_for_function('document.querySelector(".ambient-background").dataset.paletteKey.endsWith("blue.svg")')
            page.wait_for_timeout(200);mid_opacity=float(page.locator('.ambient-active').evaluate('(el)=>getComputedStyle(el).opacity'));assert 0<mid_opacity<1
            page.wait_for_timeout(1000);blue_colors=palette_colors();assert blue_colors!=red_colors;page.wait_for_function('document.querySelector("audio").currentTime>0&&!document.querySelector("audio").paused');shot('blue-controls-visible.png')
            assert page.locator('audio').evaluate('(a)=>a===firstAudio&&!a.paused')
            result['paletteProof']={'warm':red_colors,'cool':blue_colors,'crossfadeMidOpacity':mid_opacity}
            second_count=page.evaluate('extractions');choose(5);assert page.evaluate('extractions')==second_count
            choose(3);assert page.locator('.ambient-background').get_attribute('data-palette-evidence')=='fallback';shot('no-cover-neutral.png')
            choose(4);assert page.locator('.ambient-background').get_attribute('data-palette-evidence')=='fallback';shot('cors-failure-neutral.png')
            choose(2);count=len(upstream.opens)
            # 所有宽度、模板均使用真实页面，不切换音频。
            for width in (1440,768,390):
                page.set_viewport_size({'width':width,'height':844 if width==390 else 1000});page.wait_for_timeout(300)
                for identifier,name in [('classic','经典唱片机'),('vinyl-wide','沉浸大唱片'),('square-cover','方形封面'),('lyrics-only','纯净歌词')]:
                    controls.get_by_label('播放器样式',exact=True).click();page.get_by_role('button',name=name,exact=True).click();page.wait_for_timeout(700)
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                    assert page.locator('audio').evaluate('(a)=>a===firstAudio&&!a.paused')
                    shot(f'{width}-{identifier}.png')
            assert len(upstream.opens)==count
            # 触摸首击仅唤醒，不触发歌词 Seek 或播放切换。
            away();page.wait_for_timeout(4450);assert room.get_attribute('data-controls-hidden')=='true'
            before=page.locator('audio').evaluate('(a)=>a.currentTime');page.touchscreen.tap(10,90);page.wait_for_timeout(150)
            assert room.get_attribute('data-controls-hidden')=='false' and page.locator('audio').evaluate('(a)=>!a.paused')
            assert abs(page.locator('audio').evaluate('(a)=>a.currentTime')-before)<1
            result['idle']['touchWake']=True
            controls.get_by_role('button',name='播放队列').click();page.mouse.move(10,80);page.wait_for_timeout(4450);assert room.get_attribute('data-controls-hidden')=='false';page.keyboard.press('Escape')
            # 加载挂起与错误都属于需要用户关注的状态，不能闲置隐藏。
            upstream.hold_next=True;controls.get_by_role('button',name='下一首').click()
            for _ in range(100):
                if upstream.held:break
                page.wait_for_timeout(20)
            assert upstream.held;away();page.wait_for_timeout(4450);assert room.get_attribute('data-controls-hidden')=='false'
            upstream.fail_open=True;upstream.held.clear();page.wait_for_function('document.querySelector(".immersive-controls").dataset.phase==="error"')
            away();page.wait_for_timeout(4450);assert room.get_attribute('data-controls-hidden')=='false';shot('error-controls-visible.png')
            upstream.fail_open=False;controls.get_by_role('button',name='重试播放',exact=True).click();page.wait_for_function('document.querySelector(".immersive-controls").dataset.phase==="ready"')
            result['idle']['loadingAndErrorVisible']=True
            page.emulate_media(reduced_motion='reduce');assert page.locator('.immersive-control-layer').evaluate('(el)=>getComputedStyle(el).transitionDuration')=='0s'
            page.emulate_media(reduced_motion='no-preference')
            controls.get_by_role('button',name='收起歌曲详情页',exact=True).click();page.wait_for_timeout(700);assert page.locator('.immersive-player').count()==0
            assert page.locator('audio').evaluate('(a)=>a===firstAudio&&!a.paused')
            page.get_by_role('button',name='关闭播放',exact=True).click();page.wait_for_timeout(500)
            assert page.locator('audio').evaluate('(a)=>a.paused&&!a.getAttribute("src")') and page.locator('audio').count()==1
            result.update({'paletteChanged':True,'sameCoverCached':True,'noCoverFallback':True,'corsFallback':True,'templates':4,'widths':[390,768,1440],'singleAudio':True,'noVisualReopen':True,'pageErrors':errors})
            assert not errors
            browser.close()
        OUT.mkdir(parents=True,exist_ok=True)
        (OUT/'browser-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=False))
    finally:
        server.should_exit=True;thread.join(timeout=5)
        subprocess.run(['taskkill','/PID',str(vite.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)


if __name__=='__main__':main()
