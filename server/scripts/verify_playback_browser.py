"""真实Chromium验收，仅输出安全结果，不记录能力ID或上游URL。"""
import argparse
import json
import socket
import threading
import time
import httpx
import uvicorn
from playwright.sync_api import sync_playwright
from app.main import create_app
from app.core.media_store import MediaSettings


def main():
    parser=argparse.ArgumentParser(description='真实酷我原生audio播放验收')
    parser.add_argument('--browser',help='已有Chrome/Chromium可执行文件路径')
    args=parser.parse_args()
    app=create_app(media_settings=MediaSettings(media_ttl=4,lease_ttl=180,sweep_interval=1),dev_player=True)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,access_log=False,log_level='critical'))
    thread=threading.Thread(target=server.run,daemon=True);thread.start()
    summary={'rid':'9942644','port':port,'responses':[]}
    try:
        for _ in range(100):
            if server.started:break
            time.sleep(.1)
        assert server.started
        with sync_playwright() as playwright:
            browser=playwright.chromium.launch(headless=True,executable_path=args.browser,
                args=['--autoplay-policy=no-user-gesture-required'])
            try:
                page=browser.new_page()
                paths=[]
                page.on('request',lambda request:paths.append(request.url.split('/')[2]))
                def response_seen(response):
                    if '/stream' in response.url:
                        summary['responses'].append({'status':response.status,'contentRange':response.headers.get('content-range'),
                            'contentLength':response.headers.get('content-length')})
                page.on('response',response_seen)
                page.goto(f'http://127.0.0.1:{port}/dev/player');page.wait_for_load_state('networkidle')
                page.locator('#open').click()
                page.wait_for_function("Number.isFinite(audio.duration) && audio.duration>0 && audio.currentTime>2",timeout=60000)
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
                page.locator('#close').click()
                page.wait_for_function("status.textContent==='会话已关闭'")
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
                print(json.dumps(summary,ensure_ascii=True,indent=2))
            finally:
                browser.close()
    finally:
        server.should_exit=True;thread.join(timeout=15)
        assert not thread.is_alive()


if __name__=='__main__':main()
