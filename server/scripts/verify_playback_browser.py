"""真实Chromium验收，仅输出安全结果，不记录能力ID或上游URL。"""
import argparse
import json
import os
import socket
import threading
import time
import httpx
import uvicorn
from playwright.sync_api import sync_playwright
from app.main import create_app
from app.core.media_store import MediaSettings


def main():
    parser=argparse.ArgumentParser(description='四来源真实原生audio播放验收')
    parser.add_argument('--browser',default=os.environ.get('CHROMIUM_PATH'),help='已有Chrome/Chromium可执行文件路径；默认使用Playwright自带浏览器')
    parser.add_argument('--provider',choices=['kuwo','qq','netease','migu'],default='kuwo',help='本次验收平台')
    parser.add_argument('--track',help='稳定平台录音ID')
    parser.add_argument('--recover',action='store_true',help='增加已关闭旧会话后的手动稳定身份恢复验收')
    args=parser.parse_args()
    track=args.track or ('9942644' if args.provider=='kuwo' else None)
    if not track:parser.error('非酷我验收必须显式指定稳定平台歌曲ID')
    app=create_app(media_settings=MediaSettings(media_ttl=4,lease_ttl=180,sweep_interval=1),dev_player=True)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,access_log=False,log_level='critical'))
    thread=threading.Thread(target=server.run,daemon=True);thread.start()
    summary={'provider':args.provider,'platformId':track,'port':port,'responses':[]}
    try:
        for _ in range(100):
            if server.started:break
            time.sleep(.1)
        assert server.started
        resolve_count=[0]
        provider=getattr(app.state,args.provider)
        resolution_history=[]
        original_resolve=provider.resolve
        async def counted_resolve(identity,options=None):
            resolve_count[0]+=1
            resolved=await original_resolve(identity,options)
            if args.provider in ('qq','netease'):resolution_history.append(provider.last_resolution)
            return resolved
        provider.resolve=counted_resolve
        route_calls=[]
        if args.provider in ('qq','netease'):
            original_route=provider._resolve_route if args.provider=='qq' else None
            route_failures=[]
            async def counted_route(route,identity,options):
                route_calls.append(route)
                try:return await original_route(route,identity,options)
                except Exception as error:
                    route_failures.append({'route':route,'error':getattr(getattr(error,'code',None),'value',type(error).__name__)})
                    raise
            if args.provider=='qq':provider._resolve_route=counted_route
        with sync_playwright() as playwright:
            browser=playwright.chromium.launch(headless=True,executable_path=args.browser,
                args=['--autoplay-policy=no-user-gesture-required'])
            try:
                page=browser.new_page()
                paths=[]
                page.on('request',lambda request:paths.append(request.url.split('/')[2]))
                def response_seen(response):
                    if response.url.endswith('/api/playback/open') and response.status==200:
                        summary.setdefault('publicRepresentations',[]).append(response.json()['media']['representation'])
                    if '/stream' in response.url:
                        summary['responses'].append({'status':response.status,'contentRange':response.headers.get('content-range'),
                            'contentLength':response.headers.get('content-length')})
                page.on('response',response_seen)
                page.goto(f'http://127.0.0.1:{port}/dev/player');page.wait_for_load_state('networkidle')
                page.locator('#audio').evaluate('''a=>{
                    window.mediaEvents={};
                    for(const name of ['loadedmetadata','playing','pause','seeking','seeked','error'])
                        a.addEventListener(name,()=>{window.mediaEvents[name]=(window.mediaEvents[name]??0)+1});
                }''')
                original_audio=page.locator('#audio').element_handle()
                page.locator('#provider').select_option(args.provider)
                page.locator('#rid').fill(track)
                page.locator('#open').click()
                page.wait_for_function("Number.isFinite(document.querySelector('#audio').duration) && document.querySelector('#audio').duration>0 && document.querySelector('#audio').currentTime>2",timeout=60000)
                summary['duration']=page.locator('#audio').evaluate('(a)=>a.duration')
                summary['initialTime']=page.locator('#audio').evaluate('(a)=>a.currentTime')
                page.locator('#audio').evaluate('(a)=>a.pause()')
                paused=page.locator('#audio').evaluate('(a)=>a.currentTime')
                page.wait_for_timeout(1100)
                assert abs(page.locator('#audio').evaluate('(a)=>a.currentTime')-paused)<.1
                with app.state.media_store.lock:
                    assert len(app.state.media_store.records)==1
                    summary['pausedRecords']=len(app.state.media_store.records)
                page.locator('#audio').evaluate('(a)=>a.play()')
                page.wait_for_function('(t)=>audio.currentTime>t+1',arg=paused,timeout=15000)
                summary['resumeTime']=page.locator('#audio').evaluate('(a)=>a.currentTime')
                for name,fraction in [('middle',.5),('nearEnd',.94)]:
                    target=summary['duration']*fraction
                    page.locator('#audio').evaluate('(a,t)=>{a.pause();a.currentTime=t}',target)
                    page.wait_for_function('(t)=>!audio.seeking && Math.abs(audio.currentTime-t)<1 && audio.readyState>=2',arg=target,timeout=30000)
                    page.locator('#audio').evaluate('(a)=>a.play()')
                    page.wait_for_function('(t)=>audio.currentTime>t+.5',arg=target,timeout=15000)
                    summary[name]=page.locator('#audio').evaluate('(a)=>({time:a.currentTime,seeking:a.seeking,error:a.error?.code??null})')
                # 测试脚本只在内存中持有本地能力地址，不输出或保存。
                stream=page.locator('#audio').evaluate('(a)=>a.src')
                summary['normalResolveCalls']=resolve_count[0]
                assert resolve_count[0]==1
                if args.recover:
                    page.locator('#pause').click()
                    page.locator('#audio').evaluate('(a)=>{a.volume=.3;a.playbackRate=1.2}')
                    saved=page.locator('#audio').evaluate('(a)=>a.currentTime')
                    old_key=stream.split('/')[-2]
                    app.state.playback_leases.close(old_key)
                    if args.provider=='migu':
                        # 丢弃Provider实例，证明双ID重建不依赖刚才的搜索或取链内存。
                        replacement=type(provider)(app.state.http_client)
                        original_resolve=replacement.resolve
                        replacement.resolve=counted_resolve
                        app.state.migu=replacement
                        summary['providerReinitializedBeforeRecovery']=True
                    page.locator('#retry').click()
                    page.wait_for_function("document.body.dataset.phase==='ready'",timeout=60000)
                    summary['recovery']=page.locator('#audio').evaluate('(a)=>({time:a.currentTime,paused:a.paused,volume:a.volume,rate:a.playbackRate})')
                    fresh=page.locator('#audio').evaluate('(a)=>a.src')
                    summary['recovery']['differentPlaybackId']=fresh!=stream
                    summary['recovery']['sameAudio']=original_audio.evaluate('(a)=>a===document.querySelector("audio")')
                    assert fresh!=stream and abs(summary['recovery']['time']-saved)<.5 and summary['recovery']['paused']
                    assert summary['recovery']['volume']==.3 and summary['recovery']['rate']==1.2
                    stream=fresh
                page.locator('#close').click()
                page.wait_for_function("document.querySelector('#status').textContent==='会话已关闭'")
                with httpx.Client() as client:
                    summary['closedRequestStatus']=client.get(stream,headers={'Range':'bytes=0-10'}).status_code
                assert summary['closedRequestStatus']==410
                for _ in range(100):
                    with app.state.media_store.lock:
                        records=list(app.state.media_store.records.values())
                        active=sum(len(r.streams) for r in records)
                    if not records:break
                    time.sleep(.1)
                summary['remainingRecords']=len(records);summary['activeStreams']=active
                summary['browserOnlyLocalOrigin']=all(host==f'127.0.0.1:{port}' for host in paths)
                assert not records and active==0 and summary['browserOnlyLocalOrigin']
                summary['browserVersion']=browser.version
                summary['events']=page.evaluate('window.mediaEvents')
                if args.provider in ('qq','netease'):
                    if args.provider=='qq':
                        summary['routeCalls']=route_calls
                        summary['routeFailures']=route_failures
                    summary['resolutionHistory']=resolution_history
                    summary['lastResolution']=provider.last_resolution
                summary['resolveCalls']=resolve_count[0]
                assert resolve_count[0]==(2 if args.recover else 1)
                print(json.dumps(summary,ensure_ascii=True,indent=2))
            finally:
                browser.close()
    finally:
        server.should_exit=True;thread.join(timeout=15)
        assert not thread.is_alive()


if __name__=='__main__':main()
