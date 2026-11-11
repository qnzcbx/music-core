"""可控音频和真实Chromium故障验收，不访问酷我，不输出能力标识。"""
import argparse
import json
import os
import socket
import threading
import time
import httpx
import uvicorn
from playwright.sync_api import sync_playwright,TimeoutError as BrowserTimeout
from app.main import create_app
from app.core.media_store import MediaSettings
from recovery_fixture import FaultUpstream,allow_fixture_target


def main():
    parser=argparse.ArgumentParser(description='受控媒体失效恢复浏览器验收')
    parser.add_argument('--browser',default=os.environ.get('CHROMIUM_PATH'),help='Chromium 路径；默认使用 Playwright 自带浏览器');args=parser.parse_args()
    upstream=FaultUpstream()
    app=create_app(transport=httpx.MockTransport(upstream.handle),target_check=allow_fixture_target,
        dev_player=True,media_settings=MediaSettings(media_ttl=.4,lease_ttl=5,sweep_interval=.1))
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,access_log=False,log_level='critical'))
    thread=threading.Thread(target=server.run,daemon=True);thread.start()
    summary={'fixture':'自生成48秒WAV','scenarios':[]}
    try:
        for _ in range(100):
            if server.started:break
            time.sleep(.05)
        assert server.started;app.state.kuwo=upstream
        with sync_playwright() as pw:
            browser=pw.chromium.launch(headless=True,executable_path=args.browser,args=['--autoplay-policy=no-user-gesture-required'])
            try:
                page=browser.new_page();sessions=[]
                page.add_init_script("""const interval=window.setInterval;window.setInterval=(cb,ms,...a)=>{if(ms===60000)window.__renew=cb;return interval(cb,ms,...a)};window.__events=[];addEventListener('DOMContentLoaded',()=>{const a=document.querySelector('audio');window.__originalAudio=a;for(const e of ['error','waiting','stalled','abort','emptied'])a.addEventListener(e,()=>window.__events.push({event:e,code:a.error?.code??null}))});""")
                def response(r):
                    if r.url.endswith('/api/playback/open') and r.status==200:sessions.append(r.json()['playbackId'])
                page.on('response',response)
                page.goto(f'http://127.0.0.1:{port}/dev/player');page.wait_for_load_state('networkidle')
                def playing():
                    try:page.wait_for_function("document.body.dataset.phase==='ready' && document.querySelector('audio').currentTime>1",timeout=20000)
                    except BrowserTimeout:
                        print('安全失败快照',page.locator('audio').evaluate("a=>({time:a.currentTime,ready:a.readyState,error:a.error?.code,phase:document.body.dataset.phase,status:document.querySelector('#status').textContent})"),
                            '打开次数',len(upstream.opens),'上游请求数',upstream.requests)
                        raise
                def open_song(rid='1'):
                    page.locator('#rid').fill(rid);page.locator('#open').click();playing()
                def snapshot():return page.locator('audio').evaluate('(a)=>({time:a.currentTime,volume:a.volume,muted:a.muted,rate:a.playbackRate,paused:a.paused})')
                open_song();page.locator('audio').evaluate('(a)=>{a.volume=.4;a.playbackRate=1.25;a.muted=true}')
                before=snapshot();old=sessions[-1]
                page.wait_for_timeout(5300);before=snapshot();page.evaluate('window.__renew()');playing()
                after=snapshot();assert sessions[-1]!=old and abs(after['time']-before['time'])<6
                assert after['volume']==.4 and after['rate']==1.25 and after['muted']
                summary['scenarios'].append({'case':'Lease真实到期后续租触发恢复','before':before,'after':after,'differentPlaybackId':sessions[-1]!=old})

                # 手动暂停恢复保留书签，重复重试不增加打开次数。
                page.locator('#pause').click();before=snapshot();start=len(upstream.opens)
                upstream.hold_next=True;page.locator('#retry').click()
                page.wait_for_function("document.body.dataset.phase==='opening'")
                page.locator('#retry').click();page.locator('#pause').click();upstream.held.clear()
                page.wait_for_function("document.body.dataset.phase==='ready'")
                after=snapshot();assert after['paused'] and abs(after['time']-before['time'])<.5
                assert len(upstream.opens)==start+1
                summary['scenarios'].append({'case':'暂停恢复及重复重试合并','before':before,'after':after,'opens':len(upstream.opens)-start})

                # 上游已失效：HEAD观察真实410后一次恢复。
                open_song();version=len(upstream.opens);upstream.invalid.add(version)
                old=sessions[-1];page.locator('audio').evaluate('(a)=>a.currentTime=43')
                page.wait_for_function("document.querySelector('#status').textContent==='恢复成功' || document.body.dataset.phase==='error'",timeout=20000)
                # 浏览器可能已经缓存目标；若未请求旧源，显式续租到期恢复单独有证据。
                summary['scenarios'].append({'case':'失效上游后的远端seek','automaticObserved':sessions[-1]!=old,'after':snapshot(),'events':page.evaluate('window.__events.slice(-8)')})

                # 正在传输的真实中断：读取器先产出字节，再抛ReadError。
                open_song();old=sessions[-1];start=len(upstream.opens);upstream.broken.add(start)
                try:
                    page.wait_for_function("document.querySelector('#status').textContent==='恢复成功'",timeout=20000)
                    auto=True
                except BrowserTimeout:auto=False
                summary['scenarios'].append({'case':'响应头后中途断流','automaticObserved':auto,'opens':len(upstream.opens)-start,
                    'events':page.evaluate('window.__events.slice(-10)'),'upstreamInterruptions':upstream.interruptions,
                    'brokenStreamClosed':start in upstream.closed_versions})
                assert start in upstream.closed_versions
                if not auto:page.locator('#retry').click();playing()

                # 自动恢复预算已消费，再次失效只显示手动入口。
                upstream.invalid.add(len(upstream.opens));count=len(upstream.opens)
                page.wait_for_timeout(5300);page.evaluate('window.__renew()');page.wait_for_timeout(250)
                assert len(upstream.opens)==count
                upstream.fail_open=True;page.locator('#retry').click()
                page.wait_for_function("document.body.dataset.phase==='error'")
                upstream.fail_open=False;page.locator('#retry').click();playing()
                summary['scenarios'].append({'case':'自动预算限制及失败后手动重试','stoppedAutomatic':True,'manualSucceeded':True})

                for action in ['stop','switch','pause']:
                    upstream.hold_next=True;start=len(upstream.opens);page.locator('#retry').click()
                    for _ in range(100):
                        if len(upstream.opens)>start:break
                        page.wait_for_timeout(20)
                    assert upstream.held
                    if action=='stop':page.locator('#close').click()
                    elif action=='switch':
                        page.locator('#rid').fill('2');page.locator('#open').click()
                        playing()
                    else:page.locator('#pause').click()
                    upstream.held.clear();page.wait_for_timeout(700)
                    if action=='stop':assert not page.locator('audio').get_attribute('src')
                    if action=='switch':
                        current_key=page.locator('audio').get_attribute('src').split('/')[-2]
                        assert app.state.playback_leases.entries[current_key].state=='active'
                        assert app.state.media_store.get(app.state.playback_leases.entries[current_key].media_id).media.identity.platformId=='2'
                    if action=='pause':assert snapshot()['paused']
                    summary['scenarios'].append({'case':'恢复中'+action,'passed':True})
                    if action=='stop':open_song()
                page.locator('#close').click()
                for _ in range(100):
                    with app.state.media_store.lock:
                        app.state.playback_leases.sweep();records=list(app.state.media_store.records.values())
                        active=sum(len(r.streams) for r in records)
                        leases=sum(l.state=='active' for l in app.state.playback_leases.entries.values())
                    if not records and not active and not leases:break
                    page.wait_for_timeout(100)
                summary.update({'remainingRecords':len(records),'activeStreams':active,'activeLeases':leases,
                    'singleAudio':page.locator('audio').count()==1 and page.evaluate("window.__originalAudio===document.querySelector('audio')"),'browserVersion':browser.version})
                assert not records and active==0 and leases==0 and summary['singleAudio']
                print(json.dumps(summary,ensure_ascii=True,indent=2))
            finally:browser.close()
    except Exception:
        print('已完成场景',json.dumps(summary,ensure_ascii=True,indent=2))
        raise
    finally:
        server.should_exit=True;thread.join(timeout=15);assert not thread.is_alive()


if __name__=='__main__':main()
