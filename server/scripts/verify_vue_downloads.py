"""16 下载界面 新Vue下载接线：真实文件与人工并发、故障分别验收。"""
import argparse
import asyncio
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import time
from types import SimpleNamespace
import wave
import httpx
import uvicorn
from playwright.sync_api import sync_playwright
from verify_vue_player import ROOT,FaultUpstream,allow_fixture_target
from app.main import create_app
from app.models import SearchPage,SongCandidate,TrackIdentity,ResolvedMedia,MediaRepresentation
from app.lyrics import LyricDocument
from app.downloads import DownloadSettings
from app.core.errors import CoreError,ErrorCode
from app.core.media_store import MediaSettings

OUT=Path(os.environ.get('MUSIC_CORE_VERIFY_OUT',ROOT/'.runtime/verify-vue-downloads'))
CHROME=os.environ.get('CHROMIUM_PATH')

def free_port(excluded=()):
    for _ in range(20):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        if port not in excluded:return port
    raise RuntimeError('无法分配未占用的本地端口')

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--controlled',action='store_true');args=parser.parse_args()
    used_ports=set()
    controlled_api=free_port(used_ports);used_ports.add(controlled_api)
    controlled_web=free_port(used_ports);used_ports.add(controlled_web)
    real_api=free_port(used_ports);used_ports.add(real_api)
    real_web=free_port(used_ports)
    server=None;vite=None;thread=None;app=None;temporary=None;release=threading.Event();download_resolves=[];failed_once=set();url=''
    if args.controlled:
        temporary=tempfile.TemporaryDirectory(prefix='music-core-download-ui-');directory=Path(temporary.name)
        upstream=FaultUpstream();output=io.BytesIO()
        with wave.open(output,'wb') as audio:audio.setparams((1,2,8000,0,'NONE','not compressed'));audio.writeframes(upstream.audio[44:]*4)
        upstream.audio=output.getvalue()
        async def resolve(identity,options=None):
            if options and options.purpose=='download':
                download_resolves.append(identity.platformId)
                if identity.platformId=='4' and '4' not in failed_once:failed_once.add('4');raise CoreError(ErrorCode.ACCESS_DENIED)
                if identity.platformId=='5':raise CoreError(ErrorCode.UPSTREAM_TIMEOUT)
                return ResolvedMedia(id='人工下载',identity=identity,representation=MediaRepresentation(container='mpeg-audio'),resolvedAt=int(time.time()*1000),upstreamUrl=f'https://fixture.kuwo.cn/download/{identity.platformId}')
            return await upstream.resolve(identity)
        class Stream(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield b'ID3'+b'x'*65533
                while not release.is_set():await asyncio.sleep(.05)
                for _ in range(15):yield b'x'*65536;await asyncio.sleep(.03)
            async def aclose(self):pass
        async def handle(request):
            if request.url.path.startswith('/download/'):
                headers={'Content-Type':'audio/mpeg'}
                if request.url.path.rsplit('/',1)[1]!='1':headers['Content-Length']=str(1048576)
                return httpx.Response(200,headers=headers,stream=Stream())
            return await upstream.handle(request)
        async def search(*args):return SearchPage(items=tuple(SongCandidate(identity=TrackIdentity(providerId='kuwo',platformId=str(i)),title=f'人工歌曲{i}',artists=('人工',)) for i in range(1,7)))
        async def lyrics(identity):return LyricDocument(identity=identity,status='unavailable')
        app=create_app(transport=httpx.MockTransport(handle),target_check=allow_fixture_target,download_settings=DownloadSettings(directory=directory),media_settings=MediaSettings(media_ttl=.3,lease_ttl=60,sweep_interval=.1))
        server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=controlled_api,log_level='critical',access_log=False));thread=threading.Thread(target=server.run,daemon=True);thread.start()
        for _ in range(100):
            if server.started or not thread.is_alive():break
            time.sleep(.05)
        if not server.started:raise RuntimeError('受控服务启动失败')
        app.state.kuwo=SimpleNamespace(resolve=resolve,search=search,get_lyrics=lyrics)
        vite=subprocess.Popen(['cmd','/c',f'pnpm dev --host 127.0.0.1 --port {controlled_web} --strictPort'],cwd=ROOT/'web',env={**os.environ,'MUSIC_CORE_API_TARGET':f'http://127.0.0.1:{controlled_api}'},stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);url=f'http://127.0.0.1:{controlled_web}'
        for _ in range(100):
            try:
                if httpx.get(url).status_code==200:break
            except httpx.HTTPError:pass
            time.sleep(.1)
    else:
        # 真实Provider使用独立新Core，避免上次内存任务的防重复规则影响重跑。
        directory=ROOT/'downloads';app=create_app()
        server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=real_api,log_level='critical',access_log=False));thread=threading.Thread(target=server.run,daemon=True);thread.start()
        for _ in range(100):
            if server.started or not thread.is_alive():break
            time.sleep(.05)
        if not server.started:raise RuntimeError('真实验收 Core 启动失败')
        vite=subprocess.Popen(['cmd','/c',f'pnpm dev --host 127.0.0.1 --port {real_web} --strictPort'],cwd=ROOT/'web',env={**os.environ,'MUSIC_CORE_API_TARGET':f'http://127.0.0.1:{real_api}'},stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);url=f'http://127.0.0.1:{real_web}'
        for _ in range(100):
            try:
                if httpx.get(url).status_code==200:break
            except httpx.HTTPError:pass
            time.sleep(.1)
    screenshots=OUT/'screenshots';screenshots.mkdir(parents=True,exist_ok=True)
    try:
        with sync_playwright() as pw:
            browser=pw.chromium.launch(headless=True,executable_path=CHROME,args=['--autoplay-policy=no-user-gesture-required']);page=browser.new_page(viewport={'width':1440,'height':1000})
            errors=[];console=[];created=[];opens=[];lists=[];progress=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.on('console',lambda m:console.append(m.text) if m.type=='error' else None)
            def response(r):
                if r.url.endswith('/api/downloads'):
                    if r.request.method=='POST' and r.status==202:created.append(r.json())
                    elif r.request.method=='GET':lists.append(r.status)
                if r.url.endswith('/api/playback/open') and r.status==200:opens.append(r.json())
            page.on('response',response)
            if not args.controlled:page.add_init_script("localStorage.setItem('music-core.search.sources.v1',JSON.stringify(['netease']))")
            page.goto(url);page.wait_for_load_state('networkidle')
            def navigate(path):page.evaluate("path=>{history.pushState({},'',path);dispatchEvent(new PopStateEvent('popstate'))}",path);page.wait_for_timeout(250)
            def row(mid):return page.locator(f'.song-row[data-platform-id="{mid}"]').first
            def create(mid):row(mid).hover();row(mid).locator('.action-download').click()
            def task(identifier):return page.locator(f'.download-row[data-task-id="{identifier}"]')
            page.locator('#query').fill('人工' if args.controlled else '飞鸟与鱼 齐豫');page.locator('#query').press('Enter')
            first='1' if args.controlled else '284617';page.locator('.song-row').first.wait_for(timeout=30000)
            if not row(first).count():
                for button in page.locator('.versions-toggle').all():button.click()
            row(first).wait_for(timeout=30000)
            create(first)
            for _ in range(100):
                if created:break
                page.wait_for_timeout(100)
            assert created and created[0]['identity']['platformId']==first
            create(first);page.wait_for_timeout(200);assert len(created)==1 and not opens,{'creates':len(created),'opens':len(opens),'errors':errors,'console':console,'jobs':[(j.public.status,j.public.errorCode) for j in app.state.downloads.jobs.values()] if app else None}
            assert page.locator('audio').evaluate('a=>a.paused&&!a.getAttribute("src")')
            navigate('/downloads');page.get_by_role('tab',name='正在下载',exact=True).click();identifier=created[0]['id'];task(identifier).wait_for()
            if args.controlled:
                navigate('/search?q=人工');create('2');create('3')
                for _ in range(100):
                    if len(created)>=3:break
                    page.wait_for_timeout(50)
                ids=[item['id'] for item in created]
                page.wait_for_timeout(1700);states={key:job.public.status for key,job in app.state.downloads.jobs.items()}
                assert states[ids[2]]=='queued' and sum(status in ('resolving','downloading') for status in states.values())==2
                row('6').locator('.action-play').click();page.wait_for_function('document.querySelector("audio").currentTime>.2');page.evaluate('window.firstAudio=document.querySelector("audio")')
                volume=page.locator('audio').evaluate('a=>a.volume');playing_id=opens[-1]['playbackId']
                navigate('/');navigate('/downloads');page.get_by_role('tab',name='正在下载',exact=True).click();page.wait_for_timeout(1700)
                assert task(ids[0]).get_by_text('总大小未知',exact=False).count()==1
                assert task(ids[0]).locator('progress').get_attribute('value') is None
                progress.append(('downloading',app.state.downloads.get(ids[0]).public.receivedBytes))
                page.screenshot(path=str(screenshots/'download-controlled-downloading.png'))
                # 挂起一个旧列表响应，在取消完成后放行，不能复活旧状态。
                snapshot=page.request.get(url+'/api/downloads').json();held=[];hold=[True]
                def old_list(route):
                    if route.request.method=='GET' and hold[0]:held.append(route);return
                    route.continue_()
                page.route('**/api/downloads',old_list);page.get_by_role('button',name='刷新下载列表',exact=True).click()
                for _ in range(100):
                    if held:break
                    page.wait_for_timeout(30)
                assert held
                task(ids[1]).get_by_role('button',name='取消',exact=True).click();page.wait_for_function("id=>document.querySelector('[data-task-id=\"'+id+'\"]').dataset.status==='cancelled'",arg=ids[1])
                hold[0]=False
                for route in held:route.fulfill(json=snapshot)
                page.wait_for_timeout(500);assert task(ids[1]).get_attribute('data-status')=='cancelled'
                assert app.state.downloads.get(ids[2]).public.status in ('resolving','downloading')
                assert page.locator('audio').evaluate('a=>a===firstAudio&&!a.paused') and page.locator('audio').evaluate('a=>a.volume')==volume
                page.get_by_role('button',name='暂停',exact=True).click();page.get_by_role('button',name='播放',exact=True).click()
                slider=page.get_by_label('播放进度',exact=True);slider.evaluate('el=>{el.value="96";el.dispatchEvent(new Event("change",{bubbles:true}));}');page.wait_for_function('Math.abs(firstAudio.currentTime-96)<2&&!firstAudio.seeking')
                assert page.request.head(url+opens[-1]['streamUrl']).status in (200,206)
                assert opens[-1]['playbackId']==playing_id
                # 列表保留传输态，但服务端已完成时取消，必须显示真实completed。
                snapshot=page.request.get(url+'/api/downloads').json();held.clear();hold[0]=True
                page.get_by_role('button',name='刷新下载列表',exact=True).click()
                for _ in range(100):
                    if held:break
                    page.wait_for_timeout(30)
                assert held;release.set()
                for _ in range(100):
                    if app.state.downloads.get(ids[2]).public.status=='completed':break
                    page.wait_for_timeout(50)
                assert app.state.downloads.get(ids[2]).public.status=='completed'
                task(ids[2]).get_by_role('button',name='取消',exact=True).click();page.wait_for_function("id=>document.querySelector('[data-task-id=\"'+id+'\"]').dataset.status==='completed'",arg=ids[2])
                hold[0]=False
                for route in held:route.fulfill(json=snapshot)
                held.clear();page.wait_for_timeout(300);assert task(ids[2]).get_attribute('data-status')=='completed'
                navigate('/search?q=人工');row('1').locator('.action-play').click();page.wait_for_function('document.querySelector("audio").currentTime>.1');assert page.locator('audio').evaluate('a=>a===firstAudio')
                navigate('/downloads');page.get_by_role('tab',name='正在下载',exact=True).click()
                release.set()
            deadline=time.monotonic()+180
            while time.monotonic()<deadline:
                state=page.request.get(url+'/api/downloads/'+identifier).json();progress.append((state['status'],state['receivedBytes']))
                if state['status'] in ('completed','failed','cancelled'):break
                if state['status']=='downloading' and state['receivedBytes']>0 and not args.controlled:page.screenshot(path=str(screenshots/'download-real-downloading.png'))
                page.wait_for_timeout(500)
            assert state['status']=='completed',state
            page.wait_for_timeout(1800);page.get_by_role('tab',name='下载歌曲',exact=True).click()
            saved=page.locator('.download-row[data-filename="'+state['filename']+'"]');saved.wait_for();page.screenshot(path=str(screenshots/('download-controlled-completed.png' if args.controlled else 'download-real-completed.png')))
            path=directory/state['filename'];assert path.is_file() and path.stat().st_size==state['receivedBytes']
            file_summary={'filename':path.name,'bytes':path.stat().st_size,'format':state['format'],'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
            assert not list(directory.glob('.music-core-*.part'))
            if args.controlled:
                navigate('/search?q=人工');create('4');page.wait_for_timeout(1800);navigate('/downloads');page.get_by_role('tab',name='正在下载',exact=True).click()
                failed=created[-1]['id'];assert task(failed).get_by_text('平台拒绝下载访问',exact=True).count()==1
                task(failed).get_by_role('button',name='重试',exact=True).click();page.wait_for_timeout(2500)
                assert len([key for key in app.state.downloads.jobs if app.state.downloads.jobs[key].public.identity.platformId=='4'])==2
                assert download_resolves.count('4')==2 and task(failed).get_by_text('已重试',exact=True).count()==1
                page.screenshot(path=str(screenshots/'download-controlled-failed-cancelled.png'))
                # 模拟容量淘汰后重试404；当前任务视图不能冒充永久历史。
                navigate('/search?q=人工');create('5');page.wait_for_timeout(1700);missing=created[-1]['id'];navigate('/downloads');page.get_by_role('tab',name='正在下载',exact=True).click()
                app.state.downloads.jobs.pop(missing);task(missing).get_by_role('button',name='重试',exact=True).click();page.get_by_text('任务不存在或已过期，请刷新',exact=True).wait_for()
                # 服务不可用保留已有结果，手动刷新可以恢复。
                page.route('**/api/downloads',lambda route:route.fulfill(status=503,json={'error':{'message':'人工下载服务不可用'}}) if route.request.method=='GET' else route.continue_())
                page.get_by_role('button',name='刷新下载列表',exact=True).click();page.get_by_text('人工下载服务不可用',exact=True).wait_for();page.unroute('**/api/downloads');page.get_by_role('button',name='刷新下载列表',exact=True).click();page.wait_for_timeout(500)
                assert page.locator('audio').evaluate('a=>a===firstAudio&&!a.paused')
                count=len(lists);page.wait_for_timeout(3300);assert len(lists)==count
                assert not list(directory.glob('.music-core-*.part'))
                assert not any(job.worker is not None for job in app.state.downloads.jobs.values())
                page.get_by_role('button',name='关闭播放',exact=True).click();page.wait_for_timeout(700);assert not app.state.media_store.records
            else:
                # 完整文件由 Chromium 本地读取metadata，区别于人工前缀载荷。
                local=browser.new_page();local.goto(path.as_uri());local.wait_for_function('document.querySelector("audio,video")?.readyState>=1');file_summary['duration']=local.locator('audio,video').evaluate('a=>a.duration');local.close()
                # 另一具体录音下载中播放已完成歌曲，取消结果以服务端实际状态为准。
                navigate('/search?q=飞鸟与鱼 齐豫')
                if not row('284782').count():
                    for button in page.locator('.versions-toggle').all():button.click()
                create('284782')
                for _ in range(100):
                    if len(created)>1:break
                    page.wait_for_timeout(50)
                if not row(first).count():
                    for button in page.locator('.versions-toggle').all():button.click()
                row(first).locator('.action-play').click();page.wait_for_function('document.querySelector("audio").currentTime>.2',timeout=45000)
                page.evaluate('window.firstAudio=document.querySelector("audio")');lease=opens[-1]
                navigate('/downloads');page.get_by_role('tab',name='正在下载',exact=True).click();page.wait_for_timeout(1600)
                second=created[-1]['id'];current=page.request.get(url+'/api/downloads/'+second).json()
                file_summary['parallelDownloadState']=current['status']
                if current['status'] in ('queued','resolving','downloading'):
                    task(second).get_by_role('button',name='取消',exact=True).click();page.wait_for_timeout(500)
                assert page.locator('audio').evaluate('a=>a===firstAudio&&!a.paused')
                slider=page.get_by_label('播放进度',exact=True);slider.evaluate('el=>{el.value="120";el.dispatchEvent(new Event("change",{bubbles:true}));}');page.wait_for_function('Math.abs(firstAudio.currentTime-120)<2&&!firstAudio.seeking')
                assert page.request.head(url+lease['streamUrl']).status in (200,206)
                page.get_by_role('button',name='关闭播放',exact=True).click();page.wait_for_timeout(500);assert page.request.head(url+lease['streamUrl']).status==410
                final=page.request.get(url+'/api/downloads/'+second).json();file_summary['secondDownloadFinal']=final['status'];file_summary['secondDownloadErrorCode']=final['errorCode'];file_summary['secondDownloadIdentity']=final['identity']
                assert not list(directory.glob('.music-core-*.part'))
            prefix='download-controlled-' if args.controlled else 'download-'
            page.get_by_role('tab',name='下载歌曲',exact=True).click();page.screenshot(path=str(screenshots/(prefix+'desktop-download-list.png')))
            for width in (768,390):
                page.set_viewport_size({'width':width,'height':844});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                if width==390:page.screenshot(path=str(screenshots/(prefix+'mobile-downloads.png')))
            navigate('/settings');page.get_by_role('radio',name='深色',exact=True).check();navigate('/downloads');page.screenshot(path=str(screenshots/(prefix+'dark-downloads.png')))
            page.reload();page.wait_for_load_state('networkidle');assert page.locator('.download-row[data-filename]').count()>0
            assert not errors,errors
            result={'controlled':args.controlled,'created':len(created),'progress':list(dict.fromkeys(progress)),'file':file_summary,'pageErrors':errors,'consoleErrors':console,'singleAudio':page.locator('audio').count()==1,'downloadResolveCount':download_resolves if args.controlled else None}
            OUT.mkdir(parents=True,exist_ok=True)
            (OUT/('download-controlled-result.json' if args.controlled else 'download-real-result.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result));browser.close()
    finally:
        release.set()
        if server:server.should_exit=True;thread.join(10)
        if vite:subprocess.run(['taskkill','/PID',str(vite.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        if temporary:temporary.cleanup()

if __name__=='__main__':main()
